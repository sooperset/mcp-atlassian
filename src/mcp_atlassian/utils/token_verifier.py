"""Token verifier for Atlassian OAuth tokens.

FastMCP's OAuthProxy requires a TokenVerifier for loaded upstream access tokens.
Atlassian tokens are opaque, so verification must be done via an upstream API
call instead of local JWT/JWKS checks.
"""

from __future__ import annotations

import logging
import time

import httpx
from fastmcp.server.auth.auth import AccessToken, TokenVerifier

CLOUD_ACCESSIBLE_RESOURCES_URL = (
    "https://api.atlassian.com/oauth/token/accessible-resources"
)
TOKEN_VALIDATION_TIMEOUT_SECONDS = 10.0
TOKEN_CACHE_TTL_SECONDS = 300

logger = logging.getLogger("mcp-atlassian.oauth-proxy.token-verifier")


class AtlassianOpaqueTokenVerifier(TokenVerifier):
    """Validate opaque Atlassian tokens with an upstream API call."""

    async def _fetch_accessible_resources(self, token: str) -> list[dict]:
        headers = {"Authorization": f"Bearer {token}"}
        timeout = httpx.Timeout(TOKEN_VALIDATION_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                CLOUD_ACCESSIBLE_RESOURCES_URL,
                headers=headers,
            )

        if response.status_code != 200:
            logger.warning(
                "Token validation failed with status %s",
                response.status_code,
            )
            return []

        data = response.json()
        if not isinstance(data, list):
            logger.warning("Token validation returned non-list resources payload")
            return []

        return [resource for resource in data if isinstance(resource, dict)]

    async def verify_token(self, token: str) -> AccessToken | None:  # noqa: D401
        token = token.strip() if token else ""
        if not token:
            return None

        try:
            resources = await self._fetch_accessible_resources(token)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning("Token validation request failed: %s", exc)
            return None

        if not resources:
            return None

        token_scopes: set[str] = set()
        for resource in resources:
            scopes = resource.get("scopes", [])
            if isinstance(scopes, list):
                token_scopes.update(scope for scope in scopes if isinstance(scope, str))

        required_scopes = set(self.required_scopes or [])
        if required_scopes and not required_scopes.issubset(token_scopes):
            missing = sorted(required_scopes - token_scopes)
            logger.warning("Token is missing required scopes: %s", missing)
            return None

        effective_scopes = (
            sorted(token_scopes) if token_scopes else list(required_scopes)
        )
        return AccessToken(
            token=token,
            client_id="atlassian",
            scopes=effective_scopes,
            expires_at=int(time.time()) + TOKEN_CACHE_TTL_SECONDS,
        )
