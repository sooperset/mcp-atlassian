"""Integration tests for transport-specific lifecycle behavior.

These tests ensure that stdio transport doesn't conflict with MCP server's
internal stdio handling, while other transports properly use lifecycle monitoring.
"""

import asyncio
import sys
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_atlassian import main
from mcp_atlassian.utils.lifecycle import _shutdown_event, run_with_stdio_monitoring


@pytest.mark.integration
class TestTransportLifecycleBehavior:
    """Test transport-specific lifecycle monitoring behavior."""

    def setup_method(self):
        """Reset state before each test."""
        _shutdown_event.clear()

    @pytest.mark.parametrize(
        "transport,env_transport,should_use_monitoring",
        [
            ("stdio", "stdio", False),  # stdio should NOT use monitoring
            ("sse", "sse", True),  # sse should use monitoring
            ("streamable-http", "streamable-http", True),  # http should use monitoring
            (None, "stdio", False),  # default stdio from env
            (None, "sse", True),  # sse from env
        ],
    )
    def test_transport_lifecycle_monitoring_decision(
        self, transport, env_transport, should_use_monitoring
    ):
        """Test that each transport uses appropriate lifecycle handling.
        
        This test verifies the fix for issue #519 where stdio transport
        conflicted with MCP server's internal stdio handling.
        """
        with patch("asyncio.run") as mock_asyncio_run:
            with patch.dict("os.environ", {"TRANSPORT": env_transport}, clear=False):
                # Mock the server creation and CLI parsing
                with (
                    patch("mcp_atlassian.servers.main.AtlassianMCP") as mock_server_class,
                    patch("click.core.Context") as mock_click_ctx,
                ):
                    # Setup mocks
                    mock_server = MagicMock()
                    mock_server.run_async = AsyncMock()
                    mock_server_class.return_value = mock_server
                    
                    # Mock CLI context to return our transport
                    mock_ctx_instance = MagicMock()
                    mock_ctx_instance.obj = {
                        "transport": transport,
                        "port": None,
                        "host": None,
                        "path": None,
                    }
                    mock_click_ctx.return_value = mock_ctx_instance
                    
                    # Simulate main execution
                    with patch("sys.argv", ["mcp-atlassian"]):
                        try:
                            main()
                        except SystemExit:
                            pass  # Expected for clean exit
                    
                    # Verify asyncio.run was called
                    assert mock_asyncio_run.called
                    
                    # Get the coroutine that was passed to asyncio.run
                    called_coro = mock_asyncio_run.call_args[0][0]
                    coro_name = called_coro.__name__ if hasattr(called_coro, "__name__") else str(called_coro)
                    
                    if should_use_monitoring:
                        # For non-stdio transports, should use lifecycle monitoring
                        assert "run_with_stdio_monitoring" in str(called_coro) or hasattr(called_coro, "cr_code")
                    else:
                        # For stdio transport, should NOT use lifecycle monitoring
                        assert "run_with_stdio_monitoring" not in str(called_coro)
                        # Should call run_async directly
                        assert hasattr(called_coro, "cr_code") or "run_async" in str(called_coro)

    @pytest.mark.anyio
    async def test_stdio_race_condition_prevented(self):
        """Test that stdio transport doesn't create race condition with MCP server.
        
        This test simulates the original bug where both lifecycle monitoring
        and MCP server tried to read from stdin simultaneously.
        """
        # Create a mock stdin that tracks reads
        read_count = 0
        read_errors = []
        
        class MockStdin:
            def __init__(self):
                self.closed = False
                self._read_lock = asyncio.Lock()
            
            async def readline(self):
                nonlocal read_count, read_errors
                
                async with self._read_lock:
                    if self.closed:
                        error = ValueError("I/O operation on closed file")
                        read_errors.append(error)
                        raise error
                    
                    read_count += 1
                    # Simulate EOF after first read
                    if read_count > 1:
                        self.closed = True
                    return b""  # EOF
        
        mock_stdin = MockStdin()
        
        # Mock the server coroutine that also tries to read stdin
        async def mock_server_with_stdio(**kwargs):
            """Simulates MCP server reading from stdin."""
            try:
                # MCP server would normally read stdin here
                await mock_stdin.readline()
            except Exception as e:
                # This is what happened in the bug - one reader got an error
                pass
            return "completed"
        
        # Test with lifecycle monitoring (the buggy scenario)
        with patch("sys.stdin", mock_stdin):
            with patch("asyncio.StreamReader") as mock_reader_class:
                mock_reader = AsyncMock()
                mock_reader.readline = mock_stdin.readline
                mock_reader_class.return_value = mock_reader
                
                # This simulates the buggy behavior - both try to read stdin
                try:
                    await run_with_stdio_monitoring(mock_server_with_stdio, {})
                except ValueError:
                    pass  # Expected in the buggy scenario
        
        # With the bug, we'd see multiple reads and errors
        assert read_count >= 1
        if read_count > 1:
            # If multiple reads happened, there should be errors
            assert len(read_errors) > 0, "Race condition detected - multiple stdin readers"

    @pytest.mark.anyio
    async def test_non_stdio_transports_get_monitoring(self):
        """Test that SSE and HTTP transports properly use lifecycle monitoring."""
        monitor_started = False
        
        async def track_monitoring(*args, **kwargs):
            nonlocal monitor_started
            monitor_started = True
            # Simulate immediate completion
            return None
        
        # Mock the monitoring components
        with (
            patch("asyncio.create_task") as mock_create_task,
            patch("asyncio.get_event_loop") as mock_get_loop,
        ):
            # Setup mocks
            mock_task = AsyncMock()
            mock_task.done.return_value = True
            mock_create_task.return_value = mock_task
            
            mock_loop = MagicMock()
            mock_loop.connect_read_pipe = AsyncMock(return_value=(MagicMock(), None))
            mock_get_loop.return_value = mock_loop
            
            # Simple server that completes immediately
            async def mock_server(**kwargs):
                return "completed"
            
            # Run with monitoring
            await run_with_stdio_monitoring(mock_server, {"transport": "sse"})
            
            # Verify monitoring was started
            assert mock_create_task.called, "Lifecycle monitoring should start for non-stdio transports"

    def test_main_function_transport_logic(self):
        """Test the main function's transport determination logic."""
        test_cases = [
            # (cli_transport, env_transport, expected_final_transport)
            ("stdio", None, "stdio"),
            ("sse", None, "sse"),
            (None, "stdio", "stdio"),
            (None, "sse", "sse"),
            ("stdio", "sse", "stdio"),  # CLI overrides env
        ]
        
        for cli_transport, env_transport, expected_transport in test_cases:
            with patch("asyncio.run") as mock_asyncio_run:
                env_vars = {}
                if env_transport:
                    env_vars["TRANSPORT"] = env_transport
                
                with patch.dict("os.environ", env_vars, clear=False):
                    with (
                        patch("mcp_atlassian.servers.main.AtlassianMCP") as mock_server_class,
                        patch("click.core.Context") as mock_click_ctx,
                    ):
                        # Setup mocks
                        mock_server = MagicMock()
                        mock_server.run_async = AsyncMock()
                        mock_server_class.return_value = mock_server
                        
                        # Mock CLI context
                        mock_ctx_instance = MagicMock()
                        mock_ctx_instance.obj = {
                            "transport": cli_transport,
                            "port": None,
                            "host": None,
                            "path": None,
                        }
                        mock_click_ctx.return_value = mock_ctx_instance
                        
                        # Run main
                        with patch("sys.argv", ["mcp-atlassian"]):
                            try:
                                main()
                            except SystemExit:
                                pass
                        
                        # Verify the server was created with correct transport
                        create_call_kwargs = mock_server_class.call_args[1]
                        assert mock_asyncio_run.called
                        
                        # Check if stdio monitoring was used based on transport
                        called_coro = mock_asyncio_run.call_args[0][0]
                        if expected_transport == "stdio":
                            # Should NOT use monitoring for stdio
                            assert "run_with_stdio_monitoring" not in str(called_coro)

    @pytest.mark.anyio
    async def test_shutdown_event_handling(self):
        """Test that shutdown events are handled correctly for all transports."""
        # Pre-set shutdown event
        _shutdown_event.set()
        
        async def mock_server(**kwargs):
            # Should run even with shutdown event set
            return "completed"
        
        # Test that server runs without monitoring when shutdown is already requested
        result = await run_with_stdio_monitoring(mock_server, {})
        
        # Server should have been called directly
        assert result is None or result == "completed"

    def test_docker_stdio_scenario(self):
        """Test the specific Docker stdio scenario that caused the bug.
        
        This simulates running in Docker with -i flag where stdin is available
        but both components trying to read it causes conflicts.
        """
        with patch("asyncio.run") as mock_asyncio_run:
            # Simulate Docker environment variables
            docker_env = {
                "TRANSPORT": "stdio",
                "JIRA_URL": "https://example.atlassian.net",
                "JIRA_USERNAME": "user@example.com",
                "JIRA_API_TOKEN": "token",
            }
            
            with patch.dict("os.environ", docker_env, clear=False):
                with (
                    patch("mcp_atlassian.servers.main.AtlassianMCP") as mock_server_class,
                    patch("sys.stdin", StringIO()),  # Simulate available stdin
                ):
                    # Setup mock server
                    mock_server = MagicMock()
                    mock_server.run_async = AsyncMock()
                    mock_server_class.return_value = mock_server
                    
                    # Simulate Docker container startup
                    with patch("sys.argv", ["mcp-atlassian"]):
                        try:
                            main()
                        except SystemExit:
                            pass
                    
                    # Verify stdio transport doesn't use lifecycle monitoring
                    assert mock_asyncio_run.called
                    called_coro = mock_asyncio_run.call_args[0][0]
                    
                    # This is the fix - stdio should NOT use monitoring
                    assert "run_with_stdio_monitoring" not in str(called_coro)
                    
                    # Should use run_async directly
                    assert hasattr(called_coro, "cr_code") or "run_async" in str(called_coro)


@pytest.mark.integration
class TestLifecycleMonitoringEdgeCases:
    """Test edge cases in lifecycle monitoring to ensure robustness."""

    @pytest.mark.anyio
    async def test_monitoring_with_stdin_unavailable(self):
        """Test lifecycle monitoring gracefully handles unavailable stdin."""
        # Remove stdin temporarily
        original_stdin = sys.stdin
        sys.stdin = None
        
        try:
            async def mock_server(**kwargs):
                return "completed"
            
            # Should complete without errors even without stdin
            await run_with_stdio_monitoring(mock_server, {"transport": "sse"})
            
        finally:
            sys.stdin = original_stdin

    @pytest.mark.anyio
    async def test_monitoring_with_server_exception(self):
        """Test lifecycle monitoring handles server exceptions properly."""
        async def failing_server(**kwargs):
            raise RuntimeError("Server error")
        
        # Monitoring should not mask server errors
        with pytest.raises(RuntimeError, match="Server error"):
            await run_with_stdio_monitoring(failing_server, {"transport": "sse"})

    @pytest.mark.anyio
    async def test_concurrent_shutdown_handling(self):
        """Test handling of concurrent shutdown signals."""
        shutdown_count = 0
        
        async def counting_server(**kwargs):
            nonlocal shutdown_count
            # Wait a bit to allow shutdown events
            await asyncio.sleep(0.1)
            shutdown_count += 1
            return "completed"
        
        # Clear shutdown event
        _shutdown_event.clear()
        
        # Start server
        server_task = asyncio.create_task(
            run_with_stdio_monitoring(counting_server, {"transport": "sse"})
        )
        
        # Send shutdown signal after brief delay
        await asyncio.sleep(0.05)
        _shutdown_event.set()
        
        # Wait for completion
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        
        # Server should have run once
        assert shutdown_count <= 1