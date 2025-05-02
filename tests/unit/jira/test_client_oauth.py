"""Tests for the JiraClient with OAuth authentication."""

import os
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.oauth import OAuthConfig


class TestJiraClientOAuth:
    """Tests for JiraClient with OAuth authentication."""

    def test_init_with_oauth_config(self):
        """Test initializing the client with OAuth configuration."""
        # Create a mock OAuth config with both access and refresh tokens
        oauth_config = OAuthConfig(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:jira-work write:jira-work",
            cloud_id="test-cloud-id",
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_at=9999999999.0,  # Set a future expiry time
        )

        # Create a Jira config with OAuth
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=oauth_config,
        )

        # Mock dependencies
        with (
            patch("mcp_atlassian.jira.client.Jira") as mock_jira,
            patch(
                "mcp_atlassian.jira.client.configure_oauth_session"
            ) as mock_configure_oauth,
            patch(
                "mcp_atlassian.jira.client.configure_ssl_verification"
            ) as mock_configure_ssl,
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
            client = JiraClient(config=config)

            # Verify OAuth session configuration was called
            mock_configure_oauth.assert_called_once()

            # Verify Jira was initialized with the expected parameters
            mock_jira.assert_called_once()
            jira_kwargs = mock_jira.call_args[1]
            assert (
                jira_kwargs["url"]
                == f"https://api.atlassian.com/ex/jira/{oauth_config.cloud_id}"
            )
            assert "session" in jira_kwargs
            assert jira_kwargs["cloud"] is True

            # Verify SSL verification was configured
            mock_configure_ssl.assert_called_once()

    def test_init_with_oauth_missing_cloud_id(self):
        """Test initializing the client with OAuth but missing cloud_id."""
        # Create a mock OAuth config without cloud_id
        oauth_config = OAuthConfig(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:jira-work write:jira-work",
            # No cloud_id
            access_token="test-access-token",
        )

        # Create a Jira config with OAuth
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=oauth_config,
        )

        # Verify error is raised
        with pytest.raises(
            ValueError, match="OAuth authentication requires a valid cloud_id"
        ):
            JiraClient(config=config)

    def test_init_with_oauth_failed_session_config(self):
        """Test initializing the client with OAuth but failed session configuration."""
        # Create a mock OAuth config
        oauth_config = OAuthConfig(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:jira-work write:jira-work",
            cloud_id="test-cloud-id",
            access_token="test-access-token",
            refresh_token="test-refresh-token",
        )

        # Create a Jira config with OAuth
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=oauth_config,
        )

        # Mock dependencies with OAuth configuration failure
        with (
            patch("mcp_atlassian.jira.client.Jira") as mock_jira,
            # Patch where the function is imported, not where it's defined
            patch(
                "mcp_atlassian.jira.client.configure_oauth_session"
            ) as mock_configure_oauth,
            patch(
                "mcp_atlassian.jira.client.configure_ssl_verification"
            ) as mock_configure_ssl,
            patch(
                "mcp_atlassian.preprocessing.jira.JiraPreprocessor"
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
            # Configure the mock to return failure for OAuth configuration
            mock_configure_oauth.return_value = False

            # Verify error is raised
            with pytest.raises(
                MCPAtlassianAuthenticationError,
                match="Failed to configure OAuth session",
            ):
                JiraClient(config=config)

    def test_from_env_with_oauth(self):
        # Mock environment variables
        env_vars = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_AUTH_TYPE": "oauth",  # Add auth_type to env vars
            "ATLASSIAN_OAUTH_CLIENT_ID": "env-client-id",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "env-client-secret",
            "ATLASSIAN_OAUTH_REDIRECT_URI": "https://example.com/callback",
            "ATLASSIAN_OAUTH_SCOPE": "read:jira-work",
            "ATLASSIAN_OAUTH_CLOUD_ID": "env-cloud-id",
        }

        # Mock OAuth config and token loading
        mock_oauth_config = MagicMock()
        mock_oauth_config.cloud_id = "env-cloud-id"
        mock_oauth_config.access_token = "env-access-token"
        mock_oauth_config.refresh_token = "env-refresh-token"
        mock_oauth_config.expires_at = 9999999999.0

        # Set up the property and method on the mock
        type(mock_oauth_config).is_token_expired = MagicMock(return_value=False)
        mock_oauth_config.ensure_valid_token = MagicMock(return_value=True)

        with (
            patch.dict(os.environ, env_vars),
            patch(
                "mcp_atlassian.jira.config.OAuthConfig.from_env",
                return_value=mock_oauth_config,
            ),
            patch("mcp_atlassian.jira.client.Jira") as mock_jira,
            patch(
                "mcp_atlassian.jira.client.configure_oauth_session", return_value=True
            ) as mock_configure_oauth,
            patch(
                "mcp_atlassian.jira.client.configure_ssl_verification"
            ) as mock_configure_ssl,
        ):
            # Initialize client from environment
            client = JiraClient()

            # Verify client was initialized with OAuth
            assert client.config.auth_type == "oauth"
            assert client.config.oauth_config is mock_oauth_config

            # Verify Jira was initialized correctly
            mock_jira.assert_called_once()
            jira_kwargs = mock_jira.call_args[1]
            assert (
                jira_kwargs["url"]
                == f"https://api.atlassian.com/ex/jira/{mock_oauth_config.cloud_id}"
            )
            assert "session" in jira_kwargs
            assert jira_kwargs["cloud"] is True

            # Verify OAuth session was configured
            mock_configure_oauth.assert_called_once()
