"""Tests for the main MCP server implementation."""

from unittest.mock import patch

import pytest

from mcp_atlassian.servers.main import main_mcp, run_server


@pytest.mark.asyncio
async def test_run_server_stdio():
    """Test that run_server calls the correct method for stdio transport."""
    with patch.object(main_mcp, "run_stdio_async") as mock_run_stdio:
        mock_run_stdio.return_value = None

        await run_server(transport="stdio")

        mock_run_stdio.assert_called_once()


@pytest.mark.asyncio
async def test_run_server_sse():
    """Test that run_server calls the correct method for SSE transport."""
    with patch.object(main_mcp, "run_sse_async") as mock_run_sse:
        mock_run_sse.return_value = None

        test_port = 9000
        test_host = "0.0.0.0"
        await run_server(transport="sse", port=test_port, host=test_host)

        mock_run_sse.assert_called_once_with(host=test_host, port=test_port)


@pytest.mark.asyncio
async def test_run_server_invalid_transport():
    """Test that run_server raises ValueError for invalid transport."""
    with pytest.raises(ValueError) as excinfo:
        await run_server(transport="invalid")

    assert "Unsupported transport" in str(excinfo.value)
    assert "Use 'stdio' or 'sse'" in str(excinfo.value)


@pytest.mark.asyncio
async def test_run_server_stdio_fallback():
    """Test the fallback option for older FastMCP versions with stdio transport."""
    # Create a mock without run_stdio_async method
    with patch.object(main_mcp, "run_stdio_async", None):
        with patch.object(main_mcp, "run") as mock_run:
            mock_run.return_value = None

            await run_server(transport="stdio")

            mock_run.assert_called_once_with(transport="mcp.server.StdioTransport")
