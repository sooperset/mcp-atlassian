"""Token verifier for Atlassian opaque OAuth tokens.

FastMCP's OAuthProxy requires a TokenVerifier for loaded upstream access tokens.
Atlassian OAuth tokens are opaque in many environments and there is no stable
JWKS endpoint for verification, so format alone cannot tell a live token from
a fabricated one. With ``validate_cloud_token=True`` (set for Cloud instances
by :func:`mcp_atlassian.servers.main._build_auth_provider`), a Cloud token is
additionally checked against Atlassian's own
``oauth/token/accessible-resources`` endpoint: a 2xx response naming at least
one resource is the only signal Atlassian exposes that a token is live (not
expired or revoked) and not just well-formed. Server/Data Center exposes no
single, product-agnostic endpoint for this, so a DC token is still accepted
on format alone; ``validate_cloud_token`` is left ``False`` for DC.

This validation is currently defense-in-depth rather than the sole guard: in
this server's OAuth-proxy wiring, ``verify_token`` only ever sees a token this
process itself already fetched from Atlassian's real token endpoint (see
``HardenedOAuthProxy.load_access_token``), never one a client supplied
directly. A caller that constructs this class outside that wiring gets the
same real validation, so the class is now safe to use on its own merits too.

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

import requests
from fastmcp.server.auth.auth import AccessToken, TokenVerifier

logger = logging.getLogger("mcp-atlassian.auth.token_verifier")

# Keys the subject fingerprint. Sessions live in this process only.
_SUBJECT_KEY = secrets.token_bytes(32)

CLOUD_ACCESSIBLE_RESOURCES_URL = (
    "https://api.atlassian.com/oauth/token/accessible-resources"
)
_CLOUD_VALIDATION_TIMEOUT_SECONDS = 10


def principal_subject(material: str) -> str:
    """Return a keyed fingerprint that names a principal without revealing it."""
    return hmac.new(_SUBJECT_KEY, material.encode(), hashlib.sha256).hexdigest()


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
    """

    def __init__(self, *, validate_cloud_token: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._validate_cloud_token = validate_cloud_token

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
        other than a 2xx response naming at least one resource.
        """
        try:
            response = await asyncio.to_thread(
                requests.get,
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
        return True
