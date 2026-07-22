"""Token verifier for Atlassian OAuth tokens.

FastMCP's OAuthProxy requires a TokenVerifier for loaded upstream access tokens.
Atlassian tokens are opaque, so verification must be done via an upstream API
call instead of local JWT/JWKS checks.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from cachetools import TTLCache
from fastmcp.server.auth.auth import AccessToken, TokenVerifier

CLOUD_ACCESSIBLE_RESOURCES_URL = (
    "https://api.atlassian.com/oauth/token/accessible-resources"
)
TOKEN_VALIDATION_TIMEOUT_SECONDS = 10.0
TOKEN_CACHE_TTL_SECONDS = 300
TOKEN_CACHE_MAX_SIZE = 1024
NON_RESOURCE_SCOPES = frozenset({"offline_access"})
DC_TOKEN_VALIDATION_PATHS = (
    "/rest/api/2/myself",
    "/rest/api/user/current",
)

logger = logging.getLogger("mcp-atlassian.oauth-proxy.token-verifier")


class AtlassianOpaqueTokenVerifier(TokenVerifier):
    """Validate opaque Atlassian tokens with an upstream API call."""

    def __init__(
        self,
        *,
        instance_url: str | None = None,
        is_cloud: bool = True,
        cloud_id: str | None = None,
        required_scopes: list[str] | None = None,
    ) -> None:
        """Initialize a verifier bound to one Atlassian instance.

        Args:
            instance_url: Atlassian Cloud or Data Center instance URL.
            is_cloud: Whether the configured instance is Atlassian Cloud.
            cloud_id: Optional Cloud resource ID to require during validation.
            required_scopes: Scopes required by the OAuth proxy.
        """
        super().__init__(required_scopes=required_scopes)
        self.instance_url = instance_url.rstrip("/") if instance_url else None
        self.is_cloud = is_cloud
        self.cloud_id = cloud_id.strip() if cloud_id else None
        self._token_cache: TTLCache[str, AccessToken] = TTLCache(
            maxsize=TOKEN_CACHE_MAX_SIZE,
            ttl=TOKEN_CACHE_TTL_SECONDS,
        )

    @staticmethod
    def _cache_key(token: str) -> str:
        """Return a non-secret cache key for an access token."""
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _url_identity(value: str) -> tuple[str, str, int] | None:
        """Return the scheme, hostname, and effective port for a URL."""
        try:
            parsed = urlparse(value)
            scheme = parsed.scheme.lower()
            hostname = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port
        except ValueError:
            return None

        if scheme not in {"http", "https"} or not hostname:
            return None

        if port is None:
            port = 443 if scheme == "https" else 80
        return scheme, hostname, port

    async def _fetch_accessible_resources(self, token: str) -> list[dict[str, Any]]:
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

    def _matches_cloud_instance(self, resource: dict[str, Any]) -> bool:
        """Return whether a Cloud resource belongs to the configured instance."""
        resource_id = resource.get("id")
        resource_url = resource.get("url")
        resource_scopes = resource.get("scopes")
        if (
            not isinstance(resource_id, str)
            or not resource_id
            or not isinstance(resource_url, str)
            or not resource_url
            or not isinstance(resource_scopes, list)
            or any(not isinstance(scope, str) or not scope for scope in resource_scopes)
        ):
            return False

        if self.cloud_id:
            return resource_id == self.cloud_id

        if not self.instance_url:
            return False

        instance_identity = self._url_identity(self.instance_url)
        resource_identity = self._url_identity(resource_url)
        if instance_identity is None or resource_identity is None:
            return False

        return resource_identity == instance_identity

    @staticmethod
    def _is_authenticated_dc_user(data: object) -> bool:
        """Return whether a Data Center user response represents a real user."""
        if not isinstance(data, dict):
            return False
        if str(data.get("type", "")).lower() == "anonymous":
            return False
        return any(
            isinstance(data.get(field), str) and bool(data[field].strip())
            for field in ("accountId", "key", "name", "userKey", "username")
        )

    async def _validate_dc_token(self, token: str) -> bool:
        """Validate a token against an authenticated Data Center user endpoint."""
        if not self.instance_url:
            logger.warning("Data Center token validation requires an instance URL")
            return False

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        timeout = httpx.Timeout(TOKEN_VALIDATION_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for path in DC_TOKEN_VALIDATION_PATHS:
                response = await client.get(
                    f"{self.instance_url}{path}", headers=headers
                )
                if response.status_code != 200:
                    continue
                try:
                    response_data = response.json()
                except ValueError:
                    logger.warning(
                        "Token validation returned malformed JSON from %s", path
                    )
                    continue
                if self._is_authenticated_dc_user(response_data):
                    return True

        logger.warning("Token validation failed against Data Center user endpoints")
        return False

    async def _verify_cloud_token(self, token: str) -> set[str] | None:
        """Validate a Cloud token and return its resource scopes."""
        resources = await self._fetch_accessible_resources(token)
        matching_resources = [
            resource for resource in resources if self._matches_cloud_instance(resource)
        ]
        if not matching_resources:
            return None

        token_scopes: set[str] = set()
        for resource in matching_resources:
            scopes = resource.get("scopes", [])
            if isinstance(scopes, list):
                token_scopes.update(scope for scope in scopes if isinstance(scope, str))

        required_scopes = set(self.required_scopes or [])
        required_resource_scopes = required_scopes - NON_RESOURCE_SCOPES
        if not required_resource_scopes.issubset(token_scopes):
            missing = sorted(required_resource_scopes - token_scopes)
            logger.warning("Token is missing required scopes: %s", missing)
            return None

        return token_scopes | (required_scopes & NON_RESOURCE_SCOPES)

    async def verify_token(self, token: str) -> AccessToken | None:  # noqa: D401
        token = token.strip() if token else ""
        if not token:
            return None

        cache_key = self._cache_key(token)
        cached_token = self._token_cache.get(cache_key)
        if cached_token is not None:
            return cached_token

        try:
            if self.is_cloud:
                effective_scopes = await self._verify_cloud_token(token)
                if effective_scopes is None:
                    return None
            else:
                if not await self._validate_dc_token(token):
                    return None
                effective_scopes = set(self.required_scopes or [])
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning("Token validation request failed: %s", exc)
            return None

        access_token = AccessToken(
            token=token,
            client_id="atlassian",
            scopes=sorted(effective_scopes),
            expires_at=int(time.time()) + TOKEN_CACHE_TTL_SECONDS,
        )
        self._token_cache[cache_key] = access_token
        return access_token
