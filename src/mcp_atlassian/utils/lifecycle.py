"""Lifecycle management utilities for graceful shutdown and signal handling."""

import asyncio
import logging
import signal
import sys
import threading
from collections.abc import Callable, Coroutine
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


async def run_with_stdio_monitoring(
    server_coroutine: Callable[..., Coroutine[Any, Any, None]],
    run_kwargs: dict[str, Any],
) -> None:
    """Run the MCP server with actual stdin monitoring for containerized environments.

    This wrapper monitors stdin for EOF and also checks for signal-based shutdown events.
    When stdin closes (EOF detected) or a shutdown signal is received, the server
    shuts down gracefully.

    Args:
        server_coroutine: The server's run_async coroutine
        run_kwargs: Keyword arguments to pass to the server coroutine
    """
    logger.debug("Starting MCP server with stdin monitoring and signal handling...")

    # Simple approach: wrap the server execution and monitor for shutdown signals
    async def run_server_with_monitoring() -> None:
        """Run server with background monitoring."""
        # Start monitoring tasks
        monitor_task = None

        try:
            # Set up stdin monitoring in the background (non-blocking)
            async def background_monitor() -> None:
                try:
                    # Try to set up stdin monitoring
                    reader = asyncio.StreamReader()
                    protocol = asyncio.StreamReaderProtocol(reader)
                    transport, _ = await asyncio.get_event_loop().connect_read_pipe(
                        lambda: protocol, sys.stdin
                    )

                    logger.debug("Stdin monitoring started")

                    try:
                        while not _shutdown_event.is_set():
                            try:
                                # Try to read with a timeout
                                line = await asyncio.wait_for(
                                    reader.readline(), timeout=0.5
                                )
                                if not line:  # EOF detected
                                    logger.info(
                                        "stdin closed (EOF detected), initiating shutdown..."
                                    )
                                    _shutdown_event.set()
                                    break
                            except asyncio.TimeoutError:
                                continue
                    finally:
                        transport.close()
                        logger.debug("Stdin monitoring stopped")

                except Exception as e:
                    logger.debug(f"Stdin monitoring unavailable: {e}")
                    # Fall back to just waiting for signal-based shutdown
                    while not _shutdown_event.is_set():
                        await asyncio.sleep(0.5)

            # Start background monitoring
            monitor_task = asyncio.create_task(background_monitor())

            # Run the server
            await server_coroutine(**run_kwargs)

        finally:
            # Ensure monitor task is cancelled
            if monitor_task and not monitor_task.done():
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass

    # Check if we need monitoring (if shutdown event is already set, skip monitoring)
    if _shutdown_event.is_set():
        logger.info("Shutdown already requested, running server without monitoring")
        await server_coroutine(**run_kwargs)
    else:
        await run_server_with_monitoring()


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
