"""Tests for the URL utilities module."""

import io
import os
import socket
from unittest.mock import patch

import pytest
import requests

from mcp_atlassian.utils.urls import (
    is_atlassian_cloud_url,
    make_ssrf_redirect_hook,
    resolve_relative_url,
    validate_url_for_ssrf,
)


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("/login", "https://jira.example.com/login"),
        ("//cdn.example.com/file", "https://cdn.example.com/file"),
    ],
)
def test_redirect_hook_resolves_location_before_validation(
    location: str, expected: str
) -> None:
    """Relative and scheme-relative redirects are validated as absolute URLs."""
    response = requests.Response()
    response.status_code = 302
    response.url = "https://jira.example.com/start"
    response.headers["Location"] = location

    with patch("mcp_atlassian.utils.urls._validate_url", return_value=None) as validate:
        assert make_ssrf_redirect_hook()(response) is response

    validate.assert_called_once_with(expected, trusted_host=None)


def _run_hook(
    base_url: str | None,
    response_url: str,
    location: str,
    dns_ip: str = "10.0.0.5",
) -> str | None:
    """Run the redirect hook over one 302 and report why it blocked, if it did.

    Args:
        base_url: Value passed to ``make_ssrf_redirect_hook``.
        response_url: The URL the 302 itself came from.
        location: The raw ``Location`` header value, relative or absolute.
        dns_ip: The address every hostname resolves to during the call.

    Returns:
        None when the redirect is allowed, otherwise the blocking message.
    """
    response = requests.Response()
    response.status_code = 302
    response.url = response_url
    response.headers["Location"] = location
    # The hook calls response.close() before raising; requests dereferences
    # .raw there, so give it something closeable.
    response.raw = io.BytesIO(b"")

    with patch("mcp_atlassian.utils.urls.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", (dns_ip, 0))]
        try:
            make_ssrf_redirect_hook(base_url)(response)
        except ValueError as exc:
            return str(exc)
    return None


class TestRedirectHookBaseUrlBinding:
    """Redirect exemptions are limited to the base and its HTTPS counterpart."""

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch) -> None:
        """Keep the developer environment out of these tests."""
        for var in ("JIRA_URL", "CONFLUENCE_URL", "MCP_ALLOWED_URL_DOMAINS"):
            monkeypatch.delenv(var, raising=False)

    @pytest.mark.security_regression
    def test_metadata_host_blocked_from_a_trusted_session(self) -> None:
        """Trusting the session's own host does not trust cloud metadata."""
        error = _run_hook(
            "https://jira.internal",
            "https://jira.internal/start",
            "http://169.254.169.254/latest/meta-data/",
        )
        assert error is not None
        assert "non-global" in error.lower()

    @pytest.mark.security_regression
    def test_caller_supplied_base_cannot_reach_a_private_host(self) -> None:
        """A session based on a caller-supplied host may not bounce inward.

        The base URL can come from a request header, so the exemption must never
        extend past the caller's own origin.
        """
        error = _run_hook(
            "https://caller.example.com",
            "https://caller.example.com/start",
            "http://10.0.0.5/admin",
        )
        assert error is not None

    def test_off_base_hop_is_judged_strictly(self) -> None:
        """Each redirect hop is validated on its own against a fixed base."""
        error = _run_hook(
            "https://jira.internal",
            "https://jira.internal/start",
            "https://other.internal/x",
        )
        assert error is not None
        assert "non-global" in error.lower()

    def test_session_may_redirect_to_its_own_host(self) -> None:
        """An on-prem instance on a private network may redirect to itself.

        This is the reported bug: Jira answers a relative 302 to /login.jsp and the
        hook refused it because the host resolves to a private address.
        """
        assert (
            _run_hook(
                "https://jira.internal",
                "https://jira.internal/secure/attachment/1/x.txt",
                "/login.jsp?permissionViolation=true",
            )
            is None
        )

    @pytest.mark.security_regression
    @pytest.mark.parametrize(
        ("source", "target", "allowed"),
        [
            ("http://jira.internal:8080", "https://jira.internal", True),
            ("https://jira.internal", "/next", True),
            ("https://jira.internal", "http://jira.internal:8080", False),
            ("http://jira.internal:8080", "https://jira.internal:8443", False),
            ("http://jira.internal:9090", "https://jira.internal", False),
            ("https://other.internal", "https://jira.internal", False),
            ("http://jira.internal:8080", "https://evil.jira.internal", False),
        ],
    )
    def test_https_upgrade_boundaries(
        self, source: str, target: str, allowed: bool
    ) -> None:
        """Allow the HTTPS counterpart without trusting downgrades or other origins."""
        error = _run_hook("http://jira.internal:8080", source, target)
        assert (error is None) is allowed

    def test_no_base_url_trusts_nothing(self) -> None:
        """Constructed without a base URL, the hook behaves exactly as before."""
        error = _run_hook(None, "https://jira.internal/start", "/login.jsp")
        assert error is not None
        assert "non-global" in error.lower()

    @pytest.mark.security_regression
    def test_subdomain_of_the_base_is_not_trusted(self) -> None:
        """Matching is exact, so a subdomain of the base host stays untrusted."""
        error = _run_hook(
            "https://jira.internal",
            "https://jira.internal/start",
            "https://evil.jira.internal/x",
        )
        assert error is not None

    @pytest.mark.security_regression
    def test_userinfo_cannot_spoof_the_trusted_host(self) -> None:
        """The comparison uses the parsed hostname, not the raw authority."""
        error = _run_hook(
            "https://jira.internal",
            "https://jira.internal/start",
            "https://jira.internal@caller.example.com/x",
        )
        assert error is not None

    def test_localhost_base_may_redirect_to_itself(self) -> None:
        """A localhost deployment's own redirects are allowed.

        Pins the blocked-hostname branch of the waiver; without it the documented
        ``JIRA_URL=http://localhost:8080`` setup stays broken.
        """
        assert (
            _run_hook(
                "http://localhost:8080",
                "http://localhost:8080/start",
                "/login.jsp",
            )
            is None
        )

    def test_ip_literal_base_may_redirect_to_itself(self) -> None:
        """A base URL that is a bare private IP may redirect to itself.

        Pins the IP-literal branch of the waiver.
        """
        assert (
            _run_hook(
                "http://10.0.0.7:8080",
                "http://10.0.0.7:8080/start",
                "/login.jsp",
            )
            is None
        )

    @pytest.mark.security_regression
    def test_localhost_blocked_when_it_is_not_the_base(self) -> None:
        """The blocked-hostname waiver applies only to the base host."""
        error = _run_hook(
            "https://jira.internal",
            "https://jira.internal/start",
            "http://localhost:8080/x",
        )
        assert error is not None
        assert "localhost" in error

    @pytest.mark.security_regression
    def test_ip_literal_blocked_when_it_is_not_the_base(self) -> None:
        """The IP-literal waiver applies only to the base host."""
        error = _run_hook(
            "https://jira.internal", "https://jira.internal/start", "http://10.0.0.5/x"
        )
        assert error is not None

    @pytest.mark.security_regression
    def test_other_port_on_the_base_host_is_not_trusted(self) -> None:
        """The waiver is per-origin, so another port on the same host stays strict.

        Without this the waiver would open every TCP service on the host the
        session happens to be configured for.
        """
        error = _run_hook(
            "https://jira.internal:8443",
            "https://jira.internal:8443/start",
            "https://jira.internal:2375/containers/create",
        )
        assert error is not None

    @pytest.mark.security_regression
    def test_loopback_base_does_not_trust_other_loopback_ports(self) -> None:
        """A localhost deployment does not become a gateway to every local port."""
        error = _run_hook(
            "http://localhost:8080",
            "http://localhost:8080/start",
            "http://localhost:6379/",
        )
        assert error is not None

    @pytest.mark.security_regression
    def test_scheme_downgrade_on_the_base_host_is_not_trusted(self) -> None:
        """An https session is not waived into plaintext on its own host.

        requests strips Authorization on a scheme change but keeps session
        headers and non-Secure cookies, so the downgrade must be blocked here.
        """
        error = _run_hook(
            "https://jira.internal",
            "https://jira.internal/start",
            "http://jira.internal/x",
        )
        assert error is not None

    @pytest.mark.security_regression
    def test_off_host_hop_cannot_pivot_back_into_the_base(self) -> None:
        """The waiver needs the redirect to come FROM the trusted origin too.

        Otherwise one hop through any attacker-controlled URL the session fetches
        re-enters the operator's host with the waiver applied.
        """
        error = _run_hook(
            "http://jira.internal:8080",
            "https://caller.example.com/next",
            "http://jira.internal:2375/containers/json",
        )
        assert error is not None

    def test_explicit_default_port_is_the_same_origin(self) -> None:
        """`https://host` and `https://host:443` name one origin."""
        assert (
            _run_hook(
                "https://jira.internal",
                "https://jira.internal/start",
                "https://jira.internal:443/login.jsp",
            )
            is None
        )

    def test_trailing_dot_is_the_same_origin(self) -> None:
        """A fully-qualified trailing dot names the same host."""
        assert (
            _run_hook(
                "https://jira.internal",
                "https://jira.internal/start",
                "https://jira.internal./login.jsp",
            )
            is None
        )

    def test_absolute_same_origin_redirect_is_allowed(self) -> None:
        """The allowed case also holds for an absolute Location, not just relative."""
        assert (
            _run_hook(
                "https://jira.internal",
                "https://jira.internal/start",
                "https://jira.internal/login.jsp",
            )
            is None
        )

    def test_unparsable_location_is_blocked_not_raised_raw(self) -> None:
        """A malformed Location blocks with the standard message, not a parse error."""
        error = _run_hook(
            "https://jira.internal", "https://jira.internal/start", "https://[::1"
        )
        assert error is not None
        assert "Redirect blocked (SSRF)" in error

    @pytest.mark.parametrize(
        ("base", "location"),
        [
            ("https://jira.internal", "/login.jsp"),
            ("http://jira.internal:8080", "https://jira.internal/login.jsp"),
        ],
    )
    def test_allowlist_still_restricts_the_base_host(
        self, monkeypatch, base: str, location: str
    ) -> None:
        """MCP_ALLOWED_URL_DOMAINS keeps its restrictive meaning.

        The waiver drops the non-global rejections only; an operator who narrowed
        the domain set still gets that narrowing, base host included.
        """
        monkeypatch.setenv("MCP_ALLOWED_URL_DOMAINS", "corp.com")
        error = _run_hook(base, f"{base}/start", location)
        assert error is not None
        assert "not in allowed domains" in error


class TestResolveRelativeUrl:
    """Tests for resolve_relative_url."""

    @pytest.mark.parametrize(
        ("url", "base_url", "expected"),
        [
            # Relative URL gets base prepended
            (
                "/download/attachments/123/file.pdf",
                "https://confluence.example.com",
                "https://confluence.example.com/download/attachments/123/file.pdf",
            ),
            # Absolute URL passes through unchanged
            (
                "https://other.example.com/file.pdf",
                "https://confluence.example.com",
                "https://other.example.com/file.pdf",
            ),
            # Base URL with trailing slash — no double slash
            (
                "/download/file.pdf",
                "https://confluence.example.com/",
                "https://confluence.example.com/download/file.pdf",
            ),
            # Base URL with multiple trailing slashes stripped
            (
                "/path/to/file",
                "https://confluence.example.com//",
                "https://confluence.example.com/path/to/file",
            ),
            # Non-slash relative URL (e.g. bare filename) passes through
            (
                "file.pdf",
                "https://confluence.example.com",
                "file.pdf",
            ),
        ],
        ids=[
            "relative-url-prepended",
            "absolute-url-unchanged",
            "trailing-slash-stripped",
            "multiple-trailing-slashes-stripped",
            "non-slash-relative-unchanged",
        ],
    )
    def test_resolve_relative_url(self, url: str, base_url: str, expected: str) -> None:
        """Parametrized test for resolve_relative_url."""
        assert resolve_relative_url(url, base_url) == expected


def test_is_atlassian_cloud_url_empty():
    """Test that is_atlassian_cloud_url returns False for empty URL."""
    assert is_atlassian_cloud_url("") is False
    assert is_atlassian_cloud_url(None) is False


def test_is_atlassian_cloud_url_cloud():
    """Test that is_atlassian_cloud_url returns True for Atlassian Cloud URLs."""
    # Test standard Atlassian Cloud URLs
    assert is_atlassian_cloud_url("https://example.atlassian.net") is True
    assert is_atlassian_cloud_url("https://company.atlassian.net/wiki") is True
    assert is_atlassian_cloud_url("https://subdomain.atlassian.net/jira") is True
    assert is_atlassian_cloud_url("http://other.atlassian.net") is True

    # Test Jira Cloud specific domains
    assert is_atlassian_cloud_url("https://company.jira.com") is True
    assert is_atlassian_cloud_url("https://team.jira-dev.com") is True


def test_is_atlassian_cloud_url_multi_cloud_oauth():
    """Test that is_atlassian_cloud_url returns True for Multi-Cloud OAuth URLs."""
    # Test api.atlassian.com URLs used by Multi-Cloud OAuth
    assert (
        is_atlassian_cloud_url("https://api.atlassian.com/ex/jira/abc123/rest/api/2/")
        is True
    )
    assert (
        is_atlassian_cloud_url("https://api.atlassian.com/ex/confluence/xyz789/")
        is True
    )
    assert is_atlassian_cloud_url("http://api.atlassian.com/ex/jira/test/") is True
    assert is_atlassian_cloud_url("https://api.atlassian.com") is True


def test_is_atlassian_cloud_url_us_gov():
    """Test that is_atlassian_cloud_url returns True for US Government Cloud URLs."""
    # Test US Government Moderate (FedRAMP) Cloud URLs
    assert is_atlassian_cloud_url("https://company.atlassian-us-gov-mod.net") is True
    assert (
        is_atlassian_cloud_url("https://company.atlassian-us-gov-mod.net/wiki") is True
    )
    assert (
        is_atlassian_cloud_url("https://subdomain.atlassian-us-gov-mod.net/jira")
        is True
    )
    assert is_atlassian_cloud_url("http://other.atlassian-us-gov-mod.net") is True

    # Test US Government (FedRAMP) Cloud URLs
    assert is_atlassian_cloud_url("https://company.atlassian-us-gov.net") is True
    assert is_atlassian_cloud_url("https://company.atlassian-us-gov.net/wiki") is True


def test_is_atlassian_cloud_url_server():
    """Test that is_atlassian_cloud_url returns False for Atlassian Server/Data Center URLs."""
    # Test with various server/data center domains
    assert is_atlassian_cloud_url("https://jira.example.com") is False
    assert is_atlassian_cloud_url("https://confluence.company.org") is False
    assert is_atlassian_cloud_url("https://jira.internal") is False


def test_is_atlassian_cloud_url_localhost():
    """Test that is_atlassian_cloud_url returns False for localhost URLs."""
    # Test with localhost
    assert is_atlassian_cloud_url("http://localhost") is False
    assert is_atlassian_cloud_url("http://localhost:8080") is False
    assert is_atlassian_cloud_url("https://localhost/jira") is False


def test_is_atlassian_cloud_url_ip_addresses():
    """Test that is_atlassian_cloud_url returns False for IP-based URLs."""
    # Test with IP addresses
    assert is_atlassian_cloud_url("http://127.0.0.1") is False
    assert is_atlassian_cloud_url("http://127.0.0.1:8080") is False
    assert is_atlassian_cloud_url("https://192.168.1.100") is False
    assert is_atlassian_cloud_url("https://10.0.0.1") is False
    assert is_atlassian_cloud_url("https://172.16.0.1") is False
    assert is_atlassian_cloud_url("https://172.31.255.254") is False


def test_is_atlassian_cloud_url_with_protocols():
    """Test that is_atlassian_cloud_url works with different protocols."""
    # Test with different protocols
    assert is_atlassian_cloud_url("https://example.atlassian.net") is True
    assert is_atlassian_cloud_url("http://example.atlassian.net") is True
    assert (
        is_atlassian_cloud_url("ftp://example.atlassian.net") is True
    )  # URL parsing still works


class TestValidateUrlForSsrf:
    """Tests for validate_url_for_ssrf."""

    def test_valid_cloud_url(self) -> None:
        """Atlassian Cloud URL passes validation."""
        with patch("mcp_atlassian.utils.urls.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("104.192.141.1", 0))]
            assert validate_url_for_ssrf("https://company.atlassian.net") is None

    def test_valid_server_url(self) -> None:
        """Server/DC URL passes validation."""
        with patch("mcp_atlassian.utils.urls.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("8.8.8.8", 0))]
            assert validate_url_for_ssrf("https://jira.example.com") is None

    def test_empty_url(self) -> None:
        """Empty URL is rejected."""
        result = validate_url_for_ssrf("")
        assert result is not None
        assert "Empty" in result

    def test_ftp_scheme(self) -> None:
        """FTP scheme is rejected."""
        result = validate_url_for_ssrf("ftp://evil.com")
        assert result is not None
        assert "scheme" in result.lower()

    def test_file_scheme(self) -> None:
        """file:// scheme is rejected."""
        result = validate_url_for_ssrf("file:///etc/passwd")
        assert result is not None
        assert "scheme" in result.lower()

    def test_localhost(self) -> None:
        """localhost is rejected."""
        result = validate_url_for_ssrf("http://localhost:8080")
        assert result is not None
        assert "localhost" in result.lower() or "Blocked" in result

    def test_loopback_ip(self) -> None:
        """127.0.0.1 is rejected."""
        result = validate_url_for_ssrf("http://127.0.0.1")
        assert result is not None

    def test_private_10(self) -> None:
        """10.x.x.x is rejected."""
        result = validate_url_for_ssrf("http://10.0.0.1")
        assert result is not None

    def test_private_172(self) -> None:
        """172.16.x.x is rejected."""
        result = validate_url_for_ssrf("http://172.16.0.1")
        assert result is not None

    def test_private_192(self) -> None:
        """192.168.x.x is rejected."""
        result = validate_url_for_ssrf("http://192.168.1.100")
        assert result is not None

    def test_carrier_grade_nat(self) -> None:
        """100.64.x.x (CGNAT) is rejected."""
        result = validate_url_for_ssrf("http://100.64.0.1")
        assert result is not None

    def test_cloud_metadata(self) -> None:
        """169.254.169.254 (cloud metadata) is rejected."""
        result = validate_url_for_ssrf("http://169.254.169.254")
        assert result is not None

    def test_ipv6_loopback(self) -> None:
        """IPv6 loopback ::1 is rejected."""
        result = validate_url_for_ssrf("http://[::1]")
        assert result is not None

    def test_dns_resolves_private(self) -> None:
        """Hostname resolving to private IP is rejected."""
        with patch("mcp_atlassian.utils.urls.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("10.0.0.1", 0))]
            result = validate_url_for_ssrf("https://evil.example.com")
            assert result is not None
            assert "non-global" in result.lower()

    def test_dns_unresolvable(self) -> None:
        """Unresolvable hostname is rejected."""
        with patch("mcp_atlassian.utils.urls.socket.getaddrinfo") as mock_dns:
            mock_dns.side_effect = socket.gaierror("Name resolution failed")
            result = validate_url_for_ssrf("https://nonexistent.invalid")
            assert result is not None
            assert "DNS" in result

    def test_allowlist_exact_match(self) -> None:
        """Domain allowlist allows exact match."""
        with patch.dict(
            os.environ,
            {"MCP_ALLOWED_URL_DOMAINS": "corp.com"},
        ):
            with patch("mcp_atlassian.utils.urls.socket.getaddrinfo") as mock_dns:
                mock_dns.return_value = [(2, 1, 6, "", ("8.8.8.8", 0))]
                assert validate_url_for_ssrf("https://corp.com") is None

    def test_allowlist_subdomain_match(self) -> None:
        """Domain allowlist allows subdomain match."""
        with patch.dict(
            os.environ,
            {"MCP_ALLOWED_URL_DOMAINS": "atlassian.net"},
        ):
            with patch("mcp_atlassian.utils.urls.socket.getaddrinfo") as mock_dns:
                mock_dns.return_value = [(2, 1, 6, "", ("104.192.141.1", 0))]
                assert validate_url_for_ssrf("https://company.atlassian.net") is None

    def test_allowlist_reject(self) -> None:
        """Domain allowlist rejects non-matching hostname."""
        with patch.dict(
            os.environ,
            {"MCP_ALLOWED_URL_DOMAINS": "atlassian.net"},
        ):
            result = validate_url_for_ssrf("https://evil.com")
            assert result is not None
            assert "not in allowed" in result.lower()

    def test_metadata_google_internal(self) -> None:
        """GCP metadata endpoint is rejected."""
        result = validate_url_for_ssrf("http://metadata.google.internal")
        assert result is not None
        assert "Blocked hostname" in result

    def test_allowlist_subdomain_private_ip(self) -> None:
        """Allowlisted subdomain resolving to private IP is accepted."""
        with patch.dict(
            os.environ,
            {"MCP_ALLOWED_URL_DOMAINS": "corp.example.com"},
        ):
            assert validate_url_for_ssrf("https://jira.corp.example.com") is None

    def test_allowlist_exact_private_ip(self) -> None:
        """Allowlisted exact domain resolving to private IP is accepted."""
        with patch.dict(
            os.environ,
            {"MCP_ALLOWED_URL_DOMAINS": "internal.company.com"},
        ):
            assert validate_url_for_ssrf("https://internal.company.com") is None

    def test_allowlist_rejects_non_matching_private_ip(self) -> None:
        """Non-allowlisted domain resolving to private IP is still rejected."""
        with patch.dict(
            os.environ,
            {"MCP_ALLOWED_URL_DOMAINS": "corp.example.com"},
        ):
            result = validate_url_for_ssrf("https://evil.com")
            assert result is not None
            assert "not in allowed" in result.lower()

    def test_no_allowlist_private_ip_rejected(self) -> None:
        """Without allowlist, hostname resolving to private IP is rejected."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MCP_ALLOWED_URL_DOMAINS", None)
            with patch("mcp_atlassian.utils.urls.socket.getaddrinfo") as mock_dns:
                mock_dns.return_value = [(2, 1, 6, "", ("10.0.0.1", 0))]
                result = validate_url_for_ssrf("https://some.host")
                assert result is not None
                assert "non-global" in result.lower()

    def test_allowlist_bypasses_dns_failure(self) -> None:
        """Allowlisted domain is accepted even when DNS resolution fails."""
        with patch.dict(
            os.environ,
            {"MCP_ALLOWED_URL_DOMAINS": "corp.example.com"},
        ):
            with patch("mcp_atlassian.utils.urls.socket.getaddrinfo") as mock_dns:
                mock_dns.side_effect = socket.gaierror("Name resolution failed")
                assert validate_url_for_ssrf("https://jira.corp.example.com") is None

    def test_ipv4_mapped_ipv6(self) -> None:
        """IPv4-mapped IPv6 loopback is rejected."""
        result = validate_url_for_ssrf("http://[::ffff:127.0.0.1]")
        assert result is not None


class TestSsrfBackslashBypassRegression:
    """Regression (GHSA-hgcf) — backslash authority-confusion SSRF bypass.

    ``validate_url_for_ssrf`` extracts the host via ``urlparse().hostname``
    (``urls.py:92``), but ``requests`` (and browsers) parse a backslash in the
    authority differently: ``urlparse("http://localhost\\@evil.com/").hostname`` is
    ``"evil.com"`` (external, so validation passes), while ``requests`` connects to
    ``localhost`` / ``127.0.0.1`` — the validator would approve a URL that
    actually targets an internal host. These tests assert the secure outcome: the
    backslash-confusion URL is blocked.
    """

    @pytest.mark.security_regression
    @pytest.mark.parametrize(
        "url",
        ["http://localhost\\@evil.com/", "http://127.0.0.1\\@evil.com/"],
        ids=["localhost-backslash", "loopback-ip-backslash"],
    )
    @patch.dict(os.environ, {"MCP_ALLOWED_URL_DOMAINS": ""})
    @patch("mcp_atlassian.utils.urls.socket.getaddrinfo")
    def test_backslash_authority_confusion_is_blocked(
        self, mock_getaddrinfo, url: str
    ) -> None:
        """A URL whose parsed host disagrees with its connection target is blocked."""
        # DNS mock: evil.com resolves to a GLOBAL IP, so the *bare* host is "safe".
        # This isolates the block to backslash normalization, not a DNS failure.
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
        ]
        # Sanity: the external host on its own passes validation under this mock.
        assert validate_url_for_ssrf("http://evil.com/") is None
        # The backslash-confusion URL parses to evil.com but really targets internal.
        result = validate_url_for_ssrf(url)
        assert result is not None, (
            "URL with backslash authority confusion must be blocked — the parsed "
            "host disagrees with the real connection target"
        )
