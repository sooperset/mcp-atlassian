"""Token verifier for Atlassian opaque OAuth tokens.

FastMCP's OAuthProxy requires a TokenVerifier for loaded upstream access tokens.
Atlassian OAuth tokens are opaque in many environments and there is no stable
JWKS endpoint for verification, so we accept non-empty tokens and attach the
required scopes.

The verifier also names the principal behind a token (``subject``), as a keyed
fingerprint of the token. The MCP SDK binds each transport session to that
name, so one user cannot end or post into another user's session.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastmcp.server.auth.auth import AccessToken, TokenVerifier

# Keys the subject fingerprint. Sessions live in this process only.
_SUBJECT_KEY = secrets.token_bytes(32)


def principal_subject(material: str) -> str:
    """Return a keyed fingerprint that names a principal without revealing it."""
    return hmac.new(_SUBJECT_KEY, material.encode(), hashlib.sha256).hexdigest()


class AtlassianOpaqueTokenVerifier(TokenVerifier):
    """Accept opaque Atlassian tokens and wrap them in AccessToken."""

    async def verify_token(self, token: str) -> AccessToken | None:  # noqa: D401
        if not token:
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
