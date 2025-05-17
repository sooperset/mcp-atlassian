"""Dependency providers for JiraFetcher and ConfluenceFetcher with context awareness.

Provides get_jira_fetcher and get_confluence_fetcher for use in tool functions.
"""

from __future__ import annotations

import dataclasses
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
    from mcp_atlassian.confluence.config import (
        ConfluenceConfig as UserConfluenceConfigType,
    )
    from mcp_atlassian.jira.config import JiraConfig as UserJiraConfigType

logger = logging.getLogger("mcp-atlassian.servers.dependencies")


def _create_user_config_for_fetcher(
    base_config: JiraConfig | ConfluenceConfig,
    auth_type: str,
    credentials: dict[str, Any],
) -> JiraConfig | ConfluenceConfig:
    """Create a user-specific configuration for Jira or Confluence fetchers."""
    if auth_type != "oauth":
        raise ValueError(
            f"Unsupported auth_type '{auth_type}' for user-specific config creation. Expected 'oauth'."
        )

    username_for_config: str | None = credentials.get("user_email_context")

    logger.debug(
        f"Creating user config for fetcher. Auth type: {auth_type}, Credentials keys: {credentials.keys()}"
    )
    user_access_token = credentials.get("oauth_access_token")
    if not user_access_token:
        raise ValueError(
            "OAuth access token missing in credentials for user auth_type 'oauth'"
        )
    if (
        not base_config
        or not hasattr(base_config, "oauth_config")
        or not getattr(base_config, "oauth_config", None)
        or not getattr(getattr(base_config, "oauth_config", None), "cloud_id", None)
    ):
        raise ValueError(
            f"Global OAuth config (with cloud_id) for {type(base_config).__name__} is missing, "
            "but user auth_type is 'oauth'. Cannot determine cloud_id."
        )
    global_oauth_cfg = base_config.oauth_config
    oauth_config_for_user = OAuthConfig(
        client_id=global_oauth_cfg.client_id if global_oauth_cfg else "",
        client_secret=global_oauth_cfg.client_secret if global_oauth_cfg else "",
        redirect_uri=global_oauth_cfg.redirect_uri if global_oauth_cfg else "",
        scope=global_oauth_cfg.scope if global_oauth_cfg else "",
        access_token=user_access_token,
        refresh_token=None,
        expires_at=None,
        cloud_id=global_oauth_cfg.cloud_id if global_oauth_cfg else "",
    )

    common_args: dict[str, Any] = {
        "url": base_config.url,
        "auth_type": auth_type,
        "username": username_for_config,
        "api_token": None,
        "personal_token": None,
        "ssl_verify": base_config.ssl_verify,
        "oauth_config": oauth_config_for_user,
        "http_proxy": base_config.http_proxy,
        "https_proxy": base_config.https_proxy,
        "no_proxy": base_config.no_proxy,
        "socks_proxy": base_config.socks_proxy,
    }

    if isinstance(base_config, JiraConfig):
        user_jira_config: UserJiraConfigType = dataclasses.replace(
            base_config, **common_args
        )
        user_jira_config.projects_filter = base_config.projects_filter
        return user_jira_config
    elif isinstance(base_config, ConfluenceConfig):
        user_confluence_config: UserConfluenceConfigType = dataclasses.replace(
            base_config, **common_args
        )
        user_confluence_config.spaces_filter = base_config.spaces_filter
        return user_confluence_config
    else:
        raise TypeError(f"Unsupported base_config type: {type(base_config)}")


async def get_jira_fetcher(ctx: Context) -> JiraFetcher:
    """Returns a JiraFetcher instance appropriate for the current request context."""
    logger.debug(f"get_jira_fetcher: ENTERED. Context ID: {id(ctx)}")
    try:
        request: Request = get_http_request()
        logger.debug(
            f"get_jira_fetcher: In HTTP request context. Request URL: {request.url}. "
            f"State.jira_fetcher exists: {hasattr(request.state, 'jira_fetcher') and request.state.jira_fetcher is not None}. "
            f"State.user_auth_type: {getattr(request.state, 'user_atlassian_auth_type', 'N/A')}. "
            f"State.user_token_present: {hasattr(request.state, 'user_atlassian_token') and request.state.user_atlassian_token is not None}."
        )
        # Use fetcher from request.state if already present
        if hasattr(request.state, "jira_fetcher") and request.state.jira_fetcher:
            logger.debug("get_jira_fetcher: Returning JiraFetcher from request.state.")
            return request.state.jira_fetcher
        user_auth_type = getattr(request.state, "user_atlassian_auth_type", None)
        logger.debug(f"get_jira_fetcher: User auth type: {user_auth_type}")
        # If OAuth token is present, create user-specific fetcher
        if user_auth_type == "oauth" and hasattr(request.state, "user_atlassian_token"):
            user_token = getattr(request.state, "user_atlassian_token", None)
            user_email = getattr(request.state, "user_atlassian_email", None)
            if not user_token:
                raise ValueError("User Atlassian token found in state but is empty.")
            credentials = {
                "oauth_access_token": user_token,
                "user_email_context": user_email,
            }
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
            logger.info(
                f"Created user-specific JiraFetcher for user {user_email or 'unknown'} (token ...{str(user_token)[-8:]})"
            )
            user_specific_config = _create_user_config_for_fetcher(
                base_config=app_lifespan_ctx.full_jira_config,
                auth_type=user_auth_type,
                credentials=credentials,
            )
            try:
                user_jira_fetcher = JiraFetcher(config=user_specific_config)
                current_user_id = user_jira_fetcher.get_current_user_account_id()
                logger.debug(
                    f"get_jira_fetcher: Validated Jira token for user ID: {current_user_id}"
                )
                request.state.jira_fetcher = user_jira_fetcher
                return user_jira_fetcher
            except Exception as e:
                logger.error(
                    f"get_jira_fetcher: Failed to create/validate user-specific JiraFetcher: {e}",
                    exc_info=True,
                )
                raise ValueError(f"Invalid user Jira token or configuration: {e}")
        else:
            logger.debug(
                "get_jira_fetcher: No user-specific JiraFetcher in request.state and no (or non-OAuth) user token info. Will use global fallback."
            )
    except RuntimeError:
        logger.debug(
            "Not in an HTTP request context. Attempting global JiraFetcher for non-HTTP."
        )
    # Fallback to global fetcher if not in HTTP context or no user info
    lifespan_ctx_dict_global = ctx.request_context.lifespan_context  # type: ignore
    app_lifespan_ctx_global: MainAppContext | None = (
        lifespan_ctx_dict_global.get("app_lifespan_context")
        if isinstance(lifespan_ctx_dict_global, dict)
        else None
    )
    if app_lifespan_ctx_global and app_lifespan_ctx_global.full_jira_config:
        logger.debug(
            "get_jira_fetcher: Using global JiraFetcher from lifespan_context. "
            f"Global config auth_type: {app_lifespan_ctx_global.full_jira_config.auth_type}"
        )
        return JiraFetcher(config=app_lifespan_ctx_global.full_jira_config)
    logger.error("Jira configuration could not be resolved.")
    raise ValueError(
        "Jira client (fetcher) not available. Ensure server is configured correctly."
    )


async def get_confluence_fetcher(ctx: Context) -> ConfluenceFetcher:
    """Returns a ConfluenceFetcher instance appropriate for the current request context."""
    logger.debug(f"get_confluence_fetcher: ENTERED. Context ID: {id(ctx)}")
    try:
        request: Request = get_http_request()
        logger.debug(
            f"get_confluence_fetcher: In HTTP request context. Request URL: {request.url}. "
            f"State.confluence_fetcher exists: {hasattr(request.state, 'confluence_fetcher') and request.state.confluence_fetcher is not None}. "
            f"State.user_auth_type: {getattr(request.state, 'user_atlassian_auth_type', 'N/A')}. "
            f"State.user_token_present: {hasattr(request.state, 'user_atlassian_token') and request.state.user_atlassian_token is not None}."
        )
        if (
            hasattr(request.state, "confluence_fetcher")
            and request.state.confluence_fetcher
        ):
            logger.debug(
                "get_confluence_fetcher: Returning ConfluenceFetcher from request.state."
            )
            return request.state.confluence_fetcher
        user_auth_type = getattr(request.state, "user_atlassian_auth_type", None)
        logger.debug(f"get_confluence_fetcher: User auth type: {user_auth_type}")
        if user_auth_type == "oauth" and hasattr(request.state, "user_atlassian_token"):
            user_token = getattr(request.state, "user_atlassian_token", None)
            user_email = getattr(request.state, "user_atlassian_email", None)
            if not user_token:
                raise ValueError("User Atlassian token found in state but is empty.")
            credentials = {
                "oauth_access_token": user_token,
                "user_email_context": user_email,
            }
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
            logger.info(
                f"Created user-specific ConfluenceFetcher for user {user_email or 'unknown'} (token ...{str(user_token)[-8:]})"
            )
            user_specific_config = _create_user_config_for_fetcher(
                base_config=app_lifespan_ctx.full_confluence_config,
                auth_type=user_auth_type,
                credentials=credentials,
            )
            try:
                user_confluence_fetcher = ConfluenceFetcher(config=user_specific_config)
                current_user_data = user_confluence_fetcher.get_current_user_info()
                logger.debug(
                    f"get_confluence_fetcher: Validated Confluence token for user {user_email or user_confluence_fetcher.config.username}"
                )
                request.state.confluence_fetcher = user_confluence_fetcher
                if (
                    not user_email
                    and current_user_data
                    and isinstance(current_user_data, dict)
                    and current_user_data.get("email")
                ):
                    request.state.user_atlassian_email = current_user_data["email"]
                return user_confluence_fetcher
            except Exception as e:
                logger.error(
                    f"get_confluence_fetcher: Failed to create/validate user-specific ConfluenceFetcher: {e}"
                )
                raise ValueError(f"Invalid user Confluence token or configuration: {e}")
        else:
            logger.debug(
                "get_confluence_fetcher: No user-specific ConfluenceFetcher in request.state and no (or non-OAuth) user token info. Will use global fallback."
            )
    except RuntimeError:
        logger.debug(
            "Not in an HTTP request context. Attempting global ConfluenceFetcher for non-HTTP."
        )
    lifespan_ctx_dict_global = ctx.request_context.lifespan_context  # type: ignore
    app_lifespan_ctx_global: MainAppContext | None = (
        lifespan_ctx_dict_global.get("app_lifespan_context")
        if isinstance(lifespan_ctx_dict_global, dict)
        else None
    )
    if app_lifespan_ctx_global and app_lifespan_ctx_global.full_confluence_config:
        logger.debug(
            "get_confluence_fetcher: Using global ConfluenceFetcher from lifespan_context. "
            f"Global config auth_type: {app_lifespan_ctx_global.full_confluence_config.auth_type}"
        )
        return ConfluenceFetcher(config=app_lifespan_ctx_global.full_confluence_config)
    logger.error("Confluence configuration could not be resolved.")
    raise ValueError(
        "Confluence client (fetcher) not available. Ensure server is configured correctly."
    )
