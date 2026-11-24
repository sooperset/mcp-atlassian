"""Regression tests for the SSRF DNS-pinning transport adapter (DNS rebinding).

These cover GHSA-49xv, GHSA-72fm, GHSA-489g: the validate-then-reconnect TOCTOU
where a rebinding host returns a public IP to ``validate_url_for_ssrf`` and a
private/metadata IP to the actual connection. The adapter resolves once, validates
that resolution, and connects to the same address — so there is no second
resolution to rebind.
"""

import socket
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from requests.adapters import HTTPAdapter

from mcp_atlassian.utils.http import CallBudget, UpstreamCallAborted
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
        {"CONFLUENCE_URL": "https://jira.internal:8080/wiki"},
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


# A request path is built from tool arguments. ``requests`` resolves "." and
# ".." segments before sending, so a value such as "../../OTHER-1/comment/5"
# would address a different resource than the one the caller was checked for.

_BASE = "https://example.atlassian.net/rest/api/2/issue/ALLOWED-1/comment/"


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("../../OTHER-1/comment/5", id="dot-dot"),
        pytest.param("./5", id="single-dot"),
        pytest.param("%2e%2e/%2E%2E/OTHER-1/comment/5", id="percent-encoded"),
        pytest.param("..%2F..%2FOTHER-1%2Fcomment%2F5", id="encoded-slash"),
        pytest.param("..;x=1/..;/OTHER-1/comment/5", id="path-parameter"),
        pytest.param("..\\..\\OTHER-1\\comment\\5", id="backslash"),
        pytest.param("5/..", id="trailing"),
        pytest.param("%252e%252e%252fOTHER-1", id="double-encoded"),
        pytest.param("%25252e%25252e/OTHER-1", id="triple-encoded"),
        pytest.param("..%252F..%252FOTHER-1", id="double-encoded-slash"),
        pytest.param("%2525252e%2525252e/OTHER-1", id="quadruple-encoded"),
        pytest.param(("%" + "25" * 40 + "2e") * 2 + "/OTHER-1", id="deeply-encoded"),
    ],
)
def test_request_with_dot_segment_is_refused_before_sending(path):
    session = requests.Session()
    mount_ssrf_pinning(session)

    with patch.object(SsrfPinningAdapter, "send") as send:
        with pytest.raises(ValueError, match="path"):
            session.get(_BASE + path)

    send.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(_BASE + "5", id="plain"),
        pytest.param(_BASE + "5?expand=a..b&path=../x", id="dots-in-query"),
        pytest.param(
            "https://example.atlassian.net/download/attachments/1/notes..v2.txt",
            id="dots-inside-a-name",
        ),
        pytest.param(
            "https://example.atlassian.net/wiki/spaces/A/pages/1/...", id="three-dots"
        ),
        pytest.param(_BASE + "5?path=%252e%252e%252f", id="encoded-dots-in-query"),
        pytest.param(
            "https://example.atlassian.net/download/attachments/1/100%25.txt",
            id="encoded-percent-in-a-name",
        ),
        pytest.param(
            "https://example.atlassian.net/download/attachments/1/100%.txt",
            id="bare-percent-in-a-name",
        ),
        pytest.param(_BASE + "%25", id="encoded-percent"),
        pytest.param(_BASE + "%2525", id="double-encoded-percent"),
        pytest.param(
            "https://example.atlassian.net/download/attachments/1/notes%252etxt",
            id="double-encoded-dot-inside-a-name",
        ),
    ],
)
def test_request_without_dot_segment_is_sent(url):
    session = requests.Session()
    mount_ssrf_pinning(session)
    response = requests.Response()
    response.status_code = 200

    with patch.object(SsrfPinningAdapter, "send", return_value=response) as send:
        assert session.get(url).status_code == 200

    send.assert_called_once()


def test_mounting_twice_checks_the_path_once():
    session = requests.Session()
    mount_ssrf_pinning(session)
    first = session.prepare_request
    mount_ssrf_pinning(session)

    assert session.prepare_request is first


@pytest.mark.security_regression
@pytest.mark.parametrize(
    "env",
    [
        {"JIRA_URL": "http://jira.internal:8080"},
        {"CONFLUENCE_URL": "https://jira.internal/wiki"},
    ],
)
def test_other_port_of_configured_host_is_not_trusted(env, monkeypatch):
    """Only the configured host AND port waive the private-address check."""
    for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    with patch(
        "mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo",
        side_effect=_gai_returning("10.0.0.5"),
    ):
        with pytest.raises(OSError, match="non-global"):
            _pinned_create_connection(("jira.internal", 9000))


def _transport_kwargs(session: Any, url: str, **send_kwargs: Any) -> dict[str, Any]:
    """Send ``url`` through the session's adapter; return what reaches HTTPAdapter."""
    import requests
    from requests.adapters import HTTPAdapter

    request = requests.Request("GET", url).prepare()
    seen: dict[str, Any] = {}

    def fake_send(self: Any, req: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        seen["adapter"] = self
        return MagicMock(status_code=200)

    with patch.object(HTTPAdapter, "send", fake_send):
        session.get_adapter(url).send(request, **send_kwargs)
    return seen


@pytest.mark.security_regression
class TestSslVerifyOffStaysOnOperatorOrigin:
    """JIRA_SSL_VERIFY=false applies only to the session's own exact origin."""

    @staticmethod
    def _session(monkeypatch: pytest.MonkeyPatch, **config: Any) -> Any:
        from mcp_atlassian.jira import JiraConfig, JiraFetcher

        for name in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "NO_PROXY", "no_proxy"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("JIRA_URL", "https://jira.operator.example")
        monkeypatch.setenv("CONFLUENCE_URL", "https://wiki.operator.example")
        monkeypatch.setenv("MCP_ALLOWED_URL_DOMAINS", "cdn.example")
        fetcher = JiraFetcher(
            config=JiraConfig(
                url="https://jira.operator.example",
                auth_type="pat",
                personal_token="dummy",
                ssl_verify=False,
                **config,
            )
        )
        return fetcher.jira._session

    @pytest.mark.parametrize(
        "url",
        [
            "https://cdn.other.example/file",
            "https://jira.operator.example.attacker.example/file",
            "https://jira.operator.example:8443/file",
            # Other operator-trusted origins are still verified.
            "https://wiki.operator.example/rest/api/content",
            "https://files.cdn.example/file",
        ],
    )
    def test_other_origin_is_verified(
        self, monkeypatch: pytest.MonkeyPatch, url: str
    ) -> None:
        from mcp_atlassian.utils.ssl import SSLIgnoreAdapter

        seen = _transport_kwargs(self._session(monkeypatch), url, verify=False)

        assert seen["verify"] is True
        assert not isinstance(seen["adapter"], SSLIgnoreAdapter)

    @pytest.mark.parametrize(
        "url",
        [
            "https://jira.operator.example/rest/api/2/myself",
            "https://jira.operator.example:443/rest/api/2/myself",
            "https://JIRA.operator.example/rest/api/2/myself",
        ],
    )
    def test_own_origin_keeps_verification_off(
        self, monkeypatch: pytest.MonkeyPatch, url: str
    ) -> None:
        seen = _transport_kwargs(self._session(monkeypatch), url, verify=False)

        assert seen["verify"] is False

    def test_default_port_spelling_gets_the_same_proxy_policy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = self._session(monkeypatch, no_proxy="jira.operator.example")
        proxies = {"https": "http://proxy.example:3128"}

        plain = _transport_kwargs(
            session, "https://jira.operator.example/x", verify=False, proxies=proxies
        )
        explicit = _transport_kwargs(
            session,
            "https://jira.operator.example:443/x",
            verify=False,
            proxies=proxies,
        )

        assert plain["adapter"] is explicit["adapter"]
        # NO_PROXY bypass: no proxy is passed on for either spelling.
        assert not plain["proxies"]
        assert plain["proxies"] == explicit["proxies"]


@pytest.mark.security_regression
class TestAttachmentOriginRule:
    """Jira and Confluence attachment fetches share one origin rule."""

    @staticmethod
    def _fetchers() -> list[Any]:
        from mcp_atlassian.confluence import ConfluenceConfig, ConfluenceFetcher
        from mcp_atlassian.jira import JiraConfig, JiraFetcher

        jira = JiraFetcher(
            config=JiraConfig(
                url="https://jira.example.test", auth_type="pat", personal_token="d"
            )
        )
        confluence = ConfluenceFetcher(
            config=ConfluenceConfig(
                url="https://wiki.example.test", auth_type="pat", personal_token="d"
            )
        )
        return [jira, confluence]

    def test_allowlisted_host_is_accepted_by_both(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MCP_ALLOWED_URL_DOMAINS", "files.example.test")
        for fetcher in self._fetchers():
            fetcher._ensure_same_origin("https://cdn.files.example.test/a.bin")

    def test_refusal_message_has_only_the_origin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MCP_ALLOWED_URL_DOMAINS", raising=False)
        url = "https://user:pw@evil.example:8443/a.bin?sig=s3cr3t#frag"
        for fetcher in self._fetchers():
            with pytest.raises(ValueError) as excinfo:
                fetcher._ensure_same_origin(url)
            message = str(excinfo.value)
            assert "https://evil.example:8443" in message
            for secret in ("user", "pw", "sig", "s3cr3t", "a.bin", "frag"):
                assert secret not in message


_PUBLIC_IPS = ("93.184.216.34", "93.184.216.35", "93.184.216.36")


def _gai_returning_many(*ips: str):
    def gai(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]

    return gai


class _FailingConnectSock:
    """Socket whose connect fails; records each attempt and its timeout."""

    def __init__(self, attempts: list[dict[str, Any]], on_connect=None):
        self._attempts = attempts
        self._on_connect = on_connect
        self._timeout: Any = None

    def setsockopt(self, *a):
        pass

    def settimeout(self, value):
        self._timeout = value

    def bind(self, *a):
        pass

    def connect(self, sa):
        self._attempts.append({"addr": sa[0], "timeout": self._timeout})
        if self._on_connect is not None:
            self._on_connect()
        raise OSError("connection refused")

    def close(self):
        pass


def _connect_under(budget, attempts, timeout=10.0, on_connect=None):
    with (
        patch(
            "mcp_atlassian.utils.ssrf_adapter.socket.getaddrinfo",
            side_effect=_gai_returning_many(*_PUBLIC_IPS),
        ),
        patch(
            "mcp_atlassian.utils.ssrf_adapter.socket.socket",
            side_effect=lambda *a: _FailingConnectSock(attempts, on_connect),
        ),
    ):
        return budget.run(
            lambda: _pinned_create_connection(("multi.example.com", 443), timeout)
        )


class TestMultiAddressConnectStopsWithTheCall:
    """Connecting to a name with several addresses stops when its call stops."""

    def test_remaining_addresses_skipped_after_abort(self, monkeypatch):
        for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
            monkeypatch.delenv(k, raising=False)
        budget = CallBudget()
        attempts: list[dict[str, Any]] = []

        with pytest.raises(UpstreamCallAborted):
            _connect_under(budget, attempts, on_connect=budget.abort)

        assert [a["addr"] for a in attempts] == [_PUBLIC_IPS[0]]

    def test_no_attempt_once_the_deadline_passed(self, monkeypatch):
        for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
            monkeypatch.delenv(k, raising=False)
        budget = CallBudget(deadline=time.monotonic() - 1)
        attempts: list[dict[str, Any]] = []

        with pytest.raises(TimeoutError):
            _connect_under(budget, attempts)

        assert attempts == []

    def test_each_attempt_waits_at_most_until_the_deadline(self, monkeypatch):
        for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
            monkeypatch.delenv(k, raising=False)
        budget = CallBudget(deadline=time.monotonic() + 2.0)
        attempts: list[dict[str, Any]] = []

        with pytest.raises(OSError):
            _connect_under(budget, attempts, timeout=10.0)

        assert len(attempts) == len(_PUBLIC_IPS)
        assert all(0 < a["timeout"] <= 2.0 for a in attempts)

    def test_connect_timeout_kept_when_the_deadline_is_further(self, monkeypatch):
        for k in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
            monkeypatch.delenv(k, raising=False)
        budget = CallBudget(deadline=time.monotonic() + 60.0)
        attempts: list[dict[str, Any]] = []

        with pytest.raises(OSError):
            _connect_under(budget, attempts, timeout=3.0)

        assert [a["timeout"] for a in attempts] == [3.0] * len(_PUBLIC_IPS)
