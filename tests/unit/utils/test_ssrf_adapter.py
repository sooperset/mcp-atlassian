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
@pytest.mark.parametrize(
    "ip",
    [
        "169.254.169.254",
        "127.0.0.1",
        "10.0.0.5",
        "::1",
        "64:ff9b::a9fe:a9fe",
        "2002:a9fe:a9fe::",
        "::a9fe:a9fe",
    ],
)
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
@pytest.mark.parametrize("ip", ["127.0.0.1", "169.254.169.254", "fd00:ec2::254"])
def test_allowlisted_domain_does_not_waive_loopback_or_metadata(ip, monkeypatch):
    """A host under an allowlisted domain may be private, never loopback or a
    metadata address: request-supplied URLs can match the domain pattern."""
    for k in ("JIRA_URL", "CONFLUENCE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MCP_ALLOWED_URL_DOMAINS", "corp.example.com")

    with patch(
        "mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo",
        side_effect=_gai_returning(ip),
    ):
        with pytest.raises(OSError, match="non-global"):
            _pinned_create_connection(("rebind.corp.example.com", 443))


@pytest.mark.security_regression
def test_per_request_service_url_does_not_keep_operator_proxy(monkeypatch):
    """A service URL taken from a request header must not be treated as a
    proxy-trusted host: the proxy would resolve it outside the pinned
    connector and reopen DNS rebinding."""
    from mcp_atlassian.jira import JiraConfig
    from mcp_atlassian.jira.client import JiraClient

    for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
        monkeypatch.delenv(k, raising=False)
    config = JiraConfig(
        url="https://rebind.attacker.test",
        auth_type="pat",
        personal_token="caller-pat",
        https_proxy="http://proxy.example.test:8080",
    )
    client = JiraClient(config=config)
    url = "https://rebind.attacker.test/rest/api/2/myself"
    adapter = client.jira._session.get_adapter(url)
    request = requests.Request("GET", url).prepare()
    proxies = {"https": "http://proxy.example.test:8080"}

    with patch.object(HTTPAdapter, "send", return_value=requests.Response()) as send:
        adapter.send(request, proxies=proxies)

    assert send.call_args.kwargs["proxies"] == {}


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


def _credentialed_session(**config_kwargs):
    from mcp_atlassian.jira import JiraConfig
    from mcp_atlassian.jira.client import JiraClient

    config = JiraConfig(
        url="https://jira.example.test",
        auth_type="pat",
        personal_token="SERVICE-PAT",
        custom_headers={"X-Gateway-Secret": "GATEWAY-SECRET"},
        **config_kwargs,
    )
    return JiraClient(config=config).jira._session


def _sent_requests(session, responses, url):
    sent = []

    def fake_send(self, request, **kwargs):
        sent.append((request.url, dict(request.headers), kwargs.get("cert")))
        return responses.pop(0)

    public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    with (
        patch.object(HTTPAdapter, "send", fake_send),
        patch("mcp_atlassian.utils.urls.socket.getaddrinfo", return_value=public),
    ):
        session.get(url, allow_redirects=True)
    return sent


def _response(status, url, location=None):
    import io

    response = requests.Response()
    response.status_code = status
    response.url = url
    response.raw = io.BytesIO(b"")
    response.request = requests.Request("GET", url).prepare()
    if location:
        response.headers["Location"] = location
    return response


@pytest.mark.security_regression
def test_off_host_request_carries_no_service_credentials(monkeypatch):
    """An absolute off-host URL (e.g. attachment metadata) gets no credentials."""
    for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
        monkeypatch.delenv(k, raising=False)
    session = _credentialed_session()
    url = "https://download.attacker.test/file"

    [(sent_url, headers, cert)] = _sent_requests(session, [_response(200, url)], url)

    assert sent_url == url
    assert "Authorization" not in headers
    assert "X-Gateway-Secret" not in headers
    assert cert is None


@pytest.mark.security_regression
def test_cross_host_redirect_drops_custom_secret_headers(monkeypatch):
    """requests drops Authorization on a cross-host redirect, but not custom
    headers; the adapter drops both."""
    for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
        monkeypatch.delenv(k, raising=False)
    session = _credentialed_session()
    first = "https://jira.example.test/rest/api/2/attachment/content/1"
    cdn = "https://cdn.attacker.test/blob"

    sent = _sent_requests(
        session, [_response(302, first, cdn), _response(200, cdn)], first
    )

    assert sent[0][1]["Authorization"] == "Bearer SERVICE-PAT"
    assert sent[0][1]["X-Gateway-Secret"] == "GATEWAY-SECRET"
    assert sent[1][0] == cdn
    assert "Authorization" not in sent[1][1]
    assert "X-Gateway-Secret" not in sent[1][1]


def test_allowlisted_alternate_host_keeps_credentials(monkeypatch):
    """An operator can allow a known alternate base URL via the allowlist."""
    for k in ("JIRA_URL", "CONFLUENCE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MCP_ALLOWED_URL_DOMAINS", "jira-alt.example.test")
    session = _credentialed_session()
    url = "https://jira-alt.example.test/secure/attachment/1/file"

    [(_, headers, _cert)] = _sent_requests(session, [_response(200, url)], url)

    assert headers["Authorization"] == "Bearer SERVICE-PAT"
    assert headers["X-Gateway-Secret"] == "GATEWAY-SECRET"


@pytest.mark.security_regression
@pytest.mark.parametrize(
    "url",
    [
        "https://evil.jira.example.test/file",
        "http://jira.example.test/file",
        "https://jira.example.test:8443/file",
    ],
    ids=["subdomain", "scheme", "port"],
)
def test_credentials_bound_to_exact_service_origin(url, monkeypatch):
    """Credentials for https://jira.example.test do not travel to a subdomain,
    another scheme or another port of that host."""
    for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
        monkeypatch.delenv(k, raising=False)
    session = _credentialed_session()

    [(_, headers, cert)] = _sent_requests(session, [_response(200, url)], url)

    assert "Authorization" not in headers
    assert "X-Gateway-Secret" not in headers
    assert cert is None


def test_credentials_kept_for_same_origin_with_explicit_default_port(monkeypatch):
    for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
        monkeypatch.delenv(k, raising=False)
    session = _credentialed_session()
    url = "https://JIRA.example.test:443/rest/api/2/myself"

    [(_, headers, _cert)] = _sent_requests(session, [_response(200, url)], url)

    assert headers["Authorization"] == "Bearer SERVICE-PAT"


def test_allowlisted_domain_still_covers_subdomains(monkeypatch):
    """MCP_ALLOWED_URL_DOMAINS keeps its documented domain-and-subdomain match."""
    for k in ("JIRA_URL", "CONFLUENCE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MCP_ALLOWED_URL_DOMAINS", "example.test")
    session = _credentialed_session()
    url = "https://files.example.test/blob"

    [(_, headers, _cert)] = _sent_requests(session, [_response(200, url)], url)

    assert headers["Authorization"] == "Bearer SERVICE-PAT"


@pytest.mark.security_regression
@pytest.mark.parametrize(
    "target",
    [
        "https://evil.jira.internal/rest/api/2",
        "http://jira.internal/rest/api/2",
        "https://jira.internal:8443/rest/api/2",
    ],
    ids=["subdomain", "scheme", "port"],
)
def test_proxy_trust_is_exact_service_origin(target, monkeypatch):
    monkeypatch.delenv("MCP_ALLOWED_URL_DOMAINS", raising=False)
    monkeypatch.delenv("CONFLUENCE_URL", raising=False)
    monkeypatch.setenv("JIRA_URL", "https://jira.internal")
    adapter = SsrfPinningAdapter(trusted_urls=["https://gw.internal"])
    request = requests.Request("GET", target).prepare()
    proxies = {"https": "http://proxy.example.test:8080"}

    with patch.object(HTTPAdapter, "send", return_value=requests.Response()) as send:
        adapter.send(request, proxies=proxies)

    assert send.call_args.kwargs["proxies"] == {}
