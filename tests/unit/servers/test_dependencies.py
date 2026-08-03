"""Unit tests for server dependencies module."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from starlette.datastructures import Headers

from mcp_atlassian.confluence import ConfluenceConfig, ConfluenceFetcher
from mcp_atlassian.jira import JiraConfig, JiraFetcher
from mcp_atlassian.servers.context import MainAppContext
from mcp_atlassian.servers.dependencies import (
    _confluence_spec,
    _create_and_validate,
    _create_user_config_for_fetcher,
    _resolve_bearer_auth_type,
    _validation_cache,
    _validation_cache_scope,
    get_confluence_fetcher,
    get_jira_fetcher,
)
from mcp_atlassian.utils.oauth import BYOAccessTokenOAuthConfig, OAuthConfig
from tests.utils.assertions import assert_mock_called_with_partial
from tests.utils.factories import AuthConfigFactory
from tests.utils.mocks import MockFastMCP

# Configure pytest for async tests
pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _clear_validation_cache():
    """Isolate tests from the module-level credential validation cache (#1405).

    Different test scenarios intentionally reuse the same mock credential
    strings while expecting different validation outcomes, so the cache must
    be empty at the start (and end) of every test.
    """
    if _validation_cache is not None:
        _validation_cache.clear()
    yield
    if _validation_cache is not None:
        _validation_cache.clear()


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
                "proxy_wpad_enable": False,
                "proxy_wpad_url": None,
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
                "proxy_wpad_enable": False,
                "proxy_wpad_url": None,
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

    @pytest.mark.parametrize("config_type", ["jira", "confluence"])
    def test_create_user_config_preserves_proxy_and_wpad_fields(
        self, config_factory, config_type
    ):
        """Test cloned user configs preserve inherited proxy and WPAD settings."""
        proxy_kwargs = {
            "http_proxy": "http://proxy.example.com:8080",
            "https_proxy": "https://proxy.example.com:8443",
            "no_proxy": "localhost,127.0.0.1",
            "socks_proxy": "socks5://proxy.example.com:1080",
            "proxy_wpad_enable": True,
            "proxy_wpad_url": "http://wpad.example.com/wpad.dat",
        }
        if config_type == "jira":
            base_config = config_factory.create_jira_config(
                auth_type="pat", **proxy_kwargs
            )
        else:
            base_config = config_factory.create_confluence_config(
                auth_type="pat", **proxy_kwargs
            )

        result = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="pat",
            credentials={"personal_access_token": "user-pat-token"},
        )

        assert result.http_proxy == proxy_kwargs["http_proxy"]
        assert result.https_proxy == proxy_kwargs["https_proxy"]
        assert result.no_proxy == proxy_kwargs["no_proxy"]
        assert result.socks_proxy == proxy_kwargs["socks_proxy"]
        assert result.proxy_wpad_enable is True
        assert result.proxy_wpad_url == proxy_kwargs["proxy_wpad_url"]

    @pytest.mark.parametrize(
        "byo_config,cloud_id_arg,expected_cloud_id,expected_base_url",
        [
            pytest.param(
                BYOAccessTokenOAuthConfig(
                    access_token="placeholder-startup-token",
                    base_url="https://jira.dc.example.com",
                ),
                None,
                None,
                "https://jira.dc.example.com",
                id="data-center-byo-global-config",
            ),
            pytest.param(
                BYOAccessTokenOAuthConfig(
                    access_token="placeholder-startup-token",
                    cloud_id="global-cloud-id",
                ),
                "user-cloud-id",
                "user-cloud-id",
                None,
                id="cloud-byo-global-config",
            ),
        ],
    )
    def test_oauth_user_config_with_byo_global_config(
        self, byo_config, cloud_id_arg, expected_cloud_id, expected_base_url
    ):
        """Regression: global oauth_config may be a BYOAccessTokenOAuthConfig.

        When a placeholder ``*_OAUTH_ACCESS_TOKEN`` suppresses the headless OAuth
        setup flow, ``get_oauth_config_from_env()`` returns a
        ``BYOAccessTokenOAuthConfig`` (BYO takes precedence over ``OAuthConfig``).
        That dataclass has no ``client_id``/``client_secret``/``redirect_uri``/
        ``scope`` attributes. With per-request OAuth proxy auth enabled, this
        function previously read those attributes directly off the global config,
        raising ``AttributeError`` at request time. They must fall back to empty
        strings (the real client credentials come from the OAuth proxy config).
        """
        base_config = JiraConfig(
            url="https://jira.dc.example.com",
            auth_type="oauth",
            oauth_config=byo_config,
        )
        credentials = {"oauth_access_token": "user-access-token"}

        # Must not raise AttributeError on the BYO global config.
        result_config = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="oauth",
            credentials=credentials,
            cloud_id=cloud_id_arg,
        )

        assert isinstance(result_config, JiraConfig)
        assert result_config.oauth_config is not None
        assert result_config.oauth_config.access_token == "user-access-token"
        # Client credentials fall back to empty strings (supplied by the proxy).
        assert result_config.oauth_config.client_id == ""
        assert result_config.oauth_config.client_secret == ""
        assert result_config.oauth_config.redirect_uri == ""
        assert result_config.oauth_config.scope == ""
        assert result_config.oauth_config.cloud_id == expected_cloud_id
        assert result_config.oauth_config.base_url == expected_base_url

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
                self.proxy_wpad_enable = False
                self.proxy_wpad_url = None

        base_config = UnsupportedConfig()
        credentials = _create_user_credentials("pat", "test-token")

        with pytest.raises(TypeError, match="Unsupported base_config type"):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type="pat",
                credentials=credentials,
            )


def _setup_mock_request_state(
    mock_request, auth_scenario=None, cached_fetcher=None, service_headers=None
):
    """Helper to setup mock request state."""
    if cached_fetcher:
        mock_request.state.jira_fetcher = cached_fetcher
        mock_request.state.confluence_fetcher = cached_fetcher
        return

    mock_request.state.jira_fetcher = None
    mock_request.state.confluence_fetcher = None

    mock_request.state.atlassian_service_headers = service_headers or {}

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
        # Set up jira._session.hooks for SSRF redirect hook attachment
        mock_session = MagicMock()
        mock_session.hooks = {"response": []}
        mock_fetcher.jira = MagicMock()
        mock_fetcher.jira._session = mock_session
    elif fetcher_class == ConfluenceFetcher:
        if validation_error:
            mock_fetcher.get_current_user_info.side_effect = validation_error
        else:
            mock_fetcher.get_current_user_info.return_value = validation_return or {
                "email": "user@example.com",
                "displayName": "Test User",
            }
        # Set up confluence._session.hooks for SSRF redirect hook attachment
        mock_session = MagicMock()
        mock_session.hooks = {"response": []}
        mock_fetcher.confluence = MagicMock()
        mock_fetcher.confluence._session = mock_session

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

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_header_based_jira_fetcher_creation(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ):
        """Test creating header-based JiraFetcher with PAT token from headers."""
        service_headers = {
            "X-Atlassian-Jira-Url": "https://test.atlassian.net",
            "X-Atlassian-Jira-Personal-Token": "test-pat-token",
        }

        # Create a special state mock that controls hasattr() behavior
        class MockState:
            def __init__(self):
                self.jira_fetcher = None
                self.user_atlassian_auth_type = "pat"
                self.user_atlassian_email = None
                self.atlassian_service_headers = service_headers

            def __getattr__(self, name):
                if name == "user_atlassian_token":
                    raise AttributeError(
                        f"'{type(self).__name__}' object has no attribute '{name}'"
                    )
                return None

        mock_request.state = MockState()
        mock_get_http_request.return_value = mock_request

        app_context = config_factory.create_app_context(
            jira_config=config_factory.create_jira_config(
                ssl_verify=False,
                http_proxy="http://proxy.example.com:8080",
                no_proxy="localhost,127.0.0.1",
                proxy_wpad_enable=True,
                proxy_wpad_url="http://wpad.example.com/wpad.dat",
                custom_headers={"X-Global": "should-not-inherit"},
                projects_filter=["GLOBAL"],
            )
        )
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.jira_fetcher == mock_fetcher
        mock_jira_fetcher_class.assert_called_once()

        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.auth_type == "pat"
        assert called_config.url == "https://test.atlassian.net"
        assert called_config.personal_token == "test-pat-token"
        assert called_config.ssl_verify is False
        assert called_config.http_proxy == "http://proxy.example.com:8080"
        assert called_config.https_proxy is None
        assert called_config.no_proxy == "localhost,127.0.0.1"
        assert called_config.socks_proxy is None
        assert called_config.custom_headers is None
        assert called_config.projects_filter is None
        assert called_config.proxy_wpad_enable is True
        assert called_config.proxy_wpad_url == "http://wpad.example.com/wpad.dat"

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_header_based_jira_fetcher_inherits_proxy_when_wpad_disabled(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ):
        """Test header PAT inherits network settings while WPAD remains disabled."""
        service_headers = {
            "X-Atlassian-Jira-Url": "https://test.atlassian.net",
            "X-Atlassian-Jira-Personal-Token": "test-pat-token",
        }

        class MockState:
            def __init__(self):
                self.jira_fetcher = None
                self.user_atlassian_auth_type = "pat"
                self.user_atlassian_email = None
                self.atlassian_service_headers = service_headers

            def __getattr__(self, name):
                if name == "user_atlassian_token":
                    raise AttributeError(
                        f"'{type(self).__name__}' object has no attribute '{name}'"
                    )
                return None

        mock_request.state = MockState()
        mock_get_http_request.return_value = mock_request

        app_context = config_factory.create_app_context(
            jira_config=config_factory.create_jira_config(
                ssl_verify=False,
                http_proxy="http://proxy.example.com:8080",
                https_proxy="https://proxy.example.com:8443",
                no_proxy="localhost,127.0.0.1",
                socks_proxy="socks5://proxy.example.com:1080",
                proxy_wpad_enable=False,
                custom_headers={"X-Global": "should-not-inherit"},
                projects_filter=["GLOBAL"],
            )
        )
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.ssl_verify is False
        assert called_config.http_proxy == "http://proxy.example.com:8080"
        assert called_config.https_proxy == "https://proxy.example.com:8443"
        assert called_config.no_proxy == "localhost,127.0.0.1"
        assert called_config.socks_proxy == "socks5://proxy.example.com:1080"
        assert called_config.custom_headers is None
        assert called_config.projects_filter is None
        assert called_config.proxy_wpad_enable is False
        assert called_config.proxy_wpad_url is None

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_header_based_jira_fetcher_without_lifespan_context(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        monkeypatch,
    ):
        """Test header PAT reads WPAD environment without global config context."""
        for env_var in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "NO_PROXY",
            "SOCKS_PROXY",
            "JIRA_HTTP_PROXY",
            "JIRA_HTTPS_PROXY",
            "JIRA_NO_PROXY",
            "JIRA_SOCKS_PROXY",
            "ATLASSIAN_PROXY_WPAD_ENABLE",
            "JIRA_PROXY_WPAD_ENABLE",
            "ATLASSIAN_PROXY_WPAD_URL",
            "JIRA_PROXY_WPAD_URL",
        ):
            monkeypatch.delenv(env_var, raising=False)
        service_headers = {
            "X-Atlassian-Jira-Url": "https://test.atlassian.net",
            "X-Atlassian-Jira-Personal-Token": "test-pat-token",
        }

        class MockState:
            def __init__(self):
                self.jira_fetcher = None
                self.user_atlassian_auth_type = "pat"
                self.user_atlassian_email = None
                self.atlassian_service_headers = service_headers

            def __getattr__(self, name):
                if name == "user_atlassian_token":
                    raise AttributeError(
                        f"'{type(self).__name__}' object has no attribute '{name}'"
                    )
                return None

        mock_context.request_context.lifespan_context = {}
        monkeypatch.setenv("ATLASSIAN_PROXY_WPAD_ENABLE", "true")
        monkeypatch.setenv(
            "ATLASSIAN_PROXY_WPAD_URL", "http://wpad.example.com/wpad.dat"
        )
        mock_request.state = MockState()
        mock_get_http_request.return_value = mock_request
        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.proxy_wpad_enable is True
        assert called_config.proxy_wpad_url == "http://wpad.example.com/wpad.dat"
        assert called_config.no_proxy is None

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_header_based_jira_fetcher_inherits_global_network_config(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ):
        """Header PAT fetchers inherit safe global network settings."""
        service_headers = {
            "X-Atlassian-Jira-Url": "https://test.atlassian.net",
            "X-Atlassian-Jira-Personal-Token": "test-pat-token",
        }
        jira_config = config_factory.create_jira_config(
            auth_type="pat",
            ssl_verify=False,
            http_proxy="http://proxy.example",
            https_proxy="https://proxy.example",
            no_proxy="localhost",
            socks_proxy="socks5://proxy.example",
            custom_headers={"X-Instance-Secret": "do-not-forward"},
        )
        app_context = config_factory.create_app_context(jira_config=jira_config)
        _setup_mock_context(mock_context, app_context)

        class MockState:
            def __init__(self):
                self.jira_fetcher = None
                self.user_atlassian_auth_type = "pat"
                self.user_atlassian_email = None
                self.atlassian_service_headers = service_headers

            def __getattr__(self, name):
                if name == "user_atlassian_token":
                    raise AttributeError(
                        f"'{type(self).__name__}' object has no attribute '{name}'"
                    )
                return None

        mock_request.state = MockState()
        mock_get_http_request.return_value = mock_request
        mock_jira_fetcher_class.return_value = _create_mock_fetcher(JiraFetcher)

        await get_jira_fetcher(mock_context)

        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.ssl_verify is False
        assert called_config.http_proxy == "http://proxy.example"
        assert called_config.https_proxy == "https://proxy.example"
        assert called_config.no_proxy == "localhost"
        assert called_config.socks_proxy == "socks5://proxy.example"
        assert called_config.custom_headers is None

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_header_based_jira_fetcher_validation_failure(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ):
        """Test header-based JiraFetcher creation failure when validation fails."""

        service_headers = {
            "X-Atlassian-Jira-Url": "https://test.atlassian.net",
            "X-Atlassian-Jira-Personal-Token": "invalid-token",
        }

        # Create a special state mock that controls hasattr() behavior
        class MockState:
            def __init__(self):
                self.jira_fetcher = None
                self.user_atlassian_auth_type = "pat"
                self.atlassian_service_headers = service_headers

            def __getattr__(self, name):
                if name == "user_atlassian_token":
                    raise AttributeError(
                        f"'{type(self).__name__}' object has no attribute '{name}'"
                    )
                return None

        mock_request.state = MockState()
        mock_get_http_request.return_value = mock_request

        app_context = config_factory.create_app_context(
            jira_config=config_factory.create_jira_config(
                http_proxy="http://proxy.example.com:8080",
                proxy_wpad_enable=True,
                proxy_wpad_url="http://wpad.example.com/wpad.dat",
            )
        )
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(
            JiraFetcher, validation_error=Exception("Invalid token")
        )
        mock_jira_fetcher_class.return_value = mock_fetcher

        with pytest.raises(
            ValueError, match="Invalid header-based Jira token or configuration"
        ):
            await get_jira_fetcher(mock_context)

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
    async def test_user_specific_jira_passthrough_headers_override_static_headers(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
    ):
        """Passthrough headers are merged into user-specific Jira configs."""
        scenario = auth_scenarios["pat"]
        _setup_mock_request_state(mock_request, scenario)
        mock_request.headers = Headers(
            {
                "x-sso-user": "incoming-user",
                "x-request-id": "request-123",
            }
        )
        mock_get_http_request.return_value = mock_request

        jira_config = config_factory.create_jira_config(
            auth_type="pat",
            custom_headers={"X-SSO-User": "static-user", "X-Static": "keep"},
            passthrough_headers=["X-SSO-User", "X-Request-ID", "X-Missing"],
        )
        app_context = config_factory.create_app_context(jira_config=jira_config)
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.custom_headers == {
            "X-Static": "keep",
            "X-SSO-User": "incoming-user",
            "X-Request-ID": "request-123",
        }

    @patch("mcp_atlassian.servers.dependencies.get_access_token")
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_oauth_prefers_fastmcp_access_token(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_get_access_token,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
    ):
        """OAuth flow prefers FastMCP-resolved upstream access tokens."""
        scenario = auth_scenarios["oauth"].copy()
        scenario["token"] = "state-token"
        _setup_mock_request_state(mock_request, scenario)
        mock_get_http_request.return_value = mock_request
        mock_get_access_token.return_value = SimpleNamespace(token="upstream-token")

        app_context = config_factory.create_app_context(
            jira_config=config_factory.create_jira_config(auth_type="oauth")
        )
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.oauth_config is not None
        assert called_config.oauth_config.access_token == "upstream-token"

    @patch("mcp_atlassian.servers.dependencies.get_access_token")
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_oauth_falls_back_to_request_state_token(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_get_access_token,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
    ):
        """If FastMCP access token is unavailable, request token is used."""
        scenario = auth_scenarios["oauth"].copy()
        scenario["token"] = "state-token"
        _setup_mock_request_state(mock_request, scenario)
        mock_get_http_request.return_value = mock_request
        mock_get_access_token.side_effect = RuntimeError("no auth context")

        app_context = config_factory.create_app_context(
            jira_config=config_factory.create_jira_config(auth_type="oauth")
        )
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.oauth_config is not None
        assert called_config.oauth_config.access_token == "state-token"

    @patch("mcp_atlassian.servers.dependencies.get_access_token")
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_pat_flow_does_not_use_fastmcp_access_token(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_get_access_token,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
    ):
        """PAT path should not call FastMCP access-token dependency."""
        scenario = auth_scenarios["pat"]
        _setup_mock_request_state(mock_request, scenario)
        mock_get_http_request.return_value = mock_request
        mock_get_access_token.return_value = SimpleNamespace(token="unexpected-token")

        app_context = config_factory.create_app_context(
            jira_config=config_factory.create_jira_config(auth_type="pat")
        )
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.personal_token == scenario["token"]
        mock_get_access_token.assert_not_called()

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

            # The HTTP path now requires an explicit opt-in to fall back to the
            # operator's global credentials; the non-HTTP (stdio) path does not.
            env = (
                {"ALLOW_GLOBAL_CRED_FALLBACK": "true"} if scenario["setup_http"] else {}
            )
            with patch.dict("os.environ", env):
                result = await get_jira_fetcher(mock_context)

            assert result == mock_fetcher
            assert_mock_called_with_partial(
                mock_jira_fetcher_class, config=app_context.full_jira_config
            )

            # Reset mocks for next iteration
            mock_jira_fetcher_class.reset_mock()
            mock_get_http_request.reset_mock()

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_global_jira_passthrough_headers(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
        monkeypatch,
    ):
        """Global Jira fallback applies passthrough headers in HTTP requests."""
        monkeypatch.setenv("ALLOW_GLOBAL_CRED_FALLBACK", "true")
        _setup_mock_request_state(mock_request)
        mock_request.headers = Headers({"x-sso-user": "global-user"})
        mock_get_http_request.return_value = mock_request

        jira_config = config_factory.create_jira_config(
            custom_headers={"X-Static": "keep"},
            passthrough_headers=["X-SSO-User"],
        )
        app_context = config_factory.create_app_context(jira_config=jira_config)
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.custom_headers == {
            "X-Static": "keep",
            "X-SSO-User": "global-user",
        }

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

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_header_based_confluence_fetcher_creation(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ):
        """Test creating header-based ConfluenceFetcher with PAT token from headers."""
        service_headers = {
            "X-Atlassian-Confluence-Url": "https://test.atlassian.net",
            "X-Atlassian-Confluence-Personal-Token": "test-confluence-pat-token",
        }

        # Create a special state mock that controls hasattr() behavior
        class MockState:
            def __init__(self):
                self.confluence_fetcher = None
                self.user_atlassian_auth_type = "pat"
                self.user_atlassian_email = None
                self.atlassian_service_headers = service_headers

            def __getattr__(self, name):
                if name == "user_atlassian_token":
                    raise AttributeError(
                        f"'{type(self).__name__}' object has no attribute '{name}'"
                    )
                return None

        mock_request.state = MockState()
        mock_get_http_request.return_value = mock_request

        app_context = config_factory.create_app_context(
            confluence_config=config_factory.create_confluence_config(
                ssl_verify=False,
                http_proxy="http://proxy.example.com:8080",
                no_proxy="localhost,127.0.0.1",
                proxy_wpad_enable=True,
                proxy_wpad_url="http://wpad.example.com/wpad.dat",
                custom_headers={"X-Global": "should-not-inherit"},
                spaces_filter=["GLOBAL"],
            )
        )
        _setup_mock_context(mock_context, app_context)

        user_info = {"email": "user@example.com", "displayName": "Test User"}
        mock_fetcher = _create_mock_fetcher(
            ConfluenceFetcher, validation_return=user_info
        )
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.confluence_fetcher == mock_fetcher
        assert mock_request.state.user_atlassian_email == "user@example.com"
        mock_confluence_fetcher_class.assert_called_once()

        called_config = mock_confluence_fetcher_class.call_args[1]["config"]
        assert called_config.auth_type == "pat"
        assert called_config.url == "https://test.atlassian.net"
        assert called_config.personal_token == "test-confluence-pat-token"
        assert called_config.ssl_verify is False
        assert called_config.http_proxy == "http://proxy.example.com:8080"
        assert called_config.https_proxy is None
        assert called_config.no_proxy == "localhost,127.0.0.1"
        assert called_config.socks_proxy is None
        assert called_config.custom_headers is None
        assert called_config.spaces_filter is None
        assert called_config.proxy_wpad_enable is True
        assert called_config.proxy_wpad_url == "http://wpad.example.com/wpad.dat"

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_header_based_confluence_fetcher_reads_network_env_without_config(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        monkeypatch,
    ):
        """Header PAT fetchers use proxy environment variables without config."""
        monkeypatch.setenv("CONFLUENCE_SSL_VERIFY", "false")
        monkeypatch.setenv("HTTP_PROXY", "http://shared-proxy.example")
        monkeypatch.setenv("CONFLUENCE_HTTP_PROXY", "http://confluence-proxy.example")
        monkeypatch.setenv("HTTPS_PROXY", "https://shared-proxy.example")
        monkeypatch.delenv("CONFLUENCE_HTTPS_PROXY", raising=False)
        monkeypatch.setenv("CONFLUENCE_NO_PROXY", "localhost")
        monkeypatch.setenv("SOCKS_PROXY", "socks5://shared-proxy.example")
        monkeypatch.delenv("CONFLUENCE_SOCKS_PROXY", raising=False)
        monkeypatch.setenv("CONFLUENCE_PROXY_WPAD_ENABLE", "true")
        monkeypatch.setenv(
            "CONFLUENCE_PROXY_WPAD_URL", "http://wpad.example.com/wpad.dat"
        )
        monkeypatch.setenv(
            "CONFLUENCE_CUSTOM_HEADERS", "X-Instance-Secret=do-not-forward"
        )
        mock_context.request_context.lifespan_context = {}
        service_headers = {
            "X-Atlassian-Confluence-Url": "https://test.atlassian.net",
            "X-Atlassian-Confluence-Personal-Token": "test-confluence-pat-token",
        }

        class MockState:
            def __init__(self):
                self.confluence_fetcher = None
                self.user_atlassian_auth_type = "pat"
                self.user_atlassian_email = None
                self.atlassian_service_headers = service_headers

            def __getattr__(self, name):
                if name == "user_atlassian_token":
                    raise AttributeError(
                        f"'{type(self).__name__}' object has no attribute '{name}'"
                    )
                return None

        mock_request.state = MockState()
        mock_get_http_request.return_value = mock_request
        mock_confluence_fetcher_class.return_value = _create_mock_fetcher(
            ConfluenceFetcher
        )

        await get_confluence_fetcher(mock_context)

        called_config = mock_confluence_fetcher_class.call_args[1]["config"]
        assert called_config.ssl_verify is False
        assert called_config.http_proxy == "http://confluence-proxy.example"
        assert called_config.https_proxy == "https://shared-proxy.example"
        assert called_config.no_proxy == "localhost"
        assert called_config.socks_proxy == "socks5://shared-proxy.example"
        assert called_config.proxy_wpad_enable is True
        assert called_config.proxy_wpad_url == "http://wpad.example.com/wpad.dat"
        assert called_config.custom_headers is None

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_header_based_confluence_passthrough_headers_without_global_config(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        monkeypatch,
    ):
        """Header-based Confluence auth can use passthrough without global config."""
        monkeypatch.setenv("CONFLUENCE_PASSTHROUGH_HEADERS", "X-SSO-User, X-Request-ID")
        mock_context.request_context.lifespan_context = {}
        service_headers = {
            "X-Atlassian-Confluence-Url": "https://test.atlassian.net",
            "X-Atlassian-Confluence-Personal-Token": "test-confluence-pat-token",
        }

        class MockState:
            def __init__(self):
                self.confluence_fetcher = None
                self.user_atlassian_auth_type = "pat"
                self.user_atlassian_email = None
                self.atlassian_service_headers = service_headers

            def __getattr__(self, name):
                if name == "user_atlassian_token":
                    raise AttributeError(
                        f"'{type(self).__name__}' object has no attribute '{name}'"
                    )
                return None

        mock_request.state = MockState()
        mock_request.headers = Headers({"x-sso-user": "header-user"})
        mock_get_http_request.return_value = mock_request
        mock_fetcher = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        called_config = mock_confluence_fetcher_class.call_args[1]["config"]
        assert called_config.custom_headers == {"X-SSO-User": "header-user"}

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_header_based_confluence_fetcher_validation_failure(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ):
        """Test header-based ConfluenceFetcher creation failure when validation fails."""
        # Setup service headers for header-based auth
        service_headers = {
            "X-Atlassian-Confluence-Url": "https://test.atlassian.net",
            "X-Atlassian-Confluence-Personal-Token": "invalid-token",
        }

        # Create a special state mock that controls hasattr() behavior
        class MockState:
            def __init__(self):
                self.confluence_fetcher = None
                self.user_atlassian_auth_type = "pat"
                self.atlassian_service_headers = service_headers

            def __getattr__(self, name):
                if name == "user_atlassian_token":
                    raise AttributeError(
                        f"'{type(self).__name__}' object has no attribute '{name}'"
                    )
                return None

        mock_request.state = MockState()
        mock_get_http_request.return_value = mock_request

        app_context = config_factory.create_app_context(
            confluence_config=config_factory.create_confluence_config(
                http_proxy="http://proxy.example.com:8080",
                proxy_wpad_enable=True,
                proxy_wpad_url="http://wpad.example.com/wpad.dat",
            )
        )
        _setup_mock_context(mock_context, app_context)

        # Setup mock fetcher to fail validation
        mock_fetcher = _create_mock_fetcher(
            ConfluenceFetcher, validation_error=Exception("Invalid token")
        )
        mock_confluence_fetcher_class.return_value = mock_fetcher

        with pytest.raises(
            ValueError, match="Invalid header-based Confluence token or configuration"
        ):
            await get_confluence_fetcher(mock_context)

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

    @patch("mcp_atlassian.servers.dependencies.get_access_token")
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_oauth_prefers_fastmcp_access_token(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_get_access_token,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
    ):
        """OAuth flow prefers FastMCP-resolved upstream access tokens."""
        scenario = auth_scenarios["oauth"].copy()
        scenario["token"] = "state-token"
        _setup_mock_request_state(mock_request, scenario)
        mock_get_http_request.return_value = mock_request
        mock_get_access_token.return_value = SimpleNamespace(token="upstream-token")

        app_context = config_factory.create_app_context(
            confluence_config=config_factory.create_confluence_config(auth_type="oauth")
        )
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        called_config = mock_confluence_fetcher_class.call_args[1]["config"]
        assert called_config.oauth_config is not None
        assert called_config.oauth_config.access_token == "upstream-token"

    @patch("mcp_atlassian.servers.dependencies.get_access_token")
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_oauth_falls_back_to_request_state_token(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_get_access_token,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
    ):
        """If FastMCP access token is unavailable, request token is used."""
        scenario = auth_scenarios["oauth"].copy()
        scenario["token"] = "state-token"
        _setup_mock_request_state(mock_request, scenario)
        mock_get_http_request.return_value = mock_request
        mock_get_access_token.side_effect = RuntimeError("no auth context")

        app_context = config_factory.create_app_context(
            confluence_config=config_factory.create_confluence_config(auth_type="oauth")
        )
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        called_config = mock_confluence_fetcher_class.call_args[1]["config"]
        assert called_config.oauth_config is not None
        assert called_config.oauth_config.access_token == "state-token"

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

            # The HTTP path now requires an explicit opt-in to fall back to the
            # operator's global credentials; the non-HTTP (stdio) path does not.
            env = (
                {"ALLOW_GLOBAL_CRED_FALLBACK": "true"} if scenario["setup_http"] else {}
            )
            with patch.dict("os.environ", env):
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


class TestValidationCache:
    """Tests for the cross-request credential validation cache (#1405)."""

    def _confluence_headers(self, token: str) -> dict[str, str]:
        return {
            "X-Atlassian-Confluence-Url": "https://test.atlassian.net",
            "X-Atlassian-Confluence-Personal-Token": token,
        }

    def _header_pat_request(self, service_headers: dict[str, str]):
        class MockState:
            def __init__(self):
                self.confluence_fetcher = None
                self.user_atlassian_auth_type = "pat"
                self.user_atlassian_email = None
                self.atlassian_service_headers = service_headers

            def __getattr__(self, name):
                if name == "user_atlassian_token":
                    raise AttributeError(
                        f"'{type(self).__name__}' object has no attribute '{name}'"
                    )
                return None

        request = MockFastMCP.create_request()
        request.state = MockState()
        return request

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_second_request_same_credential_skips_validation_call(
        self, mock_confluence_fetcher_class, mock_get_http_request, mock_context
    ):
        """A second, independent HTTP request with the same PAT must not
        re-trigger the validation network call within the TTL window."""
        headers = self._confluence_headers("shared-pat-token")
        request1 = self._header_pat_request(headers)
        request2 = self._header_pat_request(headers)

        fetcher1 = _create_mock_fetcher(
            ConfluenceFetcher,
            validation_return={"email": "user@example.com", "displayName": "User"},
        )
        fetcher2 = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.side_effect = [fetcher1, fetcher2]

        mock_get_http_request.return_value = request1
        result1 = await get_confluence_fetcher(mock_context)
        assert result1 == fetcher1
        fetcher1.get_current_user_info.assert_called_once()

        mock_get_http_request.return_value = request2
        result2 = await get_confluence_fetcher(mock_context)

        # A fresh fetcher is still built per request...
        assert result2 == fetcher2
        assert mock_confluence_fetcher_class.call_count == 2
        # ...but the second fetcher's validation call was skipped (cache hit),
        # and request.state was still populated correctly from the cached data.
        fetcher2.get_current_user_info.assert_not_called()
        assert request2.state.user_atlassian_email == "user@example.com"

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_different_credentials_both_validated(
        self, mock_confluence_fetcher_class, mock_get_http_request, mock_context
    ):
        """Different PATs must each hit validation independently (no false hit)."""
        request1 = self._header_pat_request(self._confluence_headers("token-a"))
        request2 = self._header_pat_request(self._confluence_headers("token-b"))

        fetcher1 = _create_mock_fetcher(ConfluenceFetcher)
        fetcher2 = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.side_effect = [fetcher1, fetcher2]

        mock_get_http_request.return_value = request1
        await get_confluence_fetcher(mock_context)
        mock_get_http_request.return_value = request2
        await get_confluence_fetcher(mock_context)

        fetcher1.get_current_user_info.assert_called_once()
        fetcher2.get_current_user_info.assert_called_once()

    @pytest.mark.parametrize("passthrough_header", ["X-SSO-User", "Cookie"])
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_different_passthrough_users_are_validated_separately(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        monkeypatch,
        passthrough_header,
    ):
        """Passthrough identity must isolate shared PAT cache entries."""
        monkeypatch.setenv("CONFLUENCE_PASSTHROUGH_HEADERS", passthrough_header)
        service_headers = self._confluence_headers("shared-pat-token")
        request1 = self._header_pat_request(service_headers)
        request1.headers = Headers({passthrough_header: "user-a"})
        request2 = self._header_pat_request(service_headers)
        request2.headers = Headers({passthrough_header: "user-b"})

        fetcher1 = _create_mock_fetcher(
            ConfluenceFetcher,
            validation_return={
                "email": "user-a@example.com",
                "displayName": "User A",
            },
        )
        fetcher2 = _create_mock_fetcher(
            ConfluenceFetcher,
            validation_return={
                "email": "user-b@example.com",
                "displayName": "User B",
            },
        )
        mock_confluence_fetcher_class.side_effect = [fetcher1, fetcher2]

        mock_get_http_request.return_value = request1
        await get_confluence_fetcher(mock_context)
        mock_get_http_request.return_value = request2
        await get_confluence_fetcher(mock_context)

        fetcher1.get_current_user_info.assert_called_once()
        fetcher2.get_current_user_info.assert_called_once()
        assert request1.state.user_atlassian_email == "user-a@example.com"
        assert request2.state.user_atlassian_email == "user-b@example.com"

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_same_credential_different_url_both_validated(
        self, mock_confluence_fetcher_class, mock_get_http_request, mock_context
    ):
        """The same PAT string against two different instance URLs must not
        share a cached validation result (header-based PAT accepts the URL
        per-request, so the credential alone isn't a safe cache key)."""
        shared_token = "same-pat-token-different-instances"
        request1 = self._header_pat_request(
            {
                "X-Atlassian-Confluence-Url": "https://instance-a.atlassian.net",
                "X-Atlassian-Confluence-Personal-Token": shared_token,
            }
        )
        request2 = self._header_pat_request(
            {
                "X-Atlassian-Confluence-Url": "https://instance-b.atlassian.net",
                "X-Atlassian-Confluence-Personal-Token": shared_token,
            }
        )

        fetcher1 = _create_mock_fetcher(ConfluenceFetcher)
        fetcher2 = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.side_effect = [fetcher1, fetcher2]

        mock_get_http_request.return_value = request1
        await get_confluence_fetcher(mock_context)
        mock_get_http_request.return_value = request2
        await get_confluence_fetcher(mock_context)

        fetcher1.get_current_user_info.assert_called_once()
        fetcher2.get_current_user_info.assert_called_once()

    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    def test_different_credentials_validate_concurrently(
        self, mock_confluence_fetcher_class, config_factory
    ):
        """Different cache keys must not wait on each other's validation."""
        request1 = MockFastMCP.create_request()
        request2 = MockFastMCP.create_request()
        config1 = config_factory.create_confluence_config(
            auth_type="pat", personal_token="token-a"
        )
        config2 = config_factory.create_confluence_config(
            auth_type="pat", personal_token="token-b"
        )

        fetcher1 = _create_mock_fetcher(ConfluenceFetcher)
        fetcher2 = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.side_effect = [fetcher1, fetcher2]

        validation_started = threading.Event()
        validation_release = threading.Event()
        started_count = 0
        started_count_lock = threading.Lock()

        def validate() -> dict[str, str]:
            nonlocal started_count
            with started_count_lock:
                started_count += 1
                if started_count == 2:
                    validation_started.set()
            if not validation_release.wait(timeout=2):
                raise AssertionError("Validation release was not signaled")
            return {"email": "user@example.com", "displayName": "User"}

        fetcher1.get_current_user_info.side_effect = validate
        fetcher2.get_current_user_info.side_effect = validate

        spec = _confluence_spec()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    _create_and_validate, request1, spec, config1, "header_pat"
                ),
                executor.submit(
                    _create_and_validate, request2, spec, config2, "header_pat"
                ),
            ]
            try:
                assert validation_started.wait(timeout=1)
            finally:
                validation_release.set()

            for future in futures:
                future.result(timeout=2)

        fetcher1.get_current_user_info.assert_called_once()
        fetcher2.get_current_user_info.assert_called_once()

    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    def test_same_credential_validation_is_single_flight(
        self, mock_confluence_fetcher_class, config_factory
    ):
        """Concurrent requests for one cache key share one validation call."""
        request1 = MockFastMCP.create_request()
        request2 = MockFastMCP.create_request()
        config1 = config_factory.create_confluence_config(
            auth_type="pat", personal_token="shared-token"
        )
        config2 = config_factory.create_confluence_config(
            auth_type="pat", personal_token="shared-token"
        )

        fetcher1 = _create_mock_fetcher(ConfluenceFetcher)
        fetcher2 = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.side_effect = [fetcher1, fetcher2]

        validation_started = threading.Event()
        validation_release = threading.Event()
        validation_call_count = 0
        validation_count_lock = threading.Lock()

        def validate() -> dict[str, str]:
            nonlocal validation_call_count
            with validation_count_lock:
                validation_call_count += 1
                validation_started.set()
            if not validation_release.wait(timeout=2):
                raise AssertionError("Validation release was not signaled")
            return {"email": "user@example.com", "displayName": "User"}

        fetcher1.get_current_user_info.side_effect = validate
        fetcher2.get_current_user_info.side_effect = validate

        spec = _confluence_spec()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    _create_and_validate, request1, spec, config1, "header_pat"
                ),
                executor.submit(
                    _create_and_validate, request2, spec, config2, "header_pat"
                ),
            ]
            try:
                assert validation_started.wait(timeout=1)
            finally:
                validation_release.set()

            for future in futures:
                future.result(timeout=2)

        assert validation_call_count == 1
        assert (
            fetcher1.get_current_user_info.call_count
            + fetcher2.get_current_user_info.call_count
            == 1
        )

    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    def test_same_oauth_token_and_url_different_cloud_ids_validate_separately(
        self, mock_confluence_fetcher_class
    ):
        """Cloud OAuth cache entries must be isolated by effective Cloud ID."""
        shared_url = "https://shared.example.atlassian.net"
        shared_token = "shared-oauth-token"

        def make_config(cloud_id: str) -> ConfluenceConfig:
            return ConfluenceConfig(
                url=shared_url,
                auth_type="oauth",
                oauth_config=OAuthConfig(
                    client_id="client-id",
                    client_secret="client-secret",
                    redirect_uri="http://localhost/callback",
                    scope="read:confluence-content.all",
                    cloud_id=cloud_id,
                    access_token=shared_token,
                ),
            )

        fetcher1 = _create_mock_fetcher(ConfluenceFetcher)
        fetcher2 = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.side_effect = [fetcher1, fetcher2]
        spec = _confluence_spec()

        _create_and_validate(
            MockFastMCP.create_request(), spec, make_config("cloud-a"), "oauth"
        )
        _create_and_validate(
            MockFastMCP.create_request(), spec, make_config("cloud-b"), "oauth"
        )

        fetcher1.get_current_user_info.assert_called_once()
        fetcher2.get_current_user_info.assert_called_once()

    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    def test_cloud_oauth_scope_ignores_configured_url(
        self, mock_confluence_fetcher_class
    ):
        """Cloud OAuth validation is scoped by tenant, not the config URL."""
        shared_token = "shared-oauth-token"

        def make_config(url: str) -> ConfluenceConfig:
            return ConfluenceConfig(
                url=url,
                auth_type="oauth",
                oauth_config=OAuthConfig(
                    client_id="client-id",
                    client_secret="client-secret",
                    redirect_uri="http://localhost/callback",
                    scope="read:confluence-content.all",
                    cloud_id="cloud-a",
                    access_token=shared_token,
                ),
            )

        config1 = make_config("https://configured-a.atlassian.net")
        config2 = make_config("https://configured-b.atlassian.net")
        assert _validation_cache_scope(config1) == _validation_cache_scope(config2)

        fetcher1 = _create_mock_fetcher(ConfluenceFetcher)
        fetcher2 = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.side_effect = [fetcher1, fetcher2]
        spec = _confluence_spec()

        _create_and_validate(MockFastMCP.create_request(), spec, config1, "oauth")
        _create_and_validate(MockFastMCP.create_request(), spec, config2, "oauth")

        fetcher1.get_current_user_info.assert_called_once()
        fetcher2.get_current_user_info.assert_not_called()

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_cache_disabled_always_validates(
        self, mock_confluence_fetcher_class, mock_get_http_request, mock_context
    ):
        """When the cache is disabled (TTL=0), every request validates."""
        headers = self._confluence_headers("shared-pat-token")
        request1 = self._header_pat_request(headers)
        request2 = self._header_pat_request(headers)

        fetcher1 = _create_mock_fetcher(ConfluenceFetcher)
        fetcher2 = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.side_effect = [fetcher1, fetcher2]

        with patch("mcp_atlassian.servers.dependencies._validation_cache", None):
            mock_get_http_request.return_value = request1
            await get_confluence_fetcher(mock_context)
            mock_get_http_request.return_value = request2
            await get_confluence_fetcher(mock_context)

        fetcher1.get_current_user_info.assert_called_once()
        fetcher2.get_current_user_info.assert_called_once()

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_failed_validation_not_cached(
        self, mock_confluence_fetcher_class, mock_get_http_request, mock_context
    ):
        """A failed validation must not poison the cache for a later, valid attempt."""
        headers = self._confluence_headers("shared-pat-token")
        request1 = self._header_pat_request(headers)
        request2 = self._header_pat_request(headers)

        failing_fetcher = _create_mock_fetcher(
            ConfluenceFetcher, validation_error=Exception("Invalid token")
        )
        succeeding_fetcher = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.side_effect = [
            failing_fetcher,
            succeeding_fetcher,
        ]

        mock_get_http_request.return_value = request1
        with pytest.raises(ValueError):
            await get_confluence_fetcher(mock_context)

        mock_get_http_request.return_value = request2
        await get_confluence_fetcher(mock_context)

        succeeding_fetcher.get_current_user_info.assert_called_once()


class TestBasicAuthMultiUser:
    """Tests for Basic Auth multi-user support (#739)."""

    @pytest.mark.parametrize("config_type", ["jira", "confluence"])
    def test_create_user_config_basic_auth(self, config_factory, config_type):
        """Test creating user-specific config with basic auth credentials."""
        if config_type == "jira":
            base_config = config_factory.create_jira_config(auth_type="basic")
            expected_type = JiraConfig
        else:
            base_config = config_factory.create_confluence_config(auth_type="basic")
            expected_type = ConfluenceConfig

        credentials = {
            "user_email_context": "user@example.com",
            "user_email": "user@example.com",
            "api_token": "user-api-token-123",
        }

        result = _create_user_config_for_fetcher(
            base_config=base_config,
            auth_type="basic",
            credentials=credentials,
        )

        assert isinstance(result, expected_type)
        assert result.auth_type == "basic"
        assert result.username == "user@example.com"
        assert result.api_token == "user-api-token-123"
        assert result.personal_token is None
        assert result.oauth_config is None

    @pytest.mark.parametrize(
        "missing_field,credentials",
        [
            (
                "email",
                {"user_email_context": None, "api_token": "token"},
            ),
            (
                "api_token",
                {"user_email_context": None, "user_email": "user@example.com"},
            ),
        ],
    )
    def test_basic_auth_missing_credentials(
        self, config_factory, missing_field, credentials
    ):
        """Test that missing email or api_token raises ValueError."""
        base_config = config_factory.create_jira_config(auth_type="basic")

        with pytest.raises(ValueError, match="Email and API token missing"):
            _create_user_config_for_fetcher(
                base_config=base_config,
                auth_type="basic",
                credentials=credentials,
            )

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_jira_basic_auth_fetcher_creation(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ):
        """Test creating user-specific JiraFetcher with basic auth."""
        # Setup request state for basic auth
        mock_request.state.jira_fetcher = None
        mock_request.state.confluence_fetcher = None
        mock_request.state.atlassian_service_headers = {}
        mock_request.state.user_atlassian_auth_type = "basic"
        mock_request.state.user_atlassian_email = "user@example.com"
        mock_request.state.user_atlassian_api_token = "user-api-token"
        mock_request.state.user_atlassian_token = None
        mock_request.state.user_atlassian_cloud_id = None
        mock_get_http_request.return_value = mock_request

        # Setup context with global config
        app_context = config_factory.create_app_context()
        _setup_mock_context(mock_context, app_context)

        # Setup mock fetcher
        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        result = await get_jira_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.jira_fetcher == mock_fetcher
        mock_jira_fetcher_class.assert_called_once()

        called_config = mock_jira_fetcher_class.call_args[1]["config"]
        assert called_config.auth_type == "basic"
        assert called_config.username == "user@example.com"
        assert called_config.api_token == "user-api-token"

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_confluence_basic_auth_fetcher_creation(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ):
        """Test creating user-specific ConfluenceFetcher with basic auth."""
        mock_request.state.jira_fetcher = None
        mock_request.state.confluence_fetcher = None
        mock_request.state.atlassian_service_headers = {}
        mock_request.state.user_atlassian_auth_type = "basic"
        mock_request.state.user_atlassian_email = "user@example.com"
        mock_request.state.user_atlassian_api_token = "user-api-token"
        mock_request.state.user_atlassian_token = None
        mock_request.state.user_atlassian_cloud_id = None
        mock_get_http_request.return_value = mock_request

        app_context = config_factory.create_app_context()
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.return_value = mock_fetcher

        result = await get_confluence_fetcher(mock_context)

        assert result == mock_fetcher
        assert mock_request.state.confluence_fetcher == mock_fetcher
        mock_confluence_fetcher_class.assert_called_once()

        called_config = mock_confluence_fetcher_class.call_args[1]["config"]
        assert called_config.auth_type == "basic"
        assert called_config.username == "user@example.com"
        assert called_config.api_token == "user-api-token"

    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    async def test_basic_auth_empty_email_raises(
        self,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ):
        """Test that empty email with basic auth raises ValueError."""
        mock_request.state.jira_fetcher = None
        mock_request.state.confluence_fetcher = None
        mock_request.state.atlassian_service_headers = {}
        mock_request.state.user_atlassian_auth_type = "basic"
        mock_request.state.user_atlassian_email = None  # Empty
        mock_request.state.user_atlassian_api_token = "user-api-token"
        mock_request.state.user_atlassian_token = None
        mock_request.state.user_atlassian_cloud_id = None
        mock_get_http_request.return_value = mock_request

        app_context = config_factory.create_app_context()
        _setup_mock_context(mock_context, app_context)

        with pytest.raises(ValueError, match="email or API token missing"):
            await get_jira_fetcher(mock_context)


class TestResolveBearerAuthType:
    """Tests for _resolve_bearer_auth_type bearer token disambiguation."""

    def test_bearer_fallback_to_pat_when_no_oauth_config(self):
        """Bearer token treated as PAT when global config has no oauth_config."""
        config = JiraConfig(
            url="https://jira.corp.example.com",
            auth_type="pat",
            personal_token="server-pat",
        )
        result = _resolve_bearer_auth_type(config, "oauth")
        assert result == "pat"

    def test_bearer_with_cloud_id_stays_oauth(self):
        """Bearer token stays as OAuth when global config has cloud_id."""
        oauth_config = OAuthConfig(
            client_id="c",
            client_secret="s",
            redirect_uri="r",
            scope="sc",
            cloud_id="cloud-123",
        )
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=oauth_config,
        )
        result = _resolve_bearer_auth_type(config, "oauth")
        assert result == "oauth"

    def test_bearer_with_dc_base_url_stays_oauth(self):
        """Bearer token stays as OAuth when global config has DC base_url."""
        oauth_config = OAuthConfig(
            client_id="c",
            client_secret="s",
            redirect_uri="r",
            scope="sc",
            base_url="https://jira.corp.com",
        )
        config = JiraConfig(
            url="https://jira.corp.com",
            auth_type="oauth",
            oauth_config=oauth_config,
        )
        result = _resolve_bearer_auth_type(config, "oauth")
        assert result == "oauth"

    def test_bearer_with_header_cloud_id_stays_oauth(self):
        """Bearer token stays as OAuth when per-request cloud_id is provided."""
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="basic",
            username="user",
            api_token="token",
        )
        result = _resolve_bearer_auth_type(config, "oauth", cloud_id="from-header")
        assert result == "oauth"

    def test_pat_auth_type_passes_through(self):
        """PAT auth_type is never re-mapped."""
        config = JiraConfig(
            url="https://jira.corp.example.com",
            auth_type="pat",
            personal_token="server-pat",
        )
        result = _resolve_bearer_auth_type(config, "pat")
        assert result == "pat"

    def test_confluence_bearer_fallback_to_pat(self):
        """Bearer disambiguation works for Confluence configs too."""
        config = ConfluenceConfig(
            url="https://confluence.corp.example.com",
            auth_type="pat",
            personal_token="server-pat",
        )
        result = _resolve_bearer_auth_type(config, "oauth")
        assert result == "pat"

    def test_minimal_oauth_config_bearer_fallback_to_pat(self):
        """Regression: ATLASSIAN_OAUTH_ENABLE=true with no cloud_id creates
        minimal OAuth config. Bearer token should fall back to PAT (#858)."""
        # Minimal OAuth config: empty strings, no cloud_id, no base_url
        minimal_oauth = OAuthConfig(
            client_id="",
            client_secret="",
            redirect_uri="",
            scope="",
        )
        config = JiraConfig(
            url="https://jira.corp.example.com",
            auth_type="oauth",
            oauth_config=minimal_oauth,
        )
        result = _resolve_bearer_auth_type(config, "oauth")
        assert result == "pat"


class TestSsrfProtection:
    """SSRF protection regression tests."""

    def test_validate_rejects_private_ip(self) -> None:
        """Private IP URLs are rejected by SSRF validation."""
        from mcp_atlassian.utils.urls import validate_url_for_ssrf

        result = validate_url_for_ssrf("http://127.0.0.1:8080")
        assert result is not None

    def test_validate_rejects_metadata(self) -> None:
        """Cloud metadata endpoint is rejected."""
        from mcp_atlassian.utils.urls import validate_url_for_ssrf

        result = validate_url_for_ssrf("http://169.254.169.254")
        assert result is not None

    def test_validate_rejects_file_scheme(self) -> None:
        """file:// scheme is rejected."""
        from mcp_atlassian.utils.urls import validate_url_for_ssrf

        result = validate_url_for_ssrf("file:///etc/passwd")
        assert result is not None

    def test_redirect_hook_blocks_internal(self) -> None:
        """Redirect to internal IP is blocked by SSRF hook."""
        from mcp_atlassian.servers.dependencies import _make_ssrf_safe_hook
        from mcp_atlassian.utils.urls import validate_url_for_ssrf

        hook = _make_ssrf_safe_hook(validate_url_for_ssrf)

        # Create a mock response that simulates a redirect
        mock_response = MagicMock()
        mock_response.is_redirect = True
        mock_response.headers = {"Location": "http://169.254.169.254/latest/meta-data"}

        with pytest.raises(ValueError, match="Redirect blocked"):
            hook(mock_response)

    def test_redirect_hook_allows_safe(self) -> None:
        """Redirect to safe URL passes through."""
        from mcp_atlassian.servers.dependencies import _make_ssrf_safe_hook
        from mcp_atlassian.utils.urls import validate_url_for_ssrf

        hook = _make_ssrf_safe_hook(validate_url_for_ssrf)

        mock_response = MagicMock()
        mock_response.is_redirect = True
        mock_response.headers = {
            "Location": "https://company.atlassian.net/rest/api/2/issue"
        }

        # Mock DNS for the redirect target
        with patch("mcp_atlassian.utils.urls.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("104.192.141.1", 0))]
            result = hook(mock_response)
            assert result == mock_response

    def test_redirect_hook_ignores_non_redirect(self) -> None:
        """Non-redirect response passes through without checks."""
        from mcp_atlassian.servers.dependencies import _make_ssrf_safe_hook
        from mcp_atlassian.utils.urls import validate_url_for_ssrf

        hook = _make_ssrf_safe_hook(validate_url_for_ssrf)

        mock_response = MagicMock()
        mock_response.is_redirect = False

        result = hook(mock_response)
        assert result == mock_response


class TestSsrfHookCoverageRegression:
    """Regression (GHSA-6529) — the SSRF redirect hook must cover the basic-auth
    and OAuth per-user fetcher sessions, not only the header-PAT branch.

    ``_create_and_validate`` used to pass ``attach_ssrf_hook=True`` only on the
    header-PAT branch; the basic and oauth_pat branches omitted it, so per-user
    fetchers built from those branches followed HTTP redirects without SSRF
    validation. These tests assert the secure outcome: a redirect hook is attached
    to the fetcher's session on every auth branch.
    """

    @pytest.mark.security_regression
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_basic_auth_jira_session_has_ssrf_hook(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ) -> None:
        """A basic-auth Jira fetcher must follow redirects through the SSRF hook."""
        mock_request.state.jira_fetcher = None
        mock_request.state.confluence_fetcher = None
        mock_request.state.atlassian_service_headers = {}
        mock_request.state.user_atlassian_auth_type = "basic"
        mock_request.state.user_atlassian_email = "user@example.com"
        mock_request.state.user_atlassian_api_token = "user-api-token"
        mock_request.state.user_atlassian_token = None
        mock_request.state.user_atlassian_cloud_id = None
        mock_get_http_request.return_value = mock_request

        app_context = config_factory.create_app_context()
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        await get_jira_fetcher(mock_context)

        response_hooks = mock_fetcher.jira._session.hooks["response"]
        assert len(response_hooks) > 0, (
            "basic-auth user fetcher session must carry the SSRF redirect hook"
        )

    @pytest.mark.security_regression
    @patch("mcp_atlassian.servers.dependencies.get_access_token")
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_oauth_jira_session_has_ssrf_hook(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_get_access_token,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
    ) -> None:
        """An OAuth Jira fetcher must follow redirects through the SSRF hook."""
        _setup_mock_request_state(mock_request, auth_scenarios["oauth"])
        mock_get_http_request.return_value = mock_request
        mock_get_access_token.side_effect = RuntimeError("no auth context")

        app_context = config_factory.create_app_context(
            jira_config=config_factory.create_jira_config(auth_type="oauth")
        )
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(JiraFetcher)
        mock_jira_fetcher_class.return_value = mock_fetcher

        await get_jira_fetcher(mock_context)

        response_hooks = mock_fetcher.jira._session.hooks["response"]
        assert len(response_hooks) > 0, (
            "oauth user fetcher session must carry the SSRF redirect hook"
        )

    @pytest.mark.security_regression
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_basic_auth_confluence_session_has_ssrf_hook(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ) -> None:
        """A basic-auth Confluence fetcher must follow redirects through the hook."""
        mock_request.state.jira_fetcher = None
        mock_request.state.confluence_fetcher = None
        mock_request.state.atlassian_service_headers = {}
        mock_request.state.user_atlassian_auth_type = "basic"
        mock_request.state.user_atlassian_email = "user@example.com"
        mock_request.state.user_atlassian_api_token = "user-api-token"
        mock_request.state.user_atlassian_token = None
        mock_request.state.user_atlassian_cloud_id = None
        mock_get_http_request.return_value = mock_request

        app_context = config_factory.create_app_context()
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.return_value = mock_fetcher

        await get_confluence_fetcher(mock_context)

        response_hooks = mock_fetcher.confluence._session.hooks["response"]
        assert len(response_hooks) > 0, (
            "basic-auth user fetcher session must carry the SSRF redirect hook"
        )

    @pytest.mark.security_regression
    @patch("mcp_atlassian.servers.dependencies.get_access_token")
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_oauth_confluence_session_has_ssrf_hook(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_get_access_token,
        mock_context,
        mock_request,
        config_factory,
        auth_scenarios,
    ) -> None:
        """An OAuth Confluence fetcher must follow redirects through the hook."""
        _setup_mock_request_state(mock_request, auth_scenarios["oauth"])
        mock_get_http_request.return_value = mock_request
        mock_get_access_token.side_effect = RuntimeError("no auth context")

        app_context = config_factory.create_app_context(
            confluence_config=config_factory.create_confluence_config(auth_type="oauth")
        )
        _setup_mock_context(mock_context, app_context)

        mock_fetcher = _create_mock_fetcher(ConfluenceFetcher)
        mock_confluence_fetcher_class.return_value = mock_fetcher

        await get_confluence_fetcher(mock_context)

        response_hooks = mock_fetcher.confluence._session.hooks["response"]
        assert len(response_hooks) > 0, (
            "oauth user fetcher session must carry the SSRF redirect hook"
        )


class TestUnauthenticatedGlobalFallbackRegression:
    """Regression (GHSA-wrhw, GHSA-vc8m, GHSA-cc5h auth half) — an unauthenticated
    HTTP request must not silently fall back to the operator's global credentials.

    In an HTTP request context with no user identity, ``_get_fetcher`` used to fall
    through to the global fallback and return
    ``spec.fetcher_class(config=global_config_fallback)`` unconditionally, so any
    unauthenticated caller on a remotely-exposed streamable-http server transacted
    as the operator. These tests assert the secure outcome: the global fallback is
    refused for unauthenticated HTTP requests unless ``ALLOW_GLOBAL_CRED_FALLBACK``
    is explicitly enabled.

    The companion ``test_global_fallback_scenarios`` above pins the authenticated
    fallback behavior (returns the global fetcher), so a failure here is genuinely
    the unauthenticated fallback firing, not an incidental setup error. The
    assertion uses ``pytest.raises``: the fix refuses by raising.
    """

    @pytest.mark.security_regression
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.JiraFetcher")
    async def test_unauthenticated_http_request_refuses_global_jira_fetcher(
        self,
        mock_jira_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ) -> None:
        """No user identity + HTTP context must not yield the global Jira fetcher."""
        _setup_mock_request_state(mock_request)  # no scenario -> no user identity
        mock_get_http_request.return_value = mock_request
        app_context = config_factory.create_app_context()
        _setup_mock_context(mock_context, app_context)
        mock_jira_fetcher_class.return_value = _create_mock_fetcher(JiraFetcher)

        with pytest.raises(ValueError):
            await get_jira_fetcher(mock_context)

    @pytest.mark.security_regression
    @patch("mcp_atlassian.servers.dependencies.get_http_request")
    @patch("mcp_atlassian.servers.dependencies.ConfluenceFetcher")
    async def test_unauthenticated_http_request_refuses_global_confluence_fetcher(
        self,
        mock_confluence_fetcher_class,
        mock_get_http_request,
        mock_context,
        mock_request,
        config_factory,
    ) -> None:
        """No user identity + HTTP context must not yield the global Confluence fetcher."""
        _setup_mock_request_state(mock_request)  # no scenario -> no user identity
        mock_get_http_request.return_value = mock_request
        app_context = config_factory.create_app_context()
        _setup_mock_context(mock_context, app_context)
        mock_confluence_fetcher_class.return_value = _create_mock_fetcher(
            ConfluenceFetcher
        )

        with pytest.raises(ValueError):
            await get_confluence_fetcher(mock_context)
