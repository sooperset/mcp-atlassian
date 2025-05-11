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
from mcp_atlassian.utils.oauth import OAuthConfig

if TYPE_CHECKING:
    from mcp_atlassian.confluence.config import ConfluenceConfig
    from mcp_atlassian.jira.config import JiraConfig

logger = logging.getLogger("mcp-atlassian.servers.dependencies")


def _create_user_config_for_fetcher(
    base_config: JiraConfig | ConfluenceConfig,  # global config object
    auth_type: str,
    credentials: dict,
    config_class: type[JiraConfig] | type[ConfluenceConfig] = JiraConfig,
) -> JiraConfig | ConfluenceConfig:
    """
    Creates a user-specific configuration for Jira or Confluence fetchers.
    Supports 'token' (PAT) and 'oauth' (user access token) auth_type for user-specific config.

    Args:
        base_config: The global configuration for the service (JiraConfig or ConfluenceConfig).
        auth_type: The authentication type determined for the user ("token" or "oauth").
        credentials: Dict of credentials (token or oauth_access_token).
        config_class: JiraConfig or ConfluenceConfig.

    Returns:
        JiraConfig or ConfluenceConfig instance for the user.

    Raises:
        TypeError: If config_class is not supported.
        ValueError: If auth_type is not supported.
        ValueError: If OAuth credentials or global cloud_id are missing for 'oauth' auth_type.
    """
    username_for_config: str | None = None
    personal_token_for_config: str | None = None
    oauth_config_for_user: OAuthConfig | None = None

    logger.debug(
        f"Creating user config for fetcher. Auth type: {auth_type}, Credentials keys: {credentials.keys()}"
    )
    if auth_type == "token":
        personal_token_for_config = credentials.get("token")
        username_for_config = credentials.get("user_email_context")
    elif auth_type == "oauth":
        user_access_token = credentials.get("oauth_access_token")
        if not user_access_token:
            raise ValueError(
                "OAuth access token missing in credentials for user auth_type 'oauth'"
            )
        if (
            not base_config
            or not base_config.oauth_config
            or not base_config.oauth_config.cloud_id
        ):
            raise ValueError(
                f"Global OAuth config (with cloud_id) for {config_class.__name__} is missing, "
                "but user auth_type is 'oauth'. Cannot determine cloud_id."
            )
        oauth_config_for_user = OAuthConfig(
            client_id="",  # not needed for user token
            client_secret="",  # not needed for user token
            redirect_uri="",  # not needed for user token
            scope="",  # not needed for user token
            access_token=user_access_token,
            refresh_token=None,
            expires_at=None,
            cloud_id=base_config.oauth_config.cloud_id,
        )
        username_for_config = credentials.get("user_email_context")
    else:
        raise ValueError(
            f"Unsupported auth_type in _create_user_config_for_fetcher: {auth_type}"
        )

    common_args: dict[str, Any] = {
        "url": base_config.url,
        "auth_type": auth_type,
        "username": username_for_config,
        "api_token": None,
        "personal_token": personal_token_for_config,
        "ssl_verify": base_config.ssl_verify,
        "oauth_config": oauth_config_for_user,
        "http_proxy": base_config.http_proxy,
        "https_proxy": base_config.https_proxy,
        "no_proxy": base_config.no_proxy,
        "socks_proxy": base_config.socks_proxy,
    }

    if config_class is JiraConfig:
        return JiraConfig(**common_args, projects_filter=base_config.projects_filter)
    elif config_class is ConfluenceConfig:
        return ConfluenceConfig(**common_args, spaces_filter=base_config.spaces_filter)
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
        logger.debug(
            f"get_jira_fetcher: User auth type from request.state: {user_auth_type}"
        )
        credentials = {}
        if user_auth_type == "token":
            credentials["token"] = getattr(request.state, "user_atlassian_token", None)
            credentials["user_email_context"] = getattr(
                request.state, "user_atlassian_email", None
            )
        elif user_auth_type == "oauth":
            credentials["oauth_access_token"] = getattr(
                request.state, "user_atlassian_token", None
            )
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
            logger.debug(
                f"get_jira_fetcher: Found app_lifespan_ctx with full_jira_config URL: {app_lifespan_ctx.full_jira_config.url}"
            )
            user_specific_config = _create_user_config_for_fetcher(
                base_config=app_lifespan_ctx.full_jira_config,
                auth_type=user_auth_type,
                credentials=credentials,
                config_class=JiraConfig,
            )
            logger.debug(
                f"Created user-specific JiraConfig for token starting with {credentials.get('token', credentials.get('oauth_access_token', ''))[:10]}... Resulting auth_type: {user_specific_config.auth_type}"
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
        logger.debug(
            f"get_confluence_fetcher: User auth type from request.state: {user_auth_type}"
        )
        credentials = {}
        if user_auth_type == "token":
            credentials["token"] = getattr(request.state, "user_atlassian_token", None)
            credentials["user_email_context"] = getattr(
                request.state, "user_atlassian_email", None
            )
        elif user_auth_type == "oauth":
            credentials["oauth_access_token"] = getattr(
                request.state, "user_atlassian_token", None
            )
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
            logger.debug(
                f"get_confluence_fetcher: Found app_lifespan_ctx with full_confluence_config URL: {app_lifespan_ctx.full_confluence_config.url}"
            )
            user_specific_config = _create_user_config_for_fetcher(
                base_config=app_lifespan_ctx.full_confluence_config,
                auth_type=user_auth_type,
                credentials=credentials,
                config_class=ConfluenceConfig,
            )
            logger.debug(
                f"Created user-specific ConfluenceConfig for token starting with {credentials.get('token', credentials.get('oauth_access_token', ''))[:10]}... Resulting auth_type: {user_specific_config.auth_type}"
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
