"""Tests for the main MCP server implementation."""

import json
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from key_value.aio.stores.memory import MemoryStore

from mcp_atlassian.servers.main import AtlassianMCP, UserTokenMiddleware, main_mcp
from mcp_atlassian.servers.oauth_proxy import HardenedOAuthProxy
from mcp_atlassian.utils.token_verifier import AtlassianOpaqueTokenVerifier


@pytest.mark.anyio
async def test_run_server_stdio():
    """Test that main_mcp.run_async is called with stdio transport."""
    with patch.object(main_mcp, "run_async") as mock_run_async:
        mock_run_async.return_value = None
        await main_mcp.run_async(transport="stdio")
        mock_run_async.assert_called_once_with(transport="stdio")


@pytest.mark.anyio
async def test_run_server_sse():
    """Test that main_mcp.run_async is called with sse transport and correct port."""
    with patch.object(main_mcp, "run_async") as mock_run_async:
        mock_run_async.return_value = None
        test_port = 9000
        await main_mcp.run_async(transport="sse", port=test_port)
        mock_run_async.assert_called_once_with(transport="sse", port=test_port)


@pytest.mark.anyio
async def test_run_server_streamable_http():
    """Test that main_mcp.run_async is called with streamable-http transport and correct parameters."""
    with patch.object(main_mcp, "run_async") as mock_run_async:
        mock_run_async.return_value = None
        test_port = 9001
        test_host = "127.0.0.1"
        test_path = "/custom_mcp"
        await main_mcp.run_async(
            transport="streamable-http", port=test_port, host=test_host, path=test_path
        )
        mock_run_async.assert_called_once_with(
            transport="streamable-http", port=test_port, host=test_host, path=test_path
        )


@pytest.mark.anyio
async def test_run_server_streamable_http_stateless():
    """Test that main_mcp.run_async is called with streamable-http transport and correct parameters."""
    with patch.object(main_mcp, "run_async") as mock_run_async:
        mock_run_async.return_value = None
        test_port = 9001
        test_host = "127.0.0.1"
        test_path = "/custom_mcp"
        await main_mcp.run_async(
            transport="streamable-http",
            port=test_port,
            host=test_host,
            path=test_path,
            stateless_http=True,
        )
        mock_run_async.assert_called_once_with(
            transport="streamable-http",
            port=test_port,
            host=test_host,
            path=test_path,
            stateless_http=True,
        )


@pytest.mark.anyio
async def test_run_server_invalid_transport():
    """Test that run_server raises ValueError for invalid transport."""
    # We don't need to patch run_async here as the error occurs before it's called
    with pytest.raises(ValueError) as excinfo:
        await main_mcp.run_async(transport="invalid")  # pyright: ignore[reportArgumentType]

    assert "Unknown transport" in str(excinfo.value)
    assert "invalid" in str(excinfo.value)


@pytest.mark.anyio
async def test_tool_registration_issue_dates_name():
    """Ensure issue dates tool is registered with a single Jira prefix."""
    tools = await main_mcp.list_tools()
    tool_names = {tool.name for tool in tools}
    assert "jira_get_issue_dates" in tool_names
    assert "jira_jira_get_issue_dates" not in tool_names


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool_name",
    [
        "confluence_add_label",
        "confluence_create_page",
        "confluence_add_comment",
        "confluence_reply_to_comment",
        "jira_add_watcher",
        "jira_create_issue",
        "jira_batch_create_issues",
        "jira_add_comment",
        "jira_create_issue_link",
        "jira_create_remote_issue_link",
        "jira_create_sprint",
        "jira_create_version",
        "jira_batch_create_versions",
    ],
)
async def test_additive_write_tools_are_non_destructive(tool_name: str) -> None:
    """Ensure additive write tools advertise that they preserve existing state."""
    tools = {tool.name: tool for tool in await main_mcp.list_tools()}

    assert tools[tool_name].annotations.destructiveHint is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool_name",
    [
        "jira_remove_watcher",
        "jira_add_issues_to_sprint",
        "jira_add_worklog",
    ],
)
async def test_state_changing_write_tools_are_destructive(tool_name: str) -> None:
    """Ensure tools that remove or reassign state advertise destructive behavior."""
    tools = {tool.name: tool for tool in await main_mcp.list_tools()}

    assert tools[tool_name].annotations.destructiveHint is True


@pytest.mark.anyio
async def test_health_check_endpoint():
    """Test the health check endpoint returns 200 and correct JSON response."""
    app = main_mcp.http_app(transport="sse")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_sse_app_health_check_endpoint():
    """Test the /healthz endpoint on the SSE app returns 200 and correct JSON response."""
    app = main_mcp.http_app(transport="sse")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_streamable_http_app_health_check_endpoint():
    """Test the /healthz endpoint on the Streamable HTTP app returns 200 and correct JSON response."""
    app = main_mcp.http_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_streamable_http_path_is_normalized_without_trailing_slash():
    app = main_mcp.http_app(transport="streamable-http", path="/mcp/")
    assert app.state.path == "/mcp"


@pytest.mark.parametrize(
    ("transport", "path", "expected_paths", "expected_mounts"),
    [
        ("http", "/http-alias/", {"/http-alias"}, set()),
        ("streamable-http", "/custom-mcp/", {"/custom-mcp"}, set()),
        ("sse", "/custom-sse/", {"/custom-sse"}, {"/messages"}),
    ],
)
def test_http_app_configures_auth_for_transport_endpoints(
    transport, path, expected_paths, expected_mounts
):
    app = main_mcp.http_app(transport=transport, path=path)
    middleware = next(
        item for item in app.user_middleware if item.cls is UserTokenMiddleware
    )

    assert middleware.kwargs["auth_paths"] == frozenset(expected_paths)
    assert middleware.kwargs["auth_mounts"] == frozenset(expected_mounts)


_ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


@pytest.mark.security_regression
@pytest.mark.anyio
@pytest.mark.parametrize("method", _ALL_METHODS)
@pytest.mark.parametrize(
    "path",
    [
        "/sse",
        "/sse/",
        "/messages",
        "/messages/",
        "/messages/?session_id=missing",
        "/messages/extra",
    ],
)
async def test_sse_app_rejects_unauthenticated_requests_for_every_method(
    method, path, monkeypatch
):
    monkeypatch.delenv("ALLOW_GLOBAL_CRED_FALLBACK", raising=False)
    monkeypatch.delenv("IGNORE_HEADER_AUTH", raising=False)
    app = main_mcp.http_app(transport="sse")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(method, path)

    assert response.status_code == 401


@pytest.mark.security_regression
@pytest.mark.anyio
@pytest.mark.parametrize("method", _ALL_METHODS)
@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
async def test_streamable_http_app_rejects_unauthenticated_requests_for_every_method(
    method, path, monkeypatch
):
    monkeypatch.delenv("ALLOW_GLOBAL_CRED_FALLBACK", raising=False)
    monkeypatch.delenv("IGNORE_HEADER_AUTH", raising=False)
    app = main_mcp.http_app(transport="streamable-http")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(
            method,
            path,
            headers={
                "accept": "application/json, text/event-stream",
                "mcp-session-id": "0123456789abcdef0123456789abcdef",
            },
        )

    assert response.status_code == 401


@pytest.mark.anyio
@pytest.mark.parametrize("transport_name", ["sse", "streamable-http"])
async def test_transport_auth_gate_leaves_health_check_open(
    transport_name, monkeypatch
):
    monkeypatch.delenv("ALLOW_GLOBAL_CRED_FALLBACK", raising=False)
    app = main_mcp.http_app(transport=transport_name)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200


class TestUserTokenMiddleware:
    """Tests for the UserTokenMiddleware class."""

    @pytest.fixture
    def middleware(self):
        """Create a UserTokenMiddleware instance for testing."""
        mock_app = AsyncMock()
        # Create a mock MCP server to avoid warnings
        mock_mcp_server = MagicMock()
        mock_mcp_server.settings.streamable_http_path = "/mcp"
        mock_mcp_server.get_streamable_http_path.return_value = "/mcp"
        mock_mcp_server.auth = None
        return UserTokenMiddleware(mock_app, mcp_server_ref=mock_mcp_server)

    @pytest.fixture
    def mock_scope(self):
        """Create a mock ASGI scope for testing."""
        return {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [],
            "state": {},
        }

    @pytest.fixture
    def mock_receive(self):
        """Create a mock ASGI receive callable."""
        return AsyncMock()

    @pytest.fixture
    def mock_send(self):
        """Create a mock ASGI send callable."""
        return AsyncMock()

    @pytest.mark.anyio
    async def test_cloud_id_header_extraction_success(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test successful cloud ID header extraction."""
        # Setup scope with cloud ID header (ASGI headers are byte tuples)
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
            (b"x-atlassian-cloud-id", b"test-cloud-id-123"),
        ]

        # Call the middleware
        await middleware(mock_scope, mock_receive, mock_send)

        # Verify cloud ID was extracted and stored in scope state
        assert "user_atlassian_cloud_id" in mock_scope["state"]
        assert mock_scope["state"]["user_atlassian_cloud_id"] == "test-cloud-id-123"

        # Verify authentication token was also extracted
        assert "user_atlassian_token" in mock_scope["state"]
        assert mock_scope["state"]["user_atlassian_token"] == "test-token"
        assert mock_scope["state"]["user_atlassian_auth_type"] == "oauth"

        # Verify the app was called (we don't check exact parameters since send is wrapped)
        middleware.app.assert_called_once()

        # Verify the scope passed to the app has the correct structure
        call_args = middleware.app.call_args
        assert call_args is not None
        passed_scope, passed_receive, passed_send = call_args[0]

        # Verify scope was copied and modified correctly
        assert passed_scope["type"] == "http"
        assert passed_scope["method"] == "POST"
        assert passed_scope["path"] == "/mcp"
        assert passed_scope["state"]["user_atlassian_cloud_id"] == "test-cloud-id-123"

    @pytest.mark.anyio
    async def test_empty_bearer_token_returns_401(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that empty Bearer token returns 401 Unauthorized."""
        mock_scope["headers"] = [(b"authorization", b"Bearer ")]

        await middleware(mock_scope, mock_receive, mock_send)

        # Verify 401 response was sent (response.start + response.body)
        assert mock_send.call_count == 2
        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["type"] == "http.response.start"
        assert start_call["status"] == 401

        body_call = mock_send.call_args_list[1][0][0]
        assert body_call["type"] == "http.response.body"
        body = json.loads(body_call["body"].decode())
        assert "error" in body
        assert "Empty Bearer token" in body["error"]

        # Verify app was NOT called
        middleware.app.assert_not_called()

    @pytest.mark.anyio
    async def test_empty_pat_token_returns_401(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that empty Token (PAT) returns 401 Unauthorized."""
        mock_scope["headers"] = [(b"authorization", b"Token ")]

        await middleware(mock_scope, mock_receive, mock_send)

        # Verify 401 response was sent
        assert mock_send.call_count == 2
        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["status"] == 401

        body_call = mock_send.call_args_list[1][0][0]
        body = json.loads(body_call["body"].decode())
        assert "Empty Token (PAT)" in body["error"]

        # Verify app was NOT called
        middleware.app.assert_not_called()

    @pytest.mark.anyio
    async def test_unsupported_auth_type_returns_401(
        self, middleware, mock_scope, mock_receive, mock_send, caplog
    ):
        """Test that unsupported auth types (e.g., Digest) return 401 Unauthorized."""
        mock_scope["headers"] = [(b"authorization", b"Digest username=test")]

        with caplog.at_level(logging.WARNING, logger="mcp-atlassian.server.main"):
            await middleware(mock_scope, mock_receive, mock_send)

        # Verify 401 response was sent
        assert mock_send.call_count == 2
        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["status"] == 401

        body_call = mock_send.call_args_list[1][0][0]
        body = json.loads(body_call["body"].decode())
        assert (
            "Bearer" in body["error"]
            or "Token" in body["error"]
            or "Basic" in body["error"]
        )

        # Verify app was NOT called
        middleware.app.assert_not_called()
        assert "Unsupported Authorization type: Digest" in caplog.text
        assert "username=test" not in caplog.text

    @pytest.mark.anyio
    async def test_raw_auth_token_is_redacted_in_warning(
        self, middleware, mock_scope, mock_receive, mock_send, caplog
    ):
        """Test that raw Authorization values are redacted from warning logs."""
        raw_token = "raw-token-without-prefix"
        mock_scope["headers"] = [(b"authorization", raw_token.encode())]

        with caplog.at_level(logging.WARNING, logger="mcp-atlassian.server.main"):
            await middleware(mock_scope, mock_receive, mock_send)

        assert mock_send.call_count == 2
        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["status"] == 401

        body_call = mock_send.call_args_list[1][0][0]
        body = json.loads(body_call["body"].decode())
        assert "Bearer" in body["error"]

        middleware.app.assert_not_called()
        assert "Unsupported Authorization type: <redacted>" in caplog.text
        assert raw_token not in caplog.text

    @pytest.mark.anyio
    async def test_whitespace_only_auth_returns_401(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that whitespace-only Authorization header returns 401."""
        mock_scope["headers"] = [(b"authorization", b"   ")]

        await middleware(mock_scope, mock_receive, mock_send)

        # Verify 401 response was sent
        assert mock_send.call_count == 2
        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["status"] == 401

        body_call = mock_send.call_args_list[1][0][0]
        body = json.loads(body_call["body"].decode())
        assert "Empty Authorization header" in body["error"]

        # Verify app was NOT called
        middleware.app.assert_not_called()

    @pytest.mark.security_regression
    @pytest.mark.anyio
    async def test_missing_authorization_header_returns_401(
        self, middleware, mock_scope, mock_receive, mock_send, monkeypatch
    ):
        """An unauthenticated POST to the MCP endpoint must be rejected at the
        transport boundary, not proxied to the app with the operator's credentials.

        The dependencies-level global-fallback test is necessary but not sufficient,
        because the request can still reach the app here. Secure contract: with no
        Authorization header and ``ALLOW_GLOBAL_CRED_FALLBACK`` off, return 401 and do
        not call ``self.app``.
        """
        monkeypatch.setenv("ALLOW_GLOBAL_CRED_FALLBACK", "false")
        # No Authorization header and no service headers -> unauthenticated request.
        mock_scope["headers"] = []

        await middleware(mock_scope, mock_receive, mock_send)

        # Secure: the request must be rejected before reaching the downstream app.
        middleware.app.assert_not_called()
        assert mock_send.call_count >= 1, "expected a 401 response, none was sent"
        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["type"] == "http.response.start"
        assert start_call["status"] == 401

    @pytest.mark.security_regression
    @pytest.mark.anyio
    async def test_oauth_provider_missing_authorization_defers_to_app(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """An OAuth-protected request must reach FastMCP for its challenge."""
        middleware.mcp_server_ref.auth = MagicMock()
        mock_scope["headers"] = []

        await middleware(mock_scope, mock_receive, mock_send)

        middleware.app.assert_called_once()
        mock_send.assert_not_called()

    @pytest.mark.anyio
    async def test_client_disconnect_connection_reset(
        self, middleware, mock_scope, mock_receive
    ):
        """Test that ConnectionResetError during send is handled gracefully."""
        mock_scope["headers"] = [(b"authorization", b"Bearer valid-token")]

        # Mock send that raises ConnectionResetError
        disconnect_send = AsyncMock(
            side_effect=ConnectionResetError("Connection reset")
        )

        # Should not raise - should handle gracefully
        await middleware(mock_scope, mock_receive, disconnect_send)

        # Verify middleware completed without raising
        middleware.app.assert_called_once()

    @pytest.mark.anyio
    async def test_client_disconnect_broken_pipe(
        self, middleware, mock_scope, mock_receive
    ):
        """Test that BrokenPipeError during send is handled gracefully."""
        mock_scope["headers"] = [(b"authorization", b"Bearer valid-token")]

        disconnect_send = AsyncMock(side_effect=BrokenPipeError("Broken pipe"))

        # Should not raise
        await middleware(mock_scope, mock_receive, disconnect_send)

        middleware.app.assert_called_once()

    @pytest.mark.anyio
    async def test_client_disconnect_oserror(
        self, middleware, mock_scope, mock_receive
    ):
        """Test that OSError during send is handled gracefully."""
        mock_scope["headers"] = [(b"authorization", b"Bearer valid-token")]

        disconnect_send = AsyncMock(side_effect=OSError("Network error"))

        await middleware(mock_scope, mock_receive, disconnect_send)

        middleware.app.assert_called_once()

    @pytest.mark.anyio
    async def test_non_http_scope_passthrough(
        self, middleware, mock_receive, mock_send
    ):
        """Test that non-HTTP requests are passed through unchanged."""
        websocket_scope = {
            "type": "websocket",
            "path": "/ws",
        }

        await middleware(websocket_scope, mock_receive, mock_send)

        # Verify app was called with original scope (not modified)
        middleware.app.assert_called_once()
        passed_scope = middleware.app.call_args[0][0]
        assert passed_scope["type"] == "websocket"
        assert "state" not in passed_scope  # No auth state added

    @pytest.mark.anyio
    async def test_mcp_session_id_logged(
        self, middleware, mock_scope, mock_receive, mock_send, caplog
    ):
        """Test that mcp-session-id header is logged for debugging."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer valid-token"),
            (b"mcp-session-id", b"test-session-123"),
        ]

        with caplog.at_level(logging.DEBUG, logger="mcp-atlassian.server.main"):
            await middleware(mock_scope, mock_receive, mock_send)

        assert "MCP-Session-ID header found: test-session-123" in caplog.text

    @pytest.mark.anyio
    async def test_valid_bearer_token_proceeds(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that valid Bearer token allows request to proceed."""
        mock_scope["headers"] = [(b"authorization", b"Bearer valid-token-123")]

        await middleware(mock_scope, mock_receive, mock_send)

        # Verify app was called
        middleware.app.assert_called_once()

        # Verify no 401 was sent (send should not be called directly by middleware)
        mock_send.assert_not_called()

        # Verify token was extracted
        passed_scope = middleware.app.call_args[0][0]
        assert passed_scope["state"]["user_atlassian_token"] == "valid-token-123"
        assert passed_scope["state"]["user_atlassian_auth_type"] == "oauth"

    @pytest.mark.anyio
    async def test_valid_pat_token_proceeds(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that valid PAT token allows request to proceed."""
        mock_scope["headers"] = [(b"authorization", b"Token my-pat-token")]

        await middleware(mock_scope, mock_receive, mock_send)

        # Verify app was called
        middleware.app.assert_called_once()

        # Verify token was extracted
        passed_scope = middleware.app.call_args[0][0]
        assert passed_scope["state"]["user_atlassian_token"] == "my-pat-token"
        assert passed_scope["state"]["user_atlassian_auth_type"] == "pat"

    @pytest.mark.anyio
    async def test_basic_auth_header_extraction_success(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test successful Basic auth header extraction."""
        import base64

        credentials = base64.b64encode(b"user@example.com:api-token-123").decode()
        mock_scope["headers"] = [
            (b"authorization", f"Basic {credentials}".encode()),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        # Verify app was called (no 401)
        middleware.app.assert_called_once()
        mock_send.assert_not_called()

        # Verify credentials were extracted
        passed_scope = middleware.app.call_args[0][0]
        assert passed_scope["state"]["user_atlassian_auth_type"] == "basic"
        assert passed_scope["state"]["user_atlassian_email"] == "user@example.com"
        assert passed_scope["state"]["user_atlassian_api_token"] == "api-token-123"
        assert passed_scope["state"]["user_atlassian_token"] is None

    @pytest.mark.anyio
    async def test_basic_auth_malformed_base64_returns_401(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that malformed base64 in Basic auth returns 401."""
        mock_scope["headers"] = [(b"authorization", b"Basic !!!not-base64!!!")]

        await middleware(mock_scope, mock_receive, mock_send)

        assert mock_send.call_count == 2
        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["status"] == 401

        body_call = mock_send.call_args_list[1][0][0]
        body = json.loads(body_call["body"].decode())
        assert "error" in body
        middleware.app.assert_not_called()

    @pytest.mark.anyio
    async def test_basic_auth_missing_colon_returns_401(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that base64 without colon separator returns 401."""
        import base64

        encoded = base64.b64encode(b"no-colon-here").decode()
        mock_scope["headers"] = [(b"authorization", f"Basic {encoded}".encode())]

        await middleware(mock_scope, mock_receive, mock_send)

        assert mock_send.call_count == 2
        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["status"] == 401

        body_call = mock_send.call_args_list[1][0][0]
        body = json.loads(body_call["body"].decode())
        assert "email:api_token" in body["error"]
        middleware.app.assert_not_called()

    @pytest.mark.anyio
    async def test_basic_auth_empty_email_returns_401(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that empty email in Basic auth returns 401."""
        import base64

        encoded = base64.b64encode(b":api-token").decode()
        mock_scope["headers"] = [(b"authorization", f"Basic {encoded}".encode())]

        await middleware(mock_scope, mock_receive, mock_send)

        assert mock_send.call_count == 2
        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["status"] == 401

        body_call = mock_send.call_args_list[1][0][0]
        body = json.loads(body_call["body"].decode())
        assert "empty" in body["error"].lower() or "Email" in body["error"]
        middleware.app.assert_not_called()

    @pytest.mark.anyio
    async def test_basic_auth_empty_token_returns_401(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that empty API token in Basic auth returns 401."""
        import base64

        encoded = base64.b64encode(b"user@example.com:").decode()
        mock_scope["headers"] = [(b"authorization", f"Basic {encoded}".encode())]

        await middleware(mock_scope, mock_receive, mock_send)

        assert mock_send.call_count == 2
        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["status"] == 401

        body_call = mock_send.call_args_list[1][0][0]
        body = json.loads(body_call["body"].decode())
        assert "empty" in body["error"].lower() or "token" in body["error"].lower()
        middleware.app.assert_not_called()

    @pytest.mark.anyio
    async def test_basic_auth_empty_credentials_returns_401(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test that empty Basic auth credentials returns 401."""
        mock_scope["headers"] = [(b"authorization", b"Basic ")]

        await middleware(mock_scope, mock_receive, mock_send)

        assert mock_send.call_count == 2
        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["status"] == 401
        middleware.app.assert_not_called()

    def test_should_process_auth_uses_runtime_streamable_path(self):
        mock_app = AsyncMock()
        mock_mcp_server = MagicMock()
        mock_mcp_server.get_streamable_http_path.return_value = "/custom-mcp"

        middleware = UserTokenMiddleware(mock_app, mcp_server_ref=mock_mcp_server)

        assert (
            middleware._should_process_auth(
                {"type": "http", "method": "POST", "path": "/custom-mcp/"}
            )
            is True
        )

    @pytest.mark.parametrize(
        ("method", "path", "expected"),
        [
            ("GET", "/custom-sse/", True),
            ("HEAD", "/custom-sse", True),
            ("POST", "/messages/", True),
            ("PUT", "/messages", True),
            ("DELETE", "/messages/extra", True),
            ("GET", "/custom-mcp", True),
            ("DELETE", "/custom-mcp/", True),
            ("GET", "/messagesx", False),
            ("GET", "/healthz", False),
            ("POST", "/unrelated", False),
        ],
    )
    def test_should_process_auth_matches_paths_for_every_method(
        self, middleware, method, path, expected
    ):
        middleware.auth_paths = frozenset({"/custom-sse", "/custom-mcp"})
        middleware.auth_mounts = frozenset({"/messages"})

        assert (
            middleware._should_process_auth(
                {"type": "http", "method": method, "path": path}
            )
            is expected
        )

    @pytest.mark.anyio
    async def test_missing_auth_is_allowed_when_global_fallback_is_enabled(
        self, middleware, mock_scope, mock_receive, mock_send, monkeypatch
    ):
        monkeypatch.setenv("ALLOW_GLOBAL_CRED_FALLBACK", "true")

        await middleware(mock_scope, mock_receive, mock_send)

        middleware.app.assert_called_once()
        mock_send.assert_not_called()

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "cloud_id",
        [
            "../../admin",
            "abc/def",
            "abc?x=1",
            "abc#frag",
            "abc%2F..",
            "-leading-hyphen",
            "a" * 129,
        ],
    )
    async def test_invalid_cloud_id_header_is_rejected(
        self, middleware, mock_scope, mock_receive, mock_send, cloud_id
    ):
        mock_scope["headers"] = [
            (b"authorization", b"Bearer user-token"),
            (b"x-atlassian-cloud-id", cloud_id.encode()),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["status"] == 401
        middleware.app.assert_not_called()

    @pytest.mark.anyio
    async def test_uuid_cloud_id_header_is_accepted(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        cloud_id = "1324a887-45db-1bf4-1e99-ef0ff456d421"
        mock_scope["headers"] = [
            (b"authorization", b"Bearer user-token"),
            (b"x-atlassian-cloud-id", f" {cloud_id} ".encode()),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        middleware.app.assert_called_once()
        passed_scope = middleware.app.call_args[0][0]
        assert passed_scope["state"]["user_atlassian_cloud_id"] == cloud_id

    @pytest.mark.parametrize("method", ["GET", "DELETE", "HEAD"])
    def test_should_process_auth_default_path_covers_every_method(
        self, middleware, method
    ):
        assert (
            middleware._should_process_auth(
                {"type": "http", "method": method, "path": "/mcp"}
            )
            is True
        )

    @pytest.mark.anyio
    @pytest.mark.parametrize("method", ["GET", "DELETE"])
    async def test_streamable_get_and_delete_without_credentials_return_401(
        self, middleware, mock_scope, mock_receive, mock_send, method, monkeypatch
    ):
        monkeypatch.delenv("ALLOW_GLOBAL_CRED_FALLBACK", raising=False)
        monkeypatch.delenv("IGNORE_HEADER_AUTH", raising=False)
        mock_scope["method"] = method

        await middleware(mock_scope, mock_receive, mock_send)

        start_call = mock_send.call_args_list[0][0][0]
        assert start_call["status"] == 401
        middleware.app.assert_not_called()

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("method", "path"), [("GET", "/sse"), ("PUT", "/messages/")]
    )
    async def test_sse_transport_processes_valid_authentication(
        self, middleware, mock_scope, mock_receive, mock_send, method, path
    ):
        middleware.auth_paths = frozenset({"/sse"})
        middleware.auth_mounts = frozenset({"/messages"})
        mock_scope.update(
            {
                "method": method,
                "path": path,
                "headers": [(b"authorization", b"Bearer user-token")],
            }
        )

        await middleware(mock_scope, mock_receive, mock_send)

        middleware.app.assert_called_once()
        passed_scope = middleware.app.call_args[0][0]
        assert passed_scope["state"]["user_atlassian_token"] == "user-token"
        assert passed_scope["state"]["user_atlassian_auth_type"] == "oauth"

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "env_value,should_skip",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("Yes", True),
            ("false", False),
            ("0", False),
            ("no", False),
            ("", False),
        ],
    )
    async def test_ignore_header_auth_env_var(
        self, middleware, mock_scope, mock_receive, mock_send, env_value, should_skip
    ):
        """Test IGNORE_HEADER_AUTH env var controls auth header processing."""
        mock_scope["headers"] = [(b"authorization", b"Bearer some-proxy-token")]

        with patch.dict(os.environ, {"IGNORE_HEADER_AUTH": env_value}):
            await middleware(mock_scope, mock_receive, mock_send)

        # App should always be called (request proceeds)
        middleware.app.assert_called_once()
        passed_scope = middleware.app.call_args[0][0]

        if should_skip:
            # Auth headers should NOT be processed — state stays at defaults
            assert passed_scope["state"].get("user_atlassian_token") is None
            assert passed_scope["state"]["user_atlassian_email"] is None
        else:
            # Auth headers SHOULD be processed — token extracted
            assert passed_scope["state"]["user_atlassian_token"] == "some-proxy-token"

    @pytest.mark.anyio
    async def test_ignore_header_auth_unset(
        self, middleware, mock_scope, mock_receive, mock_send, monkeypatch
    ):
        """Test that auth processing works normally when IGNORE_HEADER_AUTH is not set."""
        mock_scope["headers"] = [(b"authorization", b"Bearer valid-token")]
        monkeypatch.delenv("IGNORE_HEADER_AUTH", raising=False)

        await middleware(mock_scope, mock_receive, mock_send)

        middleware.app.assert_called_once()
        passed_scope = middleware.app.call_args[0][0]
        assert passed_scope["state"]["user_atlassian_token"] == "valid-token"


class TestUserTokenMiddlewareSsrfValidation:
    """Regression tests for the SSRF short-circuit in UserTokenMiddleware.

    Covers the auth_validation_error path set by ``_process_authentication_headers``
    when ``validate_url_for_ssrf`` flags an X-Atlassian-Jira-Url or
    X-Atlassian-Confluence-Url header. Ensures that future refactors of the
    middleware cannot silently re-open the SSRF vector by skipping the early
    return or dropping the auth_validation_error assignment.
    """

    @pytest.fixture
    def middleware(self):
        mock_app = AsyncMock()
        mock_mcp_server = MagicMock()
        mock_mcp_server.settings.streamable_http_path = "/mcp"
        mock_mcp_server.get_streamable_http_path.return_value = "/mcp"
        return UserTokenMiddleware(mock_app, mcp_server_ref=mock_mcp_server)

    @pytest.fixture
    def mock_scope(self):
        return {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [],
            "state": {},
        }

    @pytest.fixture
    def mock_receive(self):
        return AsyncMock()

    @pytest.fixture
    def mock_send(self):
        return AsyncMock()

    @pytest.mark.parametrize(
        "header_name,url_value",
        [
            (b"x-atlassian-jira-url", b"file:///etc/passwd"),
            (b"x-atlassian-jira-url", b"http://127.0.0.1:8080/api"),
            (b"x-atlassian-jira-url", b"http://169.254.169.254/latest/meta-data/"),
            (b"x-atlassian-jira-url", b"http://10.0.0.5/"),
            (b"x-atlassian-jira-url", b"ftp://example.com/"),
            (b"x-atlassian-confluence-url", b"http://localhost:9090/"),
            (b"x-atlassian-confluence-url", b"http://169.254.169.254/"),
        ],
    )
    @pytest.mark.anyio
    async def test_ssrf_exploit_header_short_circuits_with_401(
        self,
        middleware,
        mock_scope,
        mock_receive,
        mock_send,
        header_name,
        url_value,
    ):
        """Exploit URL in Jira/Confluence header returns 401 and skips the app."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer test-token"),
            (header_name, url_value),
        ]

        await middleware(mock_scope, mock_receive, mock_send)

        middleware.app.assert_not_called()
        assert mock_send.await_count >= 2

        start_call = mock_send.await_args_list[0][0][0]
        assert start_call["type"] == "http.response.start"
        assert start_call["status"] == 401

        body_call = mock_send.await_args_list[1][0][0]
        assert body_call["type"] == "http.response.body"
        body_json = json.loads(body_call["body"].decode("utf-8"))
        assert "error" in body_json
        assert "Forbidden" in body_json["error"]

    @pytest.mark.parametrize(
        "jira_url,confluence_url",
        [
            (b"https://example.atlassian.net", None),
            (None, b"https://example.atlassian.net/wiki"),
            (b"https://jira.example.com", b"https://confluence.example.com"),
        ],
    )
    @pytest.mark.anyio
    async def test_benign_urls_pass_through(
        self,
        middleware,
        mock_scope,
        mock_receive,
        mock_send,
        jira_url,
        confluence_url,
        monkeypatch,
    ):
        """Legitimate Atlassian Cloud / self-hosted URLs must not be short-circuited.

        The benign hosts are placed on the SSRF allowlist (MCP_ALLOWED_URL_DOMAINS)
        so the assertion is deterministic and does not depend on live DNS
        resolution in CI. The exploit cases above are blocked before any DNS
        lookup (bad scheme / IP literal / blocked hostname), so they are
        unaffected by the allowlist.
        """
        monkeypatch.setenv("MCP_ALLOWED_URL_DOMAINS", "example.com,atlassian.net")
        headers = [(b"authorization", b"Bearer test-token")]
        if jira_url is not None:
            headers.append((b"x-atlassian-jira-url", jira_url))
        if confluence_url is not None:
            headers.append((b"x-atlassian-confluence-url", confluence_url))
        mock_scope["headers"] = headers

        await middleware(mock_scope, mock_receive, mock_send)

        middleware.app.assert_called_once()
        passed_scope = middleware.app.call_args[0][0]
        assert passed_scope["state"].get("auth_validation_error") in (None, "")

    @pytest.mark.anyio
    async def test_no_service_headers_does_not_trigger_ssrf_check(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Requests without Jira/Confluence URL headers skip the validator."""
        mock_scope["headers"] = [(b"authorization", b"Bearer test-token")]

        await middleware(mock_scope, mock_receive, mock_send)

        middleware.app.assert_called_once()
        passed_scope = middleware.app.call_args[0][0]
        assert passed_scope["state"].get("auth_validation_error") in (None, "")


@pytest.mark.security_regression
@pytest.mark.anyio
async def test_oauth_provider_missing_credentials_returns_discovery_challenge(
    monkeypatch,
):
    """FastMCP returns RFC 9728 discovery metadata for missing credentials."""
    monkeypatch.setenv("ALLOW_GLOBAL_CRED_FALLBACK", "false")
    provider = HardenedOAuthProxy(
        upstream_authorization_endpoint="https://idp.invalid/authorize",
        upstream_token_endpoint="https://idp.invalid/token",
        upstream_client_id="test-client",
        upstream_client_secret="test-secret",
        token_verifier=AtlassianOpaqueTokenVerifier(required_scopes=["read:jira"]),
        base_url="https://testserver",
        client_storage=MemoryStore(),
        require_authorization_consent=False,
    )
    server = AtlassianMCP("oauth-challenge-test", auth=provider)
    app = server.http_app(path="/mcp", stateless_http=True)
    transport = httpx.ASGITransport(app=app)
    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1"},
        },
    }

    with patch.object(
        server._mcp_server, "run", new_callable=AsyncMock
    ) as mock_mcp_run:
        async with httpx.AsyncClient(
            transport=transport, base_url="https://testserver"
        ) as client:
            response = await client.post(
                "/mcp",
                headers={
                    "accept": "application/json, text/event-stream",
                    "content-type": "application/json",
                },
                json=initialize_request,
            )
            invalid = await client.post(
                "/mcp",
                headers={
                    "accept": "application/json, text/event-stream",
                    "authorization": "Bearer not-a-valid-token",
                    "content-type": "application/json",
                },
                json=initialize_request,
            )
            metadata = await client.get("/.well-known/oauth-protected-resource/mcp")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        "Bearer "
        'resource_metadata="https://testserver/'
        '.well-known/oauth-protected-resource/mcp"'
    )
    assert invalid.status_code == 401
    assert 'error="invalid_token"' in invalid.headers["www-authenticate"]
    mock_mcp_run.assert_not_awaited()
    assert metadata.status_code == 200
    metadata_body = metadata.json()
    assert metadata_body["resource"] == "https://testserver/mcp"
    assert metadata_body["authorization_servers"] == ["https://testserver/"]


@pytest.mark.security_regression
@pytest.mark.parametrize("transport_name", ["sse", "streamable-http", "http"])
def test_http_app_confines_file_paths_without_cli(transport_name, monkeypatch):
    """An ASGI server that imports the app directly gets the remote file root."""
    from mcp_atlassian.utils import io as io_mod

    monkeypatch.delenv(io_mod.FILES_DIR_ENV, raising=False)
    io_mod.set_remote_transport(False)

    main_mcp.http_app(transport=transport_name)

    assert io_mod.get_file_root() == io_mod.default_files_dir().resolve()


@pytest.mark.security_regression
def test_http_app_refuses_wide_file_root(monkeypatch):
    from mcp_atlassian.utils import io as io_mod

    monkeypatch.setenv(io_mod.FILES_DIR_ENV, "/")
    with pytest.raises(ValueError, match="filesystem root"):
        main_mcp.http_app(transport="streamable-http")


@pytest.mark.security_regression
@pytest.mark.anyio
@pytest.mark.parametrize(
    ("transport_name", "path"),
    [
        ("sse", "/prefix/sse"),
        ("sse", "/prefix/messages/"),
        ("sse", "/prefix/messages/sub"),
        ("streamable-http", "/prefix/mcp"),
        ("streamable-http", "/prefix/mcp/"),
    ],
)
async def test_auth_gate_applies_under_root_path(transport_name, path, monkeypatch):
    """With root_path set, the router strips the prefix; so must the gate."""
    monkeypatch.delenv("ALLOW_GLOBAL_CRED_FALLBACK", raising=False)
    monkeypatch.delenv("IGNORE_HEADER_AUTH", raising=False)
    app = main_mcp.http_app(transport=transport_name)
    transport = httpx.ASGITransport(app=app, root_path="/prefix")

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            path, headers={"accept": "application/json, text/event-stream"}
        )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "scope",
    [
        {"path": "/mcp", "root_path": ""},
        {"path": "/prefix/mcp", "root_path": "/prefix"},
        {"path": "/prefix", "root_path": "/prefix"},
        {"path": "/prefixed/mcp", "root_path": "/prefix"},
        {"path": "/other/mcp", "root_path": "/prefix"},
    ],
)
def test_route_path_matches_starlette_router(scope):
    from starlette._utils import get_route_path

    from mcp_atlassian.servers.main import _route_path

    assert _route_path(scope) == get_route_path(scope)
