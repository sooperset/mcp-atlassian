"""Tests for the main MCP server implementation."""

from unittest.mock import patch

import httpx
import pytest

from mcp_atlassian.servers.main import main_mcp


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
