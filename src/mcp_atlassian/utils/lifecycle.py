"""Lifecycle management utilities for graceful shutdown and signal handling."""

import asyncio
import logging
import signal
import sys
import threading
from typing import Any

logger = logging.getLogger("mcp-atlassian.utils.lifecycle")

# Global shutdown event for signal-safe handling
_shutdown_event = threading.Event()


def setup_signal_handlers() -> None:
    """Set up signal handlers for graceful shutdown.

    Registers handlers for SIGTERM, SIGINT, and SIGPIPE (Unix/Linux only) to ensure
    the application shuts down cleanly when receiving termination signals.

    Platform Behavior:
        - Unix/Linux: SIGPIPE handled to prevent process termination on client disconnect
        - Windows: SIGPIPE not available (socket errors returned directly instead)

    This is particularly important for:
        - MCP stdio transport (client disconnect detection)
        - Docker containers running with the -i flag
        - Long-running server processes with unreliable clients

    Note:
        SIGPIPE handling is CRITICAL on Unix/Linux. Without it, the server process
        terminates when writing to a closed pipe (e.g., when an MCP client disconnects).
        SIGPIPE therefore does not request shutdown: a broken pipe on one
        response must not take the server down.

    Setting the event only records the request. The run path must also wait on
    it (``wait_for_shutdown_request``) and stop the server, or a handler
    registered here swallows the signal and the process never exits.
    """

    def signal_handler(signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully.

        Uses event-based shutdown to avoid signal safety issues.
        Signal handlers should be minimal and avoid complex operations.
        """
        # Only safe operations in signal handlers - set the shutdown event
        _shutdown_event.set()

    def sigpipe_handler(signum: int, frame: Any) -> None:
        """Swallow SIGPIPE so a closed pipe cannot kill the process."""

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Handle SIGPIPE which occurs when parent process closes the pipe
    # SIGPIPE is not available on Windows, so we check for it first
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, sigpipe_handler)
        logger.debug("SIGPIPE handler registered")
    else:
        # SIGPIPE may not be available on all platforms (e.g., Windows)
        logger.debug("SIGPIPE not available on this platform")


def is_shutdown_requested() -> bool:
    """Whether a SIGTERM or SIGINT has been received."""
    return _shutdown_event.is_set()


def reset_shutdown_request() -> None:
    """Clear the recorded shutdown request (tests and restarts)."""
    _shutdown_event.clear()


async def wait_for_shutdown_request(
    stop_event: threading.Event, poll_interval: float = 0.25
) -> None:
    """Return once SIGTERM or SIGINT has been received.

    Polls from a worker thread instead of using ``loop.add_signal_handler``,
    which is not available on Windows. ``stop_event`` ends the poll when the
    server stops for another reason, so the thread does not outlive the run.
    """
    loop = asyncio.get_running_loop()

    def _poll() -> None:
        while not stop_event.wait(poll_interval):
            if _shutdown_event.is_set():
                return

    await loop.run_in_executor(None, _poll)


def ensure_clean_exit() -> None:
    """Ensure all output streams are flushed before exit.

    This is important for containerized environments where output might be
    buffered and could be lost if not properly flushed before exit.

    Handles cases where streams may already be closed by the parent process,
    particularly on Windows or when run as a child process.
    """
    logger.info("Server stopped, flushing output streams...")

    # Safely flush stdout
    try:
        if hasattr(sys.stdout, "closed") and not sys.stdout.closed:
            sys.stdout.flush()
    except (ValueError, OSError, AttributeError) as e:
        # Stream might be closed or redirected
        logger.debug(f"Could not flush stdout: {e}")

    # Safely flush stderr
    try:
        if hasattr(sys.stderr, "closed") and not sys.stderr.closed:
            sys.stderr.flush()
    except (ValueError, OSError, AttributeError) as e:
        # Stream might be closed or redirected
        logger.debug(f"Could not flush stderr: {e}")

    logger.debug("Output streams flushed, exiting gracefully")
