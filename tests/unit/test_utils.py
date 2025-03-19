"""Tests for the utilities module."""

from unittest.mock import MagicMock, patch

from requests.adapters import HTTPAdapter

from mcp_atlassian.utils import SSLIgnoreAdapter, configure_ssl_verification


def test_ssl_ignore_adapter_cert_verify():
    """Test that SSLIgnoreAdapter overrides cert verification."""
    # Arrange
    adapter = SSLIgnoreAdapter()
    connection = MagicMock()
    url = "https://example.com"
    cert = None

    # Mock the super class's cert_verify method
    with patch.object(HTTPAdapter, "cert_verify") as mock_super_cert_verify:
        # Act
        adapter.cert_verify(
            connection, url, verify=True, cert=cert
        )  # Pass True, but expect False to be used

        # Assert
        mock_super_cert_verify.assert_called_once_with(
            connection, url, verify=False, cert=cert
        )


def test_configure_ssl_verification_disabled():
    """Test configure_ssl_verification when SSL verification is disabled."""
    # Arrange
    service_name = "TestService"
    url = "https://test.example.com/path"
    session = MagicMock()  # Use MagicMock instead of actual Session
    ssl_verify = False

    with patch("mcp_atlassian.utils.SSLIgnoreAdapter") as mock_adapter_class:
        mock_adapter = MagicMock()
        mock_adapter_class.return_value = mock_adapter

        # Act
        configure_ssl_verification(service_name, url, session, ssl_verify)

        # Assert
        mock_adapter_class.assert_called_once()
        # Verify the adapter is mounted for both http and https
        assert session.mount.call_count == 2
        session.mount.assert_any_call("https://test.example.com", mock_adapter)
        session.mount.assert_any_call("http://test.example.com", mock_adapter)


def test_configure_ssl_verification_enabled():
    """Test configure_ssl_verification when SSL verification is enabled."""
    # Arrange
    service_name = "TestService"
    url = "https://test.example.com/path"
    session = MagicMock()  # Use MagicMock instead of actual Session
    ssl_verify = True

    with patch("mcp_atlassian.utils.SSLIgnoreAdapter") as mock_adapter_class:
        # Act
        configure_ssl_verification(service_name, url, session, ssl_verify)

        # Assert
        mock_adapter_class.assert_not_called()
        assert session.mount.call_count == 0
