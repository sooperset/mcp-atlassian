"""Tests for lifecycle management utilities."""

import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_atlassian.utils.lifecycle import (
    _shutdown_event,
    ensure_clean_exit,
    run_with_stdio_monitoring,
    setup_signal_handlers,
)


class TestSetupSignalHandlers:
    """Test signal handler setup functionality."""

    @patch("signal.signal")
    def test_setup_signal_handlers_all_platforms(self, mock_signal):
        """Test that signal handlers are registered for all platforms."""
        # Mock SIGPIPE as available
        mock_signal.side_effect = None

        setup_signal_handlers()

        # Check that SIGTERM and SIGINT handlers were registered
        assert any(call[0][0] == signal.SIGTERM for call in mock_signal.call_args_list)
        assert any(call[0][0] == signal.SIGINT for call in mock_signal.call_args_list)

        # Check that all handlers are callable
        for call in mock_signal.call_args_list:
            assert callable(call[0][1])

    @patch("signal.signal")
    def test_setup_signal_handlers_no_sigpipe(self, mock_signal):
        """Test signal handler setup when SIGPIPE is not available (Windows)."""

        # Mock SIGPIPE as not available
        def side_effect(sig, handler):
            if sig == signal.SIGPIPE:
                raise AttributeError("SIGPIPE not available")
            return None

        mock_signal.side_effect = side_effect

        # This should not raise an exception
        setup_signal_handlers()

        # SIGTERM and SIGINT should still be registered
        assert any(call[0][0] == signal.SIGTERM for call in mock_signal.call_args_list)
        assert any(call[0][0] == signal.SIGINT for call in mock_signal.call_args_list)

    @patch("signal.signal")
    def test_signal_handler_function(self, mock_signal):
        """Test that the signal handler function works correctly."""
        handler = None

        # Capture the handler function
        def capture_handler(sig, func):
            nonlocal handler
            if sig == signal.SIGTERM:
                handler = func

        mock_signal.side_effect = capture_handler

        # Clear the shutdown event before test
        _shutdown_event.clear()

        setup_signal_handlers()

        # Call the handler
        assert handler is not None
        handler(signal.SIGTERM, None)

        # Check shutdown event was set instead of calling sys.exit
        assert _shutdown_event.is_set()


class TestRunWithStdioMonitoring:
    """Test the STDIO monitoring wrapper."""

    def setup_method(self):
        """Clear shutdown event before each test."""
        _shutdown_event.clear()

    @pytest.mark.anyio
    async def test_run_with_stdio_monitoring_signal_shutdown(self):
        """Test server shutdown when signal is received."""
        # Pre-set shutdown event to skip monitoring setup
        _shutdown_event.set()

        # Create a simple server that just completes
        async def mock_server(**kwargs):
            return "completed"

        run_kwargs = {"test": "value"}

        # This should complete immediately since shutdown is already set
        await run_with_stdio_monitoring(mock_server, run_kwargs)

    @pytest.mark.anyio
    async def test_run_with_stdio_monitoring_server_exception(self):
        """Test exception handling in server execution."""
        # Pre-set shutdown event to skip monitoring setup
        _shutdown_event.set()

        # Create a mock coroutine that raises an exception immediately
        async def mock_server(**kwargs):
            raise RuntimeError("Test error")

        run_kwargs = {"test": "value"}

        with pytest.raises(RuntimeError, match="Test error"):
            await run_with_stdio_monitoring(mock_server, run_kwargs)

    @patch("asyncio.get_event_loop")
    @pytest.mark.anyio
    async def test_run_with_stdio_monitoring_stdin_eof(self, mock_get_loop):
        """Test shutdown when stdin EOF is detected."""
        # Mock the event loop and stdin setup
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop

        # Mock the reader to return EOF immediately
        mock_reader = AsyncMock()
        mock_reader.readline = AsyncMock(return_value=b"")  # EOF

        mock_protocol = MagicMock()
        mock_transport = MagicMock()
        mock_loop.connect_read_pipe = AsyncMock(
            return_value=(mock_transport, mock_protocol)
        )

        # Mock StreamReader and StreamReaderProtocol
        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=mock_protocol),
            patch("asyncio.create_task") as mock_create_task,
        ):
            # Create a server that completes quickly
            async def mock_server(**kwargs):
                return "completed"

            run_kwargs = {"test": "value"}

            # Mock create_task to avoid actual background task creation in tests
            async def mock_background_task():
                # Simulate EOF detection
                _shutdown_event.set()
                return

            mock_create_task.return_value = AsyncMock()
            mock_create_task.return_value.done.return_value = True

            # This should complete
            await run_with_stdio_monitoring(mock_server, run_kwargs)

    @pytest.mark.anyio
    async def test_run_with_stdio_monitoring_stdin_unavailable(self):
        """Test fallback behavior when stdin monitoring is not available."""

        # Create a server that completes quickly
        async def mock_server(**kwargs):
            return "completed"

        run_kwargs = {"test": "value"}

        # Mock create_task to simulate stdin monitoring failure
        with patch("asyncio.create_task") as mock_create_task:
            mock_task = AsyncMock()
            mock_task.done.return_value = True
            mock_create_task.return_value = mock_task

            # This should complete even when stdin monitoring setup fails
            await run_with_stdio_monitoring(mock_server, run_kwargs)


class TestEnsureCleanExit:
    """Test the clean exit functionality."""

    @patch("sys.stderr")
    @patch("sys.stdout")
    def test_ensure_clean_exit(self, mock_stdout, mock_stderr):
        """Test that output streams are flushed on exit."""
        ensure_clean_exit()

        # Check both streams were flushed
        mock_stdout.flush.assert_called_once()
        mock_stderr.flush.assert_called_once()
