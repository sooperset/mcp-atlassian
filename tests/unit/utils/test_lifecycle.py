"""Tests for lifecycle management utilities."""

import asyncio
import signal
import threading
from unittest.mock import patch

from mcp_atlassian.utils.lifecycle import (
    _shutdown_event,
    ensure_clean_exit,
    is_shutdown_requested,
    reset_shutdown_request,
    setup_signal_handlers,
    wait_for_shutdown_request,
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
        # Mock hasattr to return False for SIGPIPE
        with patch("builtins.hasattr") as mock_hasattr:
            # Return False for signal.SIGPIPE, True for everything else
            def hasattr_side_effect(obj, name):
                if obj is signal and name == "SIGPIPE":
                    return False
                # Use real hasattr for other cases
                return (
                    hasattr.__wrapped__(obj, name)
                    if hasattr(hasattr, "__wrapped__")
                    else True
                )

            mock_hasattr.side_effect = hasattr_side_effect

            # This should not raise an exception
            setup_signal_handlers()

            # SIGTERM and SIGINT should still be registered
            assert any(
                call[0][0] == signal.SIGTERM for call in mock_signal.call_args_list
            )
            assert any(
                call[0][0] == signal.SIGINT for call in mock_signal.call_args_list
            )

            # SIGPIPE should not be in the calls since hasattr returned False
            sigpipe_calls = [
                call
                for call in mock_signal.call_args_list
                if len(call[0]) > 0
                and hasattr(signal, "SIGPIPE")
                and call[0][0] == signal.SIGPIPE
            ]
            assert len(sigpipe_calls) == 0

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

    @patch("signal.signal")
    def test_sigpipe_does_not_request_shutdown(self, mock_signal):
        """A broken pipe on one response must not stop the server."""
        handlers = {}

        def capture_handler(sig, func):
            handlers[sig] = func

        mock_signal.side_effect = capture_handler
        _shutdown_event.clear()

        setup_signal_handlers()

        sigpipe_handler = handlers[signal.SIGPIPE]
        assert sigpipe_handler is not handlers[signal.SIGTERM]
        sigpipe_handler(signal.SIGPIPE, None)

        assert not _shutdown_event.is_set()


class TestWaitForShutdownRequest:
    """Test the awaitable that the run path uses to notice a signal."""

    def teardown_method(self):
        reset_shutdown_request()

    def test_returns_when_shutdown_requested(self):
        """The waiter returns once the signal handler sets the event."""
        reset_shutdown_request()
        stop_event = threading.Event()

        async def scenario():
            waiter = asyncio.create_task(
                wait_for_shutdown_request(stop_event, poll_interval=0.01)
            )
            await asyncio.sleep(0.02)
            assert not waiter.done()
            _shutdown_event.set()
            await asyncio.wait_for(waiter, timeout=2)

        asyncio.run(scenario())
        assert is_shutdown_requested()

    def test_stop_event_ends_the_wait(self):
        """A server that stops for another reason does not leave the poll running."""
        reset_shutdown_request()
        stop_event = threading.Event()

        async def scenario():
            waiter = asyncio.create_task(
                wait_for_shutdown_request(stop_event, poll_interval=0.01)
            )
            await asyncio.sleep(0.02)
            stop_event.set()
            await asyncio.wait_for(waiter, timeout=2)

        asyncio.run(scenario())
        assert not is_shutdown_requested()


class TestEnsureCleanExit:
    """Test the clean exit functionality."""

    @patch("sys.stderr")
    @patch("sys.stdout")
    def test_ensure_clean_exit(self, mock_stdout, mock_stderr):
        """Test that output streams are flushed on exit."""
        # Mock streams as open
        mock_stdout.closed = False
        mock_stderr.closed = False

        ensure_clean_exit()

        # Check both streams were flushed
        mock_stdout.flush.assert_called_once()
        mock_stderr.flush.assert_called_once()

    @patch("sys.stderr")
    @patch("sys.stdout")
    def test_ensure_clean_exit_closed_stdout(self, mock_stdout, mock_stderr):
        """Test that closed stdout is handled gracefully."""
        # Mock stdout as closed, stderr as open
        mock_stdout.closed = True
        mock_stderr.closed = False

        ensure_clean_exit()

        # Check stdout was not flushed
        mock_stdout.flush.assert_not_called()
        # Check stderr was still flushed
        mock_stderr.flush.assert_called_once()

    @patch("sys.stderr")
    @patch("sys.stdout")
    def test_ensure_clean_exit_closed_stderr(self, mock_stdout, mock_stderr):
        """Test that closed stderr is handled gracefully."""
        # Mock stderr as closed, stdout as open
        mock_stdout.closed = False
        mock_stderr.closed = True

        ensure_clean_exit()

        # Check stdout was flushed
        mock_stdout.flush.assert_called_once()
        # Check stderr was not flushed
        mock_stderr.flush.assert_not_called()

    @patch("sys.stderr")
    @patch("sys.stdout")
    def test_ensure_clean_exit_both_closed(self, mock_stdout, mock_stderr):
        """Test that both streams being closed is handled gracefully."""
        # Mock both streams as closed
        mock_stdout.closed = True
        mock_stderr.closed = True

        ensure_clean_exit()

        # Check neither stream was flushed
        mock_stdout.flush.assert_not_called()
        mock_stderr.flush.assert_not_called()

    @patch("sys.stderr")
    @patch("sys.stdout")
    def test_ensure_clean_exit_flush_raises_value_error(self, mock_stdout, mock_stderr):
        """Test that ValueError during flush is handled gracefully."""
        # Mock streams as open but flush raises ValueError
        mock_stdout.closed = False
        mock_stderr.closed = False
        mock_stdout.flush.side_effect = ValueError("I/O operation on closed file")
        mock_stderr.flush.side_effect = ValueError("I/O operation on closed file")

        # Should not raise exception
        ensure_clean_exit()

        # Check both streams had flush attempts
        mock_stdout.flush.assert_called_once()
        mock_stderr.flush.assert_called_once()

    @patch("sys.stderr")
    @patch("sys.stdout")
    def test_ensure_clean_exit_no_closed_attribute(self, mock_stdout, mock_stderr):
        """Test handling of streams without 'closed' attribute."""
        # Remove closed attribute to simulate non-standard streams
        if hasattr(mock_stdout, "closed"):
            delattr(mock_stdout, "closed")
        if hasattr(mock_stderr, "closed"):
            delattr(mock_stderr, "closed")

        # Should not raise exception
        ensure_clean_exit()

        # Check neither stream was flushed (no closed attribute)
        mock_stdout.flush.assert_not_called()
        mock_stderr.flush.assert_not_called()
