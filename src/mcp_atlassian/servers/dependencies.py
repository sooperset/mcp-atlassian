"""Dependency providers for JiraFetcher and ConfluenceFetcher with context awareness.

Provides get_jira_fetcher and get_confluence_fetcher for use in tool functions.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import os
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from cachetools import TTLCache
from fastmcp import Context
from fastmcp.server.dependencies import get_access_token, get_http_request
from starlette.requests import Request

from mcp_atlassian.confluence import ConfluenceConfig, ConfluenceFetcher
from mcp_atlassian.jira import JiraConfig, JiraFetcher
from mcp_atlassian.servers.context import MainAppContext
from mcp_atlassian.utils.env import (
    get_header_names,
    is_env_ssl_verify,
    is_env_truthy,
)
from mcp_atlassian.utils.oauth import OAuthConfig
from mcp_atlassian.utils.proxy import get_proxy_settings_from_env
from mcp_atlassian.utils.urls import validate_url_for_ssrf

if TYPE_CHECKING:
    from mcp_atlassian.confluence.config import (
        ConfluenceConfig as UserConfluenceConfigType,
    )
    from mcp_atlassian.jira.config import JiraConfig as UserJiraConfigType

logger = logging.getLogger("mcp-atlassian.servers.dependencies")


# ---------------------------------------------------------------------------
# Service specification for generic fetcher resolution
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _ServiceSpec:
    """Per-service parameters for the generic fetcher dependency logic."""

    name: str  # "Jira" or "Confluence"
    fetcher_class: type  # JiraFetcher / ConfluenceFetcher
    config_class: type  # JiraConfig / ConfluenceConfig
    state_key: str  # request.state attribute for caching
    config_attr: str  # MainAppContext attribute for global config
    url_header: str  # X-Atlassian-{Service}-Url
    token_header: str  # X-Atlassian-{Service}-Personal-Token
    passthrough_env_var: str  # {SERVICE}_PASSTHROUGH_HEADERS
    filter_kwargs: dict[str, Any]  # e.g. {"projects_filter": None}
    get_session: Callable[[Any], Any]  # fetcher → session
    validate_fn: Callable[[Any], Any]  # fetcher → validation data
    on_validated: Callable[
        [str, Request, Any, str, str | None], None
    ]  # logging + email backfill


# ---------------------------------------------------------------------------
# Cross-request credential validation cache (#1405)
#
# In multi-user HTTP transport, every request builds a fresh fetcher on
# request.state, so credential validation (a network call to Atlassian) was
# firing once per request instead of once per credential. This cache dedupes
# that call across requests for the configured TTL. Only a SHA-256 digest of
# the credential AND effective validation target is ever used as a key -- raw
# tokens are never stored. Header-based PAT auth uses a per-request base URL,
# while Cloud OAuth uses the tenant-specific Cloud ID rather than its fixed
# configured URL.
# ---------------------------------------------------------------------------


def _validation_cache_ttl() -> int:
    """TTL in seconds for cached validation results. 0 disables the cache."""
    try:
        return int(os.getenv("MCP_ATLASSIAN_VALIDATION_CACHE_TTL", "300"))
    except ValueError:
        return 300


def _validation_cache_maxsize() -> int:
    try:
        return int(os.getenv("MCP_ATLASSIAN_VALIDATION_CACHE_MAXSIZE", "100"))
    except ValueError:
        return 100


_CACHE_TTL = _validation_cache_ttl()
_CACHE_MAXSIZE = _validation_cache_maxsize()
_validation_cache: TTLCache[tuple[str, str], Any] | None = (
    TTLCache(maxsize=_CACHE_MAXSIZE, ttl=_CACHE_TTL)
    if _CACHE_TTL > 0 and _CACHE_MAXSIZE > 0
    else None
)
_CACHE_MISS = object()  # sentinel distinguishing "not cached" from a cached None
_validation_cache_lock = threading.RLock()


@dataclasses.dataclass
class _ValidationInFlight:
    """Coordinate concurrent validation calls for one cache key."""

    event: threading.Event = dataclasses.field(default_factory=threading.Event)
    validation_data: Any = _CACHE_MISS
    error: BaseException | None = None


_validation_inflight: dict[tuple[str, str], _ValidationInFlight] = {}


def _credential_for_cache(config: JiraConfig | ConfluenceConfig) -> str | None:
    """Extract the secret that authenticates ``config``, for cache-key hashing.

    Returns None when no credential-bearing field is set, so the caller can
    skip caching rather than key on an empty/ambiguous value.
    """
    if config.auth_type == "oauth":
        oauth_cfg = getattr(config, "oauth_config", None)
        return getattr(oauth_cfg, "access_token", None) if oauth_cfg else None
    if config.auth_type == "pat":
        return config.personal_token
    if config.auth_type == "basic":
        if not config.api_token:
            return None
        # Username + token together identify the credential; a token reused
        # under a different username should still validate independently.
        return f"{getattr(config, 'username', '') or ''}:{config.api_token}"
    return None


def _validation_cache_key(
    spec: _ServiceSpec, credential: str, scope: str
) -> tuple[str, str]:
    """Build the cache key, scoped to both the credential and target.

    Header-based PAT auth accepts the base URL per-request (from
    X-Atlassian-*-Url), so the same credential string reused against a
    different instance must not share a cached validation result.
    """
    digest = hashlib.sha256(f"{scope}\x00{credential}".encode()).hexdigest()
    return (spec.name, digest)


def _validation_cache_scope(config: JiraConfig | ConfluenceConfig) -> str:
    """Return the target identity to include in a validation cache key.

    Cloud OAuth requests share the same API hostname, so the configured URL
    does not identify the tenant. Use the effective Cloud ID for Cloud OAuth,
    the OAuth base URL for Data Center OAuth, and the configured URL for other
    authentication modes.
    """
    oauth_config = getattr(config, "oauth_config", None)
    cloud_id = getattr(oauth_config, "cloud_id", None)
    oauth_base_url = getattr(oauth_config, "base_url", None)
    if config.auth_type == "oauth" and isinstance(cloud_id, str) and cloud_id:
        return f"cloud-oauth\x00{cloud_id}"
    if config.auth_type == "oauth" and isinstance(oauth_base_url, str):
        return f"dc-oauth\x00{oauth_base_url}"
    url = getattr(config, "url", "")
    return f"url\x00{url if isinstance(url, str) else ''}"


def _passthrough_cache_scope(passthrough_headers: dict[str, str]) -> str:
    """Hash the effective passthrough headers for validation cache scoping.

    Passthrough headers can identify the user even when the Atlassian token is
    shared. Keep their values out of the cache itself and out of logs by using
    only a stable digest of the normalized header names and values.
    """
    normalized_headers = sorted(
        (header_name.lower(), header_value)
        for header_name, header_value in passthrough_headers.items()
    )
    header_material = "\x00".join(
        f"{header_name}\x00{header_value}"
        for header_name, header_value in normalized_headers
    )
    return hashlib.sha256(header_material.encode()).hexdigest()


def _validate_with_cache(
    cache_key: tuple[str, str],
    validation_cache: TTLCache[tuple[str, str], Any],
    validate_fn: Callable[[], Any],
    fn_name: str,
    service_name: str,
) -> Any:
    """Return cached validation data or run one validation per cache key.

    The process-wide lock protects only cache and in-flight bookkeeping. The
    network validation runs outside it, allowing unrelated credentials to
    validate concurrently while callers for the same key share one result.
    """
    with _validation_cache_lock:
        cached_validation = validation_cache.get(cache_key, _CACHE_MISS)
        if cached_validation is not _CACHE_MISS:
            logger.debug(
                f"{fn_name}: Reusing cached {service_name} credential "
                "validation (skipped network call)."
            )
            return cached_validation

        in_flight = _validation_inflight.get(cache_key)
        if in_flight is None:
            in_flight = _ValidationInFlight()
            _validation_inflight[cache_key] = in_flight
            owns_validation = True
        else:
            owns_validation = False

    if not owns_validation:
        in_flight.event.wait()
        if in_flight.error is not None:
            raise in_flight.error
        return in_flight.validation_data

    try:
        validation_data = validate_fn()
    except BaseException as error:
        with _validation_cache_lock:
            in_flight.error = error
            _validation_inflight.pop(cache_key, None)
            in_flight.event.set()
        raise

    with _validation_cache_lock:
        validation_cache[cache_key] = validation_data
        in_flight.validation_data = validation_data
        _validation_inflight.pop(cache_key, None)
        in_flight.event.set()
    return validation_data


def _jira_on_validated(
    fn_name: str,
    request: Request,
    validation_data: Any,
    auth_branch: str,
    user_email: str | None,
) -> None:
    """Post-validation logging for Jira (user ID only)."""
    if auth_branch == "header_pat":
        logger.debug(
            f"{fn_name}: Validated header-based Jira token "
            f"for user ID: {validation_data}"
        )
    elif auth_branch == "basic":
        logger.debug(
            f"{fn_name}: Validated Jira basic auth for user ID: {validation_data}"
        )
    else:  # oauth_pat
        logger.debug(f"{fn_name}: Validated Jira token for user ID: {validation_data}")


def _confluence_on_validated(
    fn_name: str,
    request: Request,
    validation_data: Any,
    auth_branch: str,
    user_email: str | None,
) -> None:
    """Post-validation logging + email backfill for Confluence."""
    derived_email = (
        validation_data.get("email") if isinstance(validation_data, dict) else None
    )
    display_name = (
        validation_data.get("displayName")
        if isinstance(validation_data, dict)
        else None
    )
    if auth_branch == "header_pat":
        logger.debug(
            f"{fn_name}: Validated header-based Confluence token. "
            f"User context: Email='{derived_email}', "
            f"DisplayName='{display_name}'"
        )
        # Always backfill email in PAT header branch
        if derived_email and validation_data and isinstance(validation_data, dict):
            request.state.user_atlassian_email = validation_data["email"]
    elif auth_branch == "basic":
        logger.debug(
            f"{fn_name}: Validated basic auth. "
            f"User: {user_email}, DisplayName='{display_name}'"
        )
    else:  # oauth_pat
        logger.debug(
            f"{fn_name}: Validated Confluence token. "
            f"User context: "
            f"Email='{user_email or derived_email}', "
            f"DisplayName='{display_name}'"
        )
        # Backfill only when email not already known
        if (
            not user_email
            and derived_email
            and validation_data
            and isinstance(validation_data, dict)
            and validation_data.get("email")
        ):
            request.state.user_atlassian_email = validation_data["email"]


def _jira_spec() -> _ServiceSpec:
    """Build Jira service spec.

    Deferred to a function so test patches on ``JiraFetcher`` / ``JiraConfig``
    are picked up at call time rather than at module import time.
    """
    return _ServiceSpec(
        name="Jira",
        fetcher_class=JiraFetcher,
        config_class=JiraConfig,
        state_key="jira_fetcher",
        config_attr="full_jira_config",
        url_header="X-Atlassian-Jira-Url",
        token_header="X-Atlassian-Jira-Personal-Token",  # noqa: S106
        passthrough_env_var="JIRA_PASSTHROUGH_HEADERS",
        filter_kwargs={"projects_filter": None},
        get_session=lambda f: f.jira._session,
        validate_fn=lambda f: f.get_current_user_account_id(),
        on_validated=_jira_on_validated,
    )


def _confluence_spec() -> _ServiceSpec:
    """Build Confluence service spec.

    Deferred to a function so test patches on ``ConfluenceFetcher`` /
    ``ConfluenceConfig`` are picked up at call time.
    """
    return _ServiceSpec(
        name="Confluence",
        fetcher_class=ConfluenceFetcher,
        config_class=ConfluenceConfig,
        state_key="confluence_fetcher",
        config_attr="full_confluence_config",
        url_header="X-Atlassian-Confluence-Url",
        token_header="X-Atlassian-Confluence-Personal-Token",  # noqa: S106
        passthrough_env_var="CONFLUENCE_PASSTHROUGH_HEADERS",
        filter_kwargs={"spaces_filter": None},
        get_session=lambda f: f.confluence._session,
        validate_fn=lambda f: f.get_current_user_info(),
        on_validated=_confluence_on_validated,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_app_lifespan_ctx(ctx: Context) -> MainAppContext | None:
    """Extract MainAppContext from FastMCP lifespan context."""
    lifespan_ctx_dict = ctx.request_context.lifespan_context  # type: ignore
    return (
        lifespan_ctx_dict.get("app_lifespan_context")
        if isinstance(lifespan_ctx_dict, dict)
        else None
    )


def _get_global_config(
    ctx: Context, spec: _ServiceSpec
) -> JiraConfig | ConfluenceConfig:
    """Get global config from lifespan context.

    Raises:
        ValueError: If the global config is not available.
    """
    app_ctx = _get_app_lifespan_ctx(ctx)
    config = getattr(app_ctx, spec.config_attr, None) if app_ctx else None
    if not config:
        raise ValueError(
            f"{spec.name} global configuration (URL, SSL) is not "
            "available from lifespan context."
        )
    return config


def _get_passthrough_header_names(config: Any, spec: _ServiceSpec) -> list[str]:
    configured_names = getattr(config, "passthrough_headers", None)
    if configured_names is not None:
        return configured_names
    return get_header_names(spec.passthrough_env_var)


def _get_request_passthrough_headers(
    request: Request, spec: _ServiceSpec, config: Any
) -> dict[str, str]:
    request_headers = getattr(request, "headers", None)
    if request_headers is None:
        return {}

    passthrough_headers: dict[str, str] = {}
    for header_name in _get_passthrough_header_names(config, spec):
        header_value = request_headers.get(header_name)
        if header_value is not None:
            passthrough_headers[header_name] = header_value

    if passthrough_headers:
        logger.debug(
            "Forwarding %d passthrough headers to %s: %s",
            len(passthrough_headers),
            spec.name,
            list(passthrough_headers.keys()),
        )
    return passthrough_headers


def _merge_passthrough_headers(
    custom_headers: dict[str, str] | None, passthrough_headers: dict[str, str]
) -> dict[str, str]:
    merged_headers = dict(custom_headers or {})
    passthrough_names = {name.lower() for name in passthrough_headers}
    for header_name in list(merged_headers):
        if header_name.lower() in passthrough_names:
            del merged_headers[header_name]
    merged_headers.update(passthrough_headers)
    return merged_headers


def _with_request_passthrough_headers(
    request: Request,
    spec: _ServiceSpec,
    config: Any,
    passthrough_headers: dict[str, str] | None = None,
) -> Any:
    if passthrough_headers is None:
        passthrough_headers = _get_request_passthrough_headers(request, spec, config)
    if not passthrough_headers:
        return config

    custom_headers = _merge_passthrough_headers(
        getattr(config, "custom_headers", None), passthrough_headers
    )
    return dataclasses.replace(config, custom_headers=custom_headers)


def _get_header_pat_network_config(ctx: Context, spec: _ServiceSpec) -> dict[str, Any]:
    """Resolve operator-controlled network settings for header PAT requests.

    Args:
        ctx: FastMCP request context.
        spec: Service specification for Jira or Confluence.

    Returns:
        SSL and proxy settings from the global config when available, otherwise
        from service-specific or shared environment variables.
    """
    try:
        global_config = _get_global_config(ctx, spec)
    except ValueError:
        env_prefix = spec.name.upper()
        proxy_settings = get_proxy_settings_from_env(env_prefix)
        return {
            "ssl_verify": is_env_ssl_verify(f"{env_prefix}_SSL_VERIFY"),
            **proxy_settings,
        }

    return {
        "ssl_verify": global_config.ssl_verify,
        "http_proxy": global_config.http_proxy,
        "https_proxy": global_config.https_proxy,
        "no_proxy": global_config.no_proxy,
        "socks_proxy": global_config.socks_proxy,
        "proxy_wpad_enable": global_config.proxy_wpad_enable,
        "proxy_wpad_url": global_config.proxy_wpad_url,
    }


def _create_and_validate(
    request: Request,
    spec: _ServiceSpec,
    config: Any,
    auth_branch: str,
    user_email: str | None = None,
    *,
    attach_ssrf_hook: bool = False,
) -> Any:
    """Create a fetcher, validate credentials, cache on request.state.

    The validation network call itself is deduped across requests for the
    same credential via ``_validation_cache`` (#1405) -- only fetcher
    construction and ``request.state`` caching happen per-request.

    Args:
        request: The current Starlette request.
        spec: Service specification.
        config: Service-specific config instance.
        auth_branch: One of "header_pat", "basic", "oauth_pat".
        user_email: User email from request state (for logging).
        attach_ssrf_hook: Whether to attach SSRF redirect hook.

    Returns:
        Validated fetcher instance.

    Raises:
        ValueError: On validation or creation failure.
    """
    fn_name = f"get_{spec.name.lower()}_fetcher"
    auth_desc = "header-based" if auth_branch == "header_pat" else "user"
    try:
        request_passthrough_headers = _get_request_passthrough_headers(
            request, spec, config
        )
        config = _with_request_passthrough_headers(
            request,
            spec,
            config,
            request_passthrough_headers,
        )
        credential = _credential_for_cache(config)
        cache_scope = _validation_cache_scope(config)
        if request_passthrough_headers:
            cache_scope = (
                f"{cache_scope}\x00passthrough\x00"
                f"{_passthrough_cache_scope(request_passthrough_headers)}"
            )
        cache_key = (
            _validation_cache_key(spec, credential, cache_scope)
            if credential and _validation_cache is not None
            else None
        )
        fetcher = spec.fetcher_class(config=config)
        if attach_ssrf_hook:
            session = spec.get_session(fetcher)
            session.hooks["response"].append(
                _make_ssrf_safe_hook(validate_url_for_ssrf)
            )
        validation_cache = _validation_cache
        if cache_key is not None and validation_cache is not None:
            validation_data = _validate_with_cache(
                cache_key,
                validation_cache,
                lambda: spec.validate_fn(fetcher),
                fn_name,
                spec.name,
            )
        else:
            validation_data = spec.validate_fn(fetcher)
        spec.on_validated(
            fn_name,
            request,
            validation_data,
            auth_branch,
            user_email,
        )
        setattr(request.state, spec.state_key, fetcher)
        return fetcher
    except Exception as e:
        logger.error(
            f"{fn_name}: Failed to create/validate {auth_desc} {spec.name}Fetcher: {e}",
            exc_info=True,
        )
        raise ValueError(f"Invalid {auth_desc} {spec.name} token or configuration: {e}")


def _resolve_oauth_access_token(fallback_token: str, service: str) -> str:
    """Resolve upstream OAuth token from FastMCP auth context with safe fallback."""
    try:
        access_token = get_access_token()
    except (RuntimeError, LookupError) as e:
        logger.debug(
            "OAuth token resolution via FastMCP context failed for %s; "
            "using request token (%s)",
            service,
            e,
        )
        return fallback_token

    if access_token and access_token.token:
        if access_token.token != fallback_token:
            logger.debug(
                "Resolved upstream %s token from FastMCP auth context", service
            )
        return access_token.token

    return fallback_token


def _make_ssrf_safe_hook(
    validate_fn: Callable[[str], str | None],
) -> Callable[..., Any]:
    """Create a requests response hook that validates redirect URLs.

    Blocks HTTP redirects that target internal/private IP addresses
    to prevent SSRF via open-redirect chains.

    Args:
        validate_fn: A function that returns None if safe,
            error string if blocked.

    Returns:
        A requests response hook function.
    """

    def hook(response: Any, **kwargs: Any) -> Any:
        if response.is_redirect:
            redirect_url = response.headers.get("Location", "")
            error = validate_fn(redirect_url)
            if error:
                response.close()
                raise ValueError(f"Redirect blocked (SSRF): {error}")
        return response

    return hook


def _resolve_bearer_auth_type(
    base_config: JiraConfig | ConfluenceConfig,
    middleware_auth_type: str,
    cloud_id: str | None = None,
) -> str:
    """Disambiguate Bearer tokens: determine if they're OAuth or PAT.

    The middleware treats all ``Bearer`` tokens as ``auth_type="oauth"`` because
    it is stateless.  The dependency layer has access to the global config and can
    make a better decision:

    * If the global config has OAuth configured (cloud_id or DC base_url) → keep "oauth"
    * Otherwise → fall back to "pat" (Server/DC Bearer-prefixed PAT)

    Args:
        base_config: The global JiraConfig or ConfluenceConfig.
        middleware_auth_type: The auth_type set by the middleware ("oauth" or "pat").
        cloud_id: Optional per-request cloud_id from headers.

    Returns:
        The resolved auth_type ("oauth" or "pat").
    """
    if middleware_auth_type != "oauth":
        return middleware_auth_type

    # Per-request cloud_id header means the client intends Cloud OAuth
    if cloud_id:
        return "oauth"

    # Check if global config has OAuth set up
    global_oauth = getattr(base_config, "oauth_config", None)
    if global_oauth is not None:
        # Has cloud_id → Cloud OAuth
        if global_oauth.cloud_id:
            return "oauth"
        # Has DC base_url → DC OAuth
        if getattr(global_oauth, "is_data_center", False) is True:
            return "oauth"

    # No OAuth config globally → Bearer token is actually a PAT
    logger.info(
        "Bearer token received but no OAuth config found globally. "
        "Treating as PAT for Server/Data Center."
    )
    return "pat"


def _create_user_config_for_fetcher(
    base_config: JiraConfig | ConfluenceConfig,
    auth_type: str,
    credentials: dict[str, Any],
    cloud_id: str | None = None,
) -> JiraConfig | ConfluenceConfig:
    """Create a user-specific configuration for Jira or Confluence fetchers.

    Args:
        base_config: The base JiraConfig or ConfluenceConfig to clone and modify.
        auth_type: The authentication type ('oauth', 'pat', or 'basic').
        credentials: Dictionary of credentials (token, email, etc).
        cloud_id: Optional cloud ID to override the base config cloud ID.

    Returns:
        JiraConfig or ConfluenceConfig with user-specific credentials.

    Raises:
        ValueError: If required credentials are missing or auth_type is unsupported.
        TypeError: If base_config is not a supported type.
    """
    if auth_type not in ["oauth", "pat", "basic"]:
        raise ValueError(
            f"Unsupported auth_type '{auth_type}' for user-specific config creation. Expected 'oauth', 'pat', or 'basic'."
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
        "proxy_wpad_enable": base_config.proxy_wpad_enable,
        "proxy_wpad_url": base_config.proxy_wpad_url,
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

        # Determine if this is DC OAuth (base_url set, no cloud_id)
        is_dc_oauth = getattr(global_oauth_cfg, "is_data_center", False) is True

        # Use provided cloud_id or fall back to global config cloud_id
        effective_cloud_id = cloud_id if cloud_id else global_oauth_cfg.cloud_id
        effective_base_url = (
            getattr(global_oauth_cfg, "base_url", None) if is_dc_oauth else None
        )

        if not effective_cloud_id and not effective_base_url:
            raise ValueError(
                "Cloud ID or Data Center base URL is required for OAuth authentication. "
                "Provide cloud_id via X-Atlassian-Cloud-Id header or configure it globally, "
                "or set base_url for Data Center OAuth."
            )

        # Minimal OAuth config (user-provided tokens): client credentials fall back
        # to empty strings. The global oauth_config may be a
        # BYOAccessTokenOAuthConfig (e.g. a placeholder *_OAUTH_ACCESS_TOKEN set to
        # suppress the headless OAuth setup flow), which has no
        # client_id/client_secret/redirect_uri/scope attributes. With the OAuth proxy
        # active these come from the proxy config, not here, so getattr() with an
        # empty-string fallback is safe and avoids an AttributeError.
        oauth_config_for_user = OAuthConfig(
            client_id=getattr(global_oauth_cfg, "client_id", "") or "",
            client_secret=getattr(global_oauth_cfg, "client_secret", "") or "",
            redirect_uri=getattr(global_oauth_cfg, "redirect_uri", "") or "",
            scope=getattr(global_oauth_cfg, "scope", "") or "",
            access_token=user_access_token,
            refresh_token=None,
            expires_at=None,
            cloud_id=effective_cloud_id if not is_dc_oauth else None,
            base_url=effective_base_url,
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
    elif auth_type == "basic":
        user_email = credentials.get("user_email")
        user_api_token = credentials.get("api_token")
        if not user_email or not user_api_token:
            raise ValueError(
                "Email and API token missing in credentials for user auth_type 'basic'"
            )

        common_args.update(
            {
                "username": user_email,
                "api_token": user_api_token,
                "personal_token": None,
                "oauth_config": None,
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


async def _get_fetcher(ctx: Context, spec: _ServiceSpec) -> Any:
    """Generic fetcher resolution for both Jira and Confluence.

    Handles header-based PAT, basic auth, OAuth/PAT, and global fallback.
    """
    fn_name = f"get_{spec.name.lower()}_fetcher"
    logger.debug(f"{fn_name}: ENTERED. Context ID: {id(ctx)}")
    request: Request | None = None
    in_http_context = False
    try:
        request = get_http_request()
        in_http_context = True
        logger.debug(
            f"{fn_name}: In HTTP request context. "
            f"Request URL: {request.url}. "
            f"State.{spec.state_key} exists: "
            f"{hasattr(request.state, spec.state_key) and getattr(request.state, spec.state_key) is not None}. "
            f"State.user_auth_type: "
            f"{getattr(request.state, 'user_atlassian_auth_type', 'N/A')}. "
            f"State.user_token_present: "
            f"{hasattr(request.state, 'user_atlassian_token') and request.state.user_atlassian_token is not None}."
        )
        # Use fetcher from request.state if already present
        cached = getattr(request.state, spec.state_key, None)
        if cached:
            logger.debug(f"{fn_name}: Returning {spec.name}Fetcher from request.state.")
            return cached
        user_auth_type = getattr(request.state, "user_atlassian_auth_type", None)
        logger.debug(f"{fn_name}: User auth type: {user_auth_type}")

        service_headers = getattr(request.state, "atlassian_service_headers", {})
        url_header_val = service_headers.get(spec.url_header)
        token_header_val = service_headers.get(spec.token_header)

        # --- Branch 1: header-based PAT ---
        if (
            user_auth_type == "pat"
            and url_header_val
            and token_header_val
            and not hasattr(request.state, "user_atlassian_token")
        ):
            logger.info(
                f"Creating header-based {spec.name}Fetcher "
                f"with URL: {url_header_val} and PAT token"
            )
            header_config = spec.config_class(
                url=url_header_val,
                auth_type="pat",
                personal_token=token_header_val,
                **_get_header_pat_network_config(ctx, spec),
                # Never forward instance-specific custom headers to a URL
                # selected per request.
                custom_headers=None,
                passthrough_headers=get_header_names(spec.passthrough_env_var),
                **spec.filter_kwargs,
            )
            return _create_and_validate(
                request,
                spec,
                header_config,
                "header_pat",
                attach_ssrf_hook=True,
            )

        # --- Branch 2: basic auth ---
        elif user_auth_type == "basic":
            user_email = getattr(request.state, "user_atlassian_email", None)
            user_api_token = getattr(request.state, "user_atlassian_api_token", None)

            if not user_email or not user_api_token:
                raise ValueError("User email or API token missing for basic auth.")

            global_config = _get_global_config(ctx, spec)
            credentials = {
                "user_email_context": user_email,
                "user_email": user_email,
                "api_token": user_api_token,
            }
            logger.info(
                f"Creating user-specific {spec.name}Fetcher "
                f"(type: basic) for user {user_email}"
            )
            user_config = _create_user_config_for_fetcher(
                base_config=global_config,
                auth_type="basic",
                credentials=credentials,
            )
            return _create_and_validate(
                request,
                spec,
                user_config,
                "basic",
                user_email=user_email,
                attach_ssrf_hook=True,
            )

        # --- Branch 3: OAuth / PAT with token ---
        elif user_auth_type in ["oauth", "pat"] and hasattr(
            request.state, "user_atlassian_token"
        ):
            user_token = getattr(request.state, "user_atlassian_token", None)
            user_email = getattr(request.state, "user_atlassian_email", None)
            user_cloud_id = getattr(request.state, "user_atlassian_cloud_id", None)

            if not user_token:
                raise ValueError("User Atlassian token found in state but is empty.")

            global_config = _get_global_config(ctx, spec)

            # Disambiguate Bearer tokens: OAuth vs PAT (#892)
            resolved_auth_type = _resolve_bearer_auth_type(
                global_config, user_auth_type, user_cloud_id
            )

            credentials = {
                "user_email_context": user_email,
            }
            if resolved_auth_type == "oauth":
                credentials["oauth_access_token"] = _resolve_oauth_access_token(
                    user_token, spec.name
                )
            else:
                credentials["personal_access_token"] = user_token

            cloud_id_info = f" with cloudId {user_cloud_id}" if user_cloud_id else ""
            logger.info(
                f"Creating user-specific {spec.name}Fetcher "
                f"(type: {resolved_auth_type}) for user "
                f"{user_email or 'unknown'} "
                f"(token ...<redacted>){cloud_id_info}"
            )
            user_config = _create_user_config_for_fetcher(
                base_config=global_config,
                auth_type=resolved_auth_type,
                credentials=credentials,
                cloud_id=user_cloud_id,
            )
            return _create_and_validate(
                request,
                spec,
                user_config,
                "oauth_pat",
                user_email=user_email,
                attach_ssrf_hook=True,
            )

        else:
            logger.debug(
                f"{fn_name}: No user-specific {spec.name}Fetcher. "
                f"Auth type: {user_auth_type}. "
                f"Token present: "
                f"{hasattr(request.state, 'user_atlassian_token')}. "
                "Will use global fallback."
            )
    except RuntimeError:
        logger.debug(
            "Not in an HTTP request context. "
            f"Attempting global {spec.name}Fetcher for non-HTTP."
        )

    # Fallback to global fetcher
    app_ctx = _get_app_lifespan_ctx(ctx)
    global_config_fallback = (
        getattr(app_ctx, spec.config_attr, None) if app_ctx else None
    )
    if global_config_fallback:
        # An HTTP request that reaches here has no per-user identity: serving it
        # with the operator's global credentials lets any unauthenticated caller
        # transact as the operator. Refuse unless explicitly opted in. Non-HTTP
        # (stdio, single-user) is unaffected — the operator is the user there.
        if (
            in_http_context
            and global_config_fallback.auth_type != "external"
            and not is_env_truthy("ALLOW_GLOBAL_CRED_FALLBACK")
        ):
            raise ValueError(
                f"{spec.name} client (fetcher) not available: refusing to serve an "
                "unauthenticated request with the operator's global credentials. "
                "Provide a user token, or set ALLOW_GLOBAL_CRED_FALLBACK=true to "
                "allow the global-credential fallback (single-user deployments only)."
            )
        logger.debug(
            f"{fn_name}: Using global {spec.name}Fetcher "
            "from lifespan_context. "
            f"Global config auth_type: "
            f"{global_config_fallback.auth_type}"
        )
        if request is not None:
            # Per-request URL override for external auth mode when no URL is
            # configured server-side (URL is supplied via request header instead).
            if (
                global_config_fallback.auth_type == "external"
                and not global_config_fallback.url
            ):
                url_from_header = request.headers.get(spec.url_header)
                if url_from_header:
                    if not os.getenv("MCP_ALLOWED_URL_DOMAINS", "").strip():
                        error_msg = (
                            f"Dynamic {spec.name} URLs in external auth mode require "
                            "MCP_ALLOWED_URL_DOMAINS to prevent passthrough credential "
                            "exfiltration."
                        )
                        raise ValueError(error_msg)
                    ssrf_error = validate_url_for_ssrf(url_from_header)
                    if ssrf_error:
                        error_msg = f"Forbidden: Invalid {spec.name} URL - {ssrf_error}"
                        raise ValueError(error_msg)
                    logger.debug(
                        f"{fn_name}: Using per-request {spec.name} URL "
                        f"from {spec.url_header} header: {url_from_header}"
                    )
                    global_config_fallback = dataclasses.replace(
                        global_config_fallback, url=url_from_header
                    )
                else:
                    error_msg = (
                        f"{spec.name} URL is not configured. "
                        f"Set {spec.url_header} header or configure the "
                        f"{spec.name.upper()}_URL environment variable."
                    )
                    raise ValueError(error_msg)
            global_config_fallback = _with_request_passthrough_headers(
                request, spec, global_config_fallback
            )
        return spec.fetcher_class(config=global_config_fallback)

    logger.error(f"{spec.name} configuration could not be resolved.")
    raise ValueError(
        f"{spec.name} client (fetcher) not available. "
        "Ensure server is configured correctly."
    )


async def get_jira_fetcher(ctx: Context) -> JiraFetcher:
    """Returns a JiraFetcher instance appropriate for the current request context.

    Args:
        ctx: The FastMCP context.

    Returns:
        JiraFetcher instance for the current user or global config.

    Raises:
        ValueError: If configuration or credentials are invalid.
    """
    return await _get_fetcher(ctx, _jira_spec())


async def get_confluence_fetcher(ctx: Context) -> ConfluenceFetcher:
    """Returns a ConfluenceFetcher instance appropriate for the current request context.

    Args:
        ctx: The FastMCP context.

    Returns:
        ConfluenceFetcher instance for the current user or global config.

    Raises:
        ValueError: If configuration or credentials are invalid.
    """
    return await _get_fetcher(ctx, _confluence_spec())
