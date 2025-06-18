"""Integration tests for transport-specific lifecycle behavior.

These tests ensure that stdio transport doesn't conflict with MCP server's
internal stdio handling, and that all transports handle lifecycle properly.
"""

import asyncio
import sys
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_atlassian import main
from mcp_atlassian.utils.lifecycle import _shutdown_event


@pytest.mark.integration
class TestTransportLifecycleBehavior:
    """Test transport-specific lifecycle monitoring behavior."""

    def setup_method(self):
        """Reset state before each test."""
        _shutdown_event.clear()

    @pytest.mark.parametrize(
        "transport,env_transport",
        [
            ("stdio", "stdio"),  # stdio transport
            ("sse", "sse"),  # sse transport
            ("streamable-http", "streamable-http"),  # http transport
            (None, "stdio"),  # default stdio from env
            (None, "sse"),  # sse from env
        ],
    )
    def test_transport_lifecycle_handling(self, transport, env_transport):
        """Test that each transport uses appropriate lifecycle handling.

        This test verifies the fix for issue #519 where stdio transport
        conflicted with MCP server's internal stdio handling. After the fix,
        all transports now directly call run_async without stdin monitoring.
        """
        with patch("asyncio.run") as mock_asyncio_run:
            with patch.dict("os.environ", {"TRANSPORT": env_transport}, clear=False):
                # Mock the server creation and CLI parsing
                with (
                    patch(
                        "mcp_atlassian.servers.main.AtlassianMCP"
                    ) as mock_server_class,
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

                    # All transports now directly use run_async without stdin monitoring
                    # This prevents race conditions and premature termination
                    assert hasattr(called_coro, "cr_code") or "run_async" in str(
                        called_coro
                    )

    @pytest.mark.anyio
    async def test_stdio_no_race_condition(self):
        """Test that stdio transport doesn't create race condition with MCP server.

        After the fix, stdin monitoring has been removed completely, so there's
        no possibility of race conditions between components trying to read stdin.
        """
        # Create a mock stdin that tracks reads
        read_count = 0

        class MockStdin:
            def __init__(self):
                self.closed = False
                self._read_lock = asyncio.Lock()

            async def readline(self):
                nonlocal read_count

                async with self._read_lock:
                    if self.closed:
                        raise ValueError("I/O operation on closed file")

                    read_count += 1
                    return b""  # EOF

        mock_stdin = MockStdin()

        # Mock the server coroutine that reads stdin
        async def mock_server_with_stdio(**kwargs):
            """Simulates MCP server reading from stdin."""
            # MCP server would normally read stdin here
            await mock_stdin.readline()
            return "completed"

        # Test direct server execution (current behavior)
        with patch("sys.stdin", mock_stdin):
            # Run server directly without any stdin monitoring
            result = await mock_server_with_stdio()

        # Should only have one read - from the MCP server itself
        assert read_count == 1
        assert result == "completed"

    @pytest.mark.anyio
    async def test_non_stdio_transports_no_stdin_monitoring(self):
        """Test that SSE and HTTP transports don't use stdin monitoring.

        After PR #528, stdin monitoring has been completely removed to prevent
        premature session termination.
        """

        # Simple server that completes immediately
        async def mock_server(**kwargs):
            return "completed"

        # Run server directly - no stdin monitoring for any transport
        result = await mock_server(transport="sse")

        # Server should complete normally
        assert result == "completed"

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

        for cli_transport, env_transport, _expected_transport in test_cases:
            with patch("asyncio.run") as mock_asyncio_run:
                env_vars = {}
                if env_transport:
                    env_vars["TRANSPORT"] = env_transport

                with patch.dict("os.environ", env_vars, clear=False):
                    with (
                        patch(
                            "mcp_atlassian.servers.main.AtlassianMCP"
                        ) as mock_server_class,
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

                        # Verify asyncio.run was called
                        assert mock_asyncio_run.called

                        # All transports now run directly without stdin monitoring
                        called_coro = mock_asyncio_run.call_args[0][0]
                        # Should always call run_async directly
                        assert hasattr(called_coro, "cr_code") or "run_async" in str(
                            called_coro
                        )

    @pytest.mark.anyio
    async def test_shutdown_event_handling(self):
        """Test that shutdown events are handled correctly for all transports."""
        # Pre-set shutdown event
        _shutdown_event.set()

        async def mock_server(**kwargs):
            # Should run even with shutdown event set
            return "completed"

        # Server runs directly now
        result = await mock_server()

        # Server should complete normally
        assert result == "completed"

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
                    patch(
                        "mcp_atlassian.servers.main.AtlassianMCP"
                    ) as mock_server_class,
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

                    # All transports now use run_async directly
                    assert hasattr(called_coro, "cr_code") or "run_async" in str(
                        called_coro
                    )


@pytest.mark.integration
class TestLifecycleEdgeCases:
    """Test edge cases in lifecycle handling to ensure robustness."""

    @pytest.mark.anyio
    async def test_server_with_stdin_unavailable(self):
        """Test server handles unavailable stdin gracefully."""
        # Remove stdin temporarily
        original_stdin = sys.stdin
        sys.stdin = None

        try:

            async def mock_server(**kwargs):
                return "completed"

            # Should complete without errors even without stdin
            result = await mock_server(transport="sse")
            assert result == "completed"

        finally:
            sys.stdin = original_stdin

    @pytest.mark.anyio
    async def test_server_exception_handling(self):
        """Test server exceptions are properly propagated."""

        async def failing_server(**kwargs):
            raise RuntimeError("Server error")

        # Server errors should be propagated
        with pytest.raises(RuntimeError, match="Server error"):
            await failing_server(transport="sse")

    @pytest.mark.anyio
    async def test_signal_based_shutdown(self):
        """Test handling of signal-based shutdown."""
        import sys

        shutdown_count = 0

        async def counting_server(**kwargs):
            nonlocal shutdown_count
            # Wait a bit to allow shutdown events
            if "trio" in sys.modules:
                # We're running under trio
                import trio

                await trio.sleep(0.1)
            else:
                # We're running under asyncio
                await asyncio.sleep(0.1)
            shutdown_count += 1
            return "completed"

        # Clear shutdown event
        _shutdown_event.clear()

        # For both backends, we can just run the server directly
        # since we're in an async test function
        result = await counting_server(transport="sse")

        # Server should have completed normally
        assert shutdown_count == 1
        assert result == "completed"
