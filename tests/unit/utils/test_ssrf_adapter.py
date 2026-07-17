"""Tests for the SSRF DNS-pinning adapter.

Verifies that the adapter resolves DNS once, validates the IP, and connects
to the same validated address, preventing DNS-rebinding TOCTOU attacks.
"""

import socket
from unittest.mock import MagicMock, patch

import pytest
import requests
from requests.adapters import HTTPAdapter

from mcp_atlassian.utils.ssrf_adapter import (
    SsrfPinningAdapter,
    _operator_trusted_hosts,
    _pinned_create_connection,
    mount_ssrf_pinning,
)


class TestOperatorTrustedHosts:
    """Tests for _operator_trusted_hosts()."""

    def test_returns_operator_configured_hosts(self):
        """Should include hosts from JIRA_URL and CONFLUENCE_URL."""
        with patch.dict(
            "os.environ",
            {
                "JIRA_URL": "https://jira.example.com",
                "CONFLUENCE_URL": "https://confluence.example.com",
            },
        ):
            hosts = _operator_trusted_hosts()
            assert "jira.example.com" in hosts
            assert "confluence.example.com" in hosts

    def test_returns_domain_allowlist(self):
        """Should include MCP_ALLOWED_URL_DOMAINS entries."""
        with patch.dict(
            "os.environ",
            {"MCP_ALLOWED_URL_DOMAINS": "internal.example.com,corp.local"},
        ):
            hosts = _operator_trusted_hosts()
            assert "internal.example.com" in hosts
            assert "corp.local" in hosts

    def test_empty_when_no_env(self):
        """Should return empty list when no env vars set."""
        with patch.dict("os.environ", {}, clear=True):
            hosts = _operator_trusted_hosts()
            assert hosts == []

    def test_handles_malformed_url(self):
        """Should skip malformed URLs gracefully."""
        with patch.dict("os.environ", {"JIRA_URL": "not-a-url"}):
            hosts = _operator_trusted_hosts()
            assert hosts == []


class TestPinnedCreateConnection:
    """Tests for _pinned_create_connection()."""

    def test_blocks_private_ip(self):
        """Should raise OSError when host resolves to private IP."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # Mock DNS returning a private IP (10.x.x.x)
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
            ]
            with pytest.raises(OSError, match="SSRF blocked"):
                _pinned_create_connection(("evil.example.com", 443))

    def test_blocks_loopback_ip(self):
        """Should raise OSError when host resolves to loopback."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            ]
            with pytest.raises(OSError, match="SSRF blocked"):
                _pinned_create_connection(("evil.example.com", 443))

    def test_blocks_metadata_ip(self):
        """Should raise OSError when host resolves to cloud metadata."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80)),
            ]
            with pytest.raises(OSError, match="SSRF blocked"):
                _pinned_create_connection(("evil.example.com", 80))

    def test_allows_global_ip(self):
        """Should connect successfully when host resolves to global IP."""
        mock_socket = MagicMock()
        with (
            patch("socket.getaddrinfo") as mock_getaddrinfo,
            patch("socket.socket", return_value=mock_socket),
        ):
            # Mock DNS returning a global IP (8.8.8.8)
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            ]
            result = _pinned_create_connection(("example.com", 443))
            assert result is mock_socket
            mock_socket.connect.assert_called_once_with(("8.8.8.8", 443))

    def test_uses_same_ip_for_connect(self):
        """Should connect to the exact IP returned by DNS resolution."""
        mock_socket = MagicMock()
        with (
            patch("socket.getaddrinfo") as mock_getaddrinfo,
            patch("socket.socket", return_value=mock_socket),
        ):
            # Multiple IPs returned - should use the first valid one
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.35", 443)),
            ]
            _pinned_create_connection(("example.com", 443))
            # Should connect to the first IP, not re-resolve
            mock_socket.connect.assert_called_once_with(("93.184.216.34", 443))

    def test_trusted_host_bypasses_ip_check(self):
        """Operator-trusted hosts should bypass non-global IP check."""
        mock_socket = MagicMock()
        with (
            patch("socket.getaddrinfo") as mock_getaddrinfo,
            patch("socket.socket", return_value=mock_socket),
            patch.dict("os.environ", {"JIRA_URL": "https://jira.internal"}),
        ):
            # Mock DNS returning a private IP - should be allowed for trusted host
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
            ]
            result = _pinned_create_connection(("jira.internal", 443))
            assert result is mock_socket

    def test_no_addresses_raises(self):
        """Should raise OSError when getaddrinfo returns no addresses."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = []
            with pytest.raises(OSError, match="getaddrinfo returned no addresses"):
                _pinned_create_connection(("example.com", 443))


class TestSsrfPinningAdapter:
    """Tests for SsrfPinningAdapter."""

    def test_init_poolmanager_sets_pinned_classes(self):
        """Should use pinned connection classes in pool manager."""
        adapter = SsrfPinningAdapter()
        adapter.init_poolmanager(10, 10)
        assert "http" in adapter.poolmanager.pool_classes_by_scheme
        assert "https" in adapter.poolmanager.pool_classes_by_scheme

    def test_preserves_retry_policy(self):
        """Should preserve max_retries from existing adapter."""
        from urllib3.util.retry import Retry

        retry = Retry(total=3)
        adapter = SsrfPinningAdapter(max_retries=retry)
        assert adapter.max_retries == retry


class TestMountSsrfPinning:
    """Tests for mount_ssrf_pinning()."""

    def test_mounts_adapter_for_both_schemes(self):
        """Should mount adapter for both http and https."""
        session = requests.Session()
        mount_ssrf_pinning(session)
        assert isinstance(session.get_adapter("https://example.com"), SsrfPinningAdapter)
        assert isinstance(session.get_adapter("http://example.com"), SsrfPinningAdapter)

    def test_preserves_existing_retries(self):
        """Should preserve retry policy from existing adapters."""
        from urllib3.util.retry import Retry

        session = requests.Session()
        retry = Retry(total=5)
        session.mount("https://", HTTPAdapter(max_retries=retry))
        mount_ssrf_pinning(session)
        adapter = session.get_adapter("https://example.com")
        assert isinstance(adapter, SsrfPinningAdapter)
        assert adapter.max_retries == retry
