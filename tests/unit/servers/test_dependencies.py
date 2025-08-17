"""Unit tests for server dependencies module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.confluence import ConfluenceConfig, ConfluenceFetcher
from mcp_atlassian.jira import JiraConfig, JiraFetcher
from mcp_atlassian.servers.context import MainAppContext
from mcp_atlassian.servers.dependencies import (
    _create_user_config_for_fetcher,
    get_confluence_fetcher,
    get_jira_fetcher,
)
from mcp_atlassian.utils.oauth import OAuthConfig
from tests.utils.assertions import assert_mock_called_with_partial
from tests.utils.factories import AuthConfigFactory
from tests.utils.mocks import MockFastMCP

# Configure pytest for async tests
pytestmark = pytest.mark.anyio


@pytest.fixture
def config_factory():
    """Factory for creating various configuration objects."""

    class ConfigFactory:
        @staticmethod
        def create_jira_config(auth_type="basic", **overrides):
            """Create a JiraConfig instance."""
            defaults = {
                "url": "https://test.atlassian.net",
                "auth_type": auth_type,
                "ssl_verify": True,
                "http_proxy": None,
                "https_proxy": None,
                "no_proxy": None,
                "socks_proxy": None,
                "projects_filter": ["TEST"],
            }

            if auth_type == "basic":
                defaults.update(
                    {"username": "test_username", "api_token": "test_token"}
                )
            elif auth_type == "oauth":
                defaults["oauth_config"] = ConfigFactory.create_oauth_config()
            elif auth_type == "pat":
                defaults["personal_token"] = "test_pat_token"

            return JiraConfig(**{**defaults, **overrides})

        @staticmethod
        def create_confluence_config(auth_type="basic", **overrides):
            """Create a ConfluenceConfig instance."""
            defaults = {
                "url": "https://test.atlassian.net",
                "auth_type": auth_type,
                "ssl_verify": True,
                "http_proxy": None,
                "https_proxy": None,
                "no_proxy": None,
                "socks_proxy": None,
                "spaces_filter": ["TEST"],
            }

            if auth_type == "basic":
                defaults.update(
                    {"username": "test_username", "api_token": "test_token"}
                )
            elif auth_type == "oauth":
                defaults["oauth_config"] = ConfigFactory.create_oauth_config()
            elif auth_type == "pat":
                defaults["personal_token"] = "test_pat_token"

            return ConfluenceConfig(**{**defaults, **overrides})

        @staticmethod
        def create_oauth_config(**overrides):
            """Create an OAuthConfig instance."""
            oauth_data = AuthConfigFactory.create_oauth_config(**overrides)
            return OAuthConfig(
                client_id=oauth_data["client_id"],
                client_secret=oauth_data["client_secret"],
                redirect_uri=oauth_data["redirect_uri"],
                scope=oauth_data["scope"],
                cloud_id=oauth_data["cloud_id"],
                access_token=oauth_data["access_token"],
                refresh_token=oauth_data["refresh_token"],
                expires_at=9999999999.0,
            )

        @staticmethod
        def create_app_context(jira_config=None, confluence_config=None, **overrides):
            """Create a MainAppContext instance."""
            defaults = {
                "full_jira_config": jira_config or ConfigFactory.create_jira_config(),
                "full_confluence_config": confluence_config
                or ConfigFactory.create_confluence_config(),
                "read_only": False,
                "enabled_tools": ["jira_get_issue", "confluence_get_page"],
            }
            return MainAppContext(**{**defaults, **overrides})

    return ConfigFactory()


@pytest.fixture
def mock_context():
    """Create a mock Context instance."""
    return MockFastMCP.create_context()


@pytest.fixture
def mock_request():
    """Create a mock Request instance."""
    return MockFastMCP.create_request()


@pytest.fixture
def auth_scenarios():
    """Common authentication scenarios for testing."""
    return {
        "oauth": {
            "auth_type": "oauth",
            "token": "user-oauth-token",
            "email": "user@example.com",
            "credential_key": "oauth_access_token",
        },
        "pat": {
            "auth_type": "pat",
            "token": "user-pat-token",
            "email": "user@example.com",
            "credential_key": "personal_access_token",
        },
    }


def _create_user_credentials(auth_type, token, email="user@example.com"):
    """Helper to create user credentials for testing."""
    credentials = {"user_email_context": email}

    if auth_type == "oauth":
        credentials["oauth_access_token"] = token
    elif auth_type == "pat":
        credentials["personal_access_token"] = token

    return credentials


def _assert_config_attributes(
    config, expected_type, expected_auth_type, expected_token=None
):
    """Helper to assert configuration attributes."""
    assert isinstance(config, expected_type)
    assert config.auth_type == expected_auth_type

    if expected_auth_type == "oauth":
        assert config.oauth_config is not None
        assert config.oauth_config.access_token == expected_token
        assert config.username == "user@example.com"
        assert config.api_token is None
        assert config.personal_token is None
    elif expected_auth_type == "pat":
        assert config.personal_token == expected_token
        assert config.username is None
        assert config.api_token is None
        assert config.oauth_config is None


class TestCreateUserConfigForFetcher:
    """Tests for _create_user_config_for_fetcher function."""

    @pytest.mark.parametrize(
        "config_type,auth_type,token",
        [
            ("jira", "oauth", "user-oauth-token"),
            ("jira", "pat", "user-pat-token"),
            ("confluence", "oauth", "user-oauth-token"),
            ("confluence", "pat", "user-pat-token"),
        ],
    )
    def test_create_user_config_success(
        self, config_factory, config_type, auth_type, token
    ):
        """Test creating user-specific configs with various auth types."""
        # Create base config
        if config_type == "jira":
            base_config = config_factory.create_jira_config(auth_type=auth_type)
            expected_type = JiraConfig
        else:
            base_config = config_factory.create_confluence_config(auth_type=auth_type)
            expected_type = ConfluenceConfig

        credentials = _create_user_credentials(auth_type, token)

        result = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type=auth_type,
            credentials=credentials,
        )

        _assert_config_attributes(result, expected_type, auth_type, token)

        if config_type == "jira":
            assert result.projects_filter == ["TEST"]
        else:
            assert result.spaces_filter == ["TEST"]

    def test_oauth_auth_type_minimal_config_success(self):
        """Test OAuth auth type with minimal base config (user-provided tokens mode)."""
        # Setup minimal base config (empty credentials)
        base_oauth_config = OAuthConfig(
            client_id="",  # Empty client_id (minimal config)
            client_secret="",  # Empty client_secret (minimal config)
            redirect_uri="",
            scope="",
            cloud_id="",
        )
        base_config = JiraConfig(
            url="https://base.atlassian.net",
            auth_type="oauth",
            oauth_config=base_oauth_config,
        )

        # Test with user-provided cloud_id
        credentials = {"oauth_access_token": "user-access-token"}
        result_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=credentials,
            cloud_id="user-cloud-id",
        )

        # Verify the result
        assert isinstance(result_config, JiraConfig)
        assert result_config.auth_type == "oauth"
        assert result_config.oauth_config is not None
        assert result_config.oauth_config.access_token == "user-access-token"
        assert result_config.oauth_config.cloud_id == "user-cloud-id"
        assert (
            result_config.oauth_config.client_id == ""
        )  # Should preserve minimal config
        assert (
            result_config.oauth_config.client_secret == ""
        )  # Should preserve minimal config

    def test_multi_tenant_config_isolation(self):
        """Test that user configs are completely isolated from each other."""
        # Setup minimal base config
        base_oauth_config = OAuthConfig(
            client_id="", client_secret="", redirect_uri="", scope="", cloud_id=""
        )
        base_config = JiraConfig(
            url="https://base.atlassian.net",
            auth_type="oauth",
            oauth_config=base_oauth_config,
        )

        # Create user config for tenant 1
        tenant1_credentials = {"oauth_access_token": "tenant1-token"}
        tenant1_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=tenant1_credentials,
            cloud_id="tenant1-cloud-id",
        )

        # Create user config for tenant 2
        tenant2_credentials = {"oauth_access_token": "tenant2-token"}
        tenant2_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=tenant2_credentials,
            cloud_id="tenant2-cloud-id",
        )

        # Modify tenant1 config
        tenant1_config.oauth_config.access_token = "modified-tenant1-token"
        tenant1_config.oauth_config.cloud_id = "modified-tenant1-cloud-id"

        # Verify tenant2 config remains unchanged
        assert tenant2_config.oauth_config.access_token == "tenant2-token"
        assert tenant2_config.oauth_config.cloud_id == "tenant2-cloud-id"

        # Verify base config remains unchanged
        assert base_oauth_config.access_token is None
        assert base_oauth_config.cloud_id == ""

        # Verify tenant1 config has the modifications
        assert tenant1_config.oauth_config.access_token == "modified-tenant1-token"
        assert tenant1_config.oauth_config.cloud_id == "modified-tenant1-cloud-id"

    @pytest.mark.parametrize(
        "auth_type,missing_credential,expected_error",
        [
            (
                "oauth",
                "oauth_access_token",
                "OAuth access token missing in credentials",
            ),
            ("pat", "personal_access_token", "PAT missing in credentials"),
        ],
    )
    def test_missing_credentials(
        self, config_factory, auth_type, missing_credential, expected_error
    ):
        """Test error handling for missing credentials."""
        base_config = config_factory.create_jira_config(auth_type=auth_type)
        credentials = {"user_email_context": "user@example.com"}

        with pytest.raises(ValueError, match=expected_error):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type=auth_type,
                credentials=credentials,
            )

    def test_unsupported_auth_type(self, config_factory):
        """Test error handling for unsupported auth types."""
        base_config = config_factory.create_jira_config()
        credentials = {"user_email_context": "user@example.com"}

        with pytest.raises(ValueError, match="Unsupported auth_type 'invalid'"):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type="invalid",
                credentials=credentials,
            )

    def test_missing_oauth_config(self, config_factory):
        """Test error handling for missing OAuth config when auth_type is oauth."""
        base_config = config_factory.create_jira_config(
            auth_type="basic"
        )  # No OAuth config
        credentials = _create_user_credentials("oauth", "user-oauth-token")

        with pytest.raises(ValueError, match="Global OAuth config.*is missing"):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type="oauth",
                credentials=credentials,
            )

    def test_unsupported_base_config_type(self):
        """Test error handling for unsupported base config types."""

        class UnsupportedConfig:
            def __init__(self):
                self.url = "https://test.atlassian.net"
                self.ssl_verify = True
                self.http_proxy = None
                self.https_proxy = None
                self.no_proxy = None
                self.socks_proxy = None

        base_config = UnsupportedConfig()
        credentials = _create_user_credentials("pat", "test-token")

        with pytest.raises(TypeError, match="Unsupported base_config type"):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type="pat",
                credentials=credentials,
            )


def _setup_mock_request_state(mock_request, auth_scenario=None, cached_fetcher=None):
    """Helper to setup mock request state."""
    if cached_fetcher:
        mock_request.state.jira_fetcher = cached_fetcher
        mock_request.state.confluence_fetcher = cached_fetcher
        return

    mock_request.state.jira_fetcher = None
    mock_request.state.confluence_fetcher = None

    if auth_scenario:
        mock_request.state.user_atlassian_auth_type = auth_scenario["auth_type"]
        mock_request.state.user_atlassian_token = auth_scenario["token"]
        mock_request.state.user_atlassian_email = auth_scenario["email"]
    else:
        mock_request.state.user_atlassian_auth_type = None
        mock_request.state.user_atlassian_token = None
        mock_request.state.user_atlassian_email = None


def _setup_mock_context(mock_context, app_context):
    """Helper to setup mock context with app context."""
    mock_context.request_context.lifespan_context = {
        "app_lifespan_context": app_context
    }


def _create_mock_fetcher(fetcher_class, validation_return=None, validation_error=None):
    """Helper to create mock fetcher with validation behavior."""
    mock_fetcher = MagicMock(spec=fetcher_class)

    if fetcher_class == JiraFetcher:
        if validation_error:
            mock_fetcher.get_current_user_account_id.side_effect = validation_error
        else:
            mock_fetcher.get_current_user_account_id.return_value = (
                validation_return or "test-account-id"
            )
    elif fetcher_class == ConfluenceFetcher:
        if validation_error:
            mock_fetcher.get_current_user_info.side_effect = validation_error
        else:
            mock_fetcher.get_current_user_info.return_value = validation_return or {
                "email": "user@example.com",
                "displayName": "Test User",
            }

    return mock_fetcher


class TestGetJiraFetcher:
    """Tests for get_jira_fetcher function."""

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_cached_fetcher_returned(
        self, mock_jira_fetcher_class, mock_get_http_request, mock_context, mock_request
    ):
        """Test returning cached JiraFetcher from request state."""
        cached_fetcher = MagicMock(spec=JiraFetcher)
        _setup_mock_request_state(mock_request, cached_fetcher=cached_fetcher)
        mock_get_http_request.return_value = mock_request

        result = await get_jira_fetcher(mock_context)

        assert result == cached_fetcher
        mock_jira_fetcher_class.assert_not_called()

    @pytest.mark.parametrize("scenario_key", ["oauth", "pat"])
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_user_specific_fetcher_creation(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
        scenario_key,
    ):
        """Test creating user-specific JiraFetcher with different auth types."""
        scenario = auth_scenarios[scenario_key]

        # Setup request state
        _setup_mock_request_state(mock_request, scenario)
        mock_get_http_request.return_value = mock_request

        # Setup context
        jira_config = config_factory.create_jira_config(auth_type=scenario["auth_type"])
        confluence_config = config_factory.create_confluence_config(
            auth_type=scenario["auth_type"]
        )
        app_context = config_factory.create_app_context(jira_config, confluence_config)
        _setup_mock_context(mock_context, app_context)

        # Setup mock fetcher
        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.jira_fetcher == mock_fetcher
        mock_jira_fetcher_class.assert_called_once()

        # Verify the config passed to JiraFetcher
        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.auth_type == scenario["auth_type"]

        if scenario["auth_type"] == "oauth":
            assert called_config.oauth_config.access_token == scenario["token"]
        elif scenario["auth_type"] == "pat":
            assert called_config.personal_token == scenario["token"]

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_global_fallback_scenarios(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ):
        """Test fallback to global JiraFetcher in various scenarios."""
        # Test both HTTP context without user token and non-HTTP context
        test_scenarios = [
            {"name": "no_user_token", "setup_http": True, "user_auth": None},
            {"name": "no_http_context", "setup_http": False, "user_auth": None},
        ]

        for scenario in test_scenarios:
            # Setup request state
            if scenario["setup_http"]:
                _setup_mock_request_state(mock_request)
                mock_get_http_request.return_value = mock_request
            else:
                mock_get_http_request.side_effect = RuntimeError("No HTTP context")

            # Setup context
            app_context = config_factory.create_app_context()
            _setup_mock_context(mock_context, app_context)

            # Setup mock fetcher
            mock_fetcher = _create_mock_fetcher(JiraFetcher)
            mock_jira_fetcher_class.return_value = mock_fetcher

            result = await get_jira_fetcher(mock_context)

            assert result == mock_fetcher
            assert_mock_called_with_partial(
                mock_jira_fetcher_class, config=app_context.full_jira_config
            )

            # Reset mocks for next iteration
            mock_jira_fetcher_class.reset_mock()
            mock_get_http_request.reset_mock()

    @pytest.mark.parametrize(
        "error_scenario,expected_error_match",
        [
            ("missing_global_config", "Jira client \\(fetcher\\) not available"),
            ("empty_user_token", "User Atlassian token found in state but is empty"),
            ("validation_failure", "Invalid user Jira token or configuration"),
            (
                "missing_lifespan_context",
                "Jira global configuration.*is not available from lifespan context",
            ),
        ],
    )
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_error_scenarios(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
        error_scenario,
        expected_error_match,
    ):
        """Test various error scenarios."""
        if error_scenario == "missing_global_config":
            mock_get_http_request.side_effect = RuntimeError("No HTTP context")
            mock_context.request_context.lifespan_context = {}

        elif error_scenario == "empty_user_token":
            scenario = auth_scenarios["oauth"].copy()
            scenario["token"] = ""  # Empty token
            _setup_mock_request_state(mock_request, scenario)
            mock_get_http_request.return_value = mock_request
            app_context = config_factory.create_app_context()
            _setup_mock_context(mock_context, app_context)

        elif error_scenario == "validation_failure":
            scenario = auth_scenarios["pat"]
            _setup_mock_request_state(mock_request, scenario)
            mock_get_http_request.return_value = mock_request
            app_context = config_factory.create_app_context()
            _setup_mock_context(mock_context, app_context)

            # Setup mock fetcher to fail validation
            mock_fetcher = _create_mock_fetcher(
                JiraFetcher, validation_error=Exception("Invalid token")
            )
            mock_jira_fetcher_class.return_value = mock_fetcher

        elif error_scenario == "missing_lifespan_context":
            scenario = auth_scenarios["oauth"]
            _setup_mock_request_state(mock_request, scenario)
            mock_get_http_request.return_value = mock_request
            mock_context.request_context.lifespan_context = {}

        with pytest.raises(ValueError, match=expected_error_match):
            await get_jira_fetcher(mock_context)


class TestGetConfluenceFetcher:
    """Tests for get_confluence_fetcher function."""

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_cached_fetcher_returned(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
    ):
        """Test returning cached ConfluenceFetcher from request state."""
        cached_fetcher = MagicMock(spec=ConfluenceFetcher)
        _setup_mock_request_state(mock_request, cached_fetcher=cached_fetcher)
        mock_get_http_request.return_value = mock_request

        result = await get_confluence_fetcher(mock_context)

        assert result == cached_fetcher
        mock_confluence_fetcher_class.assert_not_called()

    @pytest.mark.parametrize("scenario_key", ["oauth", "pat"])
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_user_specific_fetcher_creation(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
        scenario_key,
    ):
        """Test creating user-specific ConfluenceFetcher with different auth types."""
        scenario = auth_scenarios[scenario_key]

        # Setup request state
        _setup_mock_request_state(mock_request, scenario)
        mock_get_http_request.return_value = mock_request

        # Setup context
        jira_config = config_factory.create_jira_config(auth_type=scenario["auth_type"])
        confluence_config = config_factory.create_confluence_config(
            auth_type=scenario["auth_type"]
        )
        app_context = config_factory.create_app_context(jira_config, confluence_config)
        _setup_mock_context(mock_context, app_context)

        # Setup mock fetcher
        mock_fetcher = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.confluence_fetcher == mock_fetcher
        mock_confluence_fetcher_class.assert_called_once()

        # Verify the config passed to ConfluenceFetcher
        called_config = mock_confluence_fetcher_class.call_args[1]["config"]
        assert called_config.auth_type == scenario["auth_type"]

        if scenario["auth_type"] == "oauth":
            assert called_config.oauth_config.access_token == scenario["token"]
        elif scenario["auth_type"] == "pat":
            assert called_config.personal_token == scenario["token"]

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_global_fallback_scenarios(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ):
        """Test fallback to global ConfluenceFetcher in various scenarios."""
        # Test both HTTP context without user token and non-HTTP context
        test_scenarios = [
            {"name": "no_user_token", "setup_http": True, "user_auth": None},
            {"name": "no_http_context", "setup_http": False, "user_auth": None},
        ]

        for scenario in test_scenarios:
            # Setup request state
            if scenario["setup_http"]:
                _setup_mock_request_state(mock_request)
                mock_get_http_request.return_value = mock_request
            else:
                mock_get_http_request.side_effect = RuntimeError("No HTTP context")

            # Setup context
            app_context = config_factory.create_app_context()
            _setup_mock_context(mock_context, app_context)

            # Setup mock fetcher
            mock_fetcher = _create_mock_fetcher(ConfluenceFetcher)
            mock_confluence_fetcher_class.return_value = mock_fetcher

            result = await get_confluence_fetcher(mock_context)

            assert result == mock_fetcher
            assert_mock_called_with_partial(
                mock_confluence_fetcher_class, config=app_context.full_confluence_config
            )

            # Reset mocks for next iteration
            mock_confluence_fetcher_class.reset_mock()
            mock_get_http_request.reset_mock()

    @pytest.mark.parametrize(
        "email_scenario,expected_email",
        [
            ("derive_email", "derived@example.com"),
            ("preserve_existing", "existing@example.com"),
        ],
    )
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_email_derivation_behavior(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
        email_scenario,
        expected_email,
    ):
        """Test email derivation behavior in different scenarios."""
        scenario = auth_scenarios["pat"].copy()

        if email_scenario == "derive_email":
            scenario["email"] = None  # No existing email
            user_info_email = "derived@example.com"
        else:  # preserve_existing
            scenario["email"] = "existing@example.com"
            user_info_email = "different@example.com"

        # Setup request state
        _setup_mock_request_state(mock_request, scenario)
        mock_get_http_request.return_value = mock_request

        # Setup context
        app_context = config_factory.create_app_context()
        _setup_mock_context(mock_context, app_context)

        # Setup mock fetcher with specific user info
        mock_fetcher = _create_mock_fetcher(
            ConfluenceFetcher,
            validation_return={
                "email": user_info_email,
                "displayName": "Test User",
            },
        )
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.confluence_fetcher == mock_fetcher
        assert mock_request.state.user_atlassian_email == expected_email

    @pytest.mark.parametrize(
        "error_scenario,expected_error_match",
        [
            ("missing_global_config", "Confluence client \\(fetcher\\) not available"),
            ("empty_user_token", "User Atlassian token found in state but is empty"),
            ("validation_failure", "Invalid user Confluence token or configuration"),
            (
                "missing_lifespan_context",
                "Confluence global configuration.*is not available from lifespan context",
            ),
        ],
    )
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_error_scenarios(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
        error_scenario,
        expected_error_match,
    ):
        """Test various error scenarios."""
        if error_scenario == "missing_global_config":
            mock_get_http_request.side_effect = RuntimeError("No HTTP context")
            mock_context.request_context.lifespan_context = {}

        elif error_scenario == "empty_user_token":
            scenario = auth_scenarios["oauth"].copy()
            scenario["token"] = ""  # Empty token
            _setup_mock_request_state(mock_request, scenario)
            mock_get_http_request.return_value = mock_request
            app_context = config_factory.create_app_context()
            _setup_mock_context(mock_context, app_context)

        elif error_scenario == "validation_failure":
            scenario = auth_scenarios["pat"]
            _setup_mock_request_state(mock_request, scenario)
            mock_get_http_request.return_value = mock_request
            app_context = config_factory.create_app_context()
            _setup_mock_context(mock_context, app_context)

            # Setup mock fetcher to fail validation
            mock_fetcher = _create_mock_fetcher(
                ConfluenceFetcher, validation_error=Exception("Invalid token")
            )
            mock_confluence_fetcher_class.return_value = mock_fetcher

        elif error_scenario == "missing_lifespan_context":
            scenario = auth_scenarios["oauth"]
            _setup_mock_request_state(mock_request, scenario)
            mock_get_http_request.return_value = mock_request
            mock_context.request_context.lifespan_context = {}

        with pytest.raises(ValueError, match=expected_error_match):
            await get_confluence_fetcher(mock_context)
