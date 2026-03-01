"""Tests for the URL utilities module."""

import os
import socket
from unittest.mock import patch

import pytest

from mcp_atlassian.utils.urls import (
    is_atlassian_cloud_url,
    resolve_relative_url,
    validate_url_for_ssrf,
)


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
