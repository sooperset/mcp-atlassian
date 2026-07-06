"""Token verifier for Atlassian opaque OAuth tokens.

FastMCP's OAuthProxy requires a TokenVerifier for loaded upstream access tokens.
Atlassian OAuth tokens are opaque in many environments and there is no stable
JWKS endpoint for verification, so we accept non-empty tokens and attach the
required scopes.
"""

from __future__ import annotations

import re
import time

from fastmcp.server.auth.auth import AccessToken, TokenVerifier


class AtlassianOpaqueTokenVerifier(TokenVerifier):
    """Accept opaque Atlassian tokens and wrap them in AccessToken."""

    async def verify_token(self, token: str) -> AccessToken | None:  # noqa: D401
        if not token:
            return None

        # Atlassian tokens have specific format: base64-like, min 20 chars.
        # Reject obviously fabricated tokens that don't match expected format.
        if len(token) < 20 or not re.match(r"^[A-Za-z0-9._-]+$", token):
            return None

        scopes = self.required_scopes or []
        return AccessToken(
            token=token,
            client_id="atlassian",
            scopes=scopes,
            expires_at=int(time.time()) + 86400 * 30,
        )
