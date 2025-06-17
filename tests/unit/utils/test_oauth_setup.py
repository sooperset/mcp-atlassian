"""Tests for the OAuth setup utilities."""

import json
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from mcp_atlassian.utils.oauth_setup import (
    OAuthSetupArgs,
    parse_redirect_uri,
    run_oauth_flow,
    run_oauth_setup,
)
from tests.utils.assertions import assert_config_contains
from tests.utils.base import BaseAuthTest
from tests.utils.mocks import MockEnvironment, MockOAuthServer


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
                mock_start_server.assert_not_called()  # No local server for external redirect
                mocks["browser"].assert_called_once()
                mock_config.exchange_code_for_tokens.assert_called_once_with(
                    "test-auth-code"
                )

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


class TestInteractiveSetup(BaseAuthTest):
    """Tests for the interactive OAuth setup wizard."""

    def test_run_oauth_setup_with_env_vars(self):
        """Test interactive setup using environment variables."""
        with MockEnvironment.oauth_env() as env_vars:
            with (
                patch("builtins.input", side_effect=["", "", "", ""]),
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

    @pytest.mark.parametrize(
        "input_values,expected_result",
        [
            (
                [
                    "user-client-id",
                    "user-secret",
                    "http://localhost:9000/callback",
                    "read:jira-work",
                ],
                0,
            ),
            (["", "client-secret", "", ""], 1),  # Missing client ID
            (["client-id", "", "", ""], 1),  # Missing client secret
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
                    "builtins.input", side_effect=["client-id", "client-secret", "", ""]
                ),
                patch(
                    "mcp_atlassian.utils.oauth_setup.run_oauth_flow", return_value=False
                ),
            ):
                result = run_oauth_setup()
                assert result == 1


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
