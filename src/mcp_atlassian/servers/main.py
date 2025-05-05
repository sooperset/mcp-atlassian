"""Main FastMCP server setup for Atlassian integration."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastmcp import FastMCP
from fastmcp.tools import Tool as FastMCPTool
from mcp.types import Tool as MCPTool

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils import is_read_only_mode
from mcp_atlassian.utils.environment import get_available_services
from mcp_atlassian.utils.tools import get_enabled_tools, should_include_tool

from .confluence import confluence_mcp
from .jira import jira_mcp

logger = logging.getLogger("mcp-atlassian.server.main")


@dataclass(frozen=True)
class MainAppContext:
    """Context holding initialized fetchers and server settings."""

    jira: JiraFetcher | None = None
    confluence: ConfluenceFetcher | None = None
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
            jira = JiraFetcher(config=jira_config)
            logger.info("Jira client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Jira client: {e}", exc_info=True)

    # Initialize Confluence if configured
    if services.get("confluence"):
        logger.info("Attempting to initialize Confluence client...")
        try:
            confluence_config = ConfluenceConfig.from_env()
            confluence = ConfluenceFetcher(config=confluence_config)
            logger.info("Confluence client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Confluence client: {e}", exc_info=True)

    app_context = MainAppContext(
        jira=jira,
        confluence=confluence,
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


async def _main_mcp_list_tools(self: FastMCP[MainAppContext]) -> list[MCPTool]:
    """
    List tools, applying filtering based on enabled_tools and read_only mode from the lifespan context.
    Tools with the 'write' tag are excluded in read-only mode.
    """
    if self._mcp_server.lifespan_context is None:
        logger.warning(
            "Lifespan context not available during _main_mcp_list_tools call."
        )
        return []

    lifespan_ctx = self._mcp_server.lifespan_context
    read_only = getattr(lifespan_ctx, "read_only", False)
    enabled_tools_filter = getattr(lifespan_ctx, "enabled_tools", None)
    logger.debug(
        f"_main_mcp_list_tools: read_only={read_only}, enabled_tools_filter={enabled_tools_filter}"
    )

    local_tools = self._tool_manager.list_tools()
    logger.debug(f"_main_mcp_list_tools: Found {len(local_tools)} local tools.")

    mounted_tools_prefixed: dict[str, FastMCPTool] = {}
    for mount_prefix, mount_info in self._mounted_servers.items():
        try:
            server_tools = await mount_info.get_tools()
            mounted_tools_prefixed.update(server_tools)
            logger.debug(
                f"_main_mcp_list_tools: Found {len(server_tools)} tools from mounted server '{mount_prefix}'."
            )
        except Exception as e:
            logger.error(
                f"Error fetching tools from mounted server '{mount_prefix}': {e}",
                exc_info=True,
            )

    logger.debug(
        f"_main_mcp_list_tools: Total tools before filtering: {len(local_tools) + len(mounted_tools_prefixed)}"
    )

    all_tool_items: list[FastMCPTool | tuple[str, FastMCPTool]] = list(
        local_tools
    ) + list(mounted_tools_prefixed.items())
    filtered_tools: list[tuple[str, FastMCPTool]] = []

    for item in all_tool_items:
        if isinstance(item, tuple):
            tool_name_registered = item[0]
            tool_obj = item[1]
            tool_name_original = tool_obj.name
        else:
            tool_name_registered = item.name
            tool_obj = item
            tool_name_original = item.name

        if not should_include_tool(tool_name_original, enabled_tools_filter):
            logger.debug(
                f"_main_mcp_list_tools: Excluding tool '{tool_name_original}' (registered as '{tool_name_registered}') due to ENABLED_TOOLS filter."
            )
            continue

        if read_only and "write" in tool_obj.tags:
            logger.debug(
                f"_main_mcp_list_tools: Excluding write tool '{tool_name_registered}' (tagged 'write') in read-only mode."
            )
            continue

        filtered_tools.append((tool_name_registered, tool_obj))

    logger.debug(
        f"_main_mcp_list_tools: Total tools after filtering: {len(filtered_tools)}"
    )

    mcp_tools = [
        tool_obj.to_mcp_tool(name=registered_name)
        for registered_name, tool_obj in filtered_tools
    ]

    return mcp_tools


# Bind the override to the main_mcp instance
main_mcp._mcp_list_tools = _main_mcp_list_tools.__get__(main_mcp, FastMCP)  # type: ignore
