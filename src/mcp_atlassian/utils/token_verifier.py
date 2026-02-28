"""Token verifier for Atlassian opaque OAuth tokens.

FastMCP's OAuthProxy requires a TokenVerifier for loaded upstream access tokens.
Atlassian OAuth tokens are opaque in many environments and there is no stable
JWKS endpoint for verification, so we accept non-empty tokens and attach the
required scopes.
"""

from __future__ import annotations

import time

from fastmcp.server.auth.auth import AccessToken, TokenVerifier


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
        )
