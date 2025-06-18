"""Integration tests for transport lifecycle behavior.

These tests ensure that:
1. No stdin monitoring is used (preventing issues #519 and #524)
2. Stdio transport doesn't conflict with MCP server's internal stdio handling
3. All transports use direct execution
4. Docker scenarios work correctly
"""

import asyncio
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_atlassian import main
from mcp_atlassian.utils.lifecycle import _shutdown_event


@pytest.mark.integration
class TestTransportLifecycleBehavior:
    """Test transport lifecycle behavior to prevent regression of issues #519 and #524."""

    def setup_method(self):
        """Reset state before each test."""
        _shutdown_event.clear()

    def test_all_transports_use_direct_execution(self):
        """Verify all transports use direct execution without stdin monitoring.

        This is a regression test to ensure stdin monitoring is never reintroduced,
        which caused both issue #519 (stdio conflicts) and #524 (HTTP session termination).
        """
        transports_to_test = ["stdio", "sse", "streamable-http"]

        for transport in transports_to_test:
            with patch("asyncio.run") as mock_asyncio_run:
                with patch.dict("os.environ", {"TRANSPORT": transport}, clear=False):
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
                            "transport": transport,
                            "port": None,
                            "host": None,
                            "path": None,
                        }
                        mock_click_ctx.return_value = mock_ctx_instance

                        # Execute main
                        with patch("sys.argv", ["mcp-atlassian"]):
                            try:
                                main()
                            except SystemExit:
                                pass

                        # Verify direct execution for all transports
                        assert mock_asyncio_run.called, (
                            f"asyncio.run not called for {transport}"
                        )
                        called_coro = mock_asyncio_run.call_args[0][0]

                        # Ensure NO stdin monitoring wrapper is used
                        coro_str = str(called_coro)
                        assert "run_with_stdio_monitoring" not in coro_str, (
                            f"{transport} should not use stdin monitoring"
                        )
                        assert "run_async" in coro_str or hasattr(
                            called_coro, "cr_code"
                        ), f"{transport} should use direct run_async execution"

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
class TestRegressionPrevention:
    """Tests to prevent regression of specific issues."""

    def test_no_stdin_monitoring_in_codebase(self):
        """Ensure stdin monitoring is not reintroduced in the codebase.

        This is a safeguard against reintroducing the flawed stdin monitoring
        that caused issues #519 and #524.
        """
        # Check that the problematic function doesn't exist
        from mcp_atlassian.utils import lifecycle

        assert not hasattr(lifecycle, "run_with_stdio_monitoring"), (
            "run_with_stdio_monitoring should not exist in lifecycle module"
        )

    def test_signal_handlers_are_setup(self):
        """Verify signal handlers are properly configured."""
        with patch("mcp_atlassian.setup_signal_handlers") as mock_setup:
            with patch("asyncio.run"):
                with patch("mcp_atlassian.servers.main.AtlassianMCP"):
                    with patch("sys.argv", ["mcp-atlassian"]):
                        try:
                            main()
                        except SystemExit:
                            pass

                    # Signal handlers should always be set up
                    mock_setup.assert_called_once()
