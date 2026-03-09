"""Tests for the OAuth setup utilities."""

import json
import logging
import os
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from mcp_atlassian.utils.oauth_setup import (
    OAuthSetupArgs,
    _log_cloud_success,
    _log_dc_success,
    parse_redirect_uri,
    run_oauth_flow,
    run_oauth_setup,
)
from tests.utils.assertions import assert_config_contains
from tests.utils.base import BaseAuthTest
from tests.utils.mocks import MockEnvironment, MockOAuthServer

DC_JIRA_URL = "https://jira.local.example.com"


class TestCallbackHandlerLogic:
    """Tests for URL parsing logic."""

    @pytest.mark.parametrize(
        "path,expected_params",
        [
            (
                "/callback?code=test-auth-code&state=test-state",
                {"code": ["test-auth-code"], "state": ["test-state"]},
            ),
            (
                "/callback?error=access_denied&error_description=User+denied+access",
                {"error": ["access_denied"]},
            ),
            ("/callback?state=test-state", {"state": ["test-state"]}),
            ("/callback", {}),
        ],
    )
    def test_url_parsing(self, path, expected_params):
        """Test URL parsing for various callback scenarios."""
        query = urlparse(path).query
        params = parse_qs(query)

        for key, expected_values in expected_params.items():
            assert key in params
            assert params[key] == expected_values


class TestRedirectUriParsing:
    """Tests for redirect URI parsing functionality."""

    @pytest.mark.parametrize(
        "redirect_uri,expected_hostname,expected_port",
        [
            ("http://localhost:8080/callback", "localhost", 8080),
            ("https://example.com:9443/callback", "example.com", 9443),
            ("http://localhost/callback", "localhost", 80),
            ("https://example.com/callback", "example.com", 443),
            ("http://127.0.0.1:3000/callback", "127.0.0.1", 3000),
            ("https://secure.domain.com:8443/auth", "secure.domain.com", 8443),
        ],
    )
    def test_parse_redirect_uri(self, redirect_uri, expected_hostname, expected_port):
        """Test redirect URI parsing for various formats."""
        hostname, port = parse_redirect_uri(redirect_uri)
        assert hostname == expected_hostname
        assert port == expected_port


class TestOAuthFlow:
    """Tests for OAuth flow orchestration."""

    @pytest.fixture(autouse=True)
    def reset_oauth_state(self):
        """Reset OAuth global state before each test."""
        import mcp_atlassian.utils.oauth_setup as oauth_module

        oauth_module.authorization_code = None
        oauth_module.authorization_state = None
        oauth_module.callback_received = False
        oauth_module.callback_error = None

    def test_run_oauth_flow_success_localhost(self):
        """Test successful OAuth flow with localhost redirect."""
        with MockOAuthServer.mock_oauth_flow() as mocks:
            with (
                patch(
                    "mcp_atlassian.utils.oauth_setup.OAuthConfig"
                ) as mock_oauth_config,
                patch("mcp_atlassian.utils.oauth_setup.wait_for_callback") as mock_wait,
                patch(
                    "mcp_atlassian.utils.oauth_setup.start_callback_server"
                ) as mock_start_server,
            ):
                # Setup global state after callback
                def setup_callback_state():
                    import mcp_atlassian.utils.oauth_setup as oauth_module

                    oauth_module.authorization_code = "test-auth-code"
                    oauth_module.authorization_state = "test-state-token"
                    return True

                mock_wait.side_effect = setup_callback_state
                mock_httpd = MagicMock()
                mock_start_server.return_value = mock_httpd

                # Setup OAuth config mock
                mock_config = MagicMock()
                mock_config.exchange_code_for_tokens.return_value = True
                mock_config.client_id = "test-client-id"
                mock_config.client_secret = "test-client-secret"
                mock_config.redirect_uri = "http://localhost:8080/callback"
                mock_config.scope = "read:jira-work"
                mock_config.cloud_id = "test-cloud-id"
                mock_config.is_data_center = False
                mock_config.access_token = "test-access-token"
                mock_config.refresh_token = "test-refresh-token"
                mock_oauth_config.return_value = mock_config

                args = OAuthSetupArgs(
                    client_id="test-client-id",
                    client_secret="test-client-secret",
                    redirect_uri="http://localhost:8080/callback",
                    scope="read:jira-work",
                )

                result = run_oauth_flow(args)

                assert result is True
                mock_start_server.assert_called_once_with(8080)
                mocks["browser"].assert_called_once()
                mock_config.exchange_code_for_tokens.assert_called_once_with(
                    "test-auth-code"
                )
                mock_httpd.shutdown.assert_called_once()

    def test_run_oauth_flow_success_external_redirect(self):
        """Test successful OAuth flow with external redirect URI."""
        with MockOAuthServer.mock_oauth_flow() as mocks:
            with (
                patch(
                    "mcp_atlassian.utils.oauth_setup.OAuthConfig"
                ) as mock_oauth_config,
                patch("mcp_atlassian.utils.oauth_setup.wait_for_callback") as mock_wait,
                patch(
                    "mcp_atlassian.utils.oauth_setup.start_callback_server"
                ) as mock_start_server,
            ):
                # Setup callback state
                def setup_callback_state():
                    import mcp_atlassian.utils.oauth_setup as oauth_module

                    oauth_module.authorization_code = "test-auth-code"
                    oauth_module.authorization_state = "test-state-token"
                    return True

                mock_wait.side_effect = setup_callback_state

                mock_config = MagicMock()
                mock_config.exchange_code_for_tokens.return_value = True
                mock_config.client_id = "test-client-id"
                mock_config.client_secret = "test-client-secret"
                mock_config.redirect_uri = "https://example.com/callback"
                mock_config.scope = "read:jira-work"
                mock_config.cloud_id = "test-cloud-id"
                mock_config.is_data_center = False
                mock_config.access_token = "test-access-token"
                mock_config.refresh_token = "test-refresh-token"
                mock_oauth_config.return_value = mock_config

                args = OAuthSetupArgs(
                    client_id="test-client-id",
                    client_secret="test-client-secret",
                    redirect_uri="https://example.com/callback",
                    scope="read:jira-work",
                )

                result = run_oauth_flow(args)

                assert result is True
                # No local server for external redirect
                mock_start_server.assert_not_called()
                mocks["browser"].assert_called_once()
                mock_config.exchange_code_for_tokens.assert_called_once_with(
                    "test-auth-code"
                )

    def test_run_oauth_flow_success_dc(self):
        """Test successful OAuth flow with DC base_url."""
        with MockOAuthServer.mock_oauth_flow():
            with (
                patch(
                    "mcp_atlassian.utils.oauth_setup.OAuthConfig"
                ) as mock_oauth_config,
                patch("mcp_atlassian.utils.oauth_setup.wait_for_callback") as mock_wait,
                patch(
                    "mcp_atlassian.utils.oauth_setup.start_callback_server"
                ) as mock_start_server,
            ):

                def setup_callback_state():
                    import mcp_atlassian.utils.oauth_setup as oauth_module

                    oauth_module.authorization_code = "test-auth-code"
                    oauth_module.authorization_state = "test-state-token"
                    return True

                mock_wait.side_effect = setup_callback_state
                mock_httpd = MagicMock()
                mock_start_server.return_value = mock_httpd

                mock_config = MagicMock()
                mock_config.exchange_code_for_tokens.return_value = True
                mock_config.client_id = "dc-client-id"
                mock_config.client_secret = "dc-client-secret"
                mock_config.redirect_uri = "http://localhost:8080/callback"
                mock_config.scope = "WRITE"
                mock_config.cloud_id = None
                mock_config.is_data_center = True
                mock_config.base_url = DC_JIRA_URL
                mock_config.access_token = "dc-access-token"
                mock_config.refresh_token = None
                mock_oauth_config.return_value = mock_config

                args = OAuthSetupArgs(
                    client_id="dc-client-id",
                    client_secret="dc-client-secret",
                    redirect_uri="http://localhost:8080/callback",
                    scope="WRITE",
                    base_url=DC_JIRA_URL,
                )

                result = run_oauth_flow(args)

                assert result is True
                mock_oauth_config.assert_called_once_with(
                    client_id="dc-client-id",
                    client_secret="dc-client-secret",
                    redirect_uri="http://localhost:8080/callback",
                    scope="WRITE",
                    base_url=DC_JIRA_URL,
                )
                mock_config.exchange_code_for_tokens.assert_called_once_with(
                    "test-auth-code"
                )
                mock_httpd.shutdown.assert_called_once()

    def test_run_oauth_flow_dc_no_cloud_id_error(self):
        """Test that DC flow does not log 'Failed to obtain cloud ID'."""
        with MockOAuthServer.mock_oauth_flow():
            with (
                patch(
                    "mcp_atlassian.utils.oauth_setup.OAuthConfig"
                ) as mock_oauth_config,
                patch("mcp_atlassian.utils.oauth_setup.wait_for_callback") as mock_wait,
                patch(
                    "mcp_atlassian.utils.oauth_setup.start_callback_server"
                ) as mock_start_server,
                patch("mcp_atlassian.utils.oauth_setup._log_dc_success") as mock_dc_log,
                patch(
                    "mcp_atlassian.utils.oauth_setup._log_cloud_success"
                ) as mock_cloud_log,
            ):

                def setup_callback_state():
                    import mcp_atlassian.utils.oauth_setup as oauth_module

                    oauth_module.authorization_code = "test-auth-code"
                    oauth_module.authorization_state = "test-state-token"
                    return True

                mock_wait.side_effect = setup_callback_state
                mock_start_server.return_value = MagicMock()

                mock_config = MagicMock()
                mock_config.exchange_code_for_tokens.return_value = True
                mock_config.is_data_center = True
                mock_config.cloud_id = None
                mock_config.refresh_token = None
                mock_oauth_config.return_value = mock_config

                args = OAuthSetupArgs(
                    client_id="dc-id",
                    client_secret="dc-secret",
                    redirect_uri="http://localhost:8080/callback",
                    scope="WRITE",
                    base_url=DC_JIRA_URL,
                )

                result = run_oauth_flow(args)

                assert result is True
                mock_dc_log.assert_called_once_with(mock_config)
                mock_cloud_log.assert_not_called()

    def test_run_oauth_flow_server_start_failure(self):
        """Test OAuth flow when server fails to start."""
        with MockOAuthServer.mock_oauth_flow() as mocks:
            with patch(
                "mcp_atlassian.utils.oauth_setup.start_callback_server"
            ) as mock_start_server:
                mock_start_server.side_effect = OSError("Port already in use")

                args = OAuthSetupArgs(
                    client_id="test-client-id",
                    client_secret="test-client-secret",
                    redirect_uri="http://localhost:8080/callback",
                    scope="read:jira-work",
                )

                result = run_oauth_flow(args)
                assert result is False
                mocks["browser"].assert_not_called()

    @pytest.mark.parametrize(
        "failure_condition,expected_result",
        [
            ("timeout", False),
            ("state_mismatch", False),
            ("token_exchange_failure", False),
        ],
    )
    def test_run_oauth_flow_failures(self, failure_condition, expected_result):
        """Test OAuth flow failure scenarios."""
        with MockOAuthServer.mock_oauth_flow():
            with (
                patch(
                    "mcp_atlassian.utils.oauth_setup.OAuthConfig"
                ) as mock_oauth_config,
                patch("mcp_atlassian.utils.oauth_setup.wait_for_callback") as mock_wait,
                patch(
                    "mcp_atlassian.utils.oauth_setup.start_callback_server"
                ) as mock_start_server,
            ):
                mock_httpd = MagicMock()
                mock_start_server.return_value = mock_httpd
                mock_config = MagicMock()
                mock_oauth_config.return_value = mock_config

                if failure_condition == "timeout":
                    mock_wait.return_value = False
                elif failure_condition == "state_mismatch":

                    def setup_mismatched_state():
                        import mcp_atlassian.utils.oauth_setup as oauth_module

                        oauth_module.authorization_code = "test-auth-code"
                        oauth_module.authorization_state = "wrong-state"
                        return True

                    mock_wait.side_effect = setup_mismatched_state
                elif failure_condition == "token_exchange_failure":

                    def setup_callback_state():
                        import mcp_atlassian.utils.oauth_setup as oauth_module

                        oauth_module.authorization_code = "test-auth-code"
                        oauth_module.authorization_state = "test-state-token"
                        return True

                    mock_wait.side_effect = setup_callback_state
                    mock_config.exchange_code_for_tokens.return_value = False

                args = OAuthSetupArgs(
                    client_id="test-client-id",
                    client_secret="test-client-secret",
                    redirect_uri="http://localhost:8080/callback",
                    scope="read:jira-work",
                )

                result = run_oauth_flow(args)
                assert result == expected_result
                mock_httpd.shutdown.assert_called_once()

    @pytest.mark.parametrize(
        "failure_condition,expected_result",
        [
            ("timeout", False),
            ("state_mismatch", False),
            ("token_exchange_failure", False),
        ],
    )
    def test_run_oauth_flow_dc_failures(self, failure_condition, expected_result):
        """Test OAuth flow failure scenarios for DC."""
        with MockOAuthServer.mock_oauth_flow():
            with (
                patch(
                    "mcp_atlassian.utils.oauth_setup.OAuthConfig"
                ) as mock_oauth_config,
                patch("mcp_atlassian.utils.oauth_setup.wait_for_callback") as mock_wait,
                patch(
                    "mcp_atlassian.utils.oauth_setup.start_callback_server"
                ) as mock_start_server,
            ):
                mock_httpd = MagicMock()
                mock_start_server.return_value = mock_httpd
                mock_config = MagicMock()
                mock_config.is_data_center = True
                mock_config.cloud_id = None
                mock_config.base_url = DC_JIRA_URL
                mock_oauth_config.return_value = mock_config

                if failure_condition == "timeout":
                    mock_wait.return_value = False
                elif failure_condition == "state_mismatch":

                    def setup_mismatched_state():
                        import mcp_atlassian.utils.oauth_setup as oauth_module

                        oauth_module.authorization_code = "test-auth-code"
                        oauth_module.authorization_state = "wrong-state"
                        return True

                    mock_wait.side_effect = setup_mismatched_state
                elif failure_condition == "token_exchange_failure":

                    def setup_callback_state():
                        import mcp_atlassian.utils.oauth_setup as oauth_module

                        oauth_module.authorization_code = "test-auth-code"
                        oauth_module.authorization_state = "test-state-token"
                        return True

                    mock_wait.side_effect = setup_callback_state
                    mock_config.exchange_code_for_tokens.return_value = False

                args = OAuthSetupArgs(
                    client_id="dc-client-id",
                    client_secret="dc-client-secret",
                    redirect_uri="http://localhost:8080/callback",
                    scope="WRITE",
                    base_url=DC_JIRA_URL,
                )

                result = run_oauth_flow(args)
                assert result == expected_result
                mock_httpd.shutdown.assert_called_once()

    def test_run_oauth_flow_dc_no_refresh_token_warning(self, caplog):
        """Test DC flow logs warning when no refresh token received."""
        with MockOAuthServer.mock_oauth_flow():
            with (
                patch(
                    "mcp_atlassian.utils.oauth_setup.OAuthConfig"
                ) as mock_oauth_config,
                patch("mcp_atlassian.utils.oauth_setup.wait_for_callback") as mock_wait,
                patch(
                    "mcp_atlassian.utils.oauth_setup.start_callback_server"
                ) as mock_start_server,
                patch("mcp_atlassian.utils.oauth_setup._log_dc_success"),
            ):

                def setup_callback_state():
                    import mcp_atlassian.utils.oauth_setup as oauth_module

                    oauth_module.authorization_code = "test-auth-code"
                    oauth_module.authorization_state = "test-state-token"
                    return True

                mock_wait.side_effect = setup_callback_state
                mock_httpd = MagicMock()
                mock_start_server.return_value = mock_httpd

                mock_config = MagicMock()
                mock_config.exchange_code_for_tokens.return_value = True
                mock_config.is_data_center = True
                mock_config.refresh_token = None
                mock_config.cloud_id = None
                mock_config.base_url = DC_JIRA_URL
                mock_oauth_config.return_value = mock_config

                args = OAuthSetupArgs(
                    client_id="dc-client-id",
                    client_secret="dc-client-secret",
                    redirect_uri="http://localhost:8080/callback",
                    scope="WRITE",
                    base_url=DC_JIRA_URL,
                )

                with caplog.at_level(
                    logging.WARNING, logger="mcp-atlassian.oauth-setup"
                ):
                    result = run_oauth_flow(args)

                assert result is True
                assert (
                    "No refresh token received. DC tokens may expire "
                    "and require re-authentication." in caplog.text
                )

    def test_run_oauth_flow_dc_with_refresh_token_no_warning(self, caplog):
        """Test DC flow does not log warning when refresh token is present."""
        with MockOAuthServer.mock_oauth_flow():
            with (
                patch(
                    "mcp_atlassian.utils.oauth_setup.OAuthConfig"
                ) as mock_oauth_config,
                patch("mcp_atlassian.utils.oauth_setup.wait_for_callback") as mock_wait,
                patch(
                    "mcp_atlassian.utils.oauth_setup.start_callback_server"
                ) as mock_start_server,
                patch("mcp_atlassian.utils.oauth_setup._log_dc_success"),
            ):

                def setup_callback_state():
                    import mcp_atlassian.utils.oauth_setup as oauth_module

                    oauth_module.authorization_code = "test-auth-code"
                    oauth_module.authorization_state = "test-state-token"
                    return True

                mock_wait.side_effect = setup_callback_state
                mock_httpd = MagicMock()
                mock_start_server.return_value = mock_httpd

                mock_config = MagicMock()
                mock_config.exchange_code_for_tokens.return_value = True
                mock_config.is_data_center = True
                mock_config.refresh_token = "dc-refresh-tok"
                mock_config.cloud_id = None
                mock_config.base_url = DC_JIRA_URL
                mock_oauth_config.return_value = mock_config

                args = OAuthSetupArgs(
                    client_id="dc-client-id",
                    client_secret="dc-client-secret",
                    redirect_uri="http://localhost:8080/callback",
                    scope="WRITE",
                    base_url=DC_JIRA_URL,
                )

                with caplog.at_level(
                    logging.WARNING, logger="mcp-atlassian.oauth-setup"
                ):
                    result = run_oauth_flow(args)

                assert result is True
                assert (
                    "No refresh token received. DC tokens may expire "
                    "and require re-authentication." not in caplog.text
                )


class TestInteractiveSetup(BaseAuthTest):
    """Tests for the interactive OAuth setup wizard."""

    def test_run_oauth_setup_with_env_vars(self):
        """Test interactive setup using Cloud environment variables."""
        with MockEnvironment.oauth_env() as env_vars:
            with (
                patch(
                    "builtins.input",
                    side_effect=[
                        "",  # instance URL (from env / empty = Cloud)
                        "",  # client_id
                        "",  # client_secret
                        "",  # redirect_uri
                        "",  # scope
                    ],
                ),
                patch(
                    "mcp_atlassian.utils.oauth_setup.run_oauth_flow", return_value=True
                ) as mock_flow,
            ):
                result = run_oauth_setup()

                assert result == 0
                mock_flow.assert_called_once()
                args = mock_flow.call_args[0][0]
                assert_config_contains(
                    vars(args),
                    client_id=env_vars["ATLASSIAN_OAUTH_CLIENT_ID"],
                    client_secret=env_vars["ATLASSIAN_OAUTH_CLIENT_SECRET"],
                )
                assert args.base_url is None

    @pytest.mark.parametrize(
        "input_values,expected_result",
        [
            (
                [
                    "",  # instance URL (empty = Cloud)
                    "user-client-id",
                    "user-secret",
                    "http://localhost:9000/callback",
                    "read:jira-work",
                ],
                0,
            ),
            (
                [
                    "",  # instance URL
                    "",  # missing client ID
                    "client-secret",
                    "",
                    "",
                ],
                1,
            ),
            (
                [
                    "",  # instance URL
                    "client-id",
                    "",  # missing client secret
                    "",
                    "",
                ],
                1,
            ),
        ],
    )
    def test_run_oauth_setup_user_input(self, input_values, expected_result):
        """Test interactive setup with various user inputs."""
        with MockEnvironment.clean_env():
            with (
                patch("builtins.input", side_effect=input_values),
                patch(
                    "mcp_atlassian.utils.oauth_setup.run_oauth_flow", return_value=True
                ) as mock_flow,
            ):
                result = run_oauth_setup()
                assert result == expected_result

                if expected_result == 0:
                    mock_flow.assert_called_once()
                else:
                    mock_flow.assert_not_called()

    def test_run_oauth_setup_flow_failure(self):
        """Test interactive setup when OAuth flow fails."""
        with MockEnvironment.clean_env():
            with (
                patch(
                    "builtins.input",
                    side_effect=[
                        "",  # instance URL
                        "client-id",
                        "client-secret",
                        "",
                        "",
                    ],
                ),
                patch(
                    "mcp_atlassian.utils.oauth_setup.run_oauth_flow", return_value=False
                ),
            ):
                result = run_oauth_setup()
                assert result == 1

    def test_run_oauth_setup_dc_instance(self):
        """Test interactive setup with a DC instance URL."""
        dc_env = {
            "JIRA_URL": DC_JIRA_URL,
            "JIRA_OAUTH_CLIENT_ID": "dc-client-id",
            "JIRA_OAUTH_CLIENT_SECRET": "dc-client-secret",
        }
        with MockEnvironment.clean_env():
            with (
                patch.dict(os.environ, dc_env, clear=False),
                patch(
                    "builtins.input",
                    side_effect=[
                        "",  # instance URL (picks up JIRA_URL)
                        "",  # client_id (picks up JIRA_OAUTH_CLIENT_ID)
                        "",  # client_secret
                        "",  # redirect_uri
                        "",  # scope
                    ],
                ),
                patch(
                    "mcp_atlassian.utils.oauth_setup.run_oauth_flow",
                    return_value=True,
                ) as mock_flow,
            ):
                result = run_oauth_setup()

                assert result == 0
                mock_flow.assert_called_once()
                args = mock_flow.call_args[0][0]
                assert args.base_url == DC_JIRA_URL
                assert args.client_id == "dc-client-id"
                assert args.scope == "WRITE"

    def test_run_oauth_setup_dc_manual_input(self):
        """Test interactive setup with manually typed DC URL."""
        with MockEnvironment.clean_env():
            with (
                patch(
                    "builtins.input",
                    side_effect=[
                        DC_JIRA_URL,  # instance URL
                        "manual-dc-id",  # client_id
                        "manual-dc-secret",  # client_secret
                        "",  # redirect_uri (default)
                        "",  # scope (default WRITE for DC)
                    ],
                ),
                patch(
                    "mcp_atlassian.utils.oauth_setup.run_oauth_flow",
                    return_value=True,
                ) as mock_flow,
            ):
                result = run_oauth_setup()

                assert result == 0
                args = mock_flow.call_args[0][0]
                assert args.base_url == DC_JIRA_URL
                assert args.client_id == "manual-dc-id"
                assert args.scope == "WRITE"

    def test_run_oauth_setup_cloud_url_no_base_url(self):
        """Test that Cloud URLs do not set base_url."""
        with MockEnvironment.clean_env():
            with (
                patch(
                    "builtins.input",
                    side_effect=[
                        "https://company.atlassian.net",  # Cloud URL
                        "cloud-id",
                        "cloud-secret",
                        "",
                        "",
                    ],
                ),
                patch(
                    "mcp_atlassian.utils.oauth_setup.run_oauth_flow",
                    return_value=True,
                ) as mock_flow,
            ):
                result = run_oauth_setup()

                assert result == 0
                args = mock_flow.call_args[0][0]
                assert args.base_url is None

    def test_run_oauth_setup_dc_fallback_to_atlassian_env_vars(self):
        """Test DC wizard falls back to ATLASSIAN_OAUTH_* when JIRA_OAUTH_* unset."""
        dc_env = {
            "JIRA_URL": DC_JIRA_URL,
            "ATLASSIAN_OAUTH_CLIENT_ID": "fallback-id",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "fallback-secret",
        }
        with MockEnvironment.clean_env():
            with (
                patch.dict(os.environ, dc_env, clear=False),
                patch(
                    "builtins.input",
                    side_effect=[
                        "",  # instance URL (picks up JIRA_URL)
                        "",  # client_id (fallback to ATLASSIAN_OAUTH_CLIENT_ID)
                        "",  # client_secret
                        "",  # redirect_uri
                        "",  # scope
                    ],
                ),
                patch(
                    "mcp_atlassian.utils.oauth_setup.run_oauth_flow",
                    return_value=True,
                ) as mock_flow,
            ):
                result = run_oauth_setup()

                assert result == 0
                mock_flow.assert_called_once()
                args = mock_flow.call_args[0][0]
                assert args.client_id == "fallback-id"
                assert args.client_secret == "fallback-secret"
                assert args.base_url == DC_JIRA_URL


class TestOAuthSetupArgs:
    """Tests for the OAuthSetupArgs dataclass."""

    def test_oauth_setup_args_creation(self):
        """Test OAuthSetupArgs dataclass creation."""
        args = OAuthSetupArgs(
            client_id="test-id",
            client_secret="test-secret",
            redirect_uri="http://localhost:8080/callback",
            scope="read:jira-work",
        )

        expected_config = {
            "client_id": "test-id",
            "client_secret": "test-secret",
            "redirect_uri": "http://localhost:8080/callback",
            "scope": "read:jira-work",
        }
        assert_config_contains(vars(args), **expected_config)
        assert args.base_url is None

    def test_oauth_setup_args_with_base_url(self):
        """Test OAuthSetupArgs with DC base_url."""
        args = OAuthSetupArgs(
            client_id="dc-id",
            client_secret="dc-secret",
            redirect_uri="http://localhost:8080/callback",
            scope="WRITE",
            base_url=DC_JIRA_URL,
        )

        assert_config_contains(
            vars(args),
            client_id="dc-id",
            scope="WRITE",
            base_url=DC_JIRA_URL,
        )


class TestConfigurationGeneration:
    """Tests for configuration output functionality."""

    def test_configuration_serialization(self):
        """Test JSON configuration serialization."""
        test_config = {
            "client_id": "test-id",
            "client_secret": "test-secret",
            "redirect_uri": "http://localhost:8080/callback",
            "scope": "read:jira-work",
            "cloud_id": "test-cloud-id",
        }

        json_str = json.dumps(test_config, indent=4)
        assert "test-id" in json_str
        assert "test-cloud-id" in json_str

        # Verify it can be parsed back
        parsed = json.loads(json_str)
        assert_config_contains(parsed, **test_config)

    def test_dc_configuration_serialization(self):
        """Test DC configuration serialization (no cloud_id, includes JIRA_URL)."""
        test_config = {
            "JIRA_URL": DC_JIRA_URL,
            "JIRA_OAUTH_CLIENT_ID": "dc-id",
            "JIRA_OAUTH_CLIENT_SECRET": "dc-secret",
            "ATLASSIAN_OAUTH_REDIRECT_URI": "http://localhost:8080/callback",
            "ATLASSIAN_OAUTH_SCOPE": "WRITE",
        }

        json_str = json.dumps(test_config, indent=4)
        assert DC_JIRA_URL in json_str
        assert "dc-id" in json_str
        assert "cloud_id" not in json_str
        assert "ATLASSIAN_OAUTH_CLOUD_ID" not in json_str

        parsed = json.loads(json_str)
        assert_config_contains(parsed, **test_config)


class TestSuccessOutputHelpers:
    """Tests for _log_cloud_success and _log_dc_success."""

    def test_log_cloud_success(self, caplog):
        """Test Cloud success output logs correct env vars."""
        mock_config = MagicMock()
        mock_config.client_id = "cloud-id"
        mock_config.client_secret = "cloud-secret"
        mock_config.redirect_uri = "http://localhost:8080/callback"
        mock_config.scope = "read:jira-work offline_access"
        mock_config.cloud_id = "test-cloud-id"

        import logging

        with caplog.at_level(logging.INFO, logger="mcp-atlassian.oauth-setup"):
            _log_cloud_success(mock_config)

        log_text = caplog.text
        assert "ATLASSIAN_OAUTH_CLOUD_ID=test-cloud-id" in log_text
        assert "ATLASSIAN_OAUTH_CLIENT_ID=cloud-id" in log_text

    def test_log_dc_success(self, caplog):
        """Test DC success output logs correct env vars."""
        mock_config = MagicMock()
        mock_config.client_id = "dc-id"
        mock_config.client_secret = "dc-secret"
        mock_config.redirect_uri = "http://localhost:8080/callback"
        mock_config.scope = "WRITE"
        mock_config.base_url = DC_JIRA_URL

        import logging

        with caplog.at_level(logging.INFO, logger="mcp-atlassian.oauth-setup"):
            _log_dc_success(mock_config)

        log_text = caplog.text
        assert f"JIRA_URL={DC_JIRA_URL}" in log_text
        assert "JIRA_OAUTH_CLIENT_ID=dc-id" in log_text
        assert "ATLASSIAN_OAUTH_CLOUD_ID" not in log_text

    def test_log_dc_success_no_cloud_id_in_vscode_config(self, caplog):
        """Test DC VS Code config does not contain ATLASSIAN_OAUTH_CLOUD_ID."""
        mock_config = MagicMock()
        mock_config.client_id = "dc-id"
        mock_config.client_secret = "dc-secret"
        mock_config.redirect_uri = "http://localhost:8080/callback"
        mock_config.scope = "WRITE"
        mock_config.base_url = DC_JIRA_URL

        import logging

        with caplog.at_level(logging.INFO, logger="mcp-atlassian.oauth-setup"):
            _log_dc_success(mock_config)

        log_text = caplog.text
        assert "ATLASSIAN_OAUTH_CLOUD_ID" not in log_text
        assert "VS CODE CONFIGURATION" in log_text
