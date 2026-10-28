"""Lifecycle management utilities for graceful shutdown and signal handling."""

import contextlib
import logging
import os
import signal
import sys
import threading
import time
from typing import Any

logger = logging.getLogger("mcp-atlassian.utils.lifecycle")

# Upper bound on graceful shutdown; below Docker's default 10s stop timeout.
SHUTDOWN_DEADLINE_SECONDS = 8.0

_shutting_down = False
_deadline_fd: int | None = None


def _start_shutdown_watchdog() -> None:
    """Start (once) a daemon thread that force-exits when shutdown overruns."""
    global _deadline_fd
    if _deadline_fd is not None:
        return
    read_fd, write_fd = os.pipe()

    def _watch() -> None:
        os.read(read_fd, 1)
        time.sleep(SHUTDOWN_DEADLINE_SECONDS)
        os._exit(1)

    threading.Thread(target=_watch, name="shutdown-watchdog", daemon=True).start()
    _deadline_fd = write_fd


def start_shutdown_deadline() -> None:
    """Force exit if shutdown is still running after SHUTDOWN_DEADLINE_SECONDS.

    Bounds shutdown steps that can block indefinitely, such as in-flight
    executor work or flushing a full output pipe. Safe to call from a signal
    handler: it only writes to a pipe.
    """
    if _deadline_fd is not None:
        with contextlib.suppress(OSError):
            os.write(_deadline_fd, b"\0")


def _handle_termination(signum: int, frame: Any) -> None:
    """Start shutdown on the first signal; force exit on a repeat."""
    global _shutting_down
    if _shutting_down:
        os._exit(128 + signum)
    _shutting_down = True
    start_shutdown_deadline()
    raise KeyboardInterrupt


def setup_signal_handlers() -> None:
    """Set up signal handlers for graceful shutdown.

    SIGINT keeps Python's default handler, so ``asyncio.run()`` cancels the main
    task on the first Ctrl+C. SIGTERM raises KeyboardInterrupt in the main
    thread, so the server unwinds and ``main()`` exits; a second SIGTERM during
    that shutdown exits immediately, and shutdown that overruns
    SHUTDOWN_DEADLINE_SECONDS is forced to exit.
    SIGPIPE (Unix/Linux only) is ignored so writes to a closed pipe raise
    BrokenPipeError instead of killing the process.

    Platform Behavior:
        - Unix/Linux: SIGPIPE ignored to prevent process termination on client disconnect
        - Windows: SIGPIPE not available (socket errors returned directly instead)

    This is particularly important for:
        - MCP stdio transport (client disconnect detection)
        - Docker containers running with the -i flag
        - Long-running server processes with unreliable clients

    Note:
        The handlers must not swallow termination signals or take locks: a
        handler that only records the signal leaves the process running after
        the client is gone, and one that blocks on a lock can deadlock the
        event loop when signals arrive back to back.
    """
    # Register signal handlers
    _start_shutdown_watchdog()
    signal.signal(signal.SIGTERM, _handle_termination)
    signal.signal(signal.SIGINT, signal.default_int_handler)

    # Handle SIGPIPE which occurs when parent process closes the pipe
    # SIGPIPE is not available on Windows, so we check for it first
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
        logger.debug("SIGPIPE ignored")
    else:
        # SIGPIPE may not be available on all platforms (e.g., Windows)
        logger.debug("SIGPIPE not available on this platform")


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
