"""Main FastMCP server setup for Atlassian integration."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools import Tool as FastMCPTool
from mcp.types import Tool as MCPTool
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
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
    """Initialize Jira/Confluence base configs and provide them in context."""
    logger.info("Main Atlassian MCP server lifespan starting...")
    services = get_available_services()
    read_only = is_read_only_mode()
    enabled_tools = get_enabled_tools()

    logger.debug(f"Lifespan start: read_only={read_only}")
    logger.debug(f"Lifespan start: enabled_tools={enabled_tools}")

    final_jira_base_config: JiraConfig | None = None
    final_confluence_base_config: ConfluenceConfig | None = None

    # Initialize Jira base config if configured
    if services.get("jira"):
        logger.info("Attempting to load Jira base configuration...")
        try:
            jira_config = JiraConfig.from_env()
            if jira_config:
                final_jira_base_config = JiraConfig(
                    url=jira_config.url,
                    auth_type=None,
                    username=None,
                    api_token=None,
                    personal_token=None,
                    oauth_config=None,
                    ssl_verify=jira_config.ssl_verify,
                    projects_filter=jira_config.projects_filter,
                    http_proxy=jira_config.http_proxy,
                    https_proxy=jira_config.https_proxy,
                    no_proxy=jira_config.no_proxy,
                    socks_proxy=jira_config.socks_proxy,
                )
                logger.info("Jira base configuration loaded.")
        except Exception as e:
            logger.error(f"Failed to load Jira base configuration: {e}", exc_info=True)

    # Initialize Confluence base config if configured
    if services.get("confluence"):
        logger.info("Attempting to load Confluence base configuration...")
        try:
            confluence_config = ConfluenceConfig.from_env()
            if confluence_config:
                final_confluence_base_config = ConfluenceConfig(
                    url=confluence_config.url,
                    auth_type=None,
                    username=None,
                    api_token=None,
                    personal_token=None,
                    oauth_config=None,
                    ssl_verify=confluence_config.ssl_verify,
                    spaces_filter=confluence_config.spaces_filter,
                    http_proxy=confluence_config.http_proxy,
                    https_proxy=confluence_config.https_proxy,
                    no_proxy=confluence_config.no_proxy,
                    socks_proxy=confluence_config.socks_proxy,
                )
                logger.info("Confluence base configuration loaded.")
        except Exception as e:
            logger.error(
                f"Failed to load Confluence base configuration: {e}", exc_info=True
            )

    app_context = MainAppContext(
        jira_base_config=final_jira_base_config,
        confluence_base_config=final_confluence_base_config,
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


class UserTokenMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and validate Atlassian user tokens from Authorization headers."""

    async def is_valid_atlassian_token(
        self, token: str, lifespan_context: MainAppContext
    ) -> tuple[bool, str | None]:
        """Validate the Atlassian token against Jira or Confluence. Returns (is_valid, user_email_if_cloud)."""
        user_email_if_cloud: str | None = None

        async def _validate_with_service(
            fetcher_cls: type,
            base_config: Any,
            token_val: str,
            service_name: str,
        ) -> tuple[bool, str | None]:
            nonlocal user_email_if_cloud
            if not base_config:
                logger.debug(
                    f"No base config for {service_name}, skipping validation with it."
                )
                return False, None
            updated_fields = {
                "auth_type": "token",
                "personal_token": token_val,
                "username": None,
                "api_token": None,
                "oauth_config": None,
            }
            if not hasattr(base_config, "model_copy"):
                logger.error(
                    f"{service_name} base_config is not a Pydantic model, cannot use model_copy."
                )
                return False, None
            temp_config = base_config.model_copy(update=updated_fields)
            try:
                fetcher = fetcher_cls(config=temp_config)
                if service_name == "Jira":
                    myself_data = await run_in_threadpool(fetcher.jira.myself)
                    if (
                        getattr(temp_config, "is_cloud", False)
                        and myself_data
                        and "emailAddress" in myself_data
                    ):
                        user_email_if_cloud = myself_data["emailAddress"]
                elif service_name == "Confluence":
                    current_user = await run_in_threadpool(
                        fetcher.confluence.get_current_user
                    )
                    if (
                        getattr(temp_config, "is_cloud", False)
                        and current_user
                        and "email" in current_user
                    ):
                        user_email_if_cloud = current_user["email"]
                return True, user_email_if_cloud
            except MCPAtlassianAuthenticationError:
                logger.warning(
                    f"{service_name} token validation failed (authentication error) for token starting with: {token_val[:8]}..."
                )
                return False, None
            except Exception as e:
                logger.error(
                    f"Unexpected error during {service_name} token validation for {token_val[:8]}...: {e}",
                    exc_info=True,
                )
                return False, None

        # Try validating with Jira config if available
        if lifespan_context.jira_base_config:
            is_valid, email = await _validate_with_service(
                JiraFetcher, lifespan_context.jira_base_config, token, "Jira"
            )
            if is_valid:
                return True, email
        # If Jira validation failed or not configured, try Confluence
        if lifespan_context.confluence_base_config:
            is_valid, email = await _validate_with_service(
                ConfluenceFetcher,
                lifespan_context.confluence_base_config,
                token,
                "Confluence",
            )
            if is_valid:
                return True, email
        logger.warning(
            f"Token validation failed for all configured services, or no service available to validate token starting with: {token[:8]}..."
        )
        return False, None

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> JSONResponse:
        mcp_server_instance = getattr(request.app.state, "mcp_server", None)
        if mcp_server_instance is None:
            return await call_next(request)
        mcp_path = mcp_server_instance.settings.streamable_http_path.rstrip("/")
        request_path = request.url.path.rstrip("/")
        if request_path == mcp_path and request.method == "POST":
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                user_atlassian_token = auth_header.split(" ", 1)[1]
                if user_atlassian_token:
                    lifespan_ctx = request.scope.get("fastmcp_lifespan_context")
                    if lifespan_ctx is None:
                        logger.warning(
                            "No lifespan context available in request.scope for token validation."
                        )
                        return JSONResponse(
                            {
                                "error": "Unauthorized: Server misconfiguration (no lifespan context)"
                            },
                            status_code=500,
                        )
                    is_valid, user_email = await self.is_valid_atlassian_token(
                        user_atlassian_token, lifespan_ctx
                    )
                    if not is_valid:
                        logger.warning(
                            f"Invalid Atlassian token provided for {request.url.path}."
                        )
                        return JSONResponse(
                            {"error": "Unauthorized: Invalid Atlassian token"},
                            status_code=401,
                        )
                    request.state.user_atlassian_token = user_atlassian_token
                    request.state.user_atlassian_email = user_email
                else:
                    logger.warning(
                        f"Authorization Bearer token is empty for {request.url.path}"
                    )
                    return JSONResponse(
                        {"error": "Unauthorized: Empty Bearer token"}, status_code=401
                    )
            else:
                logger.warning(
                    f"Authorization header missing or not Bearer for {request.url.path}"
                )
                return JSONResponse(
                    {"error": "Unauthorized: Missing or malformed Bearer token"},
                    status_code=401,
                )
        response = await call_next(request)
        return response


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


base_mcp_http_app = main_mcp.streamable_http_app()
final_middleware_stack = base_mcp_http_app.user_middleware + [
    Middleware(UserTokenMiddleware)
]
final_asgi_app = Starlette(
    routes=base_mcp_http_app.router.routes,
    middleware=final_middleware_stack,
    lifespan=main_lifespan,
)
final_asgi_app.state.mcp_server = main_mcp
