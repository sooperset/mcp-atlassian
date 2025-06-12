"""Lifecycle management utilities for graceful shutdown and signal handling."""

import logging
import signal
import sys
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger("mcp-atlassian.utils.lifecycle")


def setup_signal_handlers() -> None:
    """Set up signal handlers for graceful shutdown.

    Registers handlers for SIGTERM, SIGINT, and SIGPIPE (if available) to ensure
    the application shuts down cleanly when receiving termination signals.

    This is particularly important for Docker containers running with the -i flag,
    which need to properly handle shutdown signals from parent processes.
    """

    def signal_handler(signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully."""
        signal_name = signal.Signals(signum).name
        logger.info(
            f"Received signal {signal_name} ({signum}), initiating graceful shutdown..."
        )
        sys.exit(0)

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


async def run_with_stdio_monitoring(
    server_coroutine: Callable[..., Coroutine[Any, Any, None]],
    run_kwargs: dict[str, Any],
) -> None:
    """Run the MCP server with enhanced shutdown handling for containerized environments.

    This wrapper ensures proper shutdown handling when running in Docker containers,
    particularly when used with agent SDKs that may not send proper shutdown signals.

    Args:
        server_coroutine: The server's run_async coroutine
        run_kwargs: Keyword arguments to pass to the server coroutine
    """
    logger.debug("Starting MCP server with enhanced shutdown handling...")

    # For Docker containers, we need to be more aggressive about shutdown detection
    # This is a simpler approach that relies on the signal handlers and proper cleanup
    try:
        await server_coroutine(**run_kwargs)
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


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
