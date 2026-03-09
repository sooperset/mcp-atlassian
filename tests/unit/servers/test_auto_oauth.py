"""Tests for the auto-OAuth browser flow triggered during server startup."""

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from mcp_atlassian.servers.main import _needs_auto_oauth, _try_auto_oauth
from mcp_atlassian.utils.oauth import BYOAccessTokenOAuthConfig, OAuthConfig

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
    base_url: str | None = None,
) -> OAuthConfig:
    return OAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        access_token=access_token,
        base_url=base_url,
    )


@dataclass
class _StubConfig:
    """Minimal stand-in for JiraConfig / ConfluenceConfig."""

    auth_type: str
    oauth_config: OAuthConfig | BYOAccessTokenOAuthConfig | None = None


# ---------------------------------------------------------------------------
# _needs_auto_oauth
# ---------------------------------------------------------------------------


class TestNeedsAutoOAuth:
    """Tests for the _needs_auto_oauth helper."""

    def test_triggers_when_oauth_creds_present_no_tokens(self):
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(),
        )
        assert _needs_auto_oauth(cfg) is True

    def test_skips_when_access_token_already_present(self):
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(access_token="tok"),
        )
        assert _needs_auto_oauth(cfg) is False

    def test_skips_for_basic_auth(self):
        cfg = _StubConfig(auth_type="basic", oauth_config=None)
        assert _needs_auto_oauth(cfg) is False

    def test_skips_for_pat_auth(self):
        cfg = _StubConfig(auth_type="pat", oauth_config=None)
        assert _needs_auto_oauth(cfg) is False

    def test_skips_when_client_id_missing(self):
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(client_id=""),
        )
        assert _needs_auto_oauth(cfg) is False

    def test_skips_when_client_secret_missing(self):
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(client_secret=""),
        )
        assert _needs_auto_oauth(cfg) is False

    def test_skips_for_byo_token_config(self):
        byo = BYOAccessTokenOAuthConfig(access_token="byo-tok")
        cfg = _StubConfig(auth_type="oauth", oauth_config=byo)
        assert _needs_auto_oauth(cfg) is False

    def test_skips_when_oauth_config_is_none(self):
        cfg = _StubConfig(auth_type="oauth", oauth_config=None)
        assert _needs_auto_oauth(cfg) is False

    def test_triggers_for_dc_oauth_without_tokens(self):
        cfg = _StubConfig(
            auth_type="oauth",
            oauth_config=_make_oauth_config(
                base_url="https://jira.corp.example.com",
            ),
        )
        assert _needs_auto_oauth(cfg) is True


# ---------------------------------------------------------------------------
# _try_auto_oauth
# ---------------------------------------------------------------------------

FLOW_PATCH = "mcp_atlassian.utils.oauth_setup.run_oauth_flow"


class TestTryAutoOAuth:
    """Tests for the _try_auto_oauth helper."""

    @patch(FLOW_PATCH)
    def test_returns_true_on_success(self, mock_flow):
        mock_flow.return_value = True
        oauth_cfg = _make_oauth_config()

        result = _try_auto_oauth(oauth_cfg, "Jira")

        assert result is True
        mock_flow.assert_called_once()
        args = mock_flow.call_args[0][0]
        assert args.client_id == "cid"
        assert args.client_secret == "csec"
        assert args.redirect_uri == "http://localhost:8080/callback"
        assert args.scope == "WRITE"
        assert args.base_url is None

    @patch(FLOW_PATCH)
    def test_returns_false_on_failure(self, mock_flow):
        mock_flow.return_value = False
        oauth_cfg = _make_oauth_config()

        result = _try_auto_oauth(oauth_cfg, "Confluence")

        assert result is False
        mock_flow.assert_called_once()

    @patch(FLOW_PATCH)
    def test_passes_dc_base_url(self, mock_flow):
        mock_flow.return_value = True
        dc_url = "https://jira.corp.example.com"
        oauth_cfg = _make_oauth_config(base_url=dc_url)

        _try_auto_oauth(oauth_cfg, "Jira")

        args = mock_flow.call_args[0][0]
        assert args.base_url == dc_url

    @patch(FLOW_PATCH)
    def test_flow_exception_propagates(self, mock_flow):
        mock_flow.side_effect = RuntimeError("port in use")
        oauth_cfg = _make_oauth_config()

        with pytest.raises(RuntimeError, match="port in use"):
            _try_auto_oauth(oauth_cfg, "Jira")
