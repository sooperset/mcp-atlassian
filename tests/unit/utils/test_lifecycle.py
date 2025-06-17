"""Tests for lifecycle management utilities."""

import signal
from unittest.mock import AsyncMock, patch

import pytest

from mcp_atlassian.utils.lifecycle import (
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

    @patch("sys.exit")
    @patch("signal.signal")
    def test_signal_handler_function(self, mock_signal, mock_exit):
        """Test that the signal handler function works correctly."""
        handler = None

        # Capture the handler function
        def capture_handler(sig, func):
            nonlocal handler
            if sig == signal.SIGTERM:
                handler = func

        mock_signal.side_effect = capture_handler

        setup_signal_handlers()

        # Call the handler
        assert handler is not None
        handler(signal.SIGTERM, None)

        # Check sys.exit was called with 0
        mock_exit.assert_called_once_with(0)


class TestRunWithStdioMonitoring:
    """Test the STDIO monitoring wrapper."""

    @pytest.mark.anyio
    async def test_run_with_stdio_monitoring_success(self):
        """Test successful server execution."""
        # Create a mock coroutine
        mock_server = AsyncMock()
        run_kwargs = {"test": "value"}

        await run_with_stdio_monitoring(mock_server, run_kwargs)

        # Check the server was called with correct kwargs
        mock_server.assert_called_once_with(**run_kwargs)

    @pytest.mark.anyio
    async def test_run_with_stdio_monitoring_exception(self):
        """Test exception handling in server execution."""
        # Create a mock coroutine that raises an exception
        mock_server = AsyncMock(side_effect=RuntimeError("Test error"))
        run_kwargs = {"test": "value"}

        with pytest.raises(RuntimeError, match="Test error"):
            await run_with_stdio_monitoring(mock_server, run_kwargs)

        # Check the server was called
        mock_server.assert_called_once_with(**run_kwargs)


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
