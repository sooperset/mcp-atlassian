"""Tests for external auth passthrough mode (ATLASSIAN_EXTERNAL_AUTH_ENABLE)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from starlette.datastructures import Headers

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.environment import get_available_services

pytestmark = pytest.mark.anyio

# ---------------------------------------------------------------------------
# Config tests — JiraConfig
# ---------------------------------------------------------------------------


class TestJiraConfigExternalAuth:
    def test_from_env_with_url_creates_external_auth_type(self):
        """from_env() produces auth_type='external' when flag is set and no creds."""
        with patch.dict(
            os.environ,
            {
                "ATLASSIAN_EXTERNAL_AUTH_ENABLE": "true",
                "JIRA_URL": "https://jira.example.com",
            },
            clear=True,
        ):
            config = JiraConfig.from_env()
            assert config.auth_type == "external"
            assert config.url == "https://jira.example.com"
            assert config.username is None
            assert config.api_token is None
            assert config.personal_token is None
            assert config.oauth_config is None

    def test_from_env_without_url_creates_external_auth_type(self):
        """from_env() allows missing JIRA_URL when ATLASSIAN_EXTERNAL_AUTH_ENABLE=true."""
        with patch.dict(
            os.environ,
            {"ATLASSIAN_EXTERNAL_AUTH_ENABLE": "true"},
            clear=True,
        ):
            config = JiraConfig.from_env()
            assert config.auth_type == "external"
            assert config.url == ""

    def test_is_auth_configured_returns_true_for_external(self):
        """is_auth_configured() returns True for external auth type."""
        config = JiraConfig(url="https://jira.example.com", auth_type="external")
        assert config.is_auth_configured() is True

    def test_external_auth_ignored_when_credentials_present(self):
        """Explicit credentials take precedence over ATLASSIAN_EXTERNAL_AUTH_ENABLE."""
        with patch.dict(
            os.environ,
            {
                "ATLASSIAN_EXTERNAL_AUTH_ENABLE": "true",
                "JIRA_URL": "https://jira.example.com",
                "JIRA_PERSONAL_TOKEN": "mytoken",
            },
            clear=True,
        ):
            config = JiraConfig.from_env()
            # PAT is present → should use PAT, not external
            assert config.auth_type == "pat"
            assert config.personal_token == "mytoken"

    def test_is_cloud_with_external_auth_and_cloud_url(self):
        """is_cloud is True when URL is a cloud URL, even with external auth."""
        config = JiraConfig(
            url="https://company.atlassian.net",
            auth_type="external",
        )
        assert config.is_cloud is True

    def test_is_cloud_with_external_auth_and_server_url(self):
        """is_cloud is False when URL is a server URL with external auth."""
        config = JiraConfig(
            url="https://jira.example.com",
            auth_type="external",
        )
        assert config.is_cloud is False

    def test_is_cloud_with_external_auth_and_no_url(self):
        """is_cloud defaults to False when URL is empty with external auth."""
        config = JiraConfig(url="", auth_type="external")
        assert config.is_cloud is False


# ---------------------------------------------------------------------------
# Config tests — ConfluenceConfig
# ---------------------------------------------------------------------------


class TestConfluenceConfigExternalAuth:
    def test_from_env_with_url_creates_external_auth_type(self):
        """from_env() produces auth_type='external' when flag is set and no creds."""
        with patch.dict(
            os.environ,
            {
                "ATLASSIAN_EXTERNAL_AUTH_ENABLE": "true",
                "CONFLUENCE_URL": "https://confluence.example.com",
            },
            clear=True,
        ):
            config = ConfluenceConfig.from_env()
            assert config.auth_type == "external"
            assert config.url == "https://confluence.example.com"
            assert config.username is None
            assert config.api_token is None
            assert config.personal_token is None
            assert config.oauth_config is None

    def test_from_env_without_url_creates_external_auth_type(self):
        """from_env() allows missing CONFLUENCE_URL when external auth is enabled."""
        with patch.dict(
            os.environ,
            {"ATLASSIAN_EXTERNAL_AUTH_ENABLE": "true"},
            clear=True,
        ):
            config = ConfluenceConfig.from_env()
            assert config.auth_type == "external"
            assert config.url == ""

    def test_is_auth_configured_returns_true_for_external(self):
        """is_auth_configured() returns True for external auth type."""
        config = ConfluenceConfig(
            url="https://confluence.example.com", auth_type="external"
        )
        assert config.is_auth_configured() is True

    def test_external_auth_ignored_when_credentials_present(self):
        """Explicit credentials take precedence over ATLASSIAN_EXTERNAL_AUTH_ENABLE."""
        with patch.dict(
            os.environ,
            {
                "ATLASSIAN_EXTERNAL_AUTH_ENABLE": "true",
                "CONFLUENCE_URL": "https://confluence.example.com",
                "CONFLUENCE_PERSONAL_TOKEN": "mytoken",
            },
            clear=True,
        ):
            config = ConfluenceConfig.from_env()
            assert config.auth_type == "pat"
            assert config.personal_token == "mytoken"


# ---------------------------------------------------------------------------
# Client tests — JiraClient
# ---------------------------------------------------------------------------


class TestJiraClientExternalAuth:
    def test_init_external_auth_no_authorization_header(self):
        """JiraClient with external auth does not set an Authorization header."""
        with (
            patch("mcp_atlassian.jira.client.Jira") as mock_jira_cls,
            patch("mcp_atlassian.jira.client.configure_ssl_verification"),
        ):
            mock_session = MagicMock()
            mock_session.headers = {}
            mock_jira_instance = MagicMock()
            mock_jira_instance._session = mock_session
            mock_jira_cls.return_value = mock_jira_instance

            config = JiraConfig(
                url="https://jira.example.com",
                auth_type="external",
            )
            JiraClient(config=config)

            # Jira should be instantiated with a session but no credential kwargs
            call_kwargs = mock_jira_cls.call_args.kwargs
            assert "username" not in call_kwargs
            assert "password" not in call_kwargs
            assert "token" not in call_kwargs
            # Authorization header should be removed
            assert "Authorization" not in mock_session.headers

    def test_init_external_auth_skips_validation(self):
        """JiraClient with external auth skips _validate_authentication."""
        with (
            patch("mcp_atlassian.jira.client.Jira") as mock_jira_cls,
            patch("mcp_atlassian.jira.client.configure_ssl_verification"),
            patch("logging.Logger.isEnabledFor", return_value=True),
        ):
            mock_session = MagicMock()
            mock_session.headers = {}
            mock_jira_instance = MagicMock()
            mock_jira_instance._session = mock_session
            mock_jira_cls.return_value = mock_jira_instance

            config = JiraConfig(
                url="https://jira.example.com",
                auth_type="external",
            )
            with patch.object(JiraClient, "_validate_authentication") as mock_validate:
                JiraClient(config=config)
                mock_validate.assert_not_called()


# ---------------------------------------------------------------------------
# Client tests — ConfluenceClient
# ---------------------------------------------------------------------------


class TestConfluenceClientExternalAuth:
    def test_init_external_auth_no_authorization_header(self):
        """ConfluenceClient with external auth does not set an Authorization header."""
        with (
            patch("mcp_atlassian.confluence.client.Confluence") as mock_conf_cls,
            patch("mcp_atlassian.confluence.client.configure_ssl_verification"),
        ):
            mock_session = MagicMock()
            mock_session.headers = {}
            mock_conf_instance = MagicMock()
            mock_conf_instance._session = mock_session
            mock_conf_cls.return_value = mock_conf_instance

            config = ConfluenceConfig(
                url="https://confluence.example.com",
                auth_type="external",
            )
            ConfluenceClient(config=config)

            call_kwargs = mock_conf_cls.call_args.kwargs
            assert "username" not in call_kwargs
            assert "password" not in call_kwargs
            assert "token" not in call_kwargs
            assert "Authorization" not in mock_session.headers

    def test_init_external_auth_skips_validation(self):
        """ConfluenceClient with external auth skips _validate_authentication."""
        with (
            patch("mcp_atlassian.confluence.client.Confluence") as mock_conf_cls,
            patch("mcp_atlassian.confluence.client.configure_ssl_verification"),
            patch("logging.Logger.isEnabledFor", return_value=True),
        ):
            mock_session = MagicMock()
            mock_session.headers = {}
            mock_conf_instance = MagicMock()
            mock_conf_instance._session = mock_session
            mock_conf_cls.return_value = mock_conf_instance

            config = ConfluenceConfig(
                url="https://confluence.example.com",
                auth_type="external",
            )
            with patch.object(
                ConfluenceClient, "_validate_authentication"
            ) as mock_validate:
                ConfluenceClient(config=config)
                mock_validate.assert_not_called()


# ---------------------------------------------------------------------------
# get_available_services
# ---------------------------------------------------------------------------


class TestGetAvailableServicesExternalAuth:
    def test_both_services_available_with_only_flag(self):
        """Both services are available when ATLASSIAN_EXTERNAL_AUTH_ENABLE=true."""
        with patch.dict(
            os.environ,
            {"ATLASSIAN_EXTERNAL_AUTH_ENABLE": "true"},
            clear=True,
        ):
            result = get_available_services()
            assert result["jira"] is True
            assert result["confluence"] is True

    def test_flag_with_urls_marks_services_available(self):
        """Services with URLs and external-auth flag are reported as available."""
        with patch.dict(
            os.environ,
            {
                "ATLASSIAN_EXTERNAL_AUTH_ENABLE": "true",
                "JIRA_URL": "https://jira.example.com",
                "CONFLUENCE_URL": "https://confluence.example.com",
            },
            clear=True,
        ):
            result = get_available_services()
            assert result["jira"] is True
            assert result["confluence"] is True

    def test_flag_absent_services_not_available(self):
        """Without the flag and without credentials, services are not available."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_available_services()
            assert result["jira"] is False
            assert result["confluence"] is False


# ---------------------------------------------------------------------------
# _get_fetcher — global fallback with external auth
# ---------------------------------------------------------------------------


class TestGetFetcherExternalAuth:
    """Tests for the global-fallback path in _get_fetcher with external auth."""

    def _make_request(
        self,
        headers: dict[str, str] | None = None,
        state_overrides: dict[str, Any] | None = None,
    ) -> MagicMock:
        """Build a minimal mock Starlette request."""
        request = MagicMock()
        raw_headers = {k.lower(): v for k, v in (headers or {}).items()}
        # Starlette Headers are case-insensitive; mimic with a dict subclass
        request.headers = Headers(
            raw=[(k.encode(), v.encode()) for k, v in raw_headers.items()]
        )
        # Use SimpleNamespace so unset attributes raise AttributeError,
        # making getattr(..., None) return None instead of a truthy MagicMock.
        state = SimpleNamespace(
            user_atlassian_auth_type=None,
            atlassian_service_headers={},
            user_atlassian_email=None,
            user_atlassian_cloud_id=None,
            auth_validation_error=None,
        )
        for key, val in (state_overrides or {}).items():
            setattr(state, key, val)
        request.state = state
        return request

    def _make_context(self, jira_config: JiraConfig) -> MagicMock:
        """Build a minimal mock FastMCP context with a MainAppContext."""
        from mcp_atlassian.servers.context import MainAppContext

        app_ctx = MainAppContext(
            full_jira_config=jira_config,
            full_confluence_config=None,
            read_only=False,
            enabled_tools=None,
            enabled_toolsets=set(),
        )
        ctx = MagicMock()
        ctx.request_context.lifespan_context = {"app_lifespan_context": app_ctx}
        return ctx

    async def test_url_from_header_used_when_config_url_empty(self):
        """Per-request Jira URL header is applied when config.url is empty."""
        from mcp_atlassian.servers.dependencies import get_jira_fetcher

        base_config = JiraConfig(url="", auth_type="external")
        ctx = self._make_context(base_config)
        request = self._make_request(
            headers={"X-Atlassian-Jira-Url": "https://jira.example.com"}
        )

        with (
            patch.dict(
                os.environ,
                {"MCP_ALLOWED_URL_DOMAINS": "example.com"},
                clear=False,
            ),
            patch(
                "mcp_atlassian.servers.dependencies.get_http_request",
                return_value=request,
            ),
            patch(
                "mcp_atlassian.servers.dependencies.validate_url_for_ssrf",
                return_value=None,  # no SSRF issue
            ),
            patch("mcp_atlassian.servers.dependencies.JiraFetcher") as mock_fetcher_cls,
        ):
            mock_fetcher_cls.return_value = MagicMock()
            await get_jira_fetcher(ctx)

            called_config = mock_fetcher_cls.call_args.kwargs["config"]
            assert called_config.url == "https://jira.example.com"
            assert called_config.auth_type == "external"

    async def test_url_from_header_requires_domain_allowlist(self):
        """Dynamic external-auth URLs require an operator domain allowlist."""
        from mcp_atlassian.servers.dependencies import get_jira_fetcher

        base_config = JiraConfig(url="", auth_type="external")
        ctx = self._make_context(base_config)
        request = self._make_request(
            headers={"X-Atlassian-Jira-Url": "https://jira.example.com"}
        )

        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "mcp_atlassian.servers.dependencies.get_http_request",
                return_value=request,
            ),
        ):
            with pytest.raises(ValueError, match="MCP_ALLOWED_URL_DOMAINS"):
                await get_jira_fetcher(ctx)

    async def test_url_from_env_used_when_config_url_set(self):
        """When config URL is already set, no header override occurs."""
        from mcp_atlassian.servers.dependencies import get_jira_fetcher

        base_config = JiraConfig(url="https://jira.company.com", auth_type="external")
        ctx = self._make_context(base_config)
        request = self._make_request(
            # Header present but should NOT override env-configured URL
            headers={"X-Atlassian-Jira-Url": "https://other.example.com"}
        )

        with (
            patch(
                "mcp_atlassian.servers.dependencies.get_http_request",
                return_value=request,
            ),
            patch(
                "mcp_atlassian.servers.dependencies.validate_url_for_ssrf",
                return_value=None,
            ),
            patch("mcp_atlassian.servers.dependencies.JiraFetcher") as mock_fetcher_cls,
        ):
            mock_fetcher_cls.return_value = MagicMock()
            await get_jira_fetcher(ctx)

            called_config = mock_fetcher_cls.call_args.kwargs["config"]
            assert called_config.url == "https://jira.company.com"

    async def test_missing_url_header_raises_value_error(self):
        """ValueError raised when external auth has no URL from env or header."""
        from mcp_atlassian.servers.dependencies import get_jira_fetcher

        base_config = JiraConfig(url="", auth_type="external")
        ctx = self._make_context(base_config)
        request = self._make_request()  # no URL header

        with (
            patch(
                "mcp_atlassian.servers.dependencies.get_http_request",
                return_value=request,
            ),
        ):
            with pytest.raises(ValueError, match="Jira URL is not configured"):
                await get_jira_fetcher(ctx)

    async def test_passthrough_header_forwarded_to_fetcher(self):
        """Passthrough headers are merged into the config for external auth."""
        from mcp_atlassian.servers.dependencies import get_jira_fetcher

        base_config = JiraConfig(
            url="https://jira.example.com",
            auth_type="external",
            passthrough_headers=["Cookie"],
        )
        ctx = self._make_context(base_config)
        request = self._make_request(headers={"Cookie": "session=abc123"})

        with (
            patch(
                "mcp_atlassian.servers.dependencies.get_http_request",
                return_value=request,
            ),
            patch(
                "mcp_atlassian.servers.dependencies.validate_url_for_ssrf",
                return_value=None,
            ),
            patch("mcp_atlassian.servers.dependencies.JiraFetcher") as mock_fetcher_cls,
        ):
            mock_fetcher_cls.return_value = MagicMock()
            await get_jira_fetcher(ctx)

            called_config = mock_fetcher_cls.call_args.kwargs["config"]
            assert called_config.custom_headers is not None
            assert called_config.custom_headers.get("Cookie") == "session=abc123"

    async def test_ssrf_blocked_url_raises_value_error(self):
        """A private/SSRF URL supplied via header is rejected."""
        from mcp_atlassian.servers.dependencies import get_jira_fetcher

        base_config = JiraConfig(url="", auth_type="external")
        ctx = self._make_context(base_config)
        request = self._make_request(
            headers={"X-Atlassian-Jira-Url": "http://169.254.169.254/latest/meta-data"}
        )

        with (
            patch.dict(
                os.environ,
                {"MCP_ALLOWED_URL_DOMAINS": "example.com"},
                clear=False,
            ),
            patch(
                "mcp_atlassian.servers.dependencies.get_http_request",
                return_value=request,
            ),
        ):
            with pytest.raises(ValueError, match="Forbidden"):
                await get_jira_fetcher(ctx)
