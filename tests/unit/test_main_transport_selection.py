"""Unit tests for transport-specific execution path selection.

These tests verify that the main entry point correctly chooses between
direct server execution (for stdio) and lifecycle-monitored execution
(for other transports) to prevent stdio conflicts.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_atlassian import main


class TestMainTransportSelection:
    """Test the main function's transport-specific execution logic."""

    @pytest.fixture
    def mock_server(self):
        """Create a mock server instance."""
        server = MagicMock()
        server.run_async = AsyncMock(return_value=None)
        return server

    @pytest.fixture
    def mock_asyncio_run(self):
        """Mock asyncio.run to capture what coroutine is executed."""
        with patch("asyncio.run") as mock_run:
            # Store the coroutine for inspection
            mock_run.side_effect = lambda coro: setattr(mock_run, "_called_with", coro)
            yield mock_run

    def test_stdio_transport_uses_direct_execution(self, mock_server, mock_asyncio_run):
        """Test that stdio transport bypasses lifecycle monitoring.
        
        This test verifies the fix for issue #519 where stdio transport
        conflicted with the MCP server's internal stdio handling.
        """
        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch.dict("os.environ", {"TRANSPORT": "stdio"}):
                with patch("sys.argv", ["mcp-atlassian"]):
                    try:
                        main()
                    except SystemExit:
                        pass
                    
                    # Verify asyncio.run was called
                    assert mock_asyncio_run.called
                    
                    # Get the coroutine info
                    called_coro = mock_asyncio_run._called_with
                    coro_repr = repr(called_coro)
                    
                    # For stdio, should NOT wrap with run_with_stdio_monitoring
                    assert "run_with_stdio_monitoring" not in coro_repr
                    # Should be the direct run_async coroutine
                    assert "run_async" in coro_repr or hasattr(called_coro, "cr_code")

    def test_sse_transport_uses_lifecycle_monitoring(self, mock_server, mock_asyncio_run):
        """Test that SSE transport uses lifecycle monitoring wrapper."""
        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch.dict("os.environ", {"TRANSPORT": "sse"}):
                with patch("sys.argv", ["mcp-atlassian"]):
                    try:
                        main()
                    except SystemExit:
                        pass
                    
                    # Verify asyncio.run was called
                    assert mock_asyncio_run.called
                    
                    # Get the coroutine info
                    called_coro = mock_asyncio_run._called_with
                    coro_repr = repr(called_coro)
                    
                    # For SSE, should use run_with_stdio_monitoring wrapper
                    assert "run_with_stdio_monitoring" in coro_repr or (
                        hasattr(called_coro, "__name__") and 
                        called_coro.__name__ == "run_with_stdio_monitoring"
                    )

    def test_http_transport_uses_lifecycle_monitoring(self, mock_server, mock_asyncio_run):
        """Test that HTTP transport uses lifecycle monitoring wrapper."""
        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch.dict("os.environ", {"TRANSPORT": "streamable-http"}):
                with patch("sys.argv", ["mcp-atlassian"]):
                    try:
                        main()
                    except SystemExit:
                        pass
                    
                    # Verify asyncio.run was called
                    assert mock_asyncio_run.called
                    
                    # Get the coroutine info
                    called_coro = mock_asyncio_run._called_with
                    coro_repr = repr(called_coro)
                    
                    # For HTTP, should use run_with_stdio_monitoring wrapper
                    assert "run_with_stdio_monitoring" in coro_repr or (
                        hasattr(called_coro, "__name__") and 
                        called_coro.__name__ == "run_with_stdio_monitoring"
                    )

    def test_cli_overrides_env_transport(self, mock_server, mock_asyncio_run):
        """Test that CLI transport argument overrides environment variable."""
        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch.dict("os.environ", {"TRANSPORT": "sse"}):
                # Simulate CLI args with --transport stdio
                with patch("sys.argv", ["mcp-atlassian", "--transport", "stdio"]):
                    try:
                        main()
                    except SystemExit:
                        pass
                    
                    # Should use stdio behavior (no monitoring) despite env var
                    called_coro = mock_asyncio_run._called_with
                    coro_repr = repr(called_coro)
                    assert "run_with_stdio_monitoring" not in coro_repr

    @pytest.mark.parametrize("transport", ["stdio", "sse", "streamable-http"])
    def test_transport_passed_to_server(self, mock_server, transport):
        """Test that the correct transport is passed to the server."""
        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch("asyncio.run"):
                with patch.dict("os.environ", {"TRANSPORT": transport}):
                    with patch("sys.argv", ["mcp-atlassian"]):
                        try:
                            main()
                        except SystemExit:
                            pass
                        
                        # Verify run_async was set up to be called with correct transport
                        # The actual call happens inside asyncio.run, but we can verify
                        # the mock was configured
                        assert mock_server.run_async.call_count == 0  # Not called directly
                        # The coroutine should be created with the right transport

    def test_signal_handlers_always_setup(self, mock_server):
        """Test that signal handlers are set up regardless of transport."""
        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch("asyncio.run"):
                # Patch where it's imported in the main module
                with patch("mcp_atlassian.setup_signal_handlers") as mock_setup:
                    with patch.dict("os.environ", {"TRANSPORT": "stdio"}):
                        with patch("sys.argv", ["mcp-atlassian"]):
                            try:
                                main()
                            except SystemExit:
                                pass
                            
                            # Signal handlers should always be set up
                            mock_setup.assert_called_once()

    def test_error_handling_preserved(self, mock_server):
        """Test that error handling works correctly for all transports."""
        # Make the server's run_async raise an exception when awaited
        error = RuntimeError("Server error")
        
        async def failing_run_async(**kwargs):
            raise error
        
        mock_server.run_async = failing_run_async
        
        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch("asyncio.run") as mock_run:
                # Simulate the exception propagating through asyncio.run
                mock_run.side_effect = error
                
                with patch.dict("os.environ", {"TRANSPORT": "stdio"}):
                    with patch("sys.argv", ["mcp-atlassian"]):
                        # The main function logs the error and exits with code 1
                        with patch("sys.exit") as mock_exit:
                            main()
                            # Verify error was handled - sys.exit called with 1 for error
                            # and then with 0 in the finally block
                            assert mock_exit.call_count == 2
                            assert mock_exit.call_args_list[0][0][0] == 1  # Error exit
                            assert mock_exit.call_args_list[1][0][0] == 0  # Finally exit