"""Main FastMCP server setup for Atlassian integration."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from cachetools import TTLCache
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
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.servers.dependencies import _create_user_config_for_fetcher
from mcp_atlassian.utils.environment import get_available_services
from mcp_atlassian.utils.io import is_read_only_mode
from mcp_atlassian.utils.logging import mask_sensitive
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
async def main_lifespan(app: FastMCP[MainAppContext]) -> AsyncIterator[dict]:
    """Initialize Jira/Confluence base configs and provide them in context."""
    logger.info("Main Atlassian MCP server lifespan starting...")
    services = get_available_services()
    read_only = is_read_only_mode()
    enabled_tools = get_enabled_tools()

    logger.debug(f"Lifespan start: read_only={read_only}")
    logger.debug(f"Lifespan start: enabled_tools={enabled_tools}")

    loaded_jira_config: JiraConfig | None = None
    loaded_confluence_config: ConfluenceConfig | None = None

    # Initialize Jira full config if configured
    if services.get("jira"):
        logger.info("Attempting to load full Jira configuration from environment...")
        try:
            jira_config = JiraConfig.from_env()
            if jira_config:
                loaded_jira_config = jira_config
                logger.info("Full Jira configuration loaded.")
        except Exception as e:
            logger.error(f"Failed to load Jira configuration: {e}", exc_info=True)

    # Initialize Confluence full config if configured
    if services.get("confluence"):
        logger.info(
            "Attempting to load full Confluence configuration from environment..."
        )
        try:
            confluence_config = ConfluenceConfig.from_env()
            if confluence_config:
                loaded_confluence_config = confluence_config
                logger.info("Full Confluence configuration loaded.")
        except Exception as e:
            logger.error(f"Failed to load Confluence configuration: {e}", exc_info=True)

    app_context = MainAppContext(
        full_jira_config=loaded_jira_config,
        full_confluence_config=loaded_confluence_config,
        read_only=read_only,
        enabled_tools=enabled_tools,
    )
    logger.info(f"Read-only mode: {'ENABLED' if read_only else 'DISABLED'}")
    logger.info(f"Enabled tools filter: {enabled_tools or 'All tools enabled'}")
    yield {"app_lifespan_context": app_context}
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

        # lifespan_context is now a dict: {'app_lifespan_context': MainAppContext(...)}
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


# Create the token validation cache (module-level, shared by UserTokenMiddleware)
token_validation_cache: TTLCache[
    int, tuple[bool, str | None, JiraFetcher | None, ConfluenceFetcher | None]
] = TTLCache(maxsize=100, ttl=300)  # 100 items, 5 min TTL


class UserTokenMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and validate Atlassian user tokens/credentials from Authorization headers."""

    async def is_valid_atlassian_auth(
        self,
        auth_type: str | None,
        credentials: dict[str, str] | None,
        lifespan_context: dict[str, Any],
    ) -> tuple[bool, str | None, JiraFetcher | None, ConfluenceFetcher | None]:
        """Validate Atlassian credentials and return fetcher instances if valid.

        Args:
            auth_type: The authentication type (e.g., 'oauth').
            credentials: The credentials dictionary.
            lifespan_context: Lifespan context dict.

        Returns:
            Tuple of (is_valid, user_email_if_cloud, jira_fetcher_instance, confluence_fetcher_instance).
        """
        cache_key = hash(
            credentials.get("token") or credentials.get("oauth_access_token")
        )
        if cache_key in token_validation_cache:
            logger.debug(
                f"Returning cached validation result for token hash: {cache_key}"
            )
            return token_validation_cache[cache_key]

        user_email_if_cloud: str | None = None
        jira_fetcher_instance: JiraFetcher | None = None
        confluence_fetcher_instance: ConfluenceFetcher | None = None
        is_auth_valid = False

        app_lifespan_ctx = (
            lifespan_context.get("app_lifespan_context")
            if isinstance(lifespan_context, dict)
            else None
        )
        if not app_lifespan_ctx:
            logger.error(
                "MainAppContext not found in lifespan_context for token validation."
            )
            return False, None, None, None

        async def _validate_with_service(
            fetcher_cls: type,
            base_config: Any,
            auth_type_val: str,
            creds_val: dict[str, str],
            service_name: str,
        ) -> tuple[bool, str | None, Any]:
            try:
                user_config_for_validation = await run_in_threadpool(
                    _create_user_config_for_fetcher,
                    base_config=base_config,
                    auth_type=auth_type_val,
                    credentials=creds_val,
                )
                logger.debug(
                    f"Attempting to validate {service_name} with user_config: auth_type='{user_config_for_validation.auth_type}', user='{user_config_for_validation.username}', token_present={bool(user_config_for_validation.personal_token or (user_config_for_validation.oauth_config and user_config_for_validation.oauth_config.access_token))}"
                )
                fetcher = fetcher_cls(user_config_for_validation)
                email_for_service: str | None = None
                if service_name == "Jira":
                    myself_data = await run_in_threadpool(fetcher.myself)
                    if (
                        user_config_for_validation.is_cloud
                        and myself_data
                        and isinstance(myself_data, dict)
                        and "emailAddress" in myself_data
                    ):
                        email_for_service = myself_data["emailAddress"]
                        creds_val["user_email_context"] = email_for_service
                elif service_name == "Confluence":
                    current_user_data = await run_in_threadpool(
                        fetcher.get_current_user_info
                    )
                    if (
                        user_config_for_validation.is_cloud
                        and current_user_data
                        and isinstance(current_user_data, dict)
                        and "email" in current_user_data
                    ):
                        email_for_service = current_user_data["email"]
                        creds_val["user_email_context"] = email_for_service
                current_fetcher_instance = fetcher
                logger.debug(
                    f"{service_name} auth validated successfully for user/token: {user_config_for_validation.username}..."
                )
                return True, email_for_service, current_fetcher_instance
            except Exception as exc:
                logger.info(f"{service_name} auth validation failed: {exc}")
                return False, None, None

        jira_available = app_lifespan_ctx and app_lifespan_ctx.full_jira_config
        jira_oauth_globally_configured = (
            jira_available
            and app_lifespan_ctx.full_jira_config.oauth_config
            and app_lifespan_ctx.full_jira_config.oauth_config.cloud_id
        )

        if jira_oauth_globally_configured:
            (
                valid_jira_token,
                jira_email,
                jira_fetcher_instance,
            ) = await _validate_with_service(
                JiraFetcher,
                app_lifespan_ctx.full_jira_config,
                auth_type,
                credentials,
                "Jira",
            )
            if valid_jira_token:
                is_auth_valid = True
                if jira_email and user_email_if_cloud is None:
                    user_email_if_cloud = jira_email
        else:
            logger.debug(
                "Skipping Jira token validation as Jira is not configured for OAuth globally or cloud_id is missing."
            )

        confluence_available = (
            app_lifespan_ctx and app_lifespan_ctx.full_confluence_config
        )
        confluence_oauth_globally_configured = (
            confluence_available
            and app_lifespan_ctx.full_confluence_config.oauth_config
            and app_lifespan_ctx.full_confluence_config.oauth_config.cloud_id
        )
        if confluence_oauth_globally_configured:
            (
                valid_confluence_token,
                confluence_email,
                confluence_fetcher_instance,
            ) = await _validate_with_service(
                ConfluenceFetcher,
                app_lifespan_ctx.full_confluence_config,
                auth_type,
                credentials,
                "Confluence",
            )
            if valid_confluence_token:
                is_auth_valid = True
                if confluence_email and user_email_if_cloud is None:
                    user_email_if_cloud = confluence_email
        else:
            logger.debug(
                "Skipping Confluence token validation as Confluence is not configured for OAuth globally or cloud_id is missing."
            )

        log_identifier = (
            mask_sensitive(credentials.get("token", "unknown_user_token"), keep_chars=4)
            if credentials
            else "no_creds"
        )
        if not is_auth_valid:
            logger.info(
                f"Auth validation failed for all configured services, or no service available to validate for user/token: {log_identifier}..."
            )

        validation_result = (
            is_auth_valid,
            user_email_if_cloud,
            jira_fetcher_instance,
            confluence_fetcher_instance,
        )
        token_validation_cache[cache_key] = validation_result
        return validation_result

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> JSONResponse:
        mcp_server_instance = getattr(request.app.state, "mcp_server", None)
        if mcp_server_instance is None:
            return await call_next(request)
        if not hasattr(mcp_server_instance, "_mcp_server"):
            logger.debug(
                "UserTokenMiddleware: mcp_server_instance found but _mcp_server attribute missing, skipping MCP auth logic for non-MCP request."
            )
            return await call_next(request)

        mcp_path = mcp_server_instance.settings.streamable_http_path.rstrip("/")
        request_path = request.url.path.rstrip("/")
        if request_path == mcp_path and request.method == "POST":
            auth_header = request.headers.get("Authorization")
            logger.debug(
                f"UserTokenMiddleware: Authorization header for {request.url.path}: {auth_header!r}"
            )
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1].strip()
                if not token:
                    return JSONResponse(
                        {"error": "Unauthorized: Empty Bearer token"},
                        status_code=401,
                    )
                auth_type_to_use = "oauth"
                credentials_to_use = {"oauth_access_token": token}
                logger.debug(
                    f"UserTokenMiddleware: Interpreting Bearer token as OAuth access token (masked): ...{token[-8:]}"
                )
            elif auth_header:
                logger.warning(
                    f"Unsupported Authorization type for {request.url.path}: {auth_header.split(' ', 1)[0] if ' ' in auth_header else 'UnknownType'}"
                )
                return JSONResponse(
                    {
                        "error": "Unauthorized: Only Bearer token type is supported for OAuth"
                    },
                    status_code=401,
                )
            else:
                logger.debug(
                    f"No Authorization header provided for {request.url.path}. Will proceed with global/fallback server configuration if applicable."
                )
                auth_type_to_use = None
                credentials_to_use = None

            if auth_type_to_use and credentials_to_use:
                lifespan_ctx_dict_for_validation = {}
                if (
                    mcp_server_instance
                    and hasattr(mcp_server_instance, "_mcp_server")
                    and mcp_server_instance._mcp_server is not None
                    and hasattr(mcp_server_instance._mcp_server, "request_context")
                    and mcp_server_instance._mcp_server.request_context is not None
                    and hasattr(
                        mcp_server_instance._mcp_server.request_context,
                        "lifespan_context",
                    )
                ):
                    lifespan_ctx_dict_for_validation = (
                        mcp_server_instance._mcp_server.request_context.lifespan_context
                    )
                if not lifespan_ctx_dict_for_validation:
                    logger.error(
                        "UserTokenMiddleware: Could not retrieve lifespan_context (containing MainAppContext) for token validation."
                    )
                    return JSONResponse(
                        {
                            "error": "Server misconfiguration (lifespan context not found)"
                        },
                        status_code=500,
                    )

                (
                    is_valid,
                    auth_provided_email,
                    jira_fetcher_validated,
                    confluence_fetcher_validated,
                ) = await self.is_valid_atlassian_auth(
                    auth_type_to_use,
                    credentials_to_use,
                    lifespan_ctx_dict_for_validation,
                )

                if not is_valid:
                    logger.warning(
                        f"Invalid Atlassian credentials provided for {request.url.path} via {auth_type_to_use}."
                    )
                    return JSONResponse(
                        {
                            "error": f"Unauthorized: Invalid Atlassian credentials via {auth_type_to_use}"
                        },
                        status_code=401,
                    )
                request.state.user_atlassian_token = credentials_to_use.get(
                    "oauth_access_token"
                )
                request.state.user_atlassian_auth_type = auth_type_to_use
                request.state.user_atlassian_email = auth_provided_email
                if jira_fetcher_validated:
                    request.state.jira_fetcher = jira_fetcher_validated
                    logger.debug(
                        "Validated JiraFetcher instance injected into request.state."
                    )
                if confluence_fetcher_validated:
                    request.state.confluence_fetcher = confluence_fetcher_validated
                    logger.debug(
                        "Validated ConfluenceFetcher instance injected into request.state."
                    )
                logger.debug(
                    f"UserTokenMiddleware: Authentication successful for user {auth_provided_email or 'unknown'} (token ...{str(request.state.user_atlassian_token)[-8:]})"
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
