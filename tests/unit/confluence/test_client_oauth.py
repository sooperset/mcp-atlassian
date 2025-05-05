"""Tests for the ConfluenceClient with OAuth authentication."""

import os
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.utils.oauth import OAuthConfig


class TestConfluenceClientOAuth:
    """Tests for ConfluenceClient with OAuth authentication."""

    def test_init_with_oauth_config(self):
        """Test initializing the client with OAuth configuration."""
        # Create a mock OAuth config
        oauth_config = OAuthConfig(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:confluence-space.summary write:confluence-content",
            cloud_id="test-cloud-id",
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_at=9999999999.0,  # Set a future expiry time
        )

        # Create a Confluence config with OAuth
        config = ConfluenceConfig(
            url="https://test.atlassian.net/wiki",
            auth_type="oauth",
            oauth_config=oauth_config,
        )

        # Mock dependencies
        with (
            patch("mcp_atlassian.confluence.client.Confluence") as mock_confluence,
            patch(
                "mcp_atlassian.confluence.client.configure_oauth_session"
            ) as mock_configure_oauth,
            patch(
                "mcp_atlassian.confluence.client.configure_ssl_verification"
            ) as mock_configure_ssl,
            patch(
                "mcp_atlassian.preprocessing.confluence.ConfluencePreprocessor"
            ) as mock_preprocessor,
            patch.object(
                type(oauth_config),
                "is_token_expired",
                new=PropertyMock(return_value=False),
            ),
            patch.object(
                type(oauth_config),
                "ensure_valid_token",
                new=MagicMock(return_value=True),
            ),
        ):
            # Configure the mock to return success for OAuth configuration
            mock_configure_oauth.return_value = True

            # Initialize client
            client = ConfluenceClient(config=config)

            # Verify OAuth session configuration was called
            mock_configure_oauth.assert_called_once()

            # Verify Confluence was initialized with the expected parameters
            mock_confluence.assert_called_once()
            conf_kwargs = mock_confluence.call_args[1]
            assert (
                conf_kwargs["url"]
                == f"https://api.atlassian.com/ex/confluence/{oauth_config.cloud_id}"
            )
            assert "session" in conf_kwargs
            assert conf_kwargs["cloud"] is True

            # Verify SSL verification was configured
            mock_configure_ssl.assert_called_once()

            # Verify preprocessor was initialized
            assert client.preprocessor == mock_preprocessor.return_value

    def test_init_with_oauth_missing_cloud_id(self):
        """Test initializing the client with OAuth but missing cloud_id."""
        # Create a mock OAuth config without cloud_id
        oauth_config = OAuthConfig(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:confluence-space.summary write:confluence-content",
            # No cloud_id
            access_token="test-access-token",
        )

        # Create a Confluence config with OAuth
        config = ConfluenceConfig(
            url="https://test.atlassian.net/wiki",
            auth_type="oauth",
            oauth_config=oauth_config,
        )

        # Verify error is raised
        with pytest.raises(
            ValueError, match="OAuth authentication requires a valid cloud_id"
        ):
            ConfluenceClient(config=config)

    def test_init_with_oauth_failed_session_config(self):
        """Test initializing the client with OAuth but failed session configuration."""
        # Create a mock OAuth config
        oauth_config = OAuthConfig(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:confluence-space.summary write:confluence-content",
            cloud_id="test-cloud-id",
            access_token="test-access-token",
            refresh_token="test-refresh-token",
        )

        # Create a Confluence config with OAuth
        config = ConfluenceConfig(
            url="https://test.atlassian.net/wiki",
            auth_type="oauth",
            oauth_config=oauth_config,
        )

        # Mock dependencies with OAuth configuration failure
        with (
            patch(
                "mcp_atlassian.confluence.client.configure_oauth_session"
            ) as mock_configure_oauth,
            # Patch the methods directly on the instance, not the class
            patch.object(
                type(oauth_config),
                "is_token_expired",
                new=PropertyMock(return_value=False),
            ),
            patch.object(oauth_config, "ensure_valid_token", return_value=True),
        ):
            # Configure the mock to return failure for OAuth configuration
            mock_configure_oauth.return_value = False

            # Verify error is raised
            with pytest.raises(
                MCPAtlassianAuthenticationError,
                match="Failed to configure OAuth session",
            ):
                ConfluenceClient(config=config)

    def test_from_env_with_oauth(self):
        """Test creating client from environment variables with OAuth configuration."""
        # Mock environment variables
        env_vars = {
            "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
            "CONFLUENCE_AUTH_TYPE": "oauth",  # Add auth_type to env vars
            "ATLASSIAN_OAUTH_CLIENT_ID": "env-client-id",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "env-client-secret",
            "ATLASSIAN_OAUTH_REDIRECT_URI": "https://example.com/callback",
            "ATLASSIAN_OAUTH_SCOPE": "read:confluence-space.summary",
            "ATLASSIAN_OAUTH_CLOUD_ID": "env-cloud-id",
        }

        # Mock OAuth config and token loading
        mock_oauth_config = MagicMock()
        mock_oauth_config.cloud_id = "env-cloud-id"
        mock_oauth_config.access_token = "env-access-token"
        mock_oauth_config.refresh_token = "env-refresh-token"
        mock_oauth_config.expires_at = 9999999999.0

        # Set is_token_expired as a property
        type(mock_oauth_config).is_token_expired = MagicMock(return_value=False)
        # Set ensure_valid_token as a method
        mock_oauth_config.ensure_valid_token = MagicMock(return_value=True)

        with (
            patch.dict(os.environ, env_vars),
            patch(
                "mcp_atlassian.confluence.config.OAuthConfig.from_env",
                return_value=mock_oauth_config,
            ),
            patch("mcp_atlassian.confluence.client.Confluence") as mock_confluence,
            patch(
                "mcp_atlassian.confluence.client.configure_oauth_session",
                return_value=True,
            ) as mock_configure_oauth,
            patch(
                "mcp_atlassian.confluence.client.configure_ssl_verification"
            ) as mock_configure_ssl,
        ):
            # Initialize client from environment
            client = ConfluenceClient()

            # Verify client was initialized with OAuth
            assert client.config.auth_type == "oauth"
            assert client.config.oauth_config is mock_oauth_config

            # Verify Confluence was initialized correctly
            mock_confluence.assert_called_once()
            conf_kwargs = mock_confluence.call_args[1]
            assert (
                conf_kwargs["url"]
                == f"https://api.atlassian.com/ex/confluence/{mock_oauth_config.cloud_id}"
            )
            assert "session" in conf_kwargs
            assert conf_kwargs["cloud"] is True

            # Verify OAuth session was configured
            mock_configure_oauth.assert_called_once()
