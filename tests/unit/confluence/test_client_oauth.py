"""Tests for the ConfluenceClient with OAuth authentication."""

import os
from unittest.mock import PropertyMock, patch

import pytest

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.utils.oauth import BYOAccessTokenOAuthConfig, OAuthConfig


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

    def test_init_with_byo_access_token_oauth_config(self):
        """Test initializing the client with BYOAccessTokenOAuthConfig."""
        # Create a mock BYO OAuth config
        byo_oauth_config = BYOAccessTokenOAuthConfig(
            cloud_id="test-byo-cloud-id",
            access_token="test-byo-access-token",
        )

        # Create a Confluence config with BYO OAuth
        config = ConfluenceConfig(
            url="https://test.atlassian.net/wiki",
            auth_type="oauth",
            oauth_config=byo_oauth_config,
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
                == f"https://api.atlassian.com/ex/confluence/{byo_oauth_config.cloud_id}"
            )
            assert "session" in conf_kwargs
            assert conf_kwargs["cloud"] is True

            # Verify SSL verification was configured
            mock_configure_ssl.assert_called_once()

            # Verify preprocessor was initialized
            assert client.preprocessor == mock_preprocessor.return_value

    def test_init_with_byo_oauth_missing_cloud_id(self):
        """Test initializing the client with BYO OAuth but missing cloud_id."""
        # Create a mock BYO OAuth config without cloud_id
        byo_oauth_config = BYOAccessTokenOAuthConfig(
            access_token="test-byo-access-token",
            cloud_id="",  # Explicitly empty or None
        )

        # Create a Confluence config with BYO OAuth
        config = ConfluenceConfig(
            url="https://test.atlassian.net/wiki",
            auth_type="oauth",
            oauth_config=byo_oauth_config,
        )

        # Verify error is raised by ConfluenceClient's validation
        with pytest.raises(
            ValueError, match="OAuth authentication requires a valid cloud_id"
        ):
            ConfluenceClient(config=config)

    def test_init_with_byo_oauth_failed_session_config(self):
        """Test initializing with BYO OAuth but failed session configuration."""
        # Create a mock BYO OAuth config
        byo_oauth_config = BYOAccessTokenOAuthConfig(
            cloud_id="test-byo-cloud-id",
            access_token="test-byo-access-token",
        )

        # Create a Confluence config with BYO OAuth
        config = ConfluenceConfig(
            url="https://test.atlassian.net/wiki",
            auth_type="oauth",
            oauth_config=byo_oauth_config,
        )

        # Mock dependencies with OAuth configuration failure
        with patch(
            "mcp_atlassian.confluence.client.configure_oauth_session"
        ) as mock_configure_oauth:
            # Configure the mock to return failure for OAuth configuration
            mock_configure_oauth.return_value = False

            # Verify error is raised
            with pytest.raises(
                MCPAtlassianAuthenticationError,
                match="Failed to configure OAuth session",
            ):
                ConfluenceClient(config=config)

    def test_init_with_byo_oauth_empty_token_failed_session_config(self):
        """Test init with BYO OAuth, empty token, and failed session config."""
        # Create a mock BYO OAuth config
        byo_oauth_config = BYOAccessTokenOAuthConfig(
            cloud_id="test-byo-cloud-id",
            access_token="",  # Empty access token
        )

        # Create a Confluence config with BYO OAuth
        config = ConfluenceConfig(
            url="https://test.atlassian.net/wiki",
            auth_type="oauth",
            oauth_config=byo_oauth_config,
        )

        # Mock dependencies with OAuth configuration failure
        # configure_oauth_session might not even be called if token is validated earlier,
        # but if it is, it should fail.
        # For now, assume client init will fail due to invalid config before session setup,
        # or session setup fails because token is invalid.
        # The ConfluenceClient itself should raise error due to invalid oauth_config
        with patch(
            "mcp_atlassian.confluence.client.configure_oauth_session"
        ) as mock_configure_oauth:
            mock_configure_oauth.return_value = False  # Assume it's called and fails
            with pytest.raises(
                MCPAtlassianAuthenticationError,  # Or ValueError depending on where empty token is caught
                # For consistency with Jira, let's assume MCPAtlassianAuthenticationError if session config is attempted
                match="Failed to configure OAuth session",  # This may change if validation is earlier
            ):
                ConfluenceClient(config=config)

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
                ConfluenceClient(config=config)

    def test_from_env_with_standard_oauth(self):
        """Test creating client from env vars with standard OAuth configuration."""
        # Mock environment variables - NO CONFLUENCE_AUTH_TYPE
        env_vars = {
            "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
            "CONFLUENCE_AUTH_TYPE": "oauth",
            "ATLASSIAN_OAUTH_CLIENT_ID": "env-client-id",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "env-client-secret",
            "ATLASSIAN_OAUTH_REDIRECT_URI": "https://example.com/callback",
            "ATLASSIAN_OAUTH_SCOPE": "read:confluence-space.summary",
            "ATLASSIAN_OAUTH_CLOUD_ID": "env-cloud-id",
            "ATLASSIAN_OAUTH_ACCESS_TOKEN": "env-access-token",  # Needed by OAuthConfig
            "ATLASSIAN_OAUTH_REFRESH_TOKEN": "env-refresh-token",  # Needed by OAuthConfig
        }

        # Mock OAuthConfig instance
        mock_standard_oauth_config = OAuthConfig(
            client_id="env-client-id",
            client_secret="env-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:confluence-space.summary",
            cloud_id="env-cloud-id",
            access_token="env-access-token",
            refresh_token="env-refresh-token",
            expires_at=9999999999.0,
        )

        with (
            patch.dict(os.environ, env_vars, clear=True),  # Clear other env vars
            patch(
                "mcp_atlassian.confluence.config.get_oauth_config_from_env",  # Patch the correct utility
                return_value=mock_standard_oauth_config,
            ),
            patch.object(
                OAuthConfig,
                "is_token_expired",
                new_callable=PropertyMock,
                return_value=False,
            ) as mock_is_expired_env,
            patch.object(
                mock_standard_oauth_config, "ensure_valid_token", return_value=True
            ) as mock_ensure_valid_env,
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
            client = ConfluenceClient()  # Calls ConfluenceConfig.from_env() internally

            # Verify client was initialized with OAuth
            assert client.config.auth_type == "oauth"
            assert client.config.oauth_config is mock_standard_oauth_config

            # Verify Confluence was initialized correctly
            mock_confluence.assert_called_once()
            conf_kwargs = mock_confluence.call_args[1]
            assert (
                conf_kwargs["url"]
                == f"https://api.atlassian.com/ex/confluence/{mock_standard_oauth_config.cloud_id}"
            )
            assert "session" in conf_kwargs
            assert conf_kwargs["cloud"] is True

            # Verify OAuth session was configured
            mock_configure_oauth.assert_called_once()

    def test_from_env_with_byo_token_oauth(self):
        """Test creating client from env vars with BYO token OAuth config."""
        env_vars = {
            "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
            "ATLASSIAN_OAUTH_ACCESS_TOKEN": "env-byo-access-token",
            "ATLASSIAN_OAUTH_CLOUD_ID": "env-byo-cloud-id",
            # No other OAuth vars needed for BYO if get_oauth_config_from_env handles it
        }

        mock_byo_oauth_config = BYOAccessTokenOAuthConfig(
            cloud_id="env-byo-cloud-id", access_token="env-byo-access-token"
        )

        with (
            patch.dict(os.environ, env_vars, clear=True),
            patch(
                "mcp_atlassian.confluence.config.get_oauth_config_from_env",
                return_value=mock_byo_oauth_config,
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
            client = ConfluenceClient()

            assert client.config.auth_type == "oauth"
            assert client.config.oauth_config is mock_byo_oauth_config
            mock_confluence.assert_called_once()
            conf_kwargs = mock_confluence.call_args[1]
            assert (
                conf_kwargs["url"]
                == f"https://api.atlassian.com/ex/confluence/{mock_byo_oauth_config.cloud_id}"
            )
            mock_configure_oauth.assert_called_once()

    def test_from_env_with_no_oauth_config_found(self):
        """Test client creation from env when no OAuth config is found by the utility."""
        env_vars = {
            "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
            # Deliberately missing other auth variables (basic, token, or complete OAuth)
        }

        with (
            patch.dict(os.environ, env_vars, clear=True),
            patch(
                "mcp_atlassian.confluence.config.get_oauth_config_from_env",
                return_value=None,  # Simulate no OAuth config found by the utility
            ),
        ):
            # ConfluenceConfig.from_env should raise ValueError if no auth can be determined
            with pytest.raises(
                ValueError,
                match="Cloud authentication requires CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN, or OAuth configuration",
            ):
                ConfluenceClient()  # This will call ConfluenceConfig.from_env()
