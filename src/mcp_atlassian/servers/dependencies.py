"""Dependency providers for JiraFetcher and ConfluenceFetcher with context awareness.

Provides get_jira_fetcher and get_confluence_fetcher for use in tool functions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastmcp import Context
from fastmcp.server.dependencies import get_http_request
from starlette.requests import Request

from mcp_atlassian.confluence import ConfluenceConfig, ConfluenceFetcher
from mcp_atlassian.jira import JiraConfig, JiraFetcher
from mcp_atlassian.servers.context import MainAppContext

if TYPE_CHECKING:
    from mcp_atlassian.confluence.config import ConfluenceConfig
    from mcp_atlassian.jira.config import JiraConfig

logger = logging.getLogger("mcp-atlassian.servers.dependencies")


def _create_user_config_for_fetcher(
    base_url: str,
    base_ssl_verify: bool,
    is_cloud: bool,
    auth_type: str,
    credentials: dict,
    projects_filter: str | None = None,
    spaces_filter: str | None = None,
    http_proxy: str | None = None,
    https_proxy: str | None = None,
    no_proxy: str | None = None,
    socks_proxy: str | None = None,
    config_class: type[JiraConfig] | type[ConfluenceConfig] = JiraConfig,
) -> JiraConfig | ConfluenceConfig:
    """
    Creates a user-specific configuration for Jira or Confluence fetchers.
    Only supports 'token' auth_type for user-specific config.

    Args:
        base_url: The base URL for the service.
        base_ssl_verify: Whether to verify SSL certificates.
        is_cloud: Whether the instance is Atlassian Cloud.
        auth_type: The authentication type ("token").
        credentials: Dict of credentials (token).
        projects_filter: Project filter (Jira only).
        spaces_filter: Space filter (Confluence only).
        http_proxy: HTTP proxy.
        https_proxy: HTTPS proxy.
        no_proxy: No proxy.
        socks_proxy: SOCKS proxy.
        config_class: JiraConfig or ConfluenceConfig.

    Returns:
        JiraConfig or ConfluenceConfig instance for the user.

    Raises:
        TypeError: If config_class is not supported.
        ValueError: If auth_type is not supported.
    """
    username_for_config: str | None = None
    personal_token_for_config: str | None = None
    oauth_config_for_config = (
        None  # OAuth is not handled by this user-specific config path
    )

    if auth_type == "token":
        personal_token_for_config = credentials.get("token")
        # User email for context can be passed if needed, but not used for 'token' auth type directly in config
        username_for_config = credentials.get("user_email_context")
    else:
        raise ValueError(
            f"Unsupported auth_type in _create_user_config_for_fetcher: {auth_type}"
        )

    common_args: dict[str, Any] = {
        "url": base_url,
        "auth_type": auth_type,
        "username": username_for_config,
        "api_token": None,
        "personal_token": personal_token_for_config,
        "ssl_verify": base_ssl_verify,
        "oauth_config": oauth_config_for_config,
        "http_proxy": http_proxy,
        "https_proxy": https_proxy,
        "no_proxy": no_proxy,
        "socks_proxy": socks_proxy,
    }

    if config_class is JiraConfig:
        return JiraConfig(**common_args, projects_filter=projects_filter)
    elif config_class is ConfluenceConfig:
        return ConfluenceConfig(**common_args, spaces_filter=spaces_filter)
    else:
        raise TypeError("Unsupported config_class provided")


async def get_jira_fetcher(ctx: Context) -> JiraFetcher:
    """
    Returns a JiraFetcher instance appropriate for the current request context.

    Args:
        ctx: The FastMCP context.

    Returns:
        JiraFetcher instance.

    Raises:
        ValueError: If the Jira client is not configured or available.
    """
    try:
        request: Request = get_http_request()
        user_auth_type = getattr(request.state, "user_atlassian_auth_type", None)
        credentials = {}
        if user_auth_type == "token":
            credentials["token"] = getattr(request.state, "user_atlassian_token", None)
            credentials["user_email_context"] = getattr(
                request.state, "user_atlassian_email", None
            )
        if user_auth_type and credentials:
            lifespan_ctx_dict = ctx.request_context.lifespan_context  # type: ignore
            app_lifespan_ctx: MainAppContext | None = (
                lifespan_ctx_dict.get("app_lifespan_context")
                if isinstance(lifespan_ctx_dict, dict)
                else None
            )
            if not app_lifespan_ctx or not app_lifespan_ctx.full_jira_config:
                raise ValueError(
                    "Jira global configuration (URL, SSL) is not available from lifespan context."
                )
            user_specific_config = _create_user_config_for_fetcher(
                base_url=app_lifespan_ctx.full_jira_config.url,
                base_ssl_verify=app_lifespan_ctx.full_jira_config.ssl_verify,
                is_cloud=app_lifespan_ctx.full_jira_config.is_cloud,
                auth_type=user_auth_type,
                credentials=credentials,
                projects_filter=app_lifespan_ctx.full_jira_config.projects_filter,
                http_proxy=app_lifespan_ctx.full_jira_config.http_proxy,
                https_proxy=app_lifespan_ctx.full_jira_config.https_proxy,
                no_proxy=app_lifespan_ctx.full_jira_config.no_proxy,
                socks_proxy=app_lifespan_ctx.full_jira_config.socks_proxy,
                config_class=JiraConfig,
            )
            logger.debug(
                f"Created user-specific JiraFetcher for token starting with {credentials.get('token', '')[:8]}..."
            )
            return JiraFetcher(config=user_specific_config)
    except RuntimeError:
        logger.debug(
            "Not in an HTTP request context. Attempting global JiraFetcher for STDIO/non-HTTP."
        )
    lifespan_ctx_dict_global = ctx.request_context.lifespan_context  # type: ignore
    app_lifespan_ctx_global: MainAppContext | None = (
        lifespan_ctx_dict_global.get("app_lifespan_context")
        if isinstance(lifespan_ctx_dict_global, dict)
        else None
    )
    if app_lifespan_ctx_global and app_lifespan_ctx_global.full_jira_config:
        logger.debug(
            "Using global JiraFetcher from lifespan context (e.g., for STDIO)."
        )
        return JiraFetcher(config=app_lifespan_ctx_global.full_jira_config)
    logger.error("Jira configuration could not be resolved.")
    raise ValueError(
        "Jira client (fetcher) not available. Ensure server is configured correctly."
    )


async def get_confluence_fetcher(ctx: Context) -> ConfluenceFetcher:
    """
    Returns a ConfluenceFetcher instance appropriate for the current request context.

    Args:
        ctx: The FastMCP context.

    Returns:
        ConfluenceFetcher instance.

    Raises:
        ValueError: If the Confluence client is not configured or available.
    """
    try:
        request: Request = get_http_request()
        user_auth_type = getattr(request.state, "user_atlassian_auth_type", None)
        credentials = {}
        if user_auth_type == "token":
            credentials["token"] = getattr(request.state, "user_atlassian_token", None)
            credentials["user_email_context"] = getattr(
                request.state, "user_atlassian_email", None
            )
        if user_auth_type and credentials:
            lifespan_ctx_dict = ctx.request_context.lifespan_context  # type: ignore
            app_lifespan_ctx: MainAppContext | None = (
                lifespan_ctx_dict.get("app_lifespan_context")
                if isinstance(lifespan_ctx_dict, dict)
                else None
            )
            if not app_lifespan_ctx or not app_lifespan_ctx.full_confluence_config:
                raise ValueError(
                    "Confluence global configuration (URL, SSL) is not available from lifespan context."
                )
            user_specific_config = _create_user_config_for_fetcher(
                base_url=app_lifespan_ctx.full_confluence_config.url,
                base_ssl_verify=app_lifespan_ctx.full_confluence_config.ssl_verify,
                is_cloud=app_lifespan_ctx.full_confluence_config.is_cloud,
                auth_type=user_auth_type,
                credentials=credentials,
                spaces_filter=app_lifespan_ctx.full_confluence_config.spaces_filter,
                http_proxy=app_lifespan_ctx.full_confluence_config.http_proxy,
                https_proxy=app_lifespan_ctx.full_confluence_config.https_proxy,
                no_proxy=app_lifespan_ctx.full_confluence_config.no_proxy,
                socks_proxy=app_lifespan_ctx.full_confluence_config.socks_proxy,
                config_class=ConfluenceConfig,
            )
            logger.debug(
                f"Created user-specific ConfluenceFetcher for token starting with {credentials.get('token', '')[:8]}..."
            )
            return ConfluenceFetcher(config=user_specific_config)
    except RuntimeError:
        logger.debug(
            "Not in an HTTP request context. Attempting global ConfluenceFetcher for STDIO/non-HTTP."
        )
    lifespan_ctx_dict_global = ctx.request_context.lifespan_context  # type: ignore
    app_lifespan_ctx_global: MainAppContext | None = (
        lifespan_ctx_dict_global.get("app_lifespan_context")
        if isinstance(lifespan_ctx_dict_global, dict)
        else None
    )
    if app_lifespan_ctx_global and app_lifespan_ctx_global.full_confluence_config:
        logger.debug(
            "Using global ConfluenceFetcher from lifespan context (e.g., for STDIO)."
        )
        return ConfluenceFetcher(config=app_lifespan_ctx_global.full_confluence_config)
    logger.error("Confluence configuration could not be resolved.")
    raise ValueError(
        "Confluence client (fetcher) not available. Ensure server is configured correctly."
    )
