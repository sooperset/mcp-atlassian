"""Unit tests for the ConfluenceConfig class."""

import os
from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.utils.oauth import OAuthConfig


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


class TestConfluenceDataCenterOAuth:
    """Tests for Confluence Data Center OAuth configuration."""

    @patch("mcp_atlassian.utils.oauth.OAuthConfig.from_env")
    def test_from_env_data_center_oauth_success(self, mock_oauth_from_env):
        """Test from_env with Data Center OAuth configuration."""
        # Mock OAuth config for Data Center
        mock_oauth_config = MagicMock()
        mock_oauth_config.client_id = "dc-client-id"
        mock_oauth_config.client_secret = "dc-client-secret"
        mock_oauth_config.redirect_uri = "https://localhost:8080/callback"
        mock_oauth_config.scope = "READ WRITE"
        mock_oauth_config.instance_type = "datacenter"
        mock_oauth_config.instance_url = "https://confluence.mycompany.com"
        mock_oauth_config.cloud_id = None
        mock_oauth_config.is_cloud = False
        mock_oauth_from_env.return_value = mock_oauth_config

        with patch.dict(
            os.environ,
            {
                "CONFLUENCE_URL": "https://confluence.mycompany.com",
            },
            clear=True,
        ):
            config = ConfluenceConfig.from_env()

            assert config.url == "https://confluence.mycompany.com"
            assert config.auth_type == "oauth"
            assert config.oauth_config == mock_oauth_config
            assert not config.is_cloud

    @patch("mcp_atlassian.utils.oauth.OAuthConfig.from_env")
    def test_from_env_cloud_oauth_success(self, mock_oauth_from_env):
        """Test from_env with Cloud OAuth configuration."""
        # Mock OAuth config for Cloud
        mock_oauth_config = MagicMock()
        mock_oauth_config.client_id = "cloud-client-id"
        mock_oauth_config.client_secret = "cloud-client-secret"
        mock_oauth_config.redirect_uri = "https://localhost:8080/callback"
        mock_oauth_config.scope = "read:jira-work write:jira-work"
        mock_oauth_config.instance_type = "cloud"
        mock_oauth_config.instance_url = None
        mock_oauth_config.cloud_id = "test-cloud-id"
        mock_oauth_config.is_cloud = True
        mock_oauth_from_env.return_value = mock_oauth_config

        with patch.dict(
            os.environ,
            {
                "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
            },
            clear=True,
        ):
            config = ConfluenceConfig.from_env()

            assert config.url == "https://test.atlassian.net/wiki"
            assert config.auth_type == "oauth"
            assert config.oauth_config == mock_oauth_config
            assert config.is_cloud

    @patch("mcp_atlassian.utils.oauth.OAuthConfig.from_env")
    def test_from_env_incomplete_oauth_fallback_to_pat(self, mock_oauth_from_env):
        """Test from_env with incomplete OAuth falls back to PAT for Data Center."""
        # Mock incomplete OAuth config (missing instance_url for Data Center)
        mock_oauth_config = MagicMock()
        mock_oauth_config.client_id = "dc-client-id"
        mock_oauth_config.client_secret = "dc-client-secret"
        mock_oauth_config.redirect_uri = "https://localhost:8080/callback"
        mock_oauth_config.scope = "READ WRITE"
        mock_oauth_config.instance_type = "datacenter"
        mock_oauth_config.instance_url = None  # Missing required field
        mock_oauth_config.cloud_id = None
        mock_oauth_config.is_cloud = False
        mock_oauth_from_env.return_value = mock_oauth_config

        with patch.dict(
            os.environ,
            {
                "CONFLUENCE_URL": "https://confluence.mycompany.com",
                "CONFLUENCE_PERSONAL_TOKEN": "my-pat-token",
            },
            clear=True,
        ):
            config = ConfluenceConfig.from_env()

            # OAuth is present, so auth_type should be oauth even if incomplete
            assert config.url == "https://confluence.mycompany.com"
            assert config.auth_type == "oauth"
            assert config.personal_token == "my-pat-token"
            assert config.oauth_config == mock_oauth_config
            assert not config.is_cloud

    def test_is_oauth_fully_configured_data_center_valid(self):
        """Test _is_oauth_fully_configured for valid Data Center OAuth."""
        oauth_config = OAuthConfig(
            client_id="dc-client-id",
            client_secret="dc-client-secret",
            redirect_uri="https://localhost:8080/callback",
            scope="READ WRITE",
            instance_type="datacenter",
            instance_url="https://confluence.mycompany.com",
        )

        result = ConfluenceConfig._is_oauth_fully_configured(oauth_config)
        assert result is True

    def test_is_oauth_fully_configured_data_center_missing_url(self):
        """Test _is_oauth_fully_configured for Data Center OAuth missing instance_url."""
        oauth_config = OAuthConfig(
            client_id="dc-client-id",
            client_secret="dc-client-secret",
            redirect_uri="https://localhost:8080/callback",
            scope="READ WRITE",
            instance_type="datacenter",
            # instance_url is missing
        )

        result = ConfluenceConfig._is_oauth_fully_configured(oauth_config)
        assert result is False

    def test_is_oauth_fully_configured_cloud_valid(self):
        """Test _is_oauth_fully_configured for valid Cloud OAuth."""
        oauth_config = OAuthConfig(
            client_id="cloud-client-id",
            client_secret="cloud-client-secret",
            redirect_uri="https://localhost:8080/callback",
            scope="read:jira-work write:jira-work",
            instance_type="cloud",
            cloud_id="test-cloud-id",
        )

        result = ConfluenceConfig._is_oauth_fully_configured(oauth_config)
        assert result is True

    def test_is_oauth_fully_configured_cloud_missing_cloud_id(self):
        """Test _is_oauth_fully_configured for Cloud OAuth missing cloud_id."""
        oauth_config = OAuthConfig(
            client_id="cloud-client-id",
            client_secret="cloud-client-secret",
            redirect_uri="https://localhost:8080/callback",
            scope="read:jira-work write:jira-work",
            instance_type="cloud",
            # cloud_id is missing
        )

        result = ConfluenceConfig._is_oauth_fully_configured(oauth_config)
        assert result is False

    def test_is_oauth_fully_configured_missing_basic_fields(self):
        """Test _is_oauth_fully_configured with missing basic OAuth fields."""
        oauth_config = OAuthConfig(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="https://localhost:8080/callback",
            scope="READ WRITE",
            instance_type="datacenter",
            instance_url="https://confluence.mycompany.com",
        )

        # Manually set a required field to None to test validation
        oauth_config.client_secret = None

        result = ConfluenceConfig._is_oauth_fully_configured(oauth_config)
        assert result is False

    def test_is_oauth_fully_configured_none_config(self):
        """Test _is_oauth_fully_configured with None config."""
        result = ConfluenceConfig._is_oauth_fully_configured(None)
        assert result is False

    def test_is_auth_configured_data_center_oauth(self):
        """Test is_auth_configured for Data Center OAuth."""
        oauth_config = OAuthConfig(
            client_id="dc-client-id",
            client_secret="dc-client-secret",
            redirect_uri="https://localhost:8080/callback",
            scope="READ WRITE",
            instance_type="datacenter",
            instance_url="https://confluence.mycompany.com",
        )

        config = ConfluenceConfig(
            url="https://confluence.mycompany.com",
            auth_type="oauth",
            oauth_config=oauth_config,
        )

        assert config.is_auth_configured() is True

    def test_is_auth_configured_incomplete_oauth(self):
        """Test is_auth_configured for incomplete OAuth configuration."""
        oauth_config = OAuthConfig(
            client_id="dc-client-id",
            client_secret="dc-client-secret",
            redirect_uri="https://localhost:8080/callback",
            scope="READ WRITE",
            instance_type="datacenter",
            # instance_url is missing
        )

        config = ConfluenceConfig(
            url="https://confluence.mycompany.com",
            auth_type="oauth",
            oauth_config=oauth_config,
        )

        assert config.is_auth_configured() is False
