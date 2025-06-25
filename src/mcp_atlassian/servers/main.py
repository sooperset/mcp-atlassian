"""Main FastMCP server setup for Atlassian integration."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Literal, Optional

from cachetools import TTLCache
from fastmcp import FastMCP
from fastmcp.tools import Tool as FastMCPTool
from mcp.types import Tool as MCPTool
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.environment import get_available_services
from mcp_atlassian.utils.io import is_read_only_mode
from mcp_atlassian.utils.logging import mask_sensitive
from mcp_atlassian.utils.tools import get_enabled_tools, should_include_tool

from .confluence import register_confluence_tools
from .context import MainAppContext
from .jira import register_jira_tools

logger = logging.getLogger("mcp-atlassian.server.main")


async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def build_main_lifespan(
    confluence_config: ConfluenceConfig | None = None,
    jira_config: JiraConfig | None = None,
    read_only: bool = False,
    enabled_tools: list[str] = None,
) -> Callable[[FastMCP[MainAppContext]], AsyncIterator[dict]]:
    @asynccontextmanager
    async def lifespan(_: FastMCP[MainAppContext]) -> AsyncIterator[dict]:
        logger.info("Main Atlassian MCP server lifespan starting...")

        loaded_jira_config: JiraConfig | None = jira_config
        loaded_confluence_config: ConfluenceConfig | None = confluence_config
        loaded_read_only: bool = read_only
        loaded_enabled_tools: list[str] | None = enabled_tools
        if not loaded_jira_config and not loaded_confluence_config:
            logger.warning(
                "No Confluence or Jira configuration provided. Tools may not be available."
            )
            services = get_available_services()
            loaded_read_only = is_read_only_mode()
            loaded_enabled_tools = get_enabled_tools()

            if services.get("jira") and not loaded_jira_config:
                try:
                    tmp_jira_config = JiraConfig.from_env()
                    if tmp_jira_config.is_auth_configured():
                        loaded_jira_config = tmp_jira_config
                        logger.info(
                            "Jira configuration loaded and authentication is configured."
                        )
                    else:
                        logger.warning(
                            "Jira URL found, but authentication is not fully configured. Jira tools will be unavailable."
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to load Jira configuration: {e}", exc_info=True
                    )

            if services.get("confluence") and not loaded_confluence_config:
                try:
                    tmp_confluence_config = ConfluenceConfig.from_env()
                    if tmp_confluence_config.is_auth_configured():
                        loaded_confluence_config = tmp_confluence_config
                        logger.info(
                            "Confluence configuration loaded and authentication is configured."
                        )
                    else:
                        logger.warning(
                            "Confluence URL found, but authentication is not fully configured. Confluence tools will be unavailable."
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to load Confluence configuration: {e}", exc_info=True
                    )

        app_context = MainAppContext(
            full_jira_config=loaded_jira_config,
            full_confluence_config=loaded_confluence_config,
            read_only=loaded_read_only,
            enabled_tools=loaded_enabled_tools,
        )
        logger.info(f"Read-only mode: {'ENABLED' if loaded_read_only else 'DISABLED'}")
        logger.info(
            f"Enabled tools filter: {loaded_enabled_tools or 'All tools enabled'}"
        )
        logger.info(f"Read-only mode: {'ENABLED' if loaded_read_only else 'DISABLED'}")
        logger.info(
            f"Enabled tools filter: {loaded_enabled_tools or 'All tools enabled'}"
        )

        try:
            yield {"app_lifespan_context": app_context}
        except Exception as e:
            logger.error(f"Error during lifespan: {e}", exc_info=True)
            raise
        finally:
            logger.info("Main Atlassian MCP server lifespan shutting down...")
            # Perform any necessary cleanup here
            try:
                # Close any open connections if needed
                if loaded_jira_config:
                    logger.debug("Cleaning up Jira resources...")
                if loaded_confluence_config:
                    logger.debug("Cleaning up Confluence resources...")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}", exc_info=True)
            logger.info("Main Atlassian MCP server lifespan shutdown complete.")

    return lifespan


class AtlassianMCP(FastMCP[MainAppContext]):
    """Custom FastMCP server class for Atlassian integration with tool filtering."""

    async def _mcp_list_tools(self) -> list[MCPTool]:
        # Filter tools based on enabled_tools, read_only mode, and service configuration from the lifespan context.
        req_context = self._mcp_server.request_context
        if req_context is None or req_context.lifespan_context is None:
            logger.warning(
                "Lifespan context not available during _main_mcp_list_tools call."
            )
            return []

        lifespan_ctx_dict = req_context.lifespan_context
        app_lifespan_state: MainAppContext | None = (
            lifespan_ctx_dict.get("app_lifespan_context")
            if isinstance(lifespan_ctx_dict, dict)
            else None
        )
        read_only = (
            getattr(app_lifespan_state, "read_only", False)
            if app_lifespan_state
            else False
        )
        enabled_tools_filter = (
            getattr(app_lifespan_state, "enabled_tools", None)
            if app_lifespan_state
            else None
        )
        logger.debug(
            f"_main_mcp_list_tools: read_only={read_only}, enabled_tools_filter={enabled_tools_filter}"
        )

        all_tools: dict[str, FastMCPTool] = await self.get_tools()
        logger.debug(
            f"Aggregated {len(all_tools)} tools before filtering: {list(all_tools.keys())}"
        )

        filtered_tools: list[MCPTool] = []
        for registered_name, tool_obj in all_tools.items():
            tool_tags = tool_obj.tags

            if not should_include_tool(registered_name, enabled_tools_filter):
                logger.debug(f"Excluding tool '{registered_name}' (not enabled)")
                continue

            if tool_obj and read_only and "write" in tool_tags:
                logger.debug(
                    f"Excluding tool '{registered_name}' due to read-only mode and 'write' tag"
                )
                continue

            # Exclude Jira/Confluence tools if config is not fully authenticated
            is_jira_tool = "jira" in tool_tags
            is_confluence_tool = "confluence" in tool_tags
            service_configured_and_available = True
            if app_lifespan_state:
                if is_jira_tool and not app_lifespan_state.full_jira_config:
                    logger.debug(
                        f"Excluding Jira tool '{registered_name}' as Jira configuration/authentication is incomplete."
                    )
                    service_configured_and_available = False
                if is_confluence_tool and not app_lifespan_state.full_confluence_config:
                    logger.debug(
                        f"Excluding Confluence tool '{registered_name}' as Confluence configuration/authentication is incomplete."
                    )
                    service_configured_and_available = False
            elif is_jira_tool or is_confluence_tool:
                logger.warning(
                    f"Excluding tool '{registered_name}' as application context is unavailable to verify service configuration."
                )
                service_configured_and_available = False

            if not service_configured_and_available:
                continue

            filtered_tools.append(tool_obj.to_mcp_tool(name=registered_name))

        logger.debug(
            f"_main_mcp_list_tools: Total tools after filtering: {len(filtered_tools)}"
        )
        return filtered_tools

    def http_app(
        self,
        path: str | None = None,
        middleware: list[Middleware] | None = None,
        transport: Literal["streamable-http", "sse"] = "streamable-http",
    ) -> "Starlette":
        user_token_mw = Middleware(UserTokenMiddleware, mcp_server_ref=self)
        final_middleware_list = [user_token_mw]
        if middleware:
            final_middleware_list.extend(middleware)
        app = super().http_app(
            path=path, middleware=final_middleware_list, transport=transport
        )
        return app


token_validation_cache: TTLCache[
    int, tuple[bool, str | None, JiraFetcher | None, ConfluenceFetcher | None]
] = TTLCache(maxsize=100, ttl=300)


class UserTokenMiddleware(BaseHTTPMiddleware):
    """Middleware to extract Atlassian user tokens/credentials from Authorization headers."""

    def __init__(
        self, app: Any, mcp_server_ref: Optional["AtlassianMCP"] = None
    ) -> None:
        super().__init__(app)
        self.mcp_server_ref = mcp_server_ref
        if not self.mcp_server_ref:
            logger.warning(
                "UserTokenMiddleware initialized without mcp_server_ref. Path matching for MCP endpoint might fail if settings are needed."
            )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> JSONResponse:
        logger.debug(
            f"UserTokenMiddleware.dispatch: ENTERED for request path='{request.url.path}', method='{request.method}'"
        )
        mcp_server_instance = self.mcp_server_ref
        if mcp_server_instance is None:
            logger.debug(
                "UserTokenMiddleware.dispatch: self.mcp_server_ref is None. Skipping MCP auth logic."
            )
            return await call_next(request)

        mcp_path = mcp_server_instance.settings.streamable_http_path.rstrip("/")
        request_path = request.url.path.rstrip("/")
        logger.debug(
            f"UserTokenMiddleware.dispatch: Comparing request_path='{request_path}' with mcp_path='{mcp_path}'. Request method='{request.method}'"
        )
        if request_path == mcp_path and request.method == "POST":
            auth_header = request.headers.get("Authorization")
            cloud_id_header = request.headers.get("X-Atlassian-Cloud-Id")

            token_for_log = mask_sensitive(
                auth_header.split(" ", 1)[1].strip()
                if auth_header and " " in auth_header
                else auth_header
            )
            logger.debug(
                f"UserTokenMiddleware: Path='{request.url.path}', AuthHeader='{mask_sensitive(auth_header)}', ParsedToken(masked)='{token_for_log}', CloudId='{cloud_id_header}'"
            )

            # Extract and save cloudId if provided
            if cloud_id_header and cloud_id_header.strip():
                request.state.user_atlassian_cloud_id = cloud_id_header.strip()
                logger.debug(
                    f"UserTokenMiddleware: Extracted cloudId from header: {cloud_id_header.strip()}"
                )
            else:
                request.state.user_atlassian_cloud_id = None
                logger.debug(
                    "UserTokenMiddleware: No cloudId header provided, will use global config"
                )

            # Check for mcp-session-id header for debugging
            mcp_session_id = request.headers.get("mcp-session-id")
            if mcp_session_id:
                logger.debug(
                    f"UserTokenMiddleware: MCP-Session-ID header found: {mcp_session_id}"
                )
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1].strip()
                if not token:
                    return JSONResponse(
                        {"error": "Unauthorized: Empty Bearer token"},
                        status_code=401,
                    )
                logger.debug(
                    f"UserTokenMiddleware.dispatch: Bearer token extracted (masked): ...{mask_sensitive(token, 8)}"
                )
                request.state.user_atlassian_token = token
                request.state.user_atlassian_auth_type = "oauth"
                request.state.user_atlassian_email = None
                logger.debug(
                    f"UserTokenMiddleware.dispatch: Set request.state (pre-validation): "
                    f"auth_type='{getattr(request.state, 'user_atlassian_auth_type', 'N/A')}', "
                    f"token_present={bool(getattr(request.state, 'user_atlassian_token', None))}"
                )
            elif auth_header and auth_header.startswith("Token "):
                token = auth_header.split(" ", 1)[1].strip()
                if not token:
                    return JSONResponse(
                        {"error": "Unauthorized: Empty Token (PAT)"},
                        status_code=401,
                    )
                logger.debug(
                    f"UserTokenMiddleware.dispatch: PAT (Token scheme) extracted (masked): ...{mask_sensitive(token, 8)}"
                )
                request.state.user_atlassian_token = token
                request.state.user_atlassian_auth_type = "pat"
                request.state.user_atlassian_email = (
                    None  # PATs don't carry email in the token itself
                )
                logger.debug(
                    "UserTokenMiddleware.dispatch: Set request.state for PAT auth."
                )
            elif auth_header:
                logger.warning(
                    f"Unsupported Authorization type for {request.url.path}: {auth_header.split(' ', 1)[0] if ' ' in auth_header else 'UnknownType'}"
                )
                return JSONResponse(
                    {
                        "error": "Unauthorized: Only 'Bearer <OAuthToken>' or 'Token <PAT>' types are supported."
                    },
                    status_code=401,
                )
            else:
                logger.debug(
                    f"No Authorization header provided for {request.url.path}. Will proceed with global/fallback server configuration if applicable."
                )
        response = await call_next(request)
        logger.debug(
            f"UserTokenMiddleware.dispatch: EXITED for request path='{request.url.path}'"
        )
        return response


def build_main_mcp(
    confluence_config: ConfluenceConfig | None = None,
    jira_config: JiraConfig | None = None,
    read_only: bool = False,
    enabled_tools: list[str] = None,
) -> AtlassianMCP:
    """Build the main Atlassian MCP server with mounted Jira and Confluence servers."""
    jira_mcp = FastMCP(
        name="Jira MCP Service",
        description="Provides tools for interacting with Atlassian Jira.",
    )
    register_jira_tools(jira_mcp)
    confluence_mcp = FastMCP(
        name="Confluence MCP Service",
        description="Provides tools for interacting with Atlassian Confluence.",
    )
    register_confluence_tools(confluence_mcp)

    atlassian_mcp = AtlassianMCP(
        name="Atlassian MCP",
        lifespan=build_main_lifespan(
            confluence_config=confluence_config,
            jira_config=jira_config,
            read_only=read_only,
            enabled_tools=enabled_tools,
        ),
    )
    atlassian_mcp.mount("jira", jira_mcp)
    atlassian_mcp.mount("confluence", confluence_mcp)

    @atlassian_mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def _health_check_route(request: Request) -> JSONResponse:
        return await health_check(request)

    logger.info("Added /healthz endpoint for Kubernetes probes")
    return atlassian_mcp


main_mcp = build_main_mcp()
