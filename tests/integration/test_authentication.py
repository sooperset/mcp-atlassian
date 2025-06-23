"""Integration tests for authentication functionality."""

import json
import time
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests
from requests.exceptions import HTTPError

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.oauth import OAuthConfig, configure_oauth_session
from tests.utils.mocks import MockEnvironment


@pytest.mark.integration
class TestOAuthTokenRefreshFlow:
    """Test OAuth token refresh flow with expiration handling."""

    def test_oauth_token_refresh_on_expiration(self):
        """Test automatic token refresh when access token is expired."""
        with MockEnvironment.oauth_env() as oauth_env:
            # Create OAuth config with expired token
            oauth_config = OAuthConfig(
                client_id=oauth_env["ATLASSIAN_OAUTH_CLIENT_ID"],
                client_secret=oauth_env["ATLASSIAN_OAUTH_CLIENT_SECRET"],
                redirect_uri=oauth_env["ATLASSIAN_OAUTH_REDIRECT_URI"],
                scope=oauth_env["ATLASSIAN_OAUTH_SCOPE"],
                cloud_id=oauth_env["ATLASSIAN_OAUTH_CLOUD_ID"],
                access_token="expired-access-token",
                refresh_token="valid-refresh-token",
                expires_at=time.time() - 3600,  # Expired 1 hour ago
            )

            # Mock the token refresh endpoint
            with patch("requests.post") as mock_post:
                mock_response = Mock()
                mock_response.ok = True
                mock_response.json.return_value = {
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                    "expires_in": 3600,
                }
                mock_post.return_value = mock_response

                # Ensure valid token should trigger refresh
                assert oauth_config.is_token_expired is True
                result = oauth_config.ensure_valid_token()

                assert result is True
                assert oauth_config.access_token == "new-access-token"
                assert oauth_config.refresh_token == "new-refresh-token"
                assert oauth_config.expires_at > time.time()

                # Verify the refresh token request
                mock_post.assert_called_once()
                call_args = mock_post.call_args
                assert call_args[0][0] == "https://auth.atlassian.com/oauth/token"
                assert call_args[1]["data"]["grant_type"] == "refresh_token"
                assert call_args[1]["data"]["refresh_token"] == "valid-refresh-token"

    def test_oauth_token_refresh_failure_handling(self):
        """Test handling of token refresh failures."""
        with MockEnvironment.oauth_env() as oauth_env:
            # Create OAuth config with expired token
            oauth_config = OAuthConfig(
                client_id=oauth_env["ATLASSIAN_OAUTH_CLIENT_ID"],
                client_secret=oauth_env["ATLASSIAN_OAUTH_CLIENT_SECRET"],
                redirect_uri=oauth_env["ATLASSIAN_OAUTH_REDIRECT_URI"],
                scope=oauth_env["ATLASSIAN_OAUTH_SCOPE"],
                cloud_id=oauth_env["ATLASSIAN_OAUTH_CLOUD_ID"],
                access_token="expired-access-token",
                refresh_token="invalid-refresh-token",
                expires_at=time.time() - 3600,
            )

            # Mock the token refresh endpoint to fail
            with patch("requests.post") as mock_post:
                mock_response = Mock()
                mock_response.ok = False
                mock_response.raise_for_status.side_effect = HTTPError(
                    "401 Unauthorized"
                )
                mock_post.return_value = mock_response

                # Ensure valid token should fail
                result = oauth_config.ensure_valid_token()
                assert result is False

    def test_oauth_token_expiry_margin(self):
        """Test that tokens are refreshed before actual expiration."""
        with MockEnvironment.oauth_env():
            # Create OAuth config with token expiring in 4 minutes (within margin)
            oauth_config = OAuthConfig(
                client_id="test-client",
                client_secret="test-secret",
                redirect_uri="http://localhost:8080",
                scope="read:jira",
                access_token="almost-expired-token",
                refresh_token="valid-refresh-token",
                expires_at=time.time() + 240,  # 4 minutes from now
            )

            # Token should be considered expired due to margin
            assert oauth_config.is_token_expired is True

            # Create token expiring in 10 minutes (outside margin)
            oauth_config.expires_at = time.time() + 600
            assert oauth_config.is_token_expired is False


@pytest.mark.integration
class TestBasicAuthValidation:
    """Test basic authentication validation against real endpoints."""

    @patch("mcp_atlassian.jira.client.Jira")
    def test_jira_basic_auth_success(self, mock_jira_class):
        """Test successful Jira basic authentication."""
        with MockEnvironment.basic_auth_env() as auth_env:
            # Create mock Jira instance
            mock_jira = MagicMock()
            mock_jira_class.return_value = mock_jira

            # Create Jira client
            config = JiraConfig.from_env()
            client = JiraClient(config)

            # Verify Jira was initialized with correct params
            mock_jira_class.assert_called_once_with(
                url=auth_env["JIRA_URL"],
                username=auth_env["JIRA_USERNAME"],
                password=auth_env["JIRA_API_TOKEN"],
                cloud=True,  # Assuming cloud by default
                verify_ssl=True,
            )

    @patch("mcp_atlassian.confluence.client.Confluence")
    def test_confluence_basic_auth_success(self, mock_confluence_class):
        """Test successful Confluence basic authentication."""
        with MockEnvironment.basic_auth_env() as auth_env:
            # Create mock Confluence instance
            mock_confluence = MagicMock()
            mock_confluence_class.return_value = mock_confluence

            # Create Confluence client
            config = ConfluenceConfig.from_env()
            client = ConfluenceClient(config)

            # Verify Confluence was initialized with correct params
            mock_confluence_class.assert_called_once_with(
                url=auth_env["CONFLUENCE_URL"],
                username=auth_env["CONFLUENCE_USERNAME"],
                password=auth_env["CONFLUENCE_API_TOKEN"],
                cloud=True,
                verify_ssl=True,
            )

    def test_basic_auth_with_invalid_credentials(self):
        """Test basic authentication with invalid credentials."""
        with MockEnvironment.clean_env():
            with patch.dict(
                "os.environ",
                {
                    "JIRA_URL": "https://test.atlassian.net",
                    "JIRA_USERNAME": "invalid@example.com",
                    "JIRA_API_TOKEN": "invalid-token",
                },
            ):
                with patch("mcp_atlassian.jira.client.Jira") as mock_jira_class:
                    # Make Jira constructor raise authentication error
                    mock_jira_class.side_effect = HTTPError("401 Unauthorized")

                    config = JiraConfig.from_env()
                    with pytest.raises(HTTPError):
                        JiraClient(config)


@pytest.mark.integration
class TestPATTokenValidation:
    """Test Personal Access Token (PAT) validation and precedence."""

    @patch("mcp_atlassian.jira.client.Jira")
    def test_jira_pat_token_success(self, mock_jira_class):
        """Test successful Jira PAT authentication."""
        # Clear existing auth env vars first
        with MockEnvironment.clean_env():
            with patch.dict(
                "os.environ",
                {
                    "JIRA_URL": "https://jira.company.com",  # Server URL for PAT
                    "JIRA_PERSONAL_TOKEN": "test-personal-access-token",
                },
            ):
                # Create mock Jira instance
                mock_jira = MagicMock()
                mock_jira_class.return_value = mock_jira

                # Create Jira client
                config = JiraConfig.from_env()
                client = JiraClient(config)

                # Verify Jira was initialized with PAT token
                mock_jira_class.assert_called_once_with(
                    url="https://jira.company.com",
                    token="test-personal-access-token",
                    cloud=False,  # Server instance
                    verify_ssl=True,
                )

    @patch("mcp_atlassian.confluence.client.Confluence")
    def test_confluence_pat_token_success(self, mock_confluence_class):
        """Test successful Confluence PAT authentication."""
        # Clear existing auth env vars first
        with MockEnvironment.clean_env():
            with patch.dict(
                "os.environ",
                {
                    "CONFLUENCE_URL": "https://confluence.company.com",  # Server URL for PAT
                    "CONFLUENCE_PERSONAL_TOKEN": "test-personal-access-token",
                },
            ):
                # Create mock Confluence instance
                mock_confluence = MagicMock()
                mock_confluence_class.return_value = mock_confluence

                # Create Confluence client
                config = ConfluenceConfig.from_env()
                client = ConfluenceClient(config)

                # Verify Confluence was initialized with PAT token
                mock_confluence_class.assert_called_once_with(
                    url="https://confluence.company.com",
                    token="test-personal-access-token",
                    cloud=False,  # Server instance
                    verify_ssl=True,
                )

    def test_pat_token_precedence_over_basic_auth(self):
        """Test that PAT token takes precedence over basic auth when both are present."""
        with MockEnvironment.clean_env():
            with patch.dict(
                "os.environ",
                {
                    "JIRA_URL": "https://jira.company.com",  # Server URL for PAT
                    "JIRA_USERNAME": "user@example.com",
                    "JIRA_API_TOKEN": "basic-api-token",
                    "JIRA_PERSONAL_TOKEN": "personal-access-token",
                },
            ):
                config = JiraConfig.from_env()
                assert config.auth_type == "pat"
                assert config.personal_token == "personal-access-token"


@pytest.mark.integration
class TestAuthenticationFailureRecovery:
    """Test authentication failure recovery patterns."""

    def test_oauth_to_basic_auth_fallback(self):
        """Test fallback from OAuth to basic auth when OAuth fails."""
        # Set up environment with both OAuth and basic auth but incomplete OAuth
        with MockEnvironment.clean_env():
            # Mock token loading to return empty (no stored tokens)
            with patch(
                "mcp_atlassian.utils.oauth.OAuthConfig.load_tokens", return_value={}
            ):
                with patch.dict(
                    "os.environ",
                    {
                        # OAuth config - incomplete (missing cloud_id)
                        "ATLASSIAN_OAUTH_CLIENT_ID": "test-client",
                        "ATLASSIAN_OAUTH_CLIENT_SECRET": "test-secret",
                        "ATLASSIAN_OAUTH_REDIRECT_URI": "http://localhost:8080",
                        "ATLASSIAN_OAUTH_SCOPE": "read:jira",
                        # Basic auth config
                        "JIRA_URL": "https://test.atlassian.net",
                        "JIRA_USERNAME": "user@example.com",
                        "JIRA_API_TOKEN": "api-token",
                    },
                ):
                    # Without cloud_id, OAuth config is incomplete and should fallback to basic
                    config = JiraConfig.from_env()
                    assert config.auth_type == "basic"  # Falls back to basic auth

                    # Now add cloud_id to complete OAuth config
                    with patch.dict(
                        "os.environ", {"ATLASSIAN_OAUTH_CLOUD_ID": "test-cloud-id"}
                    ):
                        config = JiraConfig.from_env()
                        assert config.auth_type == "oauth"

                        # OAuth should fail without valid tokens
                        with pytest.raises(
                            MCPAtlassianAuthenticationError,
                            match="Failed to configure OAuth session",
                        ):
                            JiraClient(config)

    def test_authentication_retry_on_401(self):
        """Test retry behavior on 401 authentication errors."""
        with MockEnvironment.oauth_env():
            oauth_config = OAuthConfig(
                client_id="test-client",
                client_secret="test-secret",
                redirect_uri="http://localhost:8080",
                scope="read:jira",
                cloud_id="test-cloud",
                access_token="expired-token",
                refresh_token="valid-refresh-token",
                expires_at=time.time() - 3600,
            )

            session = requests.Session()

            # Mock token refresh to succeed
            with patch.object(oauth_config, "refresh_access_token") as mock_refresh:
                mock_refresh.return_value = True
                oauth_config.access_token = "new-token"

                result = configure_oauth_session(session, oauth_config)
                assert result is True
                assert session.headers["Authorization"] == "Bearer new-token"
                mock_refresh.assert_called_once()


@pytest.mark.integration
class TestTokenExpirationAndRetry:
    """Test token expiration and automatic retry."""

    def test_automatic_token_refresh_in_session(self):
        """Test that expired tokens are automatically refreshed in session."""
        with MockEnvironment.oauth_env():
            # Create OAuth config with soon-to-expire token
            oauth_config = OAuthConfig(
                client_id="test-client",
                client_secret="test-secret",
                redirect_uri="http://localhost:8080",
                scope="read:jira",
                cloud_id="test-cloud",
                access_token="expiring-token",
                refresh_token="valid-refresh-token",
                expires_at=time.time() + 100,  # Expires in 100 seconds (within margin)
            )

            session = requests.Session()

            # Mock the refresh token call
            with patch("requests.post") as mock_post:
                mock_response = Mock()
                mock_response.ok = True
                mock_response.json.return_value = {
                    "access_token": "refreshed-token",
                    "expires_in": 3600,
                }
                mock_post.return_value = mock_response

                # Configure session should refresh the token
                result = configure_oauth_session(session, oauth_config)
                assert result is True
                assert oauth_config.access_token == "refreshed-token"
                assert session.headers["Authorization"] == "Bearer refreshed-token"

    def test_token_storage_and_retrieval(self):
        """Test token storage in keyring and retrieval."""
        client_id = "test-client-storage"

        # Mock keyring operations
        with (
            patch("keyring.set_password") as mock_set,
            patch("keyring.get_password") as mock_get,
        ):
            # Create OAuth config and save tokens
            oauth_config = OAuthConfig(
                client_id=client_id,
                client_secret="test-secret",
                redirect_uri="http://localhost:8080",
                scope="read:jira",
                cloud_id="test-cloud",
                access_token="stored-token",
                refresh_token="stored-refresh",
                expires_at=time.time() + 3600,
            )

            # Save tokens
            oauth_config._save_tokens()

            # Verify keyring was called
            mock_set.assert_called_once()
            service_name, username, token_json = mock_set.call_args[0]
            assert service_name == "mcp-atlassian-oauth"
            assert username == f"oauth-{client_id}"

            # Parse stored token data
            stored_data = json.loads(token_json)
            assert stored_data["access_token"] == "stored-token"
            assert stored_data["refresh_token"] == "stored-refresh"
            assert stored_data["cloud_id"] == "test-cloud"

            # Test token retrieval
            mock_get.return_value = token_json
            loaded_data = OAuthConfig.load_tokens(client_id)
            assert loaded_data["access_token"] == "stored-token"
            assert loaded_data["refresh_token"] == "stored-refresh"


@pytest.mark.integration
class TestMixedAuthenticationScenarios:
    """Test mixed authentication scenarios and fallback patterns."""

    def test_oauth_with_direct_access_token(self):
        """Test OAuth config with only access token (no refresh token)."""
        session = requests.Session()

        # Create OAuth config with only access token
        oauth_config = OAuthConfig(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uri="http://localhost:8080",
            scope="read:jira",
            access_token="direct-access-token",
            # No refresh_token, no expires_at
        )

        # Should use token directly without refresh attempt
        result = configure_oauth_session(session, oauth_config)
        assert result is True
        assert session.headers["Authorization"] == "Bearer direct-access-token"

    def test_environment_detection_priority(self):
        """Test authentication method detection priority from environment."""
        # Test with all auth methods present - OAuth should take precedence
        with MockEnvironment.clean_env():
            with patch.dict(
                "os.environ",
                {
                    # OAuth
                    "ATLASSIAN_OAUTH_CLIENT_ID": "oauth-client",
                    "ATLASSIAN_OAUTH_CLIENT_SECRET": "oauth-secret",
                    "ATLASSIAN_OAUTH_REDIRECT_URI": "http://localhost:8080",
                    "ATLASSIAN_OAUTH_SCOPE": "read:jira",
                    "ATLASSIAN_OAUTH_CLOUD_ID": "test-cloud-id",
                    # PAT
                    "JIRA_PERSONAL_TOKEN": "personal-token",
                    # Basic
                    "JIRA_URL": "https://test.atlassian.net",
                    "JIRA_USERNAME": "user@example.com",
                    "JIRA_API_TOKEN": "api-token",
                },
            ):
                config = JiraConfig.from_env()
                assert config.auth_type == "oauth"

        # Test with PAT and basic - PAT should take precedence (for server)
        with MockEnvironment.clean_env():
            with patch.dict(
                "os.environ",
                {
                    "JIRA_URL": "https://jira.company.com",  # Server URL
                    "JIRA_PERSONAL_TOKEN": "personal-token",
                    "JIRA_USERNAME": "user@example.com",
                    "JIRA_API_TOKEN": "api-token",
                },
            ):
                config = JiraConfig.from_env()
                assert config.auth_type == "pat"

        # Test with only basic auth
        with MockEnvironment.clean_env():
            with patch.dict(
                "os.environ",
                {
                    "JIRA_URL": "https://test.atlassian.net",
                    "JIRA_USERNAME": "user@example.com",
                    "JIRA_API_TOKEN": "api-token",
                },
            ):
                config = JiraConfig.from_env()
                assert config.auth_type == "basic"

    def test_cloud_vs_server_authentication(self):
        """Test authentication differences between cloud and server instances."""
        # Cloud instance (default)
        with MockEnvironment.clean_env():
            with patch.dict(
                "os.environ",
                {
                    "JIRA_URL": "https://example.atlassian.net",
                    "JIRA_USERNAME": "user@example.com",
                    "JIRA_API_TOKEN": "api-token",
                },
            ):
                config = JiraConfig.from_env()
                assert config.is_cloud is True

        # Server instance
        with MockEnvironment.clean_env():
            with patch.dict(
                "os.environ",
                {
                    "JIRA_URL": "https://jira.company.com",
                    "JIRA_USERNAME": "user@example.com",
                    "JIRA_API_TOKEN": "api-token",
                },
            ):
                config = JiraConfig.from_env()
                assert config.is_cloud is False


@pytest.mark.integration
class TestJiraConfluenceAuthFlows:
    """Test authentication flows for both Jira and Confluence services."""

    @patch("mcp_atlassian.confluence.client.Confluence")
    @patch("mcp_atlassian.jira.client.Jira")
    def test_shared_oauth_config_both_services(
        self, mock_jira_class, mock_confluence_class
    ):
        """Test that both services can share the same OAuth configuration."""
        with MockEnvironment.oauth_env():
            # Mock cloud ID retrieval
            with patch("requests.get") as mock_get:
                mock_response = Mock()
                mock_response.ok = True
                mock_response.json.return_value = [{"id": "test-cloud-id"}]
                mock_get.return_value = mock_response

                # Create OAuth config
                oauth_config = OAuthConfig.from_env()
                oauth_config.access_token = "shared-token"
                oauth_config.cloud_id = "test-cloud-id"

                # Create both clients with same OAuth config
                jira_config = JiraConfig(
                    url="https://test.atlassian.net",
                    auth_type="oauth",
                    oauth_config=oauth_config,
                )
                confluence_config = ConfluenceConfig(
                    url="https://test.atlassian.net/wiki",
                    auth_type="oauth",
                    oauth_config=oauth_config,
                )

                # Initialize clients
                jira_client = JiraClient(jira_config)
                confluence_client = ConfluenceClient(confluence_config)

                # Verify both were initialized with OAuth URLs
                jira_url = mock_jira_class.call_args[1]["url"]
                confluence_url = mock_confluence_class.call_args[1]["url"]

                assert jira_url == "https://api.atlassian.com/ex/jira/test-cloud-id"
                assert (
                    confluence_url
                    == "https://api.atlassian.com/ex/confluence/test-cloud-id"
                )

    def test_service_specific_auth_override(self):
        """Test that service-specific auth overrides shared configuration."""
        with MockEnvironment.clean_env():
            # Mock token loading to return empty (no stored tokens)
            with patch(
                "mcp_atlassian.utils.oauth.OAuthConfig.load_tokens", return_value={}
            ):
                # Test case 1: Only service-specific auth (no OAuth config)
                with patch.dict(
                    "os.environ",
                    {
                        # Jira-specific PAT for server
                        "JIRA_URL": "https://jira.company.com",
                        "JIRA_PERSONAL_TOKEN": "jira-pat-token",
                        # Confluence basic auth
                        "CONFLUENCE_URL": "https://confluence.atlassian.net",
                        "CONFLUENCE_USERNAME": "conf-user@example.com",
                        "CONFLUENCE_API_TOKEN": "conf-api-token",
                    },
                ):
                    # Jira uses PAT (server instance)
                    jira_config = JiraConfig.from_env()
                    assert jira_config.auth_type == "pat"

                    # Confluence uses basic auth (cloud instance)
                    confluence_config = ConfluenceConfig.from_env()
                    assert confluence_config.auth_type == "basic"

                # Test case 2: OAuth takes precedence when fully configured
                with patch.dict(
                    "os.environ",
                    {
                        # Shared OAuth config
                        "ATLASSIAN_OAUTH_CLIENT_ID": "shared-client",
                        "ATLASSIAN_OAUTH_CLIENT_SECRET": "shared-secret",
                        "ATLASSIAN_OAUTH_REDIRECT_URI": "http://localhost:8080",
                        "ATLASSIAN_OAUTH_SCOPE": "read:jira read:confluence",
                        "ATLASSIAN_OAUTH_CLOUD_ID": "test-cloud-id",
                        # Service-specific auth also present
                        "JIRA_URL": "https://jira.company.com",
                        "JIRA_USERNAME": "jira-user@example.com",
                        "JIRA_API_TOKEN": "jira-token",
                        "CONFLUENCE_URL": "https://confluence.atlassian.net",
                    },
                ):
                    # OAuth takes precedence for both when cloud_id is present
                    jira_config = JiraConfig.from_env()
                    assert jira_config.auth_type == "oauth"

                    confluence_config = ConfluenceConfig.from_env()
                    assert confluence_config.auth_type == "oauth"

    def test_ssl_and_proxy_with_authentication(self):
        """Test SSL verification and proxy settings work with authentication."""
        with MockEnvironment.clean_env():
            with patch.dict(
                "os.environ",
                {
                    "JIRA_URL": "https://test.atlassian.net",
                    "JIRA_USERNAME": "user@example.com",
                    "JIRA_API_TOKEN": "api-token",
                    "JIRA_SSL_VERIFY": "false",
                    "HTTPS_PROXY": "http://proxy.company.com:8080",
                },
            ):
                config = JiraConfig.from_env()
                assert config.ssl_verify is False
                assert config.https_proxy == "http://proxy.company.com:8080"

                with patch("mcp_atlassian.jira.client.Jira") as mock_jira:
                    client = JiraClient(config)
                    # Verify SSL verification was disabled
                    mock_jira.assert_called_with(
                        url="https://test.atlassian.net",
                        username="user@example.com",
                        password="api-token",
                        cloud=True,
                        verify_ssl=False,
                    )
