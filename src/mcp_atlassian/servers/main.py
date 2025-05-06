"""Main FastMCP server setup for Atlassian integration."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp.tools import Tool as FastMCPTool
from mcp.types import Tool as MCPTool
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils import is_read_only_mode
from mcp_atlassian.utils.environment import get_available_services
from mcp_atlassian.utils.tools import get_enabled_tools, should_include_tool

from .confluence import confluence_mcp
from .context import MainAppContext
from .jira import jira_mcp

logger = logging.getLogger("mcp-atlassian.server.main")


async def health_check(request: Request) -> JSONResponse:
    """Simple health check endpoint for Kubernetes probes."""
    logger.debug("Received health check request.")
    return JSONResponse({"status": "ok"})


@asynccontextmanager
async def main_lifespan(app: FastMCP[MainAppContext]) -> AsyncIterator[MainAppContext]:
    """Initialize Jira/Confluence clients and provide them in context."""
    logger.info("Main Atlassian MCP server lifespan starting...")
    services = get_available_services()
    read_only = is_read_only_mode()
    enabled_tools = get_enabled_tools()

    logger.debug(f"Lifespan start: read_only={read_only}")
    logger.debug(f"Lifespan start: enabled_tools={enabled_tools}")

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


class AtlassianMCP(FastMCP[MainAppContext]):
    """Custom FastMCP server class for Atlassian integration with tool filtering."""

    async def _mcp_list_tools(self) -> list[MCPTool]:
        """Override: List tools, applying filtering based on context.

        List tools, applying filtering based on enabled_tools and read_only mode from the lifespan context.
        Tools with the 'write' tag are excluded in read-only mode.
        """
        # Access lifespan_context through the request_context
        req_context = self._mcp_server.request_context
        if req_context is None or req_context.lifespan_context is None:
            logger.warning(
                "Lifespan context not available via request_context during _main_mcp_list_tools call."
            )
            return []

        lifespan_ctx = req_context.lifespan_context
        read_only = getattr(lifespan_ctx, "read_only", False)
        enabled_tools_filter = getattr(lifespan_ctx, "enabled_tools", None)
        logger.debug(
            f"_main_mcp_list_tools: read_only={read_only}, enabled_tools_filter={enabled_tools_filter}"
        )

        # 1. Get the full, potentially unfiltered list of tools from the base implementation
        all_tools: dict[str, FastMCPTool] = await self.get_tools()
        logger.debug(
            f"Aggregated {len(all_tools)} tools before filtering: {list(all_tools.keys())}"
        )

        # 2. Filter the aggregated list based on the context
        filtered_tools: list[MCPTool] = []
        for registered_name, tool_obj in all_tools.items():
            original_tool_name = tool_obj.name
            tool_tags = tool_obj.tags
            logger.debug(
                f"Checking tool: registered_name='{registered_name}', original_name='{original_tool_name}', tags={tool_tags}"
            )

            # Check against enabled_tools filter using the *registered* tool name
            if not should_include_tool(registered_name, enabled_tools_filter):
                logger.debug(
                    f"Excluding tool '{registered_name}' because it's not in the enabled_tools list: {enabled_tools_filter}"
                )
                continue

            # Check read-only status and 'write' tag
            if tool_obj and read_only and "write" in tool_tags:
                logger.debug(
                    f"Excluding tool '{registered_name}' (original: '{original_tool_name}') because it has tag 'write' and read_only is True."
                )
                continue

            # Convert the filtered Tool object to MCPTool using the registered name
            logger.debug(
                f"Including tool '{registered_name}' (original: '{original_tool_name}')"
            )
            filtered_tools.append(tool_obj.to_mcp_tool(name=registered_name))

        logger.debug(
            f"_main_mcp_list_tools: Total tools after filtering: {len(filtered_tools)}"
        )
        logger.debug(
            f"_main_mcp_list_tools: Included tools: {[tool.name for tool in filtered_tools]}"
        )
        return filtered_tools


# Initialize the main MCP server using the custom class
main_mcp = AtlassianMCP(name="Atlassian MCP", lifespan=main_lifespan)

# Mount the Jira and Confluence sub-servers
main_mcp.mount("jira", jira_mcp)
main_mcp.mount("confluence", confluence_mcp)


# Add the health check endpoint using the decorator
@main_mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def _health_check_route(request: Request) -> JSONResponse:
    return await health_check(request)


logger.info("Added /healthz endpoint for Kubernetes probes")
