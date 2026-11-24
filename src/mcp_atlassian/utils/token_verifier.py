"""Token verifier for Atlassian opaque OAuth tokens.

FastMCP's OAuthProxy requires a TokenVerifier for loaded upstream access tokens.
Atlassian OAuth tokens are opaque in many environments and there is no stable
JWKS endpoint for verification, so format alone cannot tell a live token from
a fabricated one. With ``validate_cloud_token=True`` (set for Cloud instances
by :func:`mcp_atlassian.servers.main._build_auth_provider`), a Cloud token is
additionally checked against Atlassian's own
``oauth/token/accessible-resources`` endpoint: a 2xx response naming a
resource that matches the configured instance (when ``cloud_site_hostname``
is given) is the only signal Atlassian exposes that a token is live (not
expired or revoked), reachable for this specific site, and not just
well-formed. Server/Data Center exposes no single, product-agnostic endpoint
for this, so a DC token is still accepted on format alone; both
``validate_cloud_token`` and ``cloud_site_hostname`` are left unset for DC.

This check is called on every request that reaches ``load_access_token``, not
just at login, so a successful result is cached for a short time
(``_CLOUD_VALIDATION_CACHE_TTL_SECONDS``) and the outbound call reuses one
``requests.Session`` — a bare module-level ``requests.get`` opens a new
connection, including a fresh TLS handshake, on every call. A failure is
never cached, so a transient Atlassian-side error does not hold a token
rejected for the cache window; the next call re-checks live.

In this server's OAuth-proxy wiring, ``verify_token`` only ever sees a token
this process itself already fetched from Atlassian's real token endpoint
(see ``HardenedOAuthProxy.load_access_token``), never one a client supplied
directly — so this validation is currently defense-in-depth rather than the
sole guard against a forged bearer token. It is still real validation on its
own terms when ``validate_cloud_token=True``, with two known limits even
then: scopes and the expiry on the returned ``AccessToken`` are not read from
Atlassian's response (``required_scopes``/a fixed 30-day value are used
instead), and without ``cloud_site_hostname`` any live Cloud token — not
necessarily one for this deployment's Atlassian instance — passes.
``validate_cloud_token`` defaults to ``False``, so a caller that constructs
this class directly without these arguments keeps the pre-existing
format-only behavior.

The verifier also names the principal behind a token (``subject``), as a keyed
fingerprint of the token. The MCP SDK binds each transport session to that
name, so one user cannot end or post into another user's session.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlparse

import requests
from cachetools import TTLCache
from fastmcp.server.auth.auth import AccessToken, TokenVerifier

logger = logging.getLogger("mcp-atlassian.auth.token_verifier")

# Keys the subject fingerprint. Sessions live in this process only.
_SUBJECT_KEY = secrets.token_bytes(32)

CLOUD_ACCESSIBLE_RESOURCES_URL = (
    "https://api.atlassian.com/oauth/token/accessible-resources"
)
_CLOUD_VALIDATION_TIMEOUT_SECONDS = 10
# A revoked token stays accepted for at most this long. Short enough to be a
# meaningful check, long enough that a busy server does not call Atlassian on
# every single tool invocation.
_CLOUD_VALIDATION_CACHE_TTL_SECONDS = 60
_CLOUD_VALIDATION_CACHE_MAX_ENTRIES = 4096


def principal_subject(material: str) -> str:
    """Return a keyed fingerprint that names a principal without revealing it."""
    return hmac.new(_SUBJECT_KEY, material.encode(), hashlib.sha256).hexdigest()


def _resource_hostnames(resources: list[Any]) -> set[str]:
    hostnames: set[str] = set()
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        url = resource.get("url")
        if not isinstance(url, str):
            continue
        hostname = urlparse(url).hostname
        if hostname:
            hostnames.add(hostname.lower())
    return hostnames


class AtlassianOpaqueTokenVerifier(TokenVerifier):
    """Accept opaque Atlassian tokens and wrap them in AccessToken.

    Args:
        validate_cloud_token: When ``True``, a token is additionally checked
            against Atlassian Cloud's ``accessible-resources`` endpoint and
            rejected on any non-2xx response, malformed body, empty resource
            list, timeout or connection error. Defaults to ``False`` so a
            caller that only needs the pre-existing format-based behavior
            (for example constructing this class directly, outside the
            OAuth-proxy wiring) is unaffected.
        cloud_site_hostname: When given alongside ``validate_cloud_token``,
            also requires one of the token's accessible resources to be this
            exact hostname — binding the check to this deployment's
            configured Atlassian Cloud instance rather than accepting any
            Atlassian Cloud token.
    """

    def __init__(
        self,
        *,
        validate_cloud_token: bool = False,
        cloud_site_hostname: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._validate_cloud_token = validate_cloud_token
        self._cloud_site_hostname = (
            cloud_site_hostname.lower() if cloud_site_hostname else None
        )
        self._session = requests.Session()
        self._live_token_cache: TTLCache[str, bool] = TTLCache(
            maxsize=_CLOUD_VALIDATION_CACHE_MAX_ENTRIES,
            ttl=_CLOUD_VALIDATION_CACHE_TTL_SECONDS,
        )

    async def verify_token(self, token: str) -> AccessToken | None:  # noqa: D401
        if not token:
            return None

        if self._validate_cloud_token and not await self._is_live_cloud_token(token):
            return None

        scopes = self.required_scopes or []
        return AccessToken(
            token=token,
            client_id="atlassian",
            scopes=scopes,
            expires_at=int(time.time()) + 86400 * 30,
            # No claim in the token is trusted as identity: its signature is
            # not checked. HardenedOAuthProxy names the user by OAuth grant.
            subject=principal_subject(f"token:{token}"),
        )

    async def _is_live_cloud_token(self, token: str) -> bool:
        """Return whether Atlassian reports ``token`` as currently valid.

        Calls Atlassian's own accessible-resources endpoint, the one
        token-introspection-equivalent surface Atlassian Cloud exposes for an
        opaque access token. Fails closed (returns ``False``) on anything
        other than a 2xx response naming a resource that matches the
        configured site (or, with no configured site, any resource at all).
        A successful result is cached briefly; a failure never is.
        """
        cache_key = hashlib.sha256(token.encode()).hexdigest()
        if self._live_token_cache.get(cache_key):
            return True

        try:
            response = await asyncio.to_thread(
                self._session.get,
                CLOUD_ACCESSIBLE_RESOURCES_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                timeout=_CLOUD_VALIDATION_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            logger.warning("Atlassian Cloud token validation request failed: %s", exc)
            return False

        if not response.ok:
            logger.info(
                "Atlassian Cloud token validation returned status %s",
                response.status_code,
            )
            return False

        try:
            resources = response.json()
        except ValueError:
            logger.warning("Atlassian Cloud token validation returned a non-JSON body")
            return False

        if not isinstance(resources, list) or not resources:
            logger.info(
                "Atlassian Cloud token validation returned no accessible resources"
            )
            return False

        if self._cloud_site_hostname is not None:
            hostnames = _resource_hostnames(resources)
            if self._cloud_site_hostname not in hostnames:
                logger.info(
                    "Atlassian Cloud token is valid but has no accessible resource "
                    "matching the configured instance"
                )
                return False

        self._live_token_cache[cache_key] = True
        return True
