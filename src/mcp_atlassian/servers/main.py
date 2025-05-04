"""Main FastMCP server setup for Atlassian integration."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastmcp import FastMCP

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils import is_read_only_mode
from mcp_atlassian.utils.logging import log_config_param
from mcp_atlassian.utils.tools import get_enabled_tools

from ..server import get_available_services  # Import from the old server.py initially
from .confluence import confluence_mcp  # Import the instance
from .jira import jira_mcp  # Import the instance

logger = logging.getLogger("mcp-atlassian.server.main")

@dataclass
class MainAppContext:
    """Context holding initialized fetchers and server settings."""
    jira_fetcher: JiraFetcher | None = None
    confluence_fetcher: ConfluenceFetcher | None = None
    read_only: bool = False
    enabled_tools: list[str] | None = None

@asynccontextmanager
async def main_lifespan(app: FastMCP[MainAppContext]) -> AsyncIterator[MainAppContext]:
    """Initialize Jira/Confluence clients and provide them in context."""
    logger.info("Main Atlassian MCP server lifespan starting...")
    services = get_available_services()
    read_only = is_read_only_mode()
    enabled_tools = get_enabled_tools()

    jira: JiraFetcher | None = None
    confluence: ConfluenceFetcher | None = None

    # Initialize Jira if configured
    if services.get("jira"):
        logger.info("Attempting to initialize Jira client...")
        try:
            jira_config = JiraConfig.from_env()
            # (Log config details - reuse logging logic from old server.py if needed)
            jira = JiraFetcher(config=jira_config)
            logger.info("Jira client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Jira client: {e}", exc_info=True)

    # Initialize Confluence if configured
    if services.get("confluence"):
        logger.info("Attempting to initialize Confluence client...")
        try:
            confluence_config = ConfluenceConfig.from_env()
            # (Log config details)
            confluence = ConfluenceFetcher(config=confluence_config)
            logger.info("Confluence client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Confluence client: {e}", exc_info=True)

    app_context = MainAppContext(
        jira_fetcher=jira,
        confluence_fetcher=confluence,
        read_only=read_only,
        enabled_tools=enabled_tools,
    )
    logger.info(f"Read-only mode: {'ENABLED' if read_only else 'DISABLED'}")
    logger.info(f"Enabled tools filter: {enabled_tools or 'All tools enabled'}")
    yield app_context
    logger.info("Main Atlassian MCP server lifespan shutting down.")

# Initialize the main MCP server instance
main_mcp = FastMCP(name="Atlassian MCP", lifespan=main_lifespan)

# Mount the Jira and Confluence sub-servers
main_mcp.mount("jira", jira_mcp)
main_mcp.mount("confluence", confluence_mcp) 