"""Optional pagination ceiling to protect both the upstream server and the
LLM context.

A single tool call that asks for thousands of results forces N backend
round-trips and dumps a huge response into the model. This module clamps
user-supplied `limit` values to a configurable ceiling, applied at the
mixin entry point so every caller (FastMCP tool, programmatic, etc.)
benefits.

Disabled by default — opt in via ATLASSIAN_MAX_PAGINATION_LIMIT.
"""

import logging
import os

logger = logging.getLogger("mcp-atlassian.pagination")


def clamp_limit(requested: int, *, context: str = "pagination") -> int:
    """Clamp `requested` to ATLASSIAN_MAX_PAGINATION_LIMIT.

    Disabled by default (env unset or <= 0). Negative or zero `requested` is
    passed through unchanged so callers' own validation still applies.
    """
    if requested <= 0:
        return requested

    raw = os.getenv("ATLASSIAN_MAX_PAGINATION_LIMIT")
    if not raw:
        return requested

    try:
        cap = int(raw)
    except ValueError:
        logger.warning(
            "Invalid ATLASSIAN_MAX_PAGINATION_LIMIT=%r; clamping disabled",
            raw,
        )
        return requested

    if cap <= 0:
        return requested
    if requested > cap:
        logger.info(
            "%s: limit %d clamped to %d (ATLASSIAN_MAX_PAGINATION_LIMIT)",
            context,
            requested,
            cap,
        )
        return cap
    return requested
