"""Optional TrustModel AgentCert verify-gate.

Verifies a calling agent's **AgentCert + TrustScore** on each tool call, using the
dependency-free ``trustmodel-agentcert-tag`` client. It does **nothing** unless
``TRUSTMODEL_VERIFY=1`` is set; when enabled it defaults to **shadow mode** (logs a
verdict, never blocks). Set ``TRUSTMODEL_MODE=enforce`` to reject unverified/revoked
agents. Reads request metadata only (never tool payloads).

Docs: https://trustmodel.ai/verify
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("mcp-atlassian")

_TRUTHY = {"1", "true", "yes", "on"}


def register_trustmodel_verify(server) -> bool:
    """Attach the verify-gate middleware when ``TRUSTMODEL_VERIFY`` is truthy.

    Safe to call unconditionally: a no-op when the flag is unset or the optional
    ``trustmodel-agentcert-tag`` dependency isn't installed. Returns ``True`` when
    the gate was attached.
    """
    if os.environ.get("TRUSTMODEL_VERIFY", "").strip().lower() not in _TRUTHY:
        return False

    # Resolve mode before importing, so enforce mode can fail closed on a missing dep.
    mode = os.environ.get("TRUSTMODEL_MODE", "shadow").strip().lower()

    try:
        from fastmcp.server.dependencies import get_http_headers
        from fastmcp.server.middleware import Middleware
        from trustmodel_agentcert_tag import extract_token, verify_gate
    except ImportError as exc:
        # Fail CLOSED in enforce mode: never start "protected" without the verifier.
        if mode == "enforce":
            raise RuntimeError(
                "TRUSTMODEL_MODE=enforce requires 'trustmodel-agentcert-tag'; "
                "install the 'trustmodel' extra."
            ) from exc
        logger.warning(
            "TRUSTMODEL_VERIFY is set but 'trustmodel-agentcert-tag' isn't installed; "
            "install the 'trustmodel' extra. Skipping verify-gate (shadow)."
        )
        return False

    class _TrustModelVerifyMiddleware(Middleware):
        """FastMCP middleware that verifies the calling agent's AgentCert per tool call."""

        def __init__(self) -> None:
            """Build the shadow/enforce guard once from the configured mode."""
            self._guard = verify_gate(mode=mode)

        async def on_call_tool(self, context, call_next):
            """Verify the request's AgentCert token, then proceed (shadow logs; enforce raises)."""
            # metadata-only: read the AgentCert token from the request headers.
            await self._guard(extract_token(get_http_headers() or {}))
            return await call_next(context)

    server.add_middleware(_TrustModelVerifyMiddleware())
    logger.info("TrustModel AgentCert verify-gate enabled (mode=%s).", mode)
    return True
