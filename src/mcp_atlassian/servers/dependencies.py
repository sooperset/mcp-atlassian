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
    cloud_id: str | None = None,
) -> JiraConfig | ConfluenceConfig:
    """Create a user-specific configuration for Jira or Confluence fetchers.

    Args:
        base_config: The base JiraConfig or ConfluenceConfig to clone and modify.
        auth_type: The authentication type ('oauth' or 'pat').
        credentials: Dictionary of credentials (token, email, etc).
        cloud_id: Optional cloud ID to override the base config cloud ID.

    Returns:
        JiraConfig or ConfluenceConfig with user-specific credentials.

    Raises:
        ValueError: If required credentials are missing or auth_type is unsupported.
        TypeError: If base_config is not a supported type.
    """
    if auth_type not in ["oauth", "pat"]:
        raise ValueError(
            f"Unsupported auth_type '{auth_type}' for user-specific config creation. Expected 'oauth' or 'pat'."
        )

    username_for_config: str | None = credentials.get("user_email_context")

    logger.debug(
        f"Creating user config for fetcher. Auth type: {auth_type}, Credentials keys: {credentials.keys()}, Cloud ID: {cloud_id}"
    )

    common_args: dict[str, Any] = {
        "url": base_config.url,
        "auth_type": auth_type,
        "ssl_verify": base_config.ssl_verify,
        "http_proxy": base_config.http_proxy,
        "https_proxy": base_config.https_proxy,
        "no_proxy": base_config.no_proxy,
        "socks_proxy": base_config.socks_proxy,
    }

    if auth_type == "oauth":
        user_access_token = credentials.get("oauth_access_token")
        if not user_access_token:
            raise ValueError(
                "OAuth access token missing in credentials for user auth_type 'oauth'"
            )
        if (
            not base_config
            or not hasattr(base_config, "oauth_config")
            or not getattr(base_config, "oauth_config", None)
        ):
            raise ValueError(
                f"Global OAuth config for {type(base_config).__name__} is missing, "
                "but user auth_type is 'oauth'."
            )
        global_oauth_cfg = base_config.oauth_config

        # Use provided cloud_id or fall back to global config cloud_id
        effective_cloud_id = cloud_id if cloud_id else global_oauth_cfg.cloud_id
        if not effective_cloud_id:
            raise ValueError(
                "Cloud ID is required for OAuth authentication. "
                "Provide it via X-Atlassian-Cloud-Id header or configure it globally."
            )

        # For minimal OAuth config (user-provided tokens), use empty strings for client credentials
        oauth_config_for_user = OAuthConfig(
            client_id=global_oauth_cfg.client_id if global_oauth_cfg.client_id else "",
            client_secret=global_oauth_cfg.client_secret
            if global_oauth_cfg.client_secret
            else "",
            redirect_uri=global_oauth_cfg.redirect_uri
            if global_oauth_cfg.redirect_uri
            else "",
            scope=global_oauth_cfg.scope if global_oauth_cfg.scope else "",
            access_token=user_access_token,
            refresh_token=None,
            expires_at=None,
            cloud_id=effective_cloud_id,
        )
        common_args.update(
            {
                "username": username_for_config,
                "api_token": None,
                "personal_token": None,
                "oauth_config": oauth_config_for_user,
            }
        )
    elif auth_type == "pat":
        user_pat = credentials.get("personal_access_token")
        if not user_pat:
            raise ValueError("PAT missing in credentials for user auth_type 'pat'")

        # Log warning if cloud_id is provided with PAT auth (not typically needed)
        if cloud_id:
            logger.warning(
                f"Cloud ID '{cloud_id}' provided with PAT authentication. "
                "PAT authentication typically uses the base URL directly and doesn't require cloud_id override."
            )

        common_args.update(
            {
                "personal_token": user_pat,
                "oauth_config": None,
                "username": None,
                "api_token": None,
            }
        )

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
    """Returns a JiraFetcher instance appropriate for the current request context.

    Args:
        ctx: The FastMCP context.

    Returns:
        JiraFetcher instance for the current user or global config.

    Raises:
        ValueError: If configuration or credentials are invalid.
    """
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
        # If OAuth or PAT token is present, create user-specific fetcher
        if user_auth_type in ["oauth", "pat"] and hasattr(
            request.state, "user_atlassian_token"
        ):
            user_token = getattr(request.state, "user_atlassian_token", None)
            user_email = getattr(
                request.state, "user_atlassian_email", None
            )  # May be None for PAT
            user_cloud_id = getattr(request.state, "user_atlassian_cloud_id", None)

            if not user_token:
                raise ValueError("User Atlassian token found in state but is empty.")
            credentials = {"user_email_context": user_email}
            if user_auth_type == "oauth":
                credentials["oauth_access_token"] = user_token
            elif user_auth_type == "pat":
                credentials["personal_access_token"] = user_token
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

            cloud_id_info = f" with cloudId {user_cloud_id}" if user_cloud_id else ""
            logger.info(
                f"Creating user-specific JiraFetcher (type: {user_auth_type}) for user {user_email or 'unknown'} (token ...{str(user_token)[-8:]}){cloud_id_info}"
            )
            user_specific_config = _create_user_config_for_fetcher(
                base_config=app_lifespan_ctx.full_jira_config,
                auth_type=user_auth_type,
                credentials=credentials,
                cloud_id=user_cloud_id,
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
                f"get_jira_fetcher: No user-specific JiraFetcher. Auth type: {user_auth_type}. Token present: {hasattr(request.state, 'user_atlassian_token')}. Will use global fallback."
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
    """Returns a ConfluenceFetcher instance appropriate for the current request context.

    Args:
        ctx: The FastMCP context.

    Returns:
        ConfluenceFetcher instance for the current user or global config.

    Raises:
        ValueError: If configuration or credentials are invalid.
    """
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
        if user_auth_type in ["oauth", "pat"] and hasattr(
            request.state, "user_atlassian_token"
        ):
            user_token = getattr(request.state, "user_atlassian_token", None)
            user_email = getattr(request.state, "user_atlassian_email", None)
            user_cloud_id = getattr(request.state, "user_atlassian_cloud_id", None)

            if not user_token:
                raise ValueError("User Atlassian token found in state but is empty.")
            credentials = {"user_email_context": user_email}
            if user_auth_type == "oauth":
                credentials["oauth_access_token"] = user_token
            elif user_auth_type == "pat":
                credentials["personal_access_token"] = user_token
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

            cloud_id_info = f" with cloudId {user_cloud_id}" if user_cloud_id else ""
            logger.info(
                f"Creating user-specific ConfluenceFetcher (type: {user_auth_type}) for user {user_email or 'unknown'} (token ...{str(user_token)[-8:]}){cloud_id_info}"
            )
            user_specific_config = _create_user_config_for_fetcher(
                base_config=app_lifespan_ctx.full_confluence_config,
                auth_type=user_auth_type,
                credentials=credentials,
                cloud_id=user_cloud_id,
            )
            try:
                user_confluence_fetcher = ConfluenceFetcher(config=user_specific_config)
                current_user_data = user_confluence_fetcher.get_current_user_info()
                # Try to get email from Confluence if not provided (can happen with PAT)
                derived_email = (
                    current_user_data.get("email")
                    if isinstance(current_user_data, dict)
                    else None
                )
                display_name = (
                    current_user_data.get("displayName")
                    if isinstance(current_user_data, dict)
                    else None
                )
                logger.debug(
                    f"get_confluence_fetcher: Validated Confluence token. User context: Email='{user_email or derived_email}', DisplayName='{display_name}'"
                )
                request.state.confluence_fetcher = user_confluence_fetcher
                if (
                    not user_email
                    and derived_email
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
                f"get_confluence_fetcher: No user-specific ConfluenceFetcher. Auth type: {user_auth_type}. Token present: {hasattr(request.state, 'user_atlassian_token')}. Will use global fallback."
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
