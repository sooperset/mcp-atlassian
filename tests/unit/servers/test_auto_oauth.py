"""Tests for the auto-OAuth browser flow triggered during server startup."""

import os
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_atlassian.servers.main import _try_auto_oauth, main_lifespan
from mcp_atlassian.utils.oauth import BYOAccessTokenOAuthConfig, OAuthConfig
from tests.utils.mocks import MockEnvironment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_oauth_config(
    *,
    client_id: str = "cid",
    client_secret: str = "csec",
    redirect_uri: str = "http://localhost:8080/callback",
    scope: str = "WRITE",
    access_token: str | None = None,
    refresh_token: str | None = None,
    base_url: str | None = None,
) -> OAuthConfig:
    cfg = OAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        access_token=access_token,
        base_url=base_url,
    )
    cfg.refresh_token = refresh_token
    return cfg


@dataclass
class _StubConfig:
    """Minimal stand-in for JiraConfig / ConfluenceConfig."""

    auth_type: str
    oauth_config: OAuthConfig | BYOAccessTokenOAuthConfig | None = None


FLOW_PATCH = "mcp_atlassian.utils.oauth_setup.run_oauth_flow"


# ---------------------------------------------------------------------------
# _try_auto_oauth predicate (early-return when auto-OAuth not needed)
# ---------------------------------------------------------------------------


class TestTryAutoOAuthPredicate:
    """Tests for the predicate logic inside _try_auto_oauth (skips vs triggers)."""

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_triggers_when_oauth_creds_present_no_tokens(self, mock_flow):
        mock_flow.return_value = True
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(),
        )
        result = await _try_auto_oauth(cfg, "Jira")
        assert result is True
        mock_flow.assert_called_once()

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_skips_when_access_token_already_present(self, mock_flow):
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(access_token="tok"),
        )
        result = await _try_auto_oauth(cfg, "Jira")
        assert result is False
        mock_flow.assert_not_called()

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_skips_for_basic_auth(self, mock_flow):
        cfg = _StubConfig(auth_type="basic", oauth_config=None)
        result = await _try_auto_oauth(cfg, "Jira")
        assert result is False
        mock_flow.assert_not_called()

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_skips_for_pat_auth(self, mock_flow):
        cfg = _StubConfig(auth_type="pat", oauth_config=None)
        result = await _try_auto_oauth(cfg, "Jira")
        assert result is False
        mock_flow.assert_not_called()

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_skips_when_client_id_missing(self, mock_flow):
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(client_id=""),
        )
        result = await _try_auto_oauth(cfg, "Jira")
        assert result is False
        mock_flow.assert_not_called()

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_skips_when_client_secret_missing(self, mock_flow):
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(client_secret=""),
        )
        result = await _try_auto_oauth(cfg, "Jira")
        assert result is False
        mock_flow.assert_not_called()

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_skips_for_byo_token_config(self, mock_flow):
        byo = BYOAccessTokenOAuthConfig(access_token="byo-tok")
        cfg = _StubConfig(auth_type="oauth", oauth_config=byo)
        result = await _try_auto_oauth(cfg, "Jira")
        assert result is False
        mock_flow.assert_not_called()

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_skips_when_oauth_config_is_none(self, mock_flow):
        cfg = _StubConfig(auth_type="oauth", oauth_config=None)
        result = await _try_auto_oauth(cfg, "Jira")
        assert result is False
        mock_flow.assert_not_called()

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_skips_when_refresh_token_present(self, mock_flow):
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(refresh_token="rt"),
        )
        result = await _try_auto_oauth(cfg, "Jira")
        assert result is False
        mock_flow.assert_not_called()

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_triggers_for_dc_oauth_without_tokens(self, mock_flow):
        mock_flow.return_value = True
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(
                base_url="https://jira.corp.example.com",
            ),
        )
        result = await _try_auto_oauth(cfg, "Jira")
        assert result is True
        mock_flow.assert_called_once()

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_triggers_for_cloud_oauth_with_cloud_id_no_tokens(self, mock_flow):
        """Cloud OAuth with cloud_id set but no tokens should trigger auto-oauth."""
        mock_flow.return_value = True
        oauth_cfg = _make_oauth_config(
            client_id="cloud-cid",
            client_secret="cloud-csec",
            scope="read:jira-work offline_access",
        )
        oauth_cfg.cloud_id = "test-cloud-id"
        cfg = _StubConfig(auth_type="oauth", oauth_config=oauth_cfg)
        result = await _try_auto_oauth(cfg, "Jira")
        assert result is True
        mock_flow.assert_called_once()


# ---------------------------------------------------------------------------
# _try_auto_oauth
# ---------------------------------------------------------------------------


class TestTryAutoOAuth:
    """Tests for the async _try_auto_oauth helper."""

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_returns_true_on_success(self, mock_flow):
        mock_flow.return_value = True
        cfg = _StubConfig(auth_type="oauth", oauth_config=_make_oauth_config())

        result = await _try_auto_oauth(cfg, "Jira")

        assert result is True
        mock_flow.assert_called_once()
        args = mock_flow.call_args[0][0]
        assert args.client_id == "cid"
        assert args.client_secret == "csec"
        assert args.redirect_uri == "http://localhost:8080/callback"
        assert args.scope == "WRITE"
        assert args.base_url is None

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_returns_false_on_failure(self, mock_flow):
        mock_flow.return_value = False
        cfg = _StubConfig(auth_type="oauth", oauth_config=_make_oauth_config())

        result = await _try_auto_oauth(cfg, "Confluence")

        assert result is False
        mock_flow.assert_called_once()

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_passes_dc_base_url(self, mock_flow):
        mock_flow.return_value = True
        dc_url = "https://jira.corp.example.com"
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(base_url=dc_url),
        )

        await _try_auto_oauth(cfg, "Jira")

        args = mock_flow.call_args[0][0]
        assert args.base_url == dc_url

    @pytest.mark.asyncio
    @patch(FLOW_PATCH)
    async def test_flow_exception_returns_false(self, mock_flow):
        mock_flow.side_effect = RuntimeError("port in use")
        cfg = _StubConfig(auth_type="oauth", oauth_config=_make_oauth_config())

        result = await _try_auto_oauth(cfg, "Jira")

        assert result is False
        mock_flow.assert_called_once()


# ---------------------------------------------------------------------------
# main_lifespan integration (auto-OAuth branches)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
class TestLifespanAutoOAuth:
    """Integration tests for main_lifespan auto-OAuth branching."""

    async def test_jira_auth_configured_auto_oauth_success(self):
        """Auth configured, auto-oauth, _try_auto_oauth succeeds; from_env twice."""
        env = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_USERNAME": "test@example.com",
            "JIRA_API_TOKEN": "test-token",
        }
        with patch.dict(os.environ, env, clear=False):
            with (
                patch(
                    "mcp_atlassian.jira.config.JiraConfig.from_env"
                ) as mock_jira_from_env,
                patch(
                    "mcp_atlassian.servers.main._try_auto_oauth",
                    new_callable=AsyncMock,
                ) as mock_try_auto_oauth,
            ):
                initial_config = MagicMock()
                initial_config.is_auth_configured.return_value = True
                initial_config.auth_type = "oauth"
                initial_config.oauth_config = _make_oauth_config()

                reloaded_config = MagicMock()
                reloaded_config.is_auth_configured.return_value = True
                reloaded_config.auth_type = "oauth"
                reloaded_config.oauth_config = _make_oauth_config(
                    access_token="new-tok"
                )

                mock_jira_from_env.side_effect = [initial_config, reloaded_config]
                mock_try_auto_oauth.return_value = True

                app = MagicMock()
                async with main_lifespan(app) as context:
                    app_context = context["app_lifespan_context"]
                    assert app_context.full_jira_config == reloaded_config

                assert mock_jira_from_env.call_count == 2
                mock_try_auto_oauth.assert_called_once()

    async def test_jira_auth_configured_auto_oauth_failure(self):
        """Auth configured, auto-oauth, _try_auto_oauth fails; config still set."""
        env = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_USERNAME": "test@example.com",
            "JIRA_API_TOKEN": "test-token",
        }
        with patch.dict(os.environ, env, clear=False):
            with (
                patch(
                    "mcp_atlassian.jira.config.JiraConfig.from_env"
                ) as mock_jira_from_env,
                patch(
                    "mcp_atlassian.servers.main._try_auto_oauth",
                    new_callable=AsyncMock,
                ) as mock_try_auto_oauth,
            ):
                jira_config = MagicMock()
                jira_config.is_auth_configured.return_value = True
                jira_config.auth_type = "oauth"
                jira_config.oauth_config = _make_oauth_config()

                mock_jira_from_env.return_value = jira_config
                mock_try_auto_oauth.return_value = False

                app = MagicMock()
                async with main_lifespan(app) as context:
                    app_context = context["app_lifespan_context"]
                    assert app_context.full_jira_config == jira_config

                mock_jira_from_env.assert_called_once()
                mock_try_auto_oauth.assert_called_once()

    async def test_jira_auth_not_configured_auto_oauth_succeeds(self):
        """Auth not configured, auto-oauth, _try_auto_oauth succeeds; config set."""
        env = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_USERNAME": "test@example.com",
            "JIRA_API_TOKEN": "test-token",
        }
        with patch.dict(os.environ, env, clear=False):
            with (
                patch(
                    "mcp_atlassian.jira.config.JiraConfig.from_env"
                ) as mock_jira_from_env,
                patch(
                    "mcp_atlassian.servers.main._try_auto_oauth",
                    new_callable=AsyncMock,
                ) as mock_try_auto_oauth,
            ):
                initial_config = MagicMock()
                initial_config.is_auth_configured.return_value = False
                initial_config.auth_type = "oauth"
                initial_config.oauth_config = _make_oauth_config()

                reloaded_config = MagicMock()
                reloaded_config.is_auth_configured.return_value = True
                reloaded_config.auth_type = "oauth"
                reloaded_config.oauth_config = _make_oauth_config(
                    access_token="new-tok"
                )

                mock_jira_from_env.side_effect = [initial_config, reloaded_config]
                mock_try_auto_oauth.return_value = True

                app = MagicMock()
                async with main_lifespan(app) as context:
                    app_context = context["app_lifespan_context"]
                    assert app_context.full_jira_config == reloaded_config

                assert mock_jira_from_env.call_count == 2
                mock_try_auto_oauth.assert_called_once()

    async def test_jira_auth_not_configured_auto_oauth_fails(self):
        """Auth not configured, needs auto-oauth, _try_auto_oauth fails; config None."""
        env = {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_USERNAME": "test@example.com",
            "JIRA_API_TOKEN": "test-token",
        }
        with patch.dict(os.environ, env, clear=False):
            with (
                patch(
                    "mcp_atlassian.jira.config.JiraConfig.from_env"
                ) as mock_jira_from_env,
                patch(
                    "mcp_atlassian.servers.main._try_auto_oauth",
                    new_callable=AsyncMock,
                ) as mock_try_auto_oauth,
            ):
                jira_config = MagicMock()
                jira_config.is_auth_configured.return_value = False
                jira_config.auth_type = "oauth"
                jira_config.oauth_config = _make_oauth_config()

                mock_jira_from_env.return_value = jira_config
                mock_try_auto_oauth.return_value = False

                app = MagicMock()
                async with main_lifespan(app) as context:
                    app_context = context["app_lifespan_context"]
                    assert app_context.full_jira_config is None

                mock_jira_from_env.assert_called_once()
                mock_try_auto_oauth.assert_called_once()

    async def test_confluence_auth_configured_auto_oauth_success(self):
        """Confluence: auth configured, needs auto-oauth, _try_auto_oauth succeeds."""
        env = {
            "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
            "CONFLUENCE_USERNAME": "test@example.com",
            "CONFLUENCE_API_TOKEN": "test-token",
        }
        with patch.dict(os.environ, env, clear=False):
            with (
                patch(
                    "mcp_atlassian.confluence.config.ConfluenceConfig.from_env"
                ) as mock_conf_from_env,
                patch(
                    "mcp_atlassian.servers.main._try_auto_oauth",
                    new_callable=AsyncMock,
                ) as mock_try_auto_oauth,
            ):
                initial_config = MagicMock()
                initial_config.is_auth_configured.return_value = True
                initial_config.auth_type = "oauth"
                initial_config.oauth_config = _make_oauth_config()

                reloaded_config = MagicMock()
                reloaded_config.is_auth_configured.return_value = True
                reloaded_config.auth_type = "oauth"
                reloaded_config.oauth_config = _make_oauth_config(
                    access_token="new-tok"
                )

                mock_conf_from_env.side_effect = [initial_config, reloaded_config]
                mock_try_auto_oauth.return_value = True

                app = MagicMock()
                async with main_lifespan(app) as context:
                    app_context = context["app_lifespan_context"]
                    assert app_context.full_confluence_config == reloaded_config

                assert mock_conf_from_env.call_count == 2
                mock_try_auto_oauth.assert_called_once()

    async def test_confluence_auth_not_configured_auto_oauth_fails(self):
        """Confluence: auth not configured, needs auto-oauth, _try_auto_oauth fails."""
        env = {
            "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
            "CONFLUENCE_USERNAME": "test@example.com",
            "CONFLUENCE_API_TOKEN": "test-token",
        }
        with patch.dict(os.environ, env, clear=False):
            with (
                patch(
                    "mcp_atlassian.confluence.config.ConfluenceConfig.from_env"
                ) as mock_conf_from_env,
                patch(
                    "mcp_atlassian.servers.main._try_auto_oauth",
                    new_callable=AsyncMock,
                ) as mock_try_auto_oauth,
            ):
                conf_config = MagicMock()
                conf_config.is_auth_configured.return_value = False
                conf_config.auth_type = "oauth"
                conf_config.oauth_config = _make_oauth_config()

                mock_conf_from_env.return_value = conf_config
                mock_try_auto_oauth.return_value = False

                app = MagicMock()
                async with main_lifespan(app) as context:
                    app_context = context["app_lifespan_context"]
                    assert app_context.full_confluence_config is None

                mock_conf_from_env.assert_called_once()
                mock_try_auto_oauth.assert_called_once()

    async def test_both_services_auto_oauth(self):
        """Both Jira and Confluence need auto-oauth; both succeed; both loaded."""
        with MockEnvironment.basic_auth_env():
            with (
                patch(
                    "mcp_atlassian.jira.config.JiraConfig.from_env"
                ) as mock_jira_from_env,
                patch(
                    "mcp_atlassian.confluence.config.ConfluenceConfig.from_env"
                ) as mock_conf_from_env,
                patch(
                    "mcp_atlassian.servers.main._try_auto_oauth",
                    new_callable=AsyncMock,
                ) as mock_try_auto_oauth,
            ):
                jira_initial = MagicMock()
                jira_initial.is_auth_configured.return_value = True
                jira_initial.auth_type = "oauth"
                jira_initial.oauth_config = _make_oauth_config()

                jira_reloaded = MagicMock()
                jira_reloaded.is_auth_configured.return_value = True
                jira_reloaded.auth_type = "oauth"
                jira_reloaded.oauth_config = _make_oauth_config(access_token="jira-tok")

                conf_initial = MagicMock()
                conf_initial.is_auth_configured.return_value = True
                conf_initial.auth_type = "oauth"
                conf_initial.oauth_config = _make_oauth_config()

                conf_reloaded = MagicMock()
                conf_reloaded.is_auth_configured.return_value = True
                conf_reloaded.auth_type = "oauth"
                conf_reloaded.oauth_config = _make_oauth_config(access_token="conf-tok")

                mock_jira_from_env.side_effect = [jira_initial, jira_reloaded]
                mock_conf_from_env.side_effect = [conf_initial, conf_reloaded]
                mock_try_auto_oauth.return_value = True

                app = MagicMock()
                async with main_lifespan(app) as context:
                    app_context = context["app_lifespan_context"]
                    assert app_context.full_jira_config == jira_reloaded
                    assert app_context.full_confluence_config == conf_reloaded

                assert mock_jira_from_env.call_count == 2
                assert mock_conf_from_env.call_count == 2
                assert mock_try_auto_oauth.call_count == 2
