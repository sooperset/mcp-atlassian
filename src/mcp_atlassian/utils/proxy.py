"""Shared proxy utilities for Jira and Confluence clients."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

from requests import Session
from requests.utils import should_bypass_proxies

try:
    from pypac import PACSession, get_pac
    from pypac.parser import MalformedPacError
except ImportError:  # pragma: no cover - exercised without the wpad extra
    PACSession = Session  # type: ignore[assignment,misc]
    get_pac: Any = None  # type: ignore[no-redef]

    class MalformedPacError(ValueError):  # type: ignore[no-redef]
        """Fallback exception when the optional PAC dependency is unavailable."""


from .env import is_env_truthy
from .logging import log_config_param

DEFAULT_PROXY_WPAD_URL = "http://wpad/wpad.dat"
PAC_ALLOWED_CONTENT_TYPES = (
    "application/x-ns-proxy-autoconfig",
    "application/x-javascript-config",
    "application/x-javascript",
    "text/plain",
)
PAC_FETCH_TIMEOUT_SECONDS = 10


class ProxyConfigProtocol(Protocol):
    """Shared proxy settings used by Jira and Confluence configs."""

    http_proxy: str | None
    https_proxy: str | None
    no_proxy: str | None
    socks_proxy: str | None
    proxy_wpad_enable: bool
    proxy_wpad_url: str | None


class _NoProxyAwarePACSession(PACSession):  # type: ignore[misc]
    """PAC-enabled session that preserves explicit NO_PROXY bypasses."""

    def __init__(self, pac: Any, no_proxy: str | None) -> None:
        super().__init__(pac=pac)
        self._no_proxy = no_proxy

    def request(
        self,
        method: str,
        url: str,
        proxies: Any = None,
        **kwargs: Any,
    ) -> Any:
        if (
            self._no_proxy
            and not proxies
            and should_bypass_proxies(url, no_proxy=self._no_proxy)
        ):
            proxies = {"http": None, "https": None}
        return super().request(method, url, proxies=proxies, **kwargs)


@lru_cache(maxsize=16)
def _load_pac_file(
    pac_url: str,
    *,
    verify: bool | str,
    cert: str | tuple[str, str] | None,
    trust_env: bool,
) -> Any:
    """Load and cache a PAC file for later session reuse."""
    if get_pac is None:
        msg = (
            "PAC/WPAD support requires the optional 'wpad' dependency; "
            "install mcp-atlassian[wpad] to enable it"
        )
        raise ValueError(msg)

    bootstrap_session = Session()
    bootstrap_session.verify = verify
    bootstrap_session.cert = cert
    bootstrap_session.trust_env = trust_env

    pac = get_pac(
        url=pac_url,
        session=bootstrap_session,
        timeout=PAC_FETCH_TIMEOUT_SECONDS,
        allowed_content_types=list(PAC_ALLOWED_CONTENT_TYPES),
    )
    if pac is None:
        msg = f"Unable to fetch PAC file from {pac_url}"
        raise ValueError(msg)
    return pac


def get_proxy_settings_from_env(service_prefix: str) -> dict[str, str | bool | None]:
    """Load proxy settings with service-specific overrides."""
    service_http = f"{service_prefix}_HTTP_PROXY"
    service_https = f"{service_prefix}_HTTPS_PROXY"
    service_no_proxy = f"{service_prefix}_NO_PROXY"
    service_socks = f"{service_prefix}_SOCKS_PROXY"
    service_wpad_enable = f"{service_prefix}_PROXY_WPAD_ENABLE"
    service_wpad_url = f"{service_prefix}_PROXY_WPAD_URL"

    global_wpad_enable = is_env_truthy("ATLASSIAN_PROXY_WPAD_ENABLE")
    wpad_enable = (
        is_env_truthy(service_wpad_enable)
        if service_wpad_enable in os.environ
        else global_wpad_enable
    )
    configured_wpad_url = os.getenv(
        service_wpad_url, os.getenv("ATLASSIAN_PROXY_WPAD_URL")
    )

    return {
        "http_proxy": os.getenv(service_http, os.getenv("HTTP_PROXY")),
        "https_proxy": os.getenv(service_https, os.getenv("HTTPS_PROXY")),
        "no_proxy": os.getenv(service_no_proxy, os.getenv("NO_PROXY")),
        "socks_proxy": os.getenv(service_socks, os.getenv("SOCKS_PROXY")),
        "proxy_wpad_enable": wpad_enable,
        "proxy_wpad_url": (
            configured_wpad_url or DEFAULT_PROXY_WPAD_URL
            if wpad_enable
            else configured_wpad_url
        ),
    }


def get_explicit_proxy_map(config: ProxyConfigProtocol) -> dict[str, str]:
    """Return explicit proxy settings configured for a service."""
    proxies: dict[str, str] = {}
    if config.http_proxy:
        proxies["http"] = config.http_proxy
    if config.https_proxy:
        proxies["https"] = config.https_proxy
    if config.socks_proxy:
        proxies["socks"] = config.socks_proxy
    return proxies


def apply_proxy_configuration(
    *,
    logger: logging.Logger,
    service_name: str,
    session: Session,
    config: ProxyConfigProtocol,
    target_url: str,
) -> Session:
    """Apply static proxy or PAC/WPAD configuration to an existing session."""
    explicit_proxies = get_explicit_proxy_map(config)

    if config.no_proxy and isinstance(config.no_proxy, str):
        os.environ["NO_PROXY"] = config.no_proxy
        log_config_param(logger, service_name, "NO_PROXY", config.no_proxy)

    if explicit_proxies:
        session.proxies.update(explicit_proxies)
        for scheme, proxy_url in explicit_proxies.items():
            log_config_param(
                logger,
                service_name,
                f"{scheme.upper()}_PROXY",
                proxy_url,
                sensitive=True,
            )
        return session

    if not config.proxy_wpad_enable:
        return session

    pac_url = config.proxy_wpad_url or DEFAULT_PROXY_WPAD_URL
    log_config_param(
        logger,
        service_name,
        "PROXY_WPAD_URL",
        pac_url,
        sensitive="@" in pac_url,
    )

    try:
        pac = _load_pac_file(
            pac_url=pac_url,
            verify=session.verify,
            cert=session.cert,
            trust_env=session.trust_env,
        )
        _validate_pac_for_target_url(pac=pac, target_url=target_url)
    except MalformedPacError as e:
        msg = f"{service_name} PAC file at {pac_url} is malformed: {e}"
        raise ValueError(msg) from e
    except ValueError as e:
        msg = f"{service_name} WPAD/PAC configuration failed for {pac_url}: {e}"
        raise ValueError(msg) from e
    except Exception as e:  # pragma: no cover - defensive wrapper around pypac
        msg = f"{service_name} WPAD/PAC configuration failed for {pac_url}: {e}"
        raise ValueError(msg) from e

    pac_session = _NoProxyAwarePACSession(pac=pac, no_proxy=config.no_proxy)
    _copy_session_state(source=session, target=pac_session)
    logger.info(
        "%s PAC/WPAD routing enabled for %s",
        service_name,
        urlsplit(target_url).hostname or target_url,
    )
    return pac_session


def _copy_session_state(source: Session, target: Session) -> None:
    """Copy relevant requests.Session state when upgrading to PACSession."""
    target.headers.clear()
    target.headers.update(source.headers)
    target.cookies.update(source.cookies)
    target.auth = source.auth
    target.verify = source.verify
    target.cert = source.cert
    target.proxies.update(source.proxies)
    target.hooks = source.hooks
    target.params = dict(cast(dict[str, Any], source.params))
    target.stream = source.stream
    target.trust_env = source.trust_env
    target.max_redirects = source.max_redirects

    for prefix, adapter in source.adapters.items():
        target.mount(prefix, adapter)


def _validate_pac_for_target_url(*, pac: Any, target_url: str) -> None:
    """Validate that a loaded PAC file can be evaluated for the target host."""
    host = urlsplit(target_url).hostname
    if not host:
        msg = f"Target URL {target_url!r} is missing a hostname"
        raise ValueError(msg)
    pac.find_proxy_for_url(target_url, host)
