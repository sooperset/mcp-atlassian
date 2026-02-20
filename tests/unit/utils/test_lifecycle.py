"""Tests for lifecycle management utilities."""

import signal
from unittest.mock import patch

from mcp_atlassian.utils.lifecycle import (
    _shutdown_event,
    ensure_clean_exit,
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
