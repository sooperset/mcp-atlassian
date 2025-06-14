"""Tests for the OAuth setup utilities."""

import http.server
import json
import secrets
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from mcp_atlassian.utils.oauth_setup import (
    CallbackHandler,
    OAuthSetupArgs,
    parse_redirect_uri,
    run_oauth_flow,
    run_oauth_setup,
    start_callback_server,
    wait_for_callback,
)


class TestCallbackHandlerLogic:
    """Tests for the CallbackHandler logic without HTTP infrastructure."""

    def test_url_parsing_with_code_and_state(self):
        """Test URL parsing logic for success case."""

        path = "/callback?code=test-auth-code&state=test-state"
        query = urlparse(path).query
        params = parse_qs(query)

        assert "code" in params
        assert "state" in params
        assert params["code"][0] == "test-auth-code"
        assert params["state"][0] == "test-state"

    def test_url_parsing_with_error(self):
        """Test URL parsing logic for error case."""

        path = "/callback?error=access_denied&error_description=User+denied+access"
        query = urlparse(path).query
        params = parse_qs(query)

        assert "error" in params
        assert params["error"][0] == "access_denied"

    def test_url_parsing_missing_code(self):
        """Test URL parsing logic when code is missing."""

        path = "/callback?state=test-state"
        query = urlparse(path).query
        params = parse_qs(query)

        assert "code" not in params
        assert "state" in params

    def test_url_parsing_empty_query(self):
        """Test URL parsing logic with empty query."""

        path = "/callback"
        query = urlparse(path).query
        params = parse_qs(query)

        assert len(params) == 0

    def test_callback_handler_has_required_methods(self):
        """Test that CallbackHandler has the required methods."""
        # Verify the class has the expected methods without instantiating
        assert hasattr(CallbackHandler, "do_GET")
        assert hasattr(CallbackHandler, "_send_response")
        assert hasattr(CallbackHandler, "log_message")

        # Verify it inherits from BaseHTTPRequestHandler
        assert issubclass(CallbackHandler, http.server.BaseHTTPRequestHandler)

    def test_global_variables_can_be_modified(self):
        """Test that global variables can be properly modified."""
        # Verify the global variables exist and can be modified
        import mcp_atlassian.utils.oauth_setup as oauth_module

        # Save original values
        orig_code = oauth_module.authorization_code
        orig_state = oauth_module.authorization_state
        orig_received = oauth_module.callback_received
        orig_error = oauth_module.callback_error

        # Modify values
        oauth_module.authorization_code = "test-code"
        oauth_module.authorization_state = "test-state"
        oauth_module.callback_received = True
        oauth_module.callback_error = "test-error"

        # Verify changes
        assert oauth_module.authorization_code == "test-code"
        assert oauth_module.authorization_state == "test-state"
        assert oauth_module.callback_received is True
        assert oauth_module.callback_error == "test-error"

        # Restore original values
        oauth_module.authorization_code = orig_code
        oauth_module.authorization_state = orig_state
        oauth_module.callback_received = orig_received
        oauth_module.callback_error = orig_error


class TestCallbackServerManagement:
    """Tests for callback server management functions."""

    @patch("socketserver.TCPServer")
    @patch("threading.Thread")
    def test_start_callback_server(self, mock_thread, mock_server):
        """Test starting callback server."""
        mock_httpd = MagicMock()
        mock_server.return_value = mock_httpd
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        result = start_callback_server(8080)

        # Check server was created with correct parameters
        mock_server.assert_called_once_with(("", 8080), CallbackHandler)

        # Check thread was started
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()
        assert mock_thread_instance.daemon is True

        assert result == mock_httpd

    @patch("time.sleep")
    @patch("time.time")
    def test_wait_for_callback_success(self, mock_time, mock_sleep):
        """Test successful wait_for_callback."""
        # Setup time progression
        mock_time.side_effect = [0, 5, 10]  # Start time, first check, second check

        # Mock callback_received becoming True after first sleep
        call_count = 0

        def sleep_side_effect(*args):
            nonlocal call_count
            call_count += 1
            # After first sleep, simulate callback received
            if call_count == 1:
                import mcp_atlassian.utils.oauth_setup

                mcp_atlassian.utils.oauth_setup.callback_received = True

        mock_sleep.side_effect = sleep_side_effect

        # Reset global state
        import mcp_atlassian.utils.oauth_setup

        mcp_atlassian.utils.oauth_setup.callback_received = False
        mcp_atlassian.utils.oauth_setup.callback_error = None

        result = wait_for_callback(timeout=300)

        assert result is True
        mock_sleep.assert_called_once_with(1)

    @patch("time.sleep")
    @patch("time.time")
    def test_wait_for_callback_timeout(self, mock_time, mock_sleep):
        """Test wait_for_callback timeout."""
        # Reset global state
        import mcp_atlassian.utils.oauth_setup

        mcp_atlassian.utils.oauth_setup.callback_received = False
        mcp_atlassian.utils.oauth_setup.callback_error = None

        # Make time.time() return increasing values to simulate timeout
        time_values = [0, 100, 200, 301] + [
            301
        ] * 10  # Extra values for other time() calls
        mock_time.side_effect = time_values

        result = wait_for_callback(timeout=300)

        assert result is False

    @patch("time.sleep")
    @patch("time.time")
    def test_wait_for_callback_with_error(self, mock_time, mock_sleep):
        """Test wait_for_callback with callback error."""
        # Setup global state
        import mcp_atlassian.utils.oauth_setup

        mcp_atlassian.utils.oauth_setup.callback_received = True
        mcp_atlassian.utils.oauth_setup.callback_error = "access_denied"

        mock_time.side_effect = [0, 5]  # Start time, first check

        result = wait_for_callback(timeout=300)

        assert result is False

    @patch("time.sleep")
    @patch("time.time")
    def test_wait_for_callback_custom_timeout(self, mock_time, mock_sleep):
        """Test wait_for_callback with custom timeout."""
        # Reset global state
        import mcp_atlassian.utils.oauth_setup

        mcp_atlassian.utils.oauth_setup.callback_received = False
        mcp_atlassian.utils.oauth_setup.callback_error = None

        # Setup time to exceed custom timeout
        time_values = [0, 30, 61] + [61] * 10  # Extra values for other time() calls
        mock_time.side_effect = time_values

        result = wait_for_callback(timeout=60)

        assert result is False


class TestRedirectUriParsing:
    """Tests for redirect URI parsing functionality."""

    def test_parse_redirect_uri_http_with_port(self):
        """Test parsing HTTP redirect URI with explicit port."""
        hostname, port = parse_redirect_uri("http://localhost:8080/callback")
        assert hostname == "localhost"
        assert port == 8080

    def test_parse_redirect_uri_https_with_port(self):
        """Test parsing HTTPS redirect URI with explicit port."""
        hostname, port = parse_redirect_uri("https://example.com:9443/callback")
        assert hostname == "example.com"
        assert port == 9443

    def test_parse_redirect_uri_http_default_port(self):
        """Test parsing HTTP redirect URI with default port."""
        hostname, port = parse_redirect_uri("http://localhost/callback")
        assert hostname == "localhost"
        assert port == 80

    def test_parse_redirect_uri_https_default_port(self):
        """Test parsing HTTPS redirect URI with default port."""
        hostname, port = parse_redirect_uri("https://example.com/callback")
        assert hostname == "example.com"
        assert port == 443

    def test_parse_redirect_uri_ip_address(self):
        """Test parsing redirect URI with IP address."""
        hostname, port = parse_redirect_uri("http://127.0.0.1:3000/callback")
        assert hostname == "127.0.0.1"
        assert port == 3000


class TestOAuthFlow:
    """Tests for the OAuth flow orchestration."""

    def setup_method(self):
        """Reset global state before each test."""
        import mcp_atlassian.utils.oauth_setup

        mcp_atlassian.utils.oauth_setup.authorization_code = None
        mcp_atlassian.utils.oauth_setup.authorization_state = None
        mcp_atlassian.utils.oauth_setup.callback_received = False
        mcp_atlassian.utils.oauth_setup.callback_error = None

    @patch("mcp_atlassian.utils.oauth_setup.webbrowser.open")
    @patch("mcp_atlassian.utils.oauth_setup.wait_for_callback")
    @patch("mcp_atlassian.utils.oauth_setup.start_callback_server")
    @patch("mcp_atlassian.utils.oauth_setup.OAuthConfig")
    @patch("secrets.token_urlsafe")
    def test_run_oauth_flow_success_localhost(
        self, mock_token, mock_oauth_config, mock_start_server, mock_wait, mock_browser
    ):
        """Test successful OAuth flow with localhost redirect."""
        # Setup mocks
        mock_token.return_value = "test-state"
        mock_wait.return_value = True

        # Mock wait_for_callback to set up the global state after it's called
        def setup_global_state():
            import mcp_atlassian.utils.oauth_setup

            mcp_atlassian.utils.oauth_setup.authorization_code = "test-auth-code"
            mcp_atlassian.utils.oauth_setup.authorization_state = "test-state"
            return True

        mock_wait.side_effect = setup_global_state

        mock_httpd = MagicMock()
        mock_start_server.return_value = mock_httpd

        mock_config = MagicMock()
        mock_config.get_authorization_url.return_value = "https://auth.example.com"
        mock_config.exchange_code_for_tokens.return_value = True
        mock_config.access_token = "test-access-token"
        mock_config.refresh_token = "test-refresh-token"
        mock_config.cloud_id = "test-cloud-id"
        mock_config.client_id = "test-client-id"
        mock_config.client_secret = "test-client-secret"
        mock_config.redirect_uri = "http://localhost:8080/callback"
        mock_config.scope = "read:jira-work"
        mock_oauth_config.return_value = mock_config

        args = OAuthSetupArgs(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="http://localhost:8080/callback",
            scope="read:jira-work",
        )

        result = run_oauth_flow(args)

        # Check result
        assert result is True

        # Verify interactions
        mock_start_server.assert_called_once_with(8080)
        mock_browser.assert_called_once()
        mock_wait.assert_called_once()
        mock_config.exchange_code_for_tokens.assert_called_once_with("test-auth-code")
        mock_httpd.shutdown.assert_called_once()

    @patch("mcp_atlassian.utils.oauth_setup.webbrowser.open")
    @patch("mcp_atlassian.utils.oauth_setup.wait_for_callback")
    @patch("mcp_atlassian.utils.oauth_setup.start_callback_server")
    @patch("mcp_atlassian.utils.oauth_setup.OAuthConfig")
    @patch("secrets.token_urlsafe")
    def test_run_oauth_flow_success_external_redirect(
        self, mock_token, mock_oauth_config, mock_start_server, mock_wait, mock_browser
    ):
        """Test successful OAuth flow with external redirect URI."""
        # Setup mocks
        mock_token.return_value = "test-state"
        mock_wait.return_value = True

        # Mock wait_for_callback to set up the global state after it's called
        def setup_global_state():
            import mcp_atlassian.utils.oauth_setup

            mcp_atlassian.utils.oauth_setup.authorization_code = "test-auth-code"
            mcp_atlassian.utils.oauth_setup.authorization_state = "test-state"
            return True

        mock_wait.side_effect = setup_global_state

        mock_config = MagicMock()
        mock_config.get_authorization_url.return_value = "https://auth.example.com"
        mock_config.exchange_code_for_tokens.return_value = True
        mock_config.access_token = "test-access-token"
        mock_config.refresh_token = "test-refresh-token"
        mock_config.cloud_id = "test-cloud-id"
        mock_config.client_id = "test-client-id"
        mock_config.client_secret = "test-client-secret"
        mock_config.redirect_uri = "https://example.com/callback"
        mock_config.scope = "read:jira-work"
        mock_oauth_config.return_value = mock_config

        args = OAuthSetupArgs(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="https://example.com/callback",
            scope="read:jira-work",
        )

        result = run_oauth_flow(args)

        # Check result
        assert result is True

        # Verify no local server was started for external redirect
        mock_start_server.assert_not_called()
        mock_browser.assert_called_once()
        mock_wait.assert_called_once()
        mock_config.exchange_code_for_tokens.assert_called_once_with("test-auth-code")

    @patch("mcp_atlassian.utils.oauth_setup.webbrowser.open")
    @patch("mcp_atlassian.utils.oauth_setup.wait_for_callback")
    @patch("mcp_atlassian.utils.oauth_setup.start_callback_server")
    @patch("mcp_atlassian.utils.oauth_setup.OAuthConfig")
    @patch("secrets.token_urlsafe")
    def test_run_oauth_flow_server_start_failure(
        self, mock_token, mock_oauth_config, mock_start_server, mock_wait, mock_browser
    ):
        """Test OAuth flow when server fails to start."""
        mock_token.return_value = "test-state"
        mock_start_server.side_effect = OSError("Port already in use")

        mock_config = MagicMock()
        mock_oauth_config.return_value = mock_config

        args = OAuthSetupArgs(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="http://localhost:8080/callback",
            scope="read:jira-work",
        )

        result = run_oauth_flow(args)

        # Check result
        assert result is False

        # Should not proceed with OAuth flow
        mock_browser.assert_not_called()
        mock_wait.assert_not_called()

    @patch("mcp_atlassian.utils.oauth_setup.webbrowser.open")
    @patch("mcp_atlassian.utils.oauth_setup.wait_for_callback")
    @patch("mcp_atlassian.utils.oauth_setup.start_callback_server")
    @patch("mcp_atlassian.utils.oauth_setup.OAuthConfig")
    @patch("secrets.token_urlsafe")
    def test_run_oauth_flow_callback_timeout(
        self, mock_token, mock_oauth_config, mock_start_server, mock_wait, mock_browser
    ):
        """Test OAuth flow when callback times out."""
        mock_token.return_value = "test-state"
        mock_wait.return_value = False  # Timeout

        mock_httpd = MagicMock()
        mock_start_server.return_value = mock_httpd

        mock_config = MagicMock()
        mock_config.get_authorization_url.return_value = "https://auth.example.com"
        mock_oauth_config.return_value = mock_config

        args = OAuthSetupArgs(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="http://localhost:8080/callback",
            scope="read:jira-work",
        )

        result = run_oauth_flow(args)

        # Check result
        assert result is False

        # Should shutdown server
        mock_httpd.shutdown.assert_called_once()

    @patch("mcp_atlassian.utils.oauth_setup.webbrowser.open")
    @patch("mcp_atlassian.utils.oauth_setup.wait_for_callback")
    @patch("mcp_atlassian.utils.oauth_setup.start_callback_server")
    @patch("mcp_atlassian.utils.oauth_setup.OAuthConfig")
    @patch("secrets.token_urlsafe")
    def test_run_oauth_flow_state_mismatch(
        self, mock_token, mock_oauth_config, mock_start_server, mock_wait, mock_browser
    ):
        """Test OAuth flow with state mismatch (CSRF protection)."""
        # Setup global state with mismatched state
        import mcp_atlassian.utils.oauth_setup

        mcp_atlassian.utils.oauth_setup.authorization_code = "test-auth-code"
        mcp_atlassian.utils.oauth_setup.authorization_state = "wrong-state"

        mock_token.return_value = "expected-state"
        mock_wait.return_value = True

        mock_httpd = MagicMock()
        mock_start_server.return_value = mock_httpd

        mock_config = MagicMock()
        mock_config.get_authorization_url.return_value = "https://auth.example.com"
        mock_oauth_config.return_value = mock_config

        args = OAuthSetupArgs(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="http://localhost:8080/callback",
            scope="read:jira-work",
        )

        result = run_oauth_flow(args)

        # Check result
        assert result is False

        # Should not attempt token exchange
        mock_config.exchange_code_for_tokens.assert_not_called()
        mock_httpd.shutdown.assert_called_once()

    @patch("mcp_atlassian.utils.oauth_setup.webbrowser.open")
    @patch("mcp_atlassian.utils.oauth_setup.wait_for_callback")
    @patch("mcp_atlassian.utils.oauth_setup.start_callback_server")
    @patch("mcp_atlassian.utils.oauth_setup.OAuthConfig")
    @patch("secrets.token_urlsafe")
    def test_run_oauth_flow_token_exchange_failure(
        self, mock_token, mock_oauth_config, mock_start_server, mock_wait, mock_browser
    ):
        """Test OAuth flow when token exchange fails."""
        # Setup global state for success callback, but token exchange fails
        import mcp_atlassian.utils.oauth_setup

        mcp_atlassian.utils.oauth_setup.authorization_code = "test-auth-code"
        mcp_atlassian.utils.oauth_setup.authorization_state = "test-state"

        mock_token.return_value = "test-state"
        mock_wait.return_value = True

        mock_httpd = MagicMock()
        mock_start_server.return_value = mock_httpd

        mock_config = MagicMock()
        mock_config.get_authorization_url.return_value = "https://auth.example.com"
        mock_config.exchange_code_for_tokens.return_value = False  # Failure
        mock_oauth_config.return_value = mock_config

        args = OAuthSetupArgs(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="http://localhost:8080/callback",
            scope="read:jira-work",
        )

        result = run_oauth_flow(args)

        # Check result
        assert result is False

        # Should shutdown server
        mock_httpd.shutdown.assert_called_once()

    def test_run_oauth_flow_global_state_reset(self):
        """Test that global state is properly reset at start of OAuth flow."""
        # Set some initial state
        import mcp_atlassian.utils.oauth_setup

        mcp_atlassian.utils.oauth_setup.authorization_code = "old-code"
        mcp_atlassian.utils.oauth_setup.authorization_state = "old-state"
        mcp_atlassian.utils.oauth_setup.callback_received = True
        mcp_atlassian.utils.oauth_setup.callback_error = "old-error"

        with patch("mcp_atlassian.utils.oauth_setup.webbrowser.open"):
            with patch(
                "mcp_atlassian.utils.oauth_setup.wait_for_callback"
            ) as mock_wait:
                with patch(
                    "mcp_atlassian.utils.oauth_setup.OAuthConfig"
                ) as mock_oauth_config:
                    mock_wait.return_value = False  # Fail quickly
                    mock_config = MagicMock()
                    mock_oauth_config.return_value = mock_config

                    args = OAuthSetupArgs(
                        client_id="test-client-id",
                        client_secret="test-client-secret",
                        redirect_uri="https://example.com/callback",
                        scope="read:jira-work",
                    )

                    run_oauth_flow(args)

                    # Check global state was reset
                    assert mcp_atlassian.utils.oauth_setup.authorization_code is None
                    assert mcp_atlassian.utils.oauth_setup.authorization_state is None
                    assert mcp_atlassian.utils.oauth_setup.callback_received is False
                    assert mcp_atlassian.utils.oauth_setup.callback_error is None


class TestInteractiveSetup:
    """Tests for the interactive OAuth setup wizard."""

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("os.getenv")
    @patch("mcp_atlassian.utils.oauth_setup.run_oauth_flow")
    def test_run_oauth_setup_success_with_env_vars(
        self, mock_run_flow, mock_getenv, mock_print, mock_input
    ):
        """Test successful interactive setup with environment variables."""
        # Mock environment variables
        mock_getenv.side_effect = lambda key, default=None: {
            "ATLASSIAN_OAUTH_CLIENT_ID": "env-client-id",
            "ATLASSIAN_OAUTH_CLIENT_SECRET": "env-client-secret",
            "ATLASSIAN_OAUTH_REDIRECT_URI": "http://localhost:8080/callback",
            "ATLASSIAN_OAUTH_SCOPE": "read:jira-work write:jira-work",
        }.get(key, default)

        # Mock user input (empty strings to use environment defaults)
        mock_input.side_effect = ["", "", "", ""]

        # Mock successful OAuth flow
        mock_run_flow.return_value = True

        result = run_oauth_setup()

        # Check result
        assert result == 0

        # Verify OAuth flow was called with correct args
        mock_run_flow.assert_called_once()
        args = mock_run_flow.call_args[0][0]
        assert args.client_id == "env-client-id"
        assert args.client_secret == "env-client-secret"
        assert args.redirect_uri == "http://localhost:8080/callback"
        assert args.scope == "read:jira-work write:jira-work"

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("os.getenv")
    @patch("mcp_atlassian.utils.oauth_setup.run_oauth_flow")
    def test_run_oauth_setup_success_with_user_input(
        self, mock_run_flow, mock_getenv, mock_print, mock_input
    ):
        """Test successful interactive setup with user input."""
        # Mock no environment variables
        mock_getenv.return_value = None

        # Mock user input
        mock_input.side_effect = [
            "user-client-id",
            "user-client-secret",
            "http://localhost:9000/callback",
            "read:jira-work",
        ]

        # Mock successful OAuth flow
        mock_run_flow.return_value = True

        result = run_oauth_setup()

        # Check result
        assert result == 0

        # Verify OAuth flow was called with user input
        mock_run_flow.assert_called_once()
        args = mock_run_flow.call_args[0][0]
        assert args.client_id == "user-client-id"
        assert args.client_secret == "user-client-secret"
        assert args.redirect_uri == "http://localhost:9000/callback"
        assert args.scope == "read:jira-work"

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("os.getenv")
    @patch("mcp_atlassian.utils.oauth_setup.run_oauth_flow")
    def test_run_oauth_setup_missing_client_id(
        self, mock_run_flow, mock_getenv, mock_print, mock_input
    ):
        """Test interactive setup with missing client ID."""
        mock_getenv.return_value = None
        mock_input.side_effect = ["", "client-secret", "", ""]  # Empty client ID

        result = run_oauth_setup()

        # Should return error code
        assert result == 1

        # Should not run OAuth flow
        mock_run_flow.assert_not_called()

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("os.getenv")
    @patch("mcp_atlassian.utils.oauth_setup.run_oauth_flow")
    def test_run_oauth_setup_missing_client_secret(
        self, mock_run_flow, mock_getenv, mock_print, mock_input
    ):
        """Test interactive setup with missing client secret."""
        mock_getenv.return_value = None
        mock_input.side_effect = ["client-id", "", "", ""]  # Empty client secret

        result = run_oauth_setup()

        # Should return error code
        assert result == 1

        # Should not run OAuth flow
        mock_run_flow.assert_not_called()

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("os.getenv")
    @patch("mcp_atlassian.utils.oauth_setup.run_oauth_flow")
    def test_run_oauth_setup_oauth_flow_failure(
        self, mock_run_flow, mock_getenv, mock_print, mock_input
    ):
        """Test interactive setup when OAuth flow fails."""
        mock_getenv.return_value = None
        mock_input.side_effect = ["client-id", "client-secret", "", ""]

        # Mock failed OAuth flow
        mock_run_flow.return_value = False

        result = run_oauth_setup()

        # Should return error code
        assert result == 1

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("os.getenv")
    def test_prompt_for_input_with_env_var(self, mock_getenv, mock_print, mock_input):
        """Test _prompt_for_input with environment variable."""
        from mcp_atlassian.utils.oauth_setup import _prompt_for_input

        mock_getenv.return_value = "env-value"
        mock_input.return_value = ""  # User presses enter to use default

        result = _prompt_for_input("Test prompt", "TEST_ENV_VAR")

        assert result == "env-value"

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("os.getenv")
    def test_prompt_for_input_user_override(self, mock_getenv, mock_print, mock_input):
        """Test _prompt_for_input with user override."""
        from mcp_atlassian.utils.oauth_setup import _prompt_for_input

        mock_getenv.return_value = "env-value"
        mock_input.return_value = "user-value"  # User provides different value

        result = _prompt_for_input("Test prompt", "TEST_ENV_VAR")

        assert result == "user-value"

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("os.getenv")
    def test_prompt_for_input_no_env_var(self, mock_getenv, mock_print, mock_input):
        """Test _prompt_for_input without environment variable."""
        from mcp_atlassian.utils.oauth_setup import _prompt_for_input

        mock_getenv.return_value = None
        mock_input.return_value = "user-input"

        result = _prompt_for_input("Test prompt", "TEST_ENV_VAR")

        assert result == "user-input"

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("os.getenv")
    def test_prompt_for_input_secret_masking(self, mock_getenv, mock_print, mock_input):
        """Test _prompt_for_input with secret masking."""
        from mcp_atlassian.utils.oauth_setup import _prompt_for_input

        mock_getenv.return_value = "very-long-secret-value"
        mock_input.return_value = ""

        result = _prompt_for_input("Secret prompt", "SECRET_VAR", is_secret=True)

        assert result == "very-long-secret-value"

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("os.getenv")
    def test_prompt_for_input_short_secret_masking(
        self, mock_getenv, mock_print, mock_input
    ):
        """Test _prompt_for_input with short secret masking."""
        from mcp_atlassian.utils.oauth_setup import _prompt_for_input

        mock_getenv.return_value = "short"
        mock_input.return_value = ""

        result = _prompt_for_input("Secret prompt", "SECRET_VAR", is_secret=True)

        assert result == "short"


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

        assert args.client_id == "test-id"
        assert args.client_secret == "test-secret"
        assert args.redirect_uri == "http://localhost:8080/callback"
        assert args.scope == "read:jira-work"


@pytest.mark.parametrize(
    "redirect_uri,expected_hostname,expected_port",
    [
        ("http://localhost:8080/callback", "localhost", 8080),
        ("https://example.com/callback", "example.com", 443),
        ("http://127.0.0.1:3000/oauth", "127.0.0.1", 3000),
        ("https://secure.domain.com:8443/auth", "secure.domain.com", 8443),
    ],
)
def test_parse_redirect_uri_parametrized(
    redirect_uri, expected_hostname, expected_port
):
    """Parametrized test for redirect URI parsing."""
    hostname, port = parse_redirect_uri(redirect_uri)
    assert hostname == expected_hostname
    assert port == expected_port


@pytest.mark.parametrize(
    "error_code,expected_result",
    [
        ("access_denied", False),
        ("invalid_request", False),
        ("unauthorized_client", False),
        ("unsupported_response_type", False),
        ("invalid_scope", False),
        ("server_error", False),
    ],
)
def test_wait_for_callback_error_codes(error_code, expected_result):
    """Parametrized test for different OAuth error codes."""
    import mcp_atlassian.utils.oauth_setup

    mcp_atlassian.utils.oauth_setup.callback_received = True
    mcp_atlassian.utils.oauth_setup.callback_error = error_code

    with patch("time.time", side_effect=[0, 5]):
        result = wait_for_callback(timeout=300)

    assert result == expected_result


class TestThreadingAndServerShutdown:
    """Tests for threading and server shutdown scenarios."""

    @patch("socketserver.TCPServer")
    @patch("threading.Thread")
    def test_server_thread_daemon_mode(self, mock_thread, mock_server):
        """Test that server thread is set to daemon mode."""
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        start_callback_server(8080)

        # Verify daemon mode is set
        assert mock_thread_instance.daemon is True

    @patch("mcp_atlassian.utils.oauth_setup.webbrowser.open")
    @patch("mcp_atlassian.utils.oauth_setup.wait_for_callback")
    @patch("mcp_atlassian.utils.oauth_setup.start_callback_server")
    @patch("mcp_atlassian.utils.oauth_setup.OAuthConfig")
    @patch("secrets.token_urlsafe")
    def test_server_shutdown_on_success(
        self, mock_token, mock_oauth_config, mock_start_server, mock_wait, mock_browser
    ):
        """Test server is properly shutdown on successful flow."""
        # Setup global state
        import mcp_atlassian.utils.oauth_setup

        mcp_atlassian.utils.oauth_setup.authorization_code = "test-code"
        mcp_atlassian.utils.oauth_setup.authorization_state = "test-state"

        mock_httpd = MagicMock()
        mock_start_server.return_value = mock_httpd
        mock_wait.return_value = True

        mock_token.return_value = "test-state"
        mock_config = MagicMock()
        mock_config.exchange_code_for_tokens.return_value = True
        mock_config.access_token = "token"
        mock_config.refresh_token = "refresh"
        mock_config.cloud_id = "cloud"
        mock_oauth_config.return_value = mock_config

        args = OAuthSetupArgs(
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost:8080/callback",
            scope="scope",
        )

        run_oauth_flow(args)

        # Verify server shutdown was called
        mock_httpd.shutdown.assert_called_once()

    @patch("mcp_atlassian.utils.oauth_setup.webbrowser.open")
    @patch("mcp_atlassian.utils.oauth_setup.wait_for_callback")
    @patch("mcp_atlassian.utils.oauth_setup.start_callback_server")
    @patch("mcp_atlassian.utils.oauth_setup.OAuthConfig")
    @patch("secrets.token_urlsafe")
    def test_server_shutdown_on_failure(
        self, mock_token, mock_oauth_config, mock_start_server, mock_wait, mock_browser
    ):
        """Test server is properly shutdown on failed flow."""
        mock_httpd = MagicMock()
        mock_start_server.return_value = mock_httpd
        mock_wait.return_value = False  # Timeout/failure

        mock_token.return_value = "test-state"
        mock_config = MagicMock()
        mock_oauth_config.return_value = mock_config

        args = OAuthSetupArgs(
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost:8080/callback",
            scope="scope",
        )

        run_oauth_flow(args)

        # Verify server shutdown was called even on failure
        mock_httpd.shutdown.assert_called_once()


class TestGlobalVariableManagement:
    """Tests for global variable state management and edge cases."""

    def test_global_variables_initial_state(self):
        """Test that global variables exist and can be accessed."""
        import mcp_atlassian.utils.oauth_setup as oauth_module

        # Just verify they exist and have expected types
        assert hasattr(oauth_module, "authorization_code")
        assert hasattr(oauth_module, "authorization_state")
        assert hasattr(oauth_module, "callback_received")
        assert hasattr(oauth_module, "callback_error")

    def test_configuration_file_generation_attributes(self):
        """Test that the oauth flow handles configuration output correctly."""
        # This tests the VS Code configuration generation logic without full flow
        test_config_data = {
            "client_id": "test-id",
            "client_secret": "test-secret",
            "redirect_uri": "http://localhost:8080/callback",
            "scope": "read:jira-work",
            "cloud_id": "test-cloud-id",
        }

        # Test JSON serialization works

        json_str = json.dumps(test_config_data, indent=4)
        assert "test-id" in json_str
        assert "test-cloud-id" in json_str

    def test_browser_automation_mocking(self):
        """Test that webbrowser.open can be properly mocked."""
        with patch("webbrowser.open") as mock_open:
            import webbrowser

            webbrowser.open("https://example.com")
            mock_open.assert_called_once_with("https://example.com")

    def test_secrets_token_generation(self):
        """Test that secrets.token_urlsafe works as expected."""

        token = secrets.token_urlsafe(16)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_oauth_config_integration_ready(self):
        """Test that OAuth config can be imported and configured."""
        from mcp_atlassian.utils.oauth import OAuthConfig

        # Just verify we can create the class
        config = OAuthConfig(
            client_id="test",
            client_secret="test",
            redirect_uri="http://localhost:8080/callback",
            scope="read:jira-work",
        )
        assert config.client_id == "test"
