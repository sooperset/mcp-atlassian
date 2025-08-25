"""Tests for the main MCP server implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

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
    app = main_mcp.sse_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_sse_app_health_check_endpoint():
    """Test the /healthz endpoint on the SSE app returns 200 and correct JSON response."""
    app = main_mcp.sse_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_streamable_http_app_health_check_endpoint():
    """Test the /healthz endpoint on the Streamable HTTP app returns 200 and correct JSON response."""
    app = main_mcp.streamable_http_app()
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
    def mock_request(self):
        """Create a mock request for testing."""
        request = MagicMock(spec=Request)
        request.url.path = "/mcp"
        request.method = "POST"
        request.headers = {}
        # Create a real state object that can be modified
        from types import SimpleNamespace

        request.state = SimpleNamespace()
        return request

    @pytest.fixture
    def mock_call_next(self):
        """Create a mock call_next function."""
        mock_response = JSONResponse({"test": "response"})
        call_next = AsyncMock(return_value=mock_response)
        return call_next

    @pytest.mark.anyio
    async def test_cloud_id_header_extraction_success(
        self, middleware, mock_request, mock_call_next
    ):
        """Test successful cloud ID header extraction."""
        # Setup request with cloud ID header
        mock_request.headers = {
            "Authorization": "Bearer test-token",
            "X-Atlassian-Cloud-Id": "test-cloud-id-123",
        }

        result = await middleware.dispatch(mock_request, mock_call_next)

        # Verify cloud ID was extracted and stored in request state
        assert hasattr(mock_request.state, "user_atlassian_cloud_id")
        assert mock_request.state.user_atlassian_cloud_id == "test-cloud-id-123"

        # Verify the request was processed normally
        mock_call_next.assert_called_once_with(mock_request)
        assert result is not None

    @pytest.mark.anyio
    async def test_service_headers_extraction_jira_only(
        self, middleware, mock_request, mock_call_next
    ):
        """Test extraction of Jira service headers for header-based authentication."""
        mock_request.headers = {
            "X-Atlassian-Jira-Url": "https://test.atlassian.net",
            "X-Atlassian-Jira-Personal-Token": "test-jira-pat-token",
        }

        result = await middleware.dispatch(mock_request, mock_call_next)

        assert hasattr(mock_request.state, "atlassian_service_headers")
        service_headers = mock_request.state.atlassian_service_headers
        assert service_headers["X-Atlassian-Jira-Url"] == "https://test.atlassian.net"
        assert (
            service_headers["X-Atlassian-Jira-Personal-Token"] == "test-jira-pat-token"
        )

        assert hasattr(mock_request.state, "user_atlassian_auth_type")
        assert mock_request.state.user_atlassian_auth_type == "pat"
        assert mock_request.state.user_atlassian_email is None

        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.anyio
    async def test_service_headers_extraction_confluence_only(
        self, middleware, mock_request, mock_call_next
    ):
        """Test extraction of Confluence service headers for header-based authentication."""
        mock_request.headers = {
            "X-Atlassian-Confluence-Url": "https://test.atlassian.net",
            "X-Atlassian-Confluence-Personal-Token": "test-confluence-pat-token",
        }

        result = await middleware.dispatch(mock_request, mock_call_next)

        assert hasattr(mock_request.state, "atlassian_service_headers")
        service_headers = mock_request.state.atlassian_service_headers
        assert (
            service_headers["X-Atlassian-Confluence-Url"]
            == "https://test.atlassian.net"
        )
        assert (
            service_headers["X-Atlassian-Confluence-Personal-Token"]
            == "test-confluence-pat-token"
        )

        assert hasattr(mock_request.state, "user_atlassian_auth_type")
        assert mock_request.state.user_atlassian_auth_type == "pat"

        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.anyio
    async def test_service_headers_extraction_both_services(
        self, middleware, mock_request, mock_call_next
    ):
        """Test extraction of both Jira and Confluence service headers."""
        mock_request.headers = {
            "X-Atlassian-Jira-Url": "https://jira.atlassian.net",
            "X-Atlassian-Jira-Personal-Token": "test-jira-pat-token",
            "X-Atlassian-Confluence-Url": "https://confluence.atlassian.net",
            "X-Atlassian-Confluence-Personal-Token": "test-confluence-pat-token",
        }

        result = await middleware.dispatch(mock_request, mock_call_next)

        assert hasattr(mock_request.state, "atlassian_service_headers")
        service_headers = mock_request.state.atlassian_service_headers
        assert len(service_headers) == 4
        assert service_headers["X-Atlassian-Jira-Url"] == "https://jira.atlassian.net"
        assert (
            service_headers["X-Atlassian-Jira-Personal-Token"] == "test-jira-pat-token"
        )
        assert (
            service_headers["X-Atlassian-Confluence-Url"]
            == "https://confluence.atlassian.net"
        )
        assert (
            service_headers["X-Atlassian-Confluence-Personal-Token"]
            == "test-confluence-pat-token"
        )

        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.anyio
    async def test_no_service_headers_no_auth_header(
        self, middleware, mock_request, mock_call_next
    ):
        """Test behavior when no service headers or auth headers are present."""

        mock_request.headers = {"Content-Type": "application/json"}

        result = await middleware.dispatch(mock_request, mock_call_next)

        assert hasattr(mock_request.state, "atlassian_service_headers")
        service_headers = mock_request.state.atlassian_service_headers
        assert service_headers == {}

        assert (
            not hasattr(mock_request.state, "user_atlassian_auth_type")
            or mock_request.state.user_atlassian_auth_type is None
        )

        mock_call_next.assert_called_once_with(mock_request)
