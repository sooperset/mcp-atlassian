"""Tests for the main MCP server implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_atlassian.servers.main import UserTokenMiddleware, main_mcp


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
async def test_run_server_invalid_transport():
    """Test that run_server raises ValueError for invalid transport."""
    # We don't need to patch run_async here as the error occurs before it's called
    with pytest.raises(ValueError) as excinfo:
        await main_mcp.run_async(transport="invalid")  # type: ignore

    assert "Unknown transport" in str(excinfo.value)
    assert "invalid" in str(excinfo.value)


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


class TestUserTokenMiddleware:
    """Tests for the UserTokenMiddleware class."""

    @pytest.fixture
    def middleware(self):
        """Create a UserTokenMiddleware instance for testing."""
        mock_app = AsyncMock()
        # Create a mock MCP server to avoid warnings
        mock_mcp_server = MagicMock()
        mock_mcp_server.settings.streamable_http_path = "/mcp"
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
