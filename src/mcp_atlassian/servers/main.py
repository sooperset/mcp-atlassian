"""Main FastMCP server setup for Atlassian integration."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal, Optional

from cachetools import TTLCache
from fastmcp import FastMCP
from fastmcp.tools import Tool as FastMCPTool
from fastmcp.server.dependencies import get_http_request
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

from .confluence import confluence_mcp
from .context import MainAppContext
from .jira import jira_mcp

logger = logging.getLogger("mcp-atlassian.server.main")


async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@asynccontextmanager
async def main_lifespan(app: FastMCP[MainAppContext]) -> AsyncIterator[dict]:
    logger.info("Main Atlassian MCP server lifespan starting...")
    read_only = is_read_only_mode()
    enabled_tools = get_enabled_tools()

    loaded_jira_config: JiraConfig | None = None
    loaded_confluence_config: ConfluenceConfig | None = None

    # URL만 있어도 도구들을 초기화하도록 수정
    jira_url = os.getenv("JIRA_URL")
    confluence_url = os.getenv("CONFLUENCE_URL")

    if jira_url:
        try:
            # URL만으로 기본 설정 생성 (인증은 나중에 사용자별로 처리)
            from mcp_atlassian.jira.config import JiraConfig
            jira_config = JiraConfig(
                url=jira_url,
                auth_type="api_token",  # Atlassian Cloud API Token 사용
                ssl_verify=False,  # SSL 검증 무시
            )
            loaded_jira_config = jira_config
            logger.info(
                f"Jira configuration loaded (URL only: {jira_url}). Authentication will be handled per-user via headers."
            )
        except Exception as e:
            logger.error(f"Failed to load Jira configuration: {e}", exc_info=True)

    if confluence_url:
        try:
            # URL만으로 기본 설정 생성 (인증은 나중에 사용자별로 처리)
            from mcp_atlassian.confluence.config import ConfluenceConfig
            confluence_config = ConfluenceConfig(
                url=confluence_url,
                auth_type="api_token",  # Atlassian Cloud API Token 사용
                ssl_verify=False,  # SSL 검증 무시
            )
            loaded_confluence_config = confluence_config
            logger.info(
                f"Confluence configuration loaded (URL only: {confluence_url}). Authentication will be handled per-user via headers."
            )
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

        # 인증 검증 수행
        try:
            request: Request = get_http_request()
            auth_header = request.headers.get("Authorization")
            user_email = getattr(request.state, "user_atlassian_email", None)
            
            if not auth_header:
                logger.warning("No Authorization header provided during tool listing")
                return []
            
            # Bearer 토큰 검증
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1].strip()
                if not token:
                    logger.warning("Empty Bearer token provided")
                    return []
                
                # Jira 인증 검증
                try:
                    from mcp_atlassian.jira.config import JiraConfig
                    from mcp_atlassian.jira import JiraFetcher
                    import os
                    
                    jira_url = os.getenv("JIRA_URL")
                    if jira_url:
                        jira_config = JiraConfig(
                            url=jira_url,
                            auth_type="api_token",  # Atlassian Cloud API Token 사용
                            ssl_verify=False,
                            api_token=token,  # api_token 필드 사용
                            username=user_email
                        )
                        jira_fetcher = JiraFetcher(config=jira_config)
                        current_user = jira_fetcher.get_current_user_account_id()
                        logger.info(f"Jira authentication successful for user: {current_user}")
                except Exception as e:
                    logger.error(f"Jira authentication failed: {e}")
                    return []
                
                # Confluence 인증 검증
                try:
                    from mcp_atlassian.confluence.config import ConfluenceConfig
                    from mcp_atlassian.confluence import ConfluenceFetcher
                    
                    confluence_url = os.getenv("CONFLUENCE_URL")
                    if confluence_url:
                        confluence_config = ConfluenceConfig(
                            url=confluence_url,
                            auth_type="api_token",  # Atlassian Cloud API Token 사용
                            ssl_verify=False,
                            api_token=token,  # api_token 필드 사용
                            username=user_email
                        )
                        confluence_fetcher = ConfluenceFetcher(config=confluence_config)
                        current_user_info = confluence_fetcher.get_current_user_info()
                        logger.info(f"Confluence authentication successful for user: {current_user_info.get('displayName', 'unknown')}")
                except Exception as e:
                    logger.error(f"Confluence authentication failed: {e}")
                    return []
                    
            else:
                logger.warning(f"Unsupported Authorization header format: {auth_header[:20]}...")
                return []
                
        except Exception as e:
            logger.error(f"Authentication validation failed during tool listing: {e}")
            return []

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

            # 인증이 성공했으므로 모든 도구를 표시
            filtered_tools.append(tool_obj.to_mcp_tool(name=registered_name))

        logger.info(f"Tool listing successful: {len(filtered_tools)} tools enabled after authentication validation")
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
            user_email_header = request.headers.get("X-User-Email")

            token_for_log = mask_sensitive(
                auth_header.split(" ", 1)[1].strip()
                if auth_header and " " in auth_header
                else auth_header
            )
            logger.debug(
                f"UserTokenMiddleware: Path='{request.url.path}', AuthHeader='{mask_sensitive(auth_header)}', ParsedToken(masked)='{token_for_log}', CloudId='{cloud_id_header}', UserEmail='{user_email_header}'"
            )

            # Extract and save user email if provided
            if user_email_header and user_email_header.strip():
                request.state.user_atlassian_email = user_email_header.strip()
                logger.debug(
                    f"UserTokenMiddleware: Extracted user email from header: {user_email_header.strip()}"
                )
            else:
                request.state.user_atlassian_email = None
                logger.debug(
                    "UserTokenMiddleware: No user email header provided"
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
                request.state.user_atlassian_auth_type = "api_token"  # Bearer 토큰을 api_token 타입으로 처리
                request.state.user_atlassian_email = user_email_header.strip() if user_email_header else None # Set email from header
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


main_mcp = AtlassianMCP(name="Atlassian MCP", lifespan=main_lifespan)
main_mcp.mount("jira", jira_mcp)
main_mcp.mount("confluence", confluence_mcp)


@main_mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def _health_check_route(request: Request) -> JSONResponse:
    return await health_check(request)


logger.info("Added /healthz endpoint for Kubernetes probes")
