"""Confluence server implementation."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

logger = logging.getLogger("mcp-atlassian")


@asynccontextmanager
async def confluence_lifespan(app: FastMCP) -> AsyncGenerator[dict[str, Any], None]:
    """Lifespan manager for the Confluence FastMCP server.

    Creates and manages the ConfluenceFetcher instance.
    """
    logger.info("Initializing Confluence FastMCP server...")

    # In PR #1, this is just a placeholder as we're focusing on Jira
    try:
        # Will be implemented in PR #2
        yield {"confluence_fetcher": None}
    finally:
        logger.info("Shutting down Confluence FastMCP server...")


# Create the Confluence FastMCP instance
confluence_mcp = FastMCP(
    "Confluence",
    description="Tools and resources for interacting with Confluence",
    lifespan=confluence_lifespan,
)

# Resource and tool implementations will be added in PR #2
