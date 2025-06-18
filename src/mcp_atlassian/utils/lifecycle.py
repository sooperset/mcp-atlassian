"""Lifecycle management utilities for graceful shutdown and signal handling."""

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

    Registers handlers for SIGTERM, SIGINT, and SIGPIPE (if available) to ensure
    the application shuts down cleanly when receiving termination signals.

    This is particularly important for Docker containers running with the -i flag,
    which need to properly handle shutdown signals from parent processes.
    """

    def signal_handler(signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully.

        Uses event-based shutdown to avoid signal safety issues.
        Signal handlers should be minimal and avoid complex operations.
        """
        # Only safe operations in signal handlers - set the shutdown event
        _shutdown_event.set()

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Handle SIGPIPE which occurs when parent process closes the pipe
    try:
        signal.signal(signal.SIGPIPE, signal_handler)
        logger.debug("SIGPIPE handler registered")
    except AttributeError:
        # SIGPIPE may not be available on all platforms (e.g., Windows)
        logger.debug("SIGPIPE not available on this platform")


def ensure_clean_exit() -> None:
    """Ensure all output streams are flushed before exit.

    This is important for containerized environments where output might be
    buffered and could be lost if not properly flushed before exit.
    """
    logger.info("Server stopped, flushing output streams...")
    # Ensure all output is flushed before exit
    sys.stdout.flush()
    sys.stderr.flush()
    logger.debug("Output streams flushed, exiting gracefully")
