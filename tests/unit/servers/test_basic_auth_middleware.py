"""Tests for Basic Authentication in UserTokenMiddleware."""

import base64
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_atlassian.servers.main import UserTokenMiddleware


class TestUserTokenMiddlewareBasicAuth(unittest.TestCase):
    """Test cases for Basic Authentication in UserTokenMiddleware."""

    def setUp(self):
        """Set up test fixtures."""
        self.app = MagicMock()
        self.mcp_server_ref = MagicMock()
        self.mcp_server_ref.settings.streamable_http_path = "/mcp"
        self.middleware = UserTokenMiddleware(self.app, self.mcp_server_ref)

        # Create a mock request
        self.request = MagicMock(spec=Request)
        self.request.url.path = "/mcp"
        self.request.method = "POST"
        self.request.headers = {}
        self.request.state = MagicMock()

        # Mock call_next function
        self.call_next = AsyncMock()
        self.call_next.return_value = JSONResponse({"status": "ok"})

    async def _dispatch_with_auth_header(self, auth_header):
        """Helper method to dispatch a request with the given auth header."""
        self.request.headers = {"Authorization": auth_header}
        return await self.middleware.dispatch(self.request, self.call_next)

    @patch("mcp_atlassian.servers.main.logger")
    async def test_basic_auth_valid_credentials(self, mock_logger):
        """Test that valid Basic Authentication credentials are properly decoded and stored."""
        # Create valid Basic Auth token
        username = "test@example.com"
        password = "password123"
        credentials = f"{username}:{password}"
        token = base64.b64encode(credentials.encode()).decode()
        auth_header = f"Basic {token}"

        # Dispatch request with Basic Auth header
        await self._dispatch_with_auth_header(auth_header)

        # Verify that credentials were properly extracted and stored
        self.assertEqual(self.request.state.user_atlassian_auth_type, "basic")
        self.assertEqual(self.request.state.user_atlassian_email, username)
        self.assertEqual(self.request.state.user_atlassian_token, password)

        # Verify that call_next was called
        self.call_next.assert_called_once_with(self.request)

    @patch("mcp_atlassian.servers.main.logger")
    async def test_basic_auth_empty_token(self, mock_logger):
        """Test handling of empty Basic Authentication token."""
        # Create empty Basic Auth token
        auth_header = "Basic "

        # Dispatch request with empty Basic Auth header
        response = await self._dispatch_with_auth_header(auth_header)

        # Verify that an error response was returned
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            await response.json(), {"error": "Unauthorized: Empty Basic token"}
        )

        # Verify that call_next was not called
        self.call_next.assert_not_called()

    @patch("mcp_atlassian.servers.main.logger")
    async def test_basic_auth_invalid_token(self, mock_logger):
        """Test handling of invalid Basic Authentication token."""
        # Create invalid Basic Auth token
        auth_header = "Basic invalid-base64!"

        # Dispatch request with invalid Basic Auth header
        response = await self._dispatch_with_auth_header(auth_header)

        # Verify that an error response was returned
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            await response.json(),
            {"error": "Unauthorized: Invalid Basic Authentication token"},
        )

        # Verify that call_next was not called
        self.call_next.assert_not_called()

    @patch("mcp_atlassian.servers.main.logger")
    async def test_basic_auth_missing_password(self, mock_logger):
        """Test handling of Basic Authentication token without password."""
        # Create Basic Auth token without password
        username = "test@example.com"
        token = base64.b64encode(username.encode()).decode()
        auth_header = f"Basic {token}"

        # Dispatch request with Basic Auth header missing password
        response = await self._dispatch_with_auth_header(auth_header)

        # Verify that an error response was returned
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            await response.json(),
            {"error": "Unauthorized: Invalid Basic Authentication token"},
        )

        # Verify that call_next was not called
        self.call_next.assert_not_called()
