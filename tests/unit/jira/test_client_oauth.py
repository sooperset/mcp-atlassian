"""Tests for the JiraClient with OAuth authentication."""

import os
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.oauth import BYOAccessTokenOAuthConfig, OAuthConfig


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
                OAuthConfig,
                "is_token_expired",
                new_callable=PropertyMock,
                return_value=False,
            ) as mock_is_expired,
            patch.object(
                oauth_config, "ensure_valid_token", return_value=True
            ) as mock_ensure_valid,
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
                OAuthConfig,
                "is_token_expired",
                new_callable=PropertyMock,
                return_value=False,
            ) as mock_is_expired,
            patch.object(
                oauth_config, "ensure_valid_token", return_value=True
            ) as mock_ensure_valid,
        ):
            # Configure the mock to return failure for OAuth configuration
            mock_configure_oauth.return_value = False

            # Verify error is raised
            with pytest.raises(
                MCPAtlassianAuthenticationError,
                match="Failed to configure OAuth session",
            ):
                JiraClient(config=config)

    def test_init_with_byo_access_token_oauth_config(self):
        """Test initializing the client with BYO Access Token OAuth configuration."""
        # Create a mock BYO OAuth config
        byo_oauth_config = BYOAccessTokenOAuthConfig(
            cloud_id="test-cloud-id", access_token="my-byo-token"
        )

        # Create a Jira config with OAuth
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=byo_oauth_config,
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
                == f"https://api.atlassian.com/ex/jira/{byo_oauth_config.cloud_id}"
            )
            assert "session" in jira_kwargs
            assert jira_kwargs["cloud"] is True

            # Verify SSL verification was configured
            mock_configure_ssl.assert_called_once()

    def test_init_with_byo_oauth_missing_cloud_id(self):
        """Test initializing with BYO OAuth but missing cloud_id."""
        # Create a mock BYO OAuth config with an empty cloud_id
        byo_oauth_config = BYOAccessTokenOAuthConfig(
            cloud_id="", access_token="my-byo-token"
        )

        # Create a Jira config with OAuth
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=byo_oauth_config,
        )

        # Verify error is raised
        with pytest.raises(
            ValueError, match="OAuth authentication requires a valid cloud_id"
        ):
            JiraClient(config=config)

    def test_init_with_byo_oauth_failed_session_config(self):
        """Test init with BYO OAuth but failed session configuration."""
        # Create a mock BYO OAuth config
        byo_oauth_config = BYOAccessTokenOAuthConfig(
            cloud_id="test-cloud-id", access_token="my_byo_token"
        )

        # Create a Jira config with OAuth
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=byo_oauth_config,
        )

        # Mock dependencies with OAuth configuration failure
        with (
            patch("mcp_atlassian.jira.client.Jira"),  # No need to assert mock_jira
            patch(
                "mcp_atlassian.jira.client.configure_oauth_session"
            ) as mock_configure_oauth,
            patch("mcp_atlassian.jira.client.configure_ssl_verification"),
        ):
            # Configure the mock to return failure for OAuth configuration
            mock_configure_oauth.return_value = False

            # Verify error is raised
            with pytest.raises(
                MCPAtlassianAuthenticationError,
                match="Failed to configure OAuth session",
            ):
                JiraClient(config=config)

    def test_init_with_byo_oauth_empty_token_failed_session_config(self):
        """Test init with BYO OAuth, empty token, so session config fails."""
        # Create a mock BYO OAuth config with an empty token
        byo_oauth_config_empty_token = BYOAccessTokenOAuthConfig(
            cloud_id="test-cloud-id",
            access_token="",  # Empty token
        )

        # Create a Jira config with OAuth
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=byo_oauth_config_empty_token,
        )

        # Mock dependencies - configure_oauth_session will be called with real logic
        with (
            patch("mcp_atlassian.jira.client.Jira"),
            patch("mcp_atlassian.jira.client.configure_ssl_verification"),
            # We want to test the actual behavior of configure_oauth_session here for empty token
        ):
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

        with (
            patch.dict(os.environ, env_vars),
            patch(
                "mcp_atlassian.jira.config.get_oauth_config_from_env",
                return_value=mock_oauth_config,
            ),
            patch.object(
                OAuthConfig,
                "is_token_expired",
                new_callable=PropertyMock,
                return_value=False,
            ) as mock_is_expired_env,
            patch.object(
                mock_oauth_config, "ensure_valid_token", return_value=True
            ) as mock_ensure_valid_env,
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

    def test_from_env_with_byo_token_oauth(self):
        """Test JiraClient.from_env() when BYO token OAuth config is found."""
        env_vars = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_AUTH_TYPE": "oauth",
            "ATLASSIAN_OAUTH_ACCESS_TOKEN": "env-byo-access-token",
            "ATLASSIAN_OAUTH_CLOUD_ID": "env-byo-cloud-id",
            # Ensure other standard OAuth env vars are not set or are ignored
            "ATLASSIAN_OAUTH_CLIENT_ID": "",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "",
        }

        # Mock BYO OAuth config
        mock_byo_oauth_config = MagicMock(spec=BYOAccessTokenOAuthConfig)
        mock_byo_oauth_config.cloud_id = "env-byo-cloud-id"
        mock_byo_oauth_config.access_token = "env-byo-access-token"
        # BYO config does not have refresh_token or expires_at in the same way
        # and does not have is_token_expired or ensure_valid_token methods

        with (
            patch.dict(os.environ, env_vars),
            patch(
                "mcp_atlassian.jira.config.get_oauth_config_from_env",
                return_value=mock_byo_oauth_config,
            ),
            patch("mcp_atlassian.jira.client.Jira") as mock_jira,
            patch(
                "mcp_atlassian.jira.client.configure_oauth_session", return_value=True
            ) as mock_configure_oauth,
            patch(
                "mcp_atlassian.jira.client.configure_ssl_verification"
            ) as mock_configure_ssl,
        ):
            client = JiraClient()  # Initializes from env via JiraConfig.from_env()

            assert client.config.auth_type == "oauth"
            assert client.config.oauth_config is mock_byo_oauth_config

            # Verify OAuth session configuration was called
            mock_configure_oauth.assert_called_once()

            mock_jira.assert_called_once()
            jira_kwargs = mock_jira.call_args[1]
            assert (
                jira_kwargs["url"]
                == f"https://api.atlassian.com/ex/jira/{mock_byo_oauth_config.cloud_id}"
            )
            mock_configure_ssl.assert_called_once()

    def test_from_env_with_no_oauth_config_found(self):
        """Test JiraClient.from_env() when no OAuth config is found."""
        env_vars = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_AUTH_TYPE": "oauth",
            # No OAuth specific variables set
            "ATLASSIAN_OAUTH_CLIENT_ID": "",
            "ATLASSIAN_OAUTH_ACCESS_TOKEN": "",
            # Explicitly clear basic auth credentials
            "JIRA_USERNAME": "",
            "JIRA_API_TOKEN": "",
        }

        with (
            patch.dict(os.environ, env_vars, clear=True),
            patch(
                "mcp_atlassian.jira.config.get_oauth_config_from_env",
                return_value=None,  # Simulate no config found
            ),
        ):
            with pytest.raises(
                ValueError,  # Adjusted to actual error raised by JiraConfig.from_env
                match=r"Cloud authentication requires JIRA_USERNAME and JIRA_API_TOKEN, or OAuth configuration.*",
            ):
                JiraClient()
