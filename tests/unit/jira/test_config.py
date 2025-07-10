"""Tests for the Jira config module."""

import os
from unittest.mock import patch

import pytest

from mcp_atlassian.jira.config import JiraConfig


def test_from_env_basic_auth():
    """Test that from_env correctly loads basic auth configuration."""
    with patch.dict(
        os.environ,
        {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_USERNAME": "test_username",
            "JIRA_API_TOKEN": "test_token",
        },
        clear=True,
    ):
        config = JiraConfig.from_env()
        assert config.url == "https://test.atlassian.net"
        assert config.auth_type == "basic"
        assert config.username == "test_username"
        assert config.api_token == "test_token"
        assert config.personal_token is None
        assert config.ssl_verify is True


def test_from_env_token_auth():
    """Test that from_env correctly loads token auth configuration."""
    with patch.dict(
        os.environ,
        {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_PERSONAL_TOKEN": "test_personal_token",
            "JIRA_SSL_VERIFY": "false",
        },
        clear=True,
    ):
        config = JiraConfig.from_env()
        assert config.url == "https://jira.example.com"
        assert config.auth_type == "pat"
        assert config.username is None
        assert config.api_token is None
        assert config.personal_token == "test_personal_token"
        assert config.ssl_verify is False


def test_from_env_missing_url():
    """Test that from_env raises ValueError when URL is missing."""
    original_env = os.environ.copy()
    try:
        os.environ.clear()
        with pytest.raises(
            ValueError, match="Missing required JIRA_URL environment variable"
        ):
            JiraConfig.from_env()
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


def test_from_env_missing_cloud_auth():
    """Test that from_env raises ValueError when cloud auth credentials are missing."""
    with patch.dict(
        os.environ,
        {
            "JIRA_URL": "https://test.atlassian.net",  # Cloud URL
        },
        clear=True,
    ):
        with pytest.raises(
            ValueError,
            match="Cloud authentication requires JIRA_USERNAME and JIRA_API_TOKEN",
        ):
            JiraConfig.from_env()


def test_from_env_missing_server_auth():
    """Test that from_env raises ValueError when server auth credentials are missing."""
    with patch.dict(
        os.environ,
        {
            "JIRA_URL": "https://jira.example.com",  # Server URL
        },
        clear=True,
    ):
        with pytest.raises(
            ValueError,
            match="Server/Data Center authentication requires JIRA_PERSONAL_TOKEN",
        ):
            JiraConfig.from_env()


def test_is_cloud():
    """Test that is_cloud property returns correct value."""
    # Arrange & Act - Cloud URL
    config = JiraConfig(
        url="https://example.atlassian.net",
        auth_type="basic",
        username="test",
        api_token="test",
    )

    # Assert
    assert config.is_cloud is True

    # Arrange & Act - Server URL
    config = JiraConfig(
        url="https://jira.example.com",
        auth_type="pat",
        personal_token="test",
    )

    # Assert
    assert config.is_cloud is False

    # Arrange & Act - Localhost URL (Data Center/Server)
    config = JiraConfig(
        url="http://localhost:8080",
        auth_type="pat",
        personal_token="test",
    )

    # Assert
    assert config.is_cloud is False

    # Arrange & Act - IP localhost URL (Data Center/Server)
    config = JiraConfig(
        url="http://127.0.0.1:8080",
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
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_USERNAME": "test_username",
            "JIRA_API_TOKEN": "test_token",
            "HTTP_PROXY": "http://proxy.example.com:8080",
            "HTTPS_PROXY": "https://proxy.example.com:8443",
            "SOCKS_PROXY": "socks5://user:pass@proxy.example.com:1080",
            "NO_PROXY": "localhost,127.0.0.1",
        },
        clear=True,
    ):
        config = JiraConfig.from_env()
        assert config.http_proxy == "http://proxy.example.com:8080"
        assert config.https_proxy == "https://proxy.example.com:8443"
        assert config.socks_proxy == "socks5://user:pass@proxy.example.com:1080"
        assert config.no_proxy == "localhost,127.0.0.1"

    # Service-specific overrides
    with patch.dict(
        os.environ,
        {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_USERNAME": "test_username",
            "JIRA_API_TOKEN": "test_token",
            "JIRA_HTTP_PROXY": "http://jira-proxy.example.com:8080",
            "JIRA_HTTPS_PROXY": "https://jira-proxy.example.com:8443",
            "JIRA_SOCKS_PROXY": "socks5://user:pass@jira-proxy.example.com:1080",
            "JIRA_NO_PROXY": "localhost,127.0.0.1,.internal.example.com",
        },
        clear=True,
    ):
        config = JiraConfig.from_env()
        assert config.http_proxy == "http://jira-proxy.example.com:8080"
        assert config.https_proxy == "https://jira-proxy.example.com:8443"
        assert config.socks_proxy == "socks5://user:pass@jira-proxy.example.com:1080"
        assert config.no_proxy == "localhost,127.0.0.1,.internal.example.com"


def test_is_cloud_oauth_with_cloud_id():
    """Test that is_cloud returns True for OAuth with cloud_id regardless of URL."""
    from mcp_atlassian.utils.oauth import BYOAccessTokenOAuthConfig

    # OAuth with cloud_id and no URL - should be Cloud
    oauth_config = BYOAccessTokenOAuthConfig(
        cloud_id="test-cloud-id", access_token="test-token"
    )
    config = JiraConfig(
        url=None,  # URL can be None in Multi-Cloud OAuth mode
        auth_type="oauth",
        oauth_config=oauth_config,
    )
    assert config.is_cloud is True

    # OAuth with cloud_id and server URL - should still be Cloud
    config = JiraConfig(
        url="https://jira.example.com",  # Server-like URL
        auth_type="oauth",
        oauth_config=oauth_config,
    )
    assert config.is_cloud is True
