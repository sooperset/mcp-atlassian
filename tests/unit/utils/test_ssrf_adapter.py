"""Regression tests for the SSRF DNS-pinning transport adapter (DNS rebinding).

These cover GHSA-49xv, GHSA-72fm, GHSA-489g: the validate-then-reconnect TOCTOU
where a rebinding host returns a public IP to ``validate_url_for_ssrf`` and a
private/metadata IP to the actual connection. The adapter resolves once, validates
that resolution, and connects to the same address — so there is no second
resolution to rebind.
"""

import socket
from unittest.mock import patch

import pytest
import requests
from requests.adapters import HTTPAdapter

from mcp_atlassian.utils.ssrf_adapter import (
    SsrfPinningAdapter,
    _pinned_create_connection,
    mount_ssrf_pinning,
)


def _gai_returning(ip: str):
    def gai(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 443))]

    return gai


@pytest.mark.security_regression
def test_rebind_internal_address_refused_with_single_resolution():
    """A host resolving to a non-global address is refused, after exactly one
    resolution — the resolved address is the one that would be connected to."""
    calls = {"n": 0}

    def gai(host, port, *args, **kwargs):
        calls["n"] += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))]

    with patch("mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo", side_effect=gai):
        with pytest.raises(OSError, match="non-global"):
            _pinned_create_connection(("rebind.attacker.test", 443))

    assert calls["n"] == 1


@pytest.mark.security_regression
@pytest.mark.parametrize("ip", ["169.254.169.254", "127.0.0.1", "10.0.0.5", "::1"])
def test_pinning_adapter_blocks_internal_through_real_stack(ip):
    """End-to-end through the mounted adapter and the real requests/urllib3 stack:
    a host resolving to an internal address is refused — proving the adapter is
    actually wired into the connection path (not a mock-only green)."""
    session = requests.Session()
    session.mount("https://", SsrfPinningAdapter())
    session.mount("http://", SsrfPinningAdapter())

    with patch(
        "mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo",
        side_effect=_gai_returning(ip),
    ):
        with pytest.raises(requests.exceptions.ConnectionError, match="SSRF blocked"):
            session.get("https://rebind.attacker.test", timeout=5)


@pytest.mark.security_regression
def test_untrusted_target_bypasses_proxy_to_keep_dns_pinning():
    """A proxy must not re-resolve a caller-controlled target outside the guard."""
    adapter = SsrfPinningAdapter()
    request = requests.Request("GET", "https://rebind.attacker.test").prepare()
    proxies = {"https": "http://proxy.example.test:8080"}
    response = requests.Response()

    with patch.object(HTTPAdapter, "send", return_value=response) as send:
        assert adapter.send(request, proxies=proxies) is response

    assert send.call_args.kwargs["proxies"] == {}


def test_operator_configured_target_keeps_proxy(monkeypatch):
    """Operator-controlled service hosts may continue using deployment proxies."""
    monkeypatch.setenv("JIRA_URL", "https://jira.internal")
    adapter = SsrfPinningAdapter()
    request = requests.Request("GET", "https://jira.internal/rest/api/2").prepare()
    proxies = {"https": "http://proxy.example.test:8080"}
    response = requests.Response()

    with patch.object(HTTPAdapter, "send", return_value=response) as send:
        assert adapter.send(request, proxies=proxies) is response

    assert send.call_args.kwargs["proxies"] == proxies


@pytest.mark.security_regression
def test_cloud_oauth_gateway_keeps_proxy_through_no_proxy_adapter(monkeypatch):
    """The fixed Cloud OAuth transport remains proxyable after NO_PROXY handling."""
    from mcp_atlassian.utils.ssl import NoProxyAdapter

    for key in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
        monkeypatch.delenv(key, raising=False)
    url = "https://api.atlassian.com/ex/jira/cloud-id/rest/api/3/myself"
    session = requests.Session()
    session.mount("https://api.atlassian.com", NoProxyAdapter(no_proxy="localhost"))
    mount_ssrf_pinning(session, url)
    adapter = session.get_adapter(url)
    request = requests.Request("GET", url).prepare()
    proxies = {"https": "http://proxy.example.test:8080"}
    response = requests.Response()

    with patch.object(HTTPAdapter, "send", return_value=response) as send:
        assert adapter.send(request, proxies=proxies) is response

    assert send.call_args.kwargs["proxies"] == proxies


class _FakeConnectSock:
    def __init__(self, connected):
        self._connected = connected

    def setsockopt(self, *a):
        pass

    def settimeout(self, *a):
        pass

    def bind(self, *a):
        pass

    def connect(self, sa):
        self._connected["addr"] = sa

    def close(self):
        pass


@pytest.mark.parametrize(
    "env",
    [
        {"JIRA_URL": "http://jira.internal:8080"},
        {"CONFLUENCE_URL": "https://jira.internal/wiki"},
        {"MCP_ALLOWED_URL_DOMAINS": "jira.internal"},
    ],
)
def test_operator_configured_host_may_resolve_private(env, monkeypatch):
    """The operator-configured base host (or an allowlisted domain) may live on a
    private network — the non-global rejection is waived, but the connection is
    still pinned to the single resolved address."""
    for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    connected = {"addr": None}

    with (
        patch(
            "mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo",
            side_effect=_gai_returning("10.0.0.5"),
        ),
        patch(
            "mcp_atlassian.utils.ssrf_adapter.socket.socket",
            return_value=_FakeConnectSock(connected),
        ),
    ):
        _pinned_create_connection(("jira.internal", 8080))

    assert connected["addr"][0] == "10.0.0.5"


@pytest.mark.security_regression
def test_untrusted_host_still_refused_when_other_hosts_are_trusted(monkeypatch):
    """Trusting the operator's own host must not waive the guard for a
    caller-supplied host (the rebinding-attack case)."""
    monkeypatch.setenv("JIRA_URL", "http://jira.internal:8080")

    with patch(
        "mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo",
        side_effect=_gai_returning("169.254.169.254"),
    ):
        with pytest.raises(OSError, match="non-global"):
            _pinned_create_connection(("rebind.attacker.test", 443))


@pytest.mark.security_regression
def test_ssl_ignore_adapter_keeps_the_pinning_guard(monkeypatch):
    """SSLIgnoreAdapter mounts at a more specific prefix than the session-wide
    pinning adapter (requests picks the longest prefix), so it must carry the
    pinned connection classes itself — otherwise ssl_verify=false silently
    disables the SSRF rebinding guard."""
    from mcp_atlassian.utils.ssl import SSLIgnoreAdapter

    monkeypatch.delenv("JIRA_URL", raising=False)
    session = requests.Session()
    session.mount("http://", SsrfPinningAdapter())
    session.mount("http://rebind.attacker.test", SSLIgnoreAdapter())

    with patch(
        "mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo",
        side_effect=_gai_returning("169.254.169.254"),
    ):
        with pytest.raises(requests.exceptions.ConnectionError, match="SSRF blocked"):
            session.get("http://rebind.attacker.test", timeout=5)


def test_global_address_connects_to_the_validated_ip():
    """A global address passes the gate and the connection targets that same IP
    (the pin) — not a re-resolved one."""
    connected = {"addr": None}

    class _FakeSock:
        def setsockopt(self, *a):
            pass

        def settimeout(self, *a):
            pass

        def bind(self, *a):
            pass

        def connect(self, sa):
            connected["addr"] = sa

        def close(self):
            pass

    with (
        patch(
            "mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo",
            side_effect=_gai_returning("93.184.216.34"),
        ),
        patch(
            "mcp_atlassian.utils.ssrf_adapter.socket.socket",
            return_value=_FakeSock(),
        ),
    ):
        _pinned_create_connection(("example.com", 443))

    assert connected["addr"][0] == "93.184.216.34"
