"""OAuth proxy extensions and configuration helpers."""

from __future__ import annotations

import ipaddress
import logging
import posixpath
from collections.abc import Iterable
from urllib.parse import unquote, urlsplit, urlunsplit

from fastmcp.server.auth.oauth_proxy import OAuthProxy
from mcp.server.auth.provider import (
    OAuthClientInformationFull,
    RegistrationError,
)
from pydantic import AnyHttpUrl

logger = logging.getLogger("mcp-atlassian.server.oauth_proxy")


def _normalize_list(values: Iterable[str] | None) -> list[str] | None:
    if values is None:
        return None
    return [value.strip() for value in values if value and value.strip()]


def parse_env_list(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    if not raw.strip():
        return []
    normalized = raw.replace(",", " ")
    return [item.strip() for item in normalized.split() if item.strip()]


def _redirect_target(uri: str) -> tuple[str, str, int | None, str] | None:
    """Return the origin and route used by a redirect URI."""
    try:
        parsed = urlsplit(uri)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if not parsed.scheme or not hostname:
        return None

    scheme = parsed.scheme.lower()
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None

    hostname = hostname.rstrip(".").lower()
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    try:
        hostname = str(ipaddress.ip_address(hostname))
    except ValueError:
        pass

    path = posixpath.normpath(unquote(parsed.path or "/"))
    if not path.startswith("/"):
        path = f"/{path}"

    return scheme, hostname, port, path.rstrip("/") or "/"


def _callback_uri(base_url: str, redirect_path: str) -> str:
    """Build the proxy's callback URI from its public base URL and route."""
    parsed = urlsplit(base_url)
    callback_path = f"{parsed.path.rstrip('/')}/{redirect_path.lstrip('/')}"
    return urlunsplit((parsed.scheme, parsed.netloc, callback_path, "", ""))


class HardenedOAuthProxy(OAuthProxy):
    """OAuthProxy with stricter DCR controls for grants and scopes."""

    def __init__(
        self,
        *,
        base_url: AnyHttpUrl | str,
        redirect_path: str | None = None,
        allowed_grant_types: list[str] | None = None,
        forced_scopes: list[str] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(base_url=base_url, redirect_path=redirect_path, **kwargs)
        self._allowed_grant_types = _normalize_list(allowed_grant_types)
        self._forced_scopes = _normalize_list(forced_scopes)
        self._proxy_callback_target = _redirect_target(
            _callback_uri(str(self.base_url), self._redirect_path)
        )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        for redirect_uri in client_info.redirect_uris or []:
            if _redirect_target(str(redirect_uri)) == self._proxy_callback_target:
                raise RegistrationError(
                    "invalid_redirect_uri",
                    "DCR redirect_uri must not target the OAuth proxy callback",
                )

        updates: dict[str, object] = {"response_types": ["code"]}

        if self._allowed_grant_types is not None:
            requested = list(client_info.grant_types or [])
            filtered = [gt for gt in requested if gt in self._allowed_grant_types]
            if requested and set(requested) - set(filtered):
                logger.warning(
                    "DCR requested unsupported grant types %s; enforcing %s",
                    sorted(set(requested) - set(filtered)),
                    self._allowed_grant_types,
                )
            if not filtered:
                filtered = list(self._allowed_grant_types)
            updates["grant_types"] = filtered

        if self._forced_scopes is not None:
            forced_scope = " ".join(self._forced_scopes).strip()
            updates["scope"] = forced_scope or None
            if client_info.scope and client_info.scope != forced_scope:
                logger.warning(
                    "DCR requested scope '%s'; enforcing '%s'",
                    client_info.scope,
                    forced_scope,
                )

        client_info = client_info.model_copy(update=updates)
        await super().register_client(client_info)


__all__ = ["HardenedOAuthProxy", "parse_env_list"]
