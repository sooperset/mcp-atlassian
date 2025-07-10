"""Unit tests for the ConfluenceConfig class."""

import os
from unittest.mock import patch

import pytest

from mcp_atlassian.confluence.config import ConfluenceConfig


def test_from_env_success():
    """Test that from_env successfully creates a config from environment variables."""
    # Need to clear and reset the environment for this test
    with patch.dict(
        "os.environ",
        {
            "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
            "CONFLUENCE_USERNAME": "test_username",
            "CONFLUENCE_API_TOKEN": "test_token",
        },
        clear=True,  # Clear existing environment variables
    ):
        config = ConfluenceConfig.from_env()
        assert config.url == "https://test.atlassian.net/wiki"
        assert config.username == "test_username"
        assert config.api_token == "test_token"


def test_from_env_missing_url():
    """Test that from_env raises ValueError when URL is missing."""
    original_env = os.environ.copy()
    try:
        os.environ.clear()
        with pytest.raises(
            ValueError, match="Missing required CONFLUENCE_URL environment variable"
        ):
            ConfluenceConfig.from_env()
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


def test_from_env_missing_cloud_auth():
    """Test that from_env raises ValueError when cloud auth credentials are missing."""
    with patch.dict(
        os.environ,
        {
            "CONFLUENCE_URL": "https://test.atlassian.net",  # Cloud URL
        },
        clear=True,
    ):
        with pytest.raises(
            ValueError,
            match="Cloud authentication requires CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN",
        ):
            ConfluenceConfig.from_env()


def test_from_env_missing_server_auth():
    """Test that from_env raises ValueError when server auth credentials are missing."""
    with patch.dict(
        os.environ,
        {
            "CONFLUENCE_URL": "https://confluence.example.com",  # Server URL
        },
        clear=True,
    ):
        with pytest.raises(
            ValueError,
            match="Server/Data Center authentication requires CONFLUENCE_PERSONAL_TOKEN",
        ):
            ConfluenceConfig.from_env()


def test_is_cloud():
    """Test that is_cloud property returns correct value."""
    # Arrange & Act - Cloud URL
    config = ConfluenceConfig(
        url="https://example.atlassian.net/wiki",
        auth_type="basic",
        username="test",
        api_token="test",
    )

    # Assert
    assert config.is_cloud is True

    # Arrange & Act - Server URL
    config = ConfluenceConfig(
        url="https://confluence.example.com",
        auth_type="pat",
        personal_token="test",
    )

    # Assert
    assert config.is_cloud is False

    # Arrange & Act - Localhost URL (Data Center/Server)
    config = ConfluenceConfig(
        url="http://localhost:8090",
        auth_type="pat",
        personal_token="test",
    )

    # Assert
    assert config.is_cloud is False

    # Arrange & Act - IP localhost URL (Data Center/Server)
    config = ConfluenceConfig(
        url="http://127.0.0.1:8090",
        auth_type="pat",
        personal_token="test",
    )

    # Assert
    assert config.is_cloud is False


def test_from_env_proxy_settings():
    """Test that from_env correctly loads proxy environment variables."""
    with patch.dict(
        os.environ,
        {
            "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
            "CONFLUENCE_USERNAME": "test_username",
            "CONFLUENCE_API_TOKEN": "test_token",
            "HTTP_PROXY": "http://proxy.example.com:8080",
            "HTTPS_PROXY": "https://proxy.example.com:8443",
            "SOCKS_PROXY": "socks5://user:pass@proxy.example.com:1080",
            "NO_PROXY": "localhost,127.0.0.1",
        },
        clear=True,
    ):
        config = ConfluenceConfig.from_env()
        assert config.http_proxy == "http://proxy.example.com:8080"
        assert config.https_proxy == "https://proxy.example.com:8443"
        assert config.socks_proxy == "socks5://user:pass@proxy.example.com:1080"
        assert config.no_proxy == "localhost,127.0.0.1"

    # Service-specific overrides
    with patch.dict(
        os.environ,
        {
            "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
            "CONFLUENCE_USERNAME": "test_username",
            "CONFLUENCE_API_TOKEN": "test_token",
            "CONFLUENCE_HTTP_PROXY": "http://confluence-proxy.example.com:8080",
            "CONFLUENCE_HTTPS_PROXY": "https://confluence-proxy.example.com:8443",
            "CONFLUENCE_SOCKS_PROXY": "socks5://user:pass@confluence-proxy.example.com:1080",
            "CONFLUENCE_NO_PROXY": "localhost,127.0.0.1,.internal.example.com",
        },
        clear=True,
    ):
        config = ConfluenceConfig.from_env()
        assert config.http_proxy == "http://confluence-proxy.example.com:8080"
        assert config.https_proxy == "https://confluence-proxy.example.com:8443"
        assert (
            config.socks_proxy == "socks5://user:pass@confluence-proxy.example.com:1080"
        )
        assert config.no_proxy == "localhost,127.0.0.1,.internal.example.com"


def test_is_cloud_oauth_with_cloud_id():
    """Test that is_cloud returns True for OAuth with cloud_id regardless of URL."""
    from mcp_atlassian.utils.oauth import BYOAccessTokenOAuthConfig

    # OAuth with cloud_id and no URL - should be Cloud
    oauth_config = BYOAccessTokenOAuthConfig(
        cloud_id="test-cloud-id", access_token="test-token"
    )
    config = ConfluenceConfig(
        url=None,  # URL can be None in Multi-Cloud OAuth mode
        auth_type="oauth",
        oauth_config=oauth_config,
    )
    assert config.is_cloud is True

    # OAuth with cloud_id and server URL - should still be Cloud
    config = ConfluenceConfig(
        url="https://confluence.example.com",  # Server-like URL
        auth_type="oauth",
        oauth_config=oauth_config,
    )
    assert config.is_cloud is True
