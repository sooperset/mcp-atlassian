"""OAuth proxy extensions and configuration helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from fastmcp.server.auth.oauth_proxy import OAuthProxy
from mcp.server.auth.provider import OAuthClientInformationFull

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


class HardenedOAuthProxy(OAuthProxy):
    """OAuthProxy with stricter DCR controls for grants and scopes."""

    def __init__(
        self,
        *,
        allowed_grant_types: list[str] | None = None,
        forced_scopes: list[str] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._allowed_grant_types = _normalize_list(allowed_grant_types)
        self._forced_scopes = _normalize_list(forced_scopes)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
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
