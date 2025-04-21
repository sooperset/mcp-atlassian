"""Main server implementation that mounts all service servers."""

import logging
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Literal

from fastmcp import FastMCP

from ..utils.io import is_read_only_mode
from .confluence import confluence_lifespan, confluence_mcp
from .jira import jira_lifespan, jira_mcp

logger = logging.getLogger("mcp-atlassian")


@asynccontextmanager
async def main_lifespan(app: FastMCP) -> AsyncGenerator[dict[str, Any], None]:
    """Manages lifespans of mounted Jira and Confluence servers."""
    logger.info("Entering main application lifespan...")

    # Determine global read-only status
    global_read_only = is_read_only_mode()
    logger.info(
        f"Main Lifespan: Global Read-only mode is {'ENABLED' if global_read_only else 'DISABLED'}"
    )

    async with AsyncExitStack() as stack:
        # Initialize Jira context
        try:
            jira_context = await stack.enter_async_context(jira_lifespan(jira_mcp))
        except Exception as e:
            logger.error(f"Error during Jira lifespan startup: {e}", exc_info=True)
            jira_context = {"jira_fetcher": None, "read_only": global_read_only}

        # Initialize Confluence context
        try:
            confluence_context = await stack.enter_async_context(
                confluence_lifespan(confluence_mcp)
            )
        except Exception as e:
            logger.error(
                f"Error during Confluence lifespan startup: {e}", exc_info=True
            )
            confluence_context = {
                "confluence_fetcher": None,
                "read_only": global_read_only,
            }

        # Combine contexts and set global read-only
        combined_context = {
            **confluence_context,
            **jira_context,
            "read_only": global_read_only,
        }

        try:
            yield combined_context
        finally:
            logger.info("Exiting main application lifespan...")


# Create the main FastMCP instance
main_mcp = FastMCP(
    "Atlassian MCP",
    description="Atlassian tools and resources for interacting with Jira and Confluence",
    lifespan=main_lifespan,
)

# Mount service-specific FastMCP instances
main_mcp.mount("jira", jira_mcp)
main_mcp.mount("confluence", confluence_mcp)


async def run_server(
    transport: Literal["stdio", "sse"] = "stdio",
    port: int = 8000,
) -> None:
    """Run the MCP Atlassian server.

    Args:
        transport: The transport to use. One of "stdio" or "sse".
        port: The port to use for SSE transport.
    """
    if transport == "stdio":
        # Use the built-in method if available, otherwise fallback
        await main_mcp.run_stdio_async()

    elif transport == "sse":
        # Use FastMCP's built-in SSE runner
        logger.info(f"Starting server with SSE transport on http://0.0.0.0:{port}")
        await main_mcp.run_sse_async(host="0.0.0.0", port=port)  # noqa: S104
