"""Unit tests for server dependencies module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Context
from starlette.requests import Request

from mcp_atlassian.confluence import ConfluenceConfig, ConfluenceFetcher
from mcp_atlassian.jira import JiraConfig, JiraFetcher
from mcp_atlassian.servers.context import MainAppContext
from mcp_atlassian.servers.dependencies import (
    _create_user_config_for_fetcher,
    get_confluence_fetcher,
    get_jira_fetcher,
)
from mcp_atlassian.utils.oauth import OAuthConfig

# Configure pytest for async tests
pytestmark = pytest.mark.anyio


@pytest.fixture
def mock_jira_config():
    """Create a mock JiraConfig instance."""
    return JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="test_username",
        api_token="test_token",
        ssl_verify=True,
        http_proxy=None,
        https_proxy=None,
        no_proxy=None,
        socks_proxy=None,
        projects_filter=["TEST"],
    )


@pytest.fixture
def mock_confluence_config():
    """Create a mock ConfluenceConfig instance."""
    return ConfluenceConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="test_username",
        api_token="test_token",
        ssl_verify=True,
        http_proxy=None,
        https_proxy=None,
        no_proxy=None,
        socks_proxy=None,
        spaces_filter=["TEST"],
    )


@pytest.fixture
def mock_oauth_config():
    """Create a mock OAuthConfig instance."""
    return OAuthConfig(
        client_id="test-client-id",
        client_secret="test-client-secret",
        redirect_uri="https://example.com/callback",
        scope="read:jira-work write:jira-work",
        cloud_id="test-cloud-id",
        access_token="global-access-token",
        refresh_token="test-refresh-token",
        expires_at=9999999999.0,
    )


@pytest.fixture
def mock_jira_config_with_oauth(mock_oauth_config):
    """Create a mock JiraConfig instance with OAuth."""
    return JiraConfig(
        url="https://test.atlassian.net",
        auth_type="oauth",
        oauth_config=mock_oauth_config,
        ssl_verify=True,
        http_proxy=None,
        https_proxy=None,
        no_proxy=None,
        socks_proxy=None,
        projects_filter=["TEST"],
    )


@pytest.fixture
def mock_confluence_config_with_oauth(mock_oauth_config):
    """Create a mock ConfluenceConfig instance with OAuth."""
    return ConfluenceConfig(
        url="https://test.atlassian.net",
        auth_type="oauth",
        oauth_config=mock_oauth_config,
        ssl_verify=True,
        http_proxy=None,
        https_proxy=None,
        no_proxy=None,
        socks_proxy=None,
        spaces_filter=["TEST"],
    )


@pytest.fixture
def mock_context():
    """Create a mock Context instance."""
    context = MagicMock(spec=Context)
    context.request_context = MagicMock()
    context.request_context.lifespan_context = {}
    return context


@pytest.fixture
def mock_request():
    """Create a mock Request instance."""
    request = MagicMock(spec=Request)
    request.url = "https://test.example.com/api"
    request.state = MagicMock()
    return request


class TestCreateUserConfigForFetcher:
    """Tests for _create_user_config_for_fetcher function."""

    def test_create_jira_config_with_oauth(self, mock_jira_config_with_oauth):
        """Test creating user-specific JiraConfig with OAuth credentials."""
        credentials = {
            "user_email_context": "user@example.com",
            "oauth_access_token": "user-access-token",
        }

        result = _create_user_config_for_fetcher(
            base_config=mock_jira_config_with_oauth,
            auth_type="oauth",
            credentials=credentials,
        )

        assert isinstance(result, JiraConfig)
        assert result.url == mock_jira_config_with_oauth.url
        assert result.auth_type == "oauth"
        assert result.username == "user@example.com"
        assert result.api_token is None
        assert result.personal_token is None
        assert result.oauth_config is not None
        assert result.oauth_config.access_token == "user-access-token"
        assert result.oauth_config.cloud_id == "test-cloud-id"
        assert result.projects_filter == ["TEST"]

    def test_create_confluence_config_with_oauth(
        self, mock_confluence_config_with_oauth
    ):
        """Test creating user-specific ConfluenceConfig with OAuth credentials."""
        credentials = {
            "user_email_context": "user@example.com",
            "oauth_access_token": "user-access-token",
        }

        result = _create_user_config_for_fetcher(
            base_config=mock_confluence_config_with_oauth,
            auth_type="oauth",
            credentials=credentials,
        )

        assert isinstance(result, ConfluenceConfig)
        assert result.url == mock_confluence_config_with_oauth.url
        assert result.auth_type == "oauth"
        assert result.username == "user@example.com"
        assert result.api_token is None
        assert result.personal_token is None
        assert result.oauth_config is not None
        assert result.oauth_config.access_token == "user-access-token"
        assert result.oauth_config.cloud_id == "test-cloud-id"
        assert result.spaces_filter == ["TEST"]

    def test_create_jira_config_with_pat(self, mock_jira_config):
        """Test creating user-specific JiraConfig with PAT credentials."""
        credentials = {
            "user_email_context": "user@example.com",
            "personal_access_token": "user-pat-token",
        }

        result = _create_user_config_for_fetcher(
            base_config=mock_jira_config,
            auth_type="pat",
            credentials=credentials,
        )

        assert isinstance(result, JiraConfig)
        assert result.url == mock_jira_config.url
        assert result.auth_type == "pat"
        assert result.username is None
        assert result.api_token is None
        assert result.personal_token == "user-pat-token"
        assert result.oauth_config is None
        assert result.projects_filter == ["TEST"]

    def test_create_confluence_config_with_pat(self, mock_confluence_config):
        """Test creating user-specific ConfluenceConfig with PAT credentials."""
        credentials = {
            "user_email_context": "user@example.com",
            "personal_access_token": "user-pat-token",
        }

        result = _create_user_config_for_fetcher(
            base_config=mock_confluence_config,
            auth_type="pat",
            credentials=credentials,
        )

        assert isinstance(result, ConfluenceConfig)
        assert result.url == mock_confluence_config.url
        assert result.auth_type == "pat"
        assert result.username is None
        assert result.api_token is None
        assert result.personal_token == "user-pat-token"
        assert result.oauth_config is None
        assert result.spaces_filter == ["TEST"]

    def test_unsupported_auth_type(self, mock_jira_config):
        """Test error handling for unsupported auth types."""
        credentials = {"user_email_context": "user@example.com"}

        with pytest.raises(ValueError, match="Unsupported auth_type 'invalid'"):
            _create_user_config_for_fetcher(
                base_config=mock_jira_config,
                auth_type="invalid",
                credentials=credentials,
            )

    def test_missing_oauth_access_token(self, mock_jira_config_with_oauth):
        """Test error handling for missing OAuth access token."""
        credentials = {"user_email_context": "user@example.com"}

        with pytest.raises(
            ValueError, match="OAuth access token missing in credentials"
        ):
            _create_user_config_for_fetcher(
                base_config=mock_jira_config_with_oauth,
                auth_type="oauth",
                credentials=credentials,
            )

    def test_missing_pat_token(self, mock_jira_config):
        """Test error handling for missing PAT token."""
        credentials = {"user_email_context": "user@example.com"}

        with pytest.raises(ValueError, match="PAT missing in credentials"):
            _create_user_config_for_fetcher(
                base_config=mock_jira_config,
                auth_type="pat",
                credentials=credentials,
            )

    def test_missing_oauth_config(self, mock_jira_config):
        """Test error handling for missing OAuth config when auth_type is oauth."""
        credentials = {
            "user_email_context": "user@example.com",
            "oauth_access_token": "user-access-token",
        }

        with pytest.raises(ValueError, match="Global OAuth config.*is missing"):
            _create_user_config_for_fetcher(
                base_config=mock_jira_config,
                auth_type="oauth",
                credentials=credentials,
            )

    def test_unsupported_base_config_type(self):
        """Test error handling for unsupported base config types."""

        # Create a mock object that has the required attributes but wrong type
        class UnsupportedConfig:
            def __init__(self):
                self.url = "https://test.atlassian.net"
                self.ssl_verify = True
                self.http_proxy = None
                self.https_proxy = None
                self.no_proxy = None
                self.socks_proxy = None

        base_config = UnsupportedConfig()
        credentials = {
            "user_email_context": "user@example.com",
            "personal_access_token": "test-token",
        }

        with pytest.raises(TypeError, match="Unsupported base_config type"):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type="pat",
                credentials=credentials,
            )


class TestGetJiraFetcher:
    """Tests for get_jira_fetcher function."""

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_http_context_with_cached_fetcher(
        self, mock_jira_fetcher_class, mock_get_http_request, mock_context, mock_request
    ):
        """Test returning cached JiraFetcher from request state."""
        cached_fetcher = MagicMock(spec=JiraFetcher)
        mock_request.state.jira_fetcher = cached_fetcher
        mock_get_http_request.return_value = mock_request

        result = await get_jira_fetcher(mock_context)

        assert result == cached_fetcher
        mock_jira_fetcher_class.assert_not_called()

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_http_context_with_oauth_user_token(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config_with_oauth,
        mock_confluence_config_with_oauth,
    ):
        """Test creating user-specific JiraFetcher with OAuth token."""
        # Setup request state
        mock_request.state.jira_fetcher = None
        mock_request.state.user_atlassian_auth_type = "oauth"
        mock_request.state.user_atlassian_token = "user-oauth-token"
        mock_request.state.user_atlassian_email = "user@example.com"
        mock_get_http_request.return_value = mock_request

        # Setup context with OAuth configs
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config_with_oauth,
            full_confluence_config=mock_confluence_config_with_oauth,
            read_only=False,
            enabled_tools=["jira_get_issue"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher
        mock_fetcher = MagicMock(spec=JiraFetcher)
        mock_fetcher.get_current_user_account_id.return_value = "test-account-id"
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.jira_fetcher == mock_fetcher
        mock_jira_fetcher_class.assert_called_once()

        # Verify the config passed to JiraFetcher
        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.auth_type == "oauth"
        assert called_config.oauth_config.access_token == "user-oauth-token"

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_http_context_with_pat_user_token(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config,
        mock_confluence_config,
    ):
        """Test creating user-specific JiraFetcher with PAT token."""
        # Setup request state
        mock_request.state.jira_fetcher = None
        mock_request.state.user_atlassian_auth_type = "pat"
        mock_request.state.user_atlassian_token = "user-pat-token"
        mock_request.state.user_atlassian_email = "user@example.com"
        mock_get_http_request.return_value = mock_request

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config,
            full_confluence_config=mock_confluence_config,
            read_only=False,
            enabled_tools=["jira_get_issue"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher
        mock_fetcher = MagicMock(spec=JiraFetcher)
        mock_fetcher.get_current_user_account_id.return_value = "test-account-id"
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.jira_fetcher == mock_fetcher
        mock_jira_fetcher_class.assert_called_once()

        # Verify the config passed to JiraFetcher
        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.auth_type == "pat"
        assert called_config.personal_token == "user-pat-token"

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_http_context_fallback_to_global(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config,
        mock_confluence_config,
    ):
        """Test fallback to global JiraFetcher when no user token."""
        # Setup request state without user tokens
        mock_request.state.jira_fetcher = None
        mock_request.state.user_atlassian_auth_type = None
        mock_get_http_request.return_value = mock_request

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config,
            full_confluence_config=mock_confluence_config,
            read_only=False,
            enabled_tools=["jira_get_issue"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher
        mock_fetcher = MagicMock(spec=JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        mock_jira_fetcher_class.assert_called_once_with(
            config=mock_app_context.full_jira_config
        )

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_non_http_context_global_fallback(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_jira_config,
        mock_confluence_config,
    ):
        """Test global fallback when not in HTTP context."""
        # Simulate RuntimeError when getting HTTP request
        mock_get_http_request.side_effect = RuntimeError("No HTTP context")

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config,
            full_confluence_config=mock_confluence_config,
            read_only=False,
            enabled_tools=["jira_get_issue"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher
        mock_fetcher = MagicMock(spec=JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        mock_jira_fetcher_class.assert_called_once_with(
            config=mock_app_context.full_jira_config
        )

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    async def test_missing_global_config(self, mock_get_http_request, mock_context):
        """Test error handling when global config is missing."""
        mock_get_http_request.side_effect = RuntimeError("No HTTP context")
        mock_context.request_context.lifespan_context = {}

        with pytest.raises(ValueError, match="Jira client \\(fetcher\\) not available"):
            await get_jira_fetcher(mock_context)

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    async def test_empty_user_token(
        self,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config,
        mock_confluence_config,
    ):
        """Test error handling for empty user token."""
        # Setup request state with empty token
        mock_request.state.jira_fetcher = None
        mock_request.state.user_atlassian_auth_type = "oauth"
        mock_request.state.user_atlassian_token = ""
        mock_get_http_request.return_value = mock_request

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config,
            full_confluence_config=mock_confluence_config,
            read_only=False,
            enabled_tools=["jira_get_issue"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        with pytest.raises(
            ValueError, match="User Atlassian token found in state but is empty"
        ):
            await get_jira_fetcher(mock_context)

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_fetcher_validation_failure(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config,
        mock_confluence_config,
    ):
        """Test error handling when fetcher validation fails."""
        # Setup request state
        mock_request.state.jira_fetcher = None
        mock_request.state.user_atlassian_auth_type = "pat"
        mock_request.state.user_atlassian_token = "invalid-token"
        mock_request.state.user_atlassian_email = "user@example.com"
        mock_get_http_request.return_value = mock_request

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config,
            full_confluence_config=mock_confluence_config,
            read_only=False,
            enabled_tools=["jira_get_issue"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher to fail validation
        mock_fetcher = MagicMock(spec=JiraFetcher)
        mock_fetcher.get_current_user_account_id.side_effect = Exception(
            "Invalid token"
        )
        mock_jira_fetcher_class.return_value = mock_fetcher

        with pytest.raises(
            ValueError, match="Invalid user Jira token or configuration"
        ):
            await get_jira_fetcher(mock_context)

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    async def test_missing_lifespan_context(
        self, mock_get_http_request, mock_context, mock_request
    ):
        """Test error handling when lifespan context is missing."""
        # Setup request state
        mock_request.state.jira_fetcher = None
        mock_request.state.user_atlassian_auth_type = "oauth"
        mock_request.state.user_atlassian_token = "user-token"
        mock_get_http_request.return_value = mock_request

        # Setup context without app_lifespan_context
        mock_context.request_context.lifespan_context = {}

        with pytest.raises(
            ValueError,
            match="Jira global configuration.*is not available from lifespan context",
        ):
            await get_jira_fetcher(mock_context)


class TestGetConfluenceFetcher:
    """Tests for get_confluence_fetcher function."""

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_http_context_with_cached_fetcher(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
    ):
        """Test returning cached ConfluenceFetcher from request state."""
        cached_fetcher = MagicMock(spec=ConfluenceFetcher)
        mock_request.state.confluence_fetcher = cached_fetcher
        mock_get_http_request.return_value = mock_request

        result = await get_confluence_fetcher(mock_context)

        assert result == cached_fetcher
        mock_confluence_fetcher_class.assert_not_called()

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_http_context_with_oauth_user_token(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config_with_oauth,
        mock_confluence_config_with_oauth,
    ):
        """Test creating user-specific ConfluenceFetcher with OAuth token."""
        # Setup request state
        mock_request.state.confluence_fetcher = None
        mock_request.state.user_atlassian_auth_type = "oauth"
        mock_request.state.user_atlassian_token = "user-oauth-token"
        mock_request.state.user_atlassian_email = "user@example.com"
        mock_get_http_request.return_value = mock_request

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config_with_oauth,
            full_confluence_config=mock_confluence_config_with_oauth,
            read_only=False,
            enabled_tools=["confluence_get_page"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher
        mock_fetcher = MagicMock(spec=ConfluenceFetcher)
        mock_fetcher.get_current_user_info.return_value = {
            "email": "user@example.com",
            "displayName": "Test User",
        }
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.confluence_fetcher == mock_fetcher
        mock_confluence_fetcher_class.assert_called_once()

        # Verify the config passed to ConfluenceFetcher
        called_config = mock_confluence_fetcher_class.call_args[1]["config"]
        assert called_config.auth_type == "oauth"
        assert called_config.oauth_config.access_token == "user-oauth-token"

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_http_context_with_pat_user_token(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config,
        mock_confluence_config,
    ):
        """Test creating user-specific ConfluenceFetcher with PAT token."""
        # Setup request state
        mock_request.state.confluence_fetcher = None
        mock_request.state.user_atlassian_auth_type = "pat"
        mock_request.state.user_atlassian_token = "user-pat-token"
        mock_request.state.user_atlassian_email = (
            None  # PAT may not have email initially
        )
        mock_get_http_request.return_value = mock_request

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config,
            full_confluence_config=mock_confluence_config,
            read_only=False,
            enabled_tools=["confluence_get_page"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher
        mock_fetcher = MagicMock(spec=ConfluenceFetcher)
        mock_fetcher.get_current_user_info.return_value = {
            "email": "derived@example.com",
            "displayName": "Test User",
        }
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.confluence_fetcher == mock_fetcher
        assert mock_request.state.user_atlassian_email == "derived@example.com"
        mock_confluence_fetcher_class.assert_called_once()

        # Verify the config passed to ConfluenceFetcher
        called_config = mock_confluence_fetcher_class.call_args[1]["config"]
        assert called_config.auth_type == "pat"
        assert called_config.personal_token == "user-pat-token"

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_http_context_fallback_to_global(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config,
        mock_confluence_config,
    ):
        """Test fallback to global ConfluenceFetcher when no user token."""
        # Setup request state without user tokens
        mock_request.state.confluence_fetcher = None
        mock_request.state.user_atlassian_auth_type = None
        mock_get_http_request.return_value = mock_request

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config,
            full_confluence_config=mock_confluence_config,
            read_only=False,
            enabled_tools=["confluence_get_page"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher
        mock_fetcher = MagicMock(spec=ConfluenceFetcher)
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        mock_confluence_fetcher_class.assert_called_once_with(
            config=mock_app_context.full_confluence_config
        )

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_non_http_context_global_fallback(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_jira_config,
        mock_confluence_config,
    ):
        """Test global fallback when not in HTTP context."""
        # Simulate RuntimeError when getting HTTP request
        mock_get_http_request.side_effect = RuntimeError("No HTTP context")

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config,
            full_confluence_config=mock_confluence_config,
            read_only=False,
            enabled_tools=["confluence_get_page"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher
        mock_fetcher = MagicMock(spec=ConfluenceFetcher)
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        mock_confluence_fetcher_class.assert_called_once_with(
            config=mock_app_context.full_confluence_config
        )

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    async def test_missing_global_config(self, mock_get_http_request, mock_context):
        """Test error handling when global config is missing."""
        mock_get_http_request.side_effect = RuntimeError("No HTTP context")
        mock_context.request_context.lifespan_context = {}

        with pytest.raises(
            ValueError, match="Confluence client \\(fetcher\\) not available"
        ):
            await get_confluence_fetcher(mock_context)

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    async def test_empty_user_token(
        self,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config,
        mock_confluence_config,
    ):
        """Test error handling for empty user token."""
        # Setup request state with empty token
        mock_request.state.confluence_fetcher = None
        mock_request.state.user_atlassian_auth_type = "oauth"
        mock_request.state.user_atlassian_token = ""
        mock_get_http_request.return_value = mock_request

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config,
            full_confluence_config=mock_confluence_config,
            read_only=False,
            enabled_tools=["confluence_get_page"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        with pytest.raises(
            ValueError, match="User Atlassian token found in state but is empty"
        ):
            await get_confluence_fetcher(mock_context)

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_fetcher_validation_failure(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config,
        mock_confluence_config,
    ):
        """Test error handling when fetcher validation fails."""
        # Setup request state
        mock_request.state.confluence_fetcher = None
        mock_request.state.user_atlassian_auth_type = "pat"
        mock_request.state.user_atlassian_token = "invalid-token"
        mock_request.state.user_atlassian_email = "user@example.com"
        mock_get_http_request.return_value = mock_request

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config,
            full_confluence_config=mock_confluence_config,
            read_only=False,
            enabled_tools=["confluence_get_page"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher to fail validation
        mock_fetcher = MagicMock(spec=ConfluenceFetcher)
        mock_fetcher.get_current_user_info.side_effect = Exception("Invalid token")
        mock_confluence_fetcher_class.return_value = mock_fetcher

        with pytest.raises(
            ValueError, match="Invalid user Confluence token or configuration"
        ):
            await get_confluence_fetcher(mock_context)

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    async def test_missing_lifespan_context(
        self, mock_get_http_request, mock_context, mock_request
    ):
        """Test error handling when lifespan context is missing."""
        # Setup request state
        mock_request.state.confluence_fetcher = None
        mock_request.state.user_atlassian_auth_type = "oauth"
        mock_request.state.user_atlassian_token = "user-token"
        mock_get_http_request.return_value = mock_request

        # Setup context without app_lifespan_context
        mock_context.request_context.lifespan_context = {}

        with pytest.raises(
            ValueError,
            match="Confluence global configuration.*is not available from lifespan context",  # noqa: E501
        ):
            await get_confluence_fetcher(mock_context)

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_email_derivation_without_existing_email(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config,
        mock_confluence_config,
    ):
        """Test email derivation when user email is not present but returns email."""
        # Setup request state without user email
        mock_request.state.confluence_fetcher = None
        mock_request.state.user_atlassian_auth_type = "pat"
        mock_request.state.user_atlassian_token = "user-pat-token"
        mock_request.state.user_atlassian_email = None
        mock_get_http_request.return_value = mock_request

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config,
            full_confluence_config=mock_confluence_config,
            read_only=False,
            enabled_tools=["confluence_get_page"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher to return user info with email
        mock_fetcher = MagicMock(spec=ConfluenceFetcher)
        mock_fetcher.get_current_user_info.return_value = {
            "email": "derived@example.com",
            "displayName": "Test User",
        }
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.confluence_fetcher == mock_fetcher
        # Verify email was derived and set on request state
        assert mock_request.state.user_atlassian_email == "derived@example.com"

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_no_email_derivation_when_existing_email(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        mock_jira_config_with_oauth,
        mock_confluence_config_with_oauth,
    ):
        """Test that email derivation doesn't override existing email."""
        # Setup request state with existing user email
        mock_request.state.confluence_fetcher = None
        mock_request.state.user_atlassian_auth_type = "oauth"
        mock_request.state.user_atlassian_token = "user-oauth-token"
        mock_request.state.user_atlassian_email = "existing@example.com"
        mock_get_http_request.return_value = mock_request

        # Setup context
        mock_app_context = MainAppContext(
            full_jira_config=mock_jira_config_with_oauth,
            full_confluence_config=mock_confluence_config_with_oauth,
            read_only=False,
            enabled_tools=["confluence_get_page"],
        )
        mock_context.request_context.lifespan_context = {
            "app_lifespan_context": mock_app_context
        }

        # Setup mock fetcher to return different email
        mock_fetcher = MagicMock(spec=ConfluenceFetcher)
        mock_fetcher.get_current_user_info.return_value = {
            "email": "different@example.com",
            "displayName": "Test User",
        }
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.confluence_fetcher == mock_fetcher
        # Verify original email was preserved
        assert mock_request.state.user_atlassian_email == "existing@example.com"
