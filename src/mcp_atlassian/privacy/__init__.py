"""Opt-in privacy filter for MCP Atlassian tool responses.

Public API
----------

* :class:`PrivacyConfig` — env-derived configuration dataclass.
* :class:`PrivacyPipeline` — the (resource → field → PII) filter chain.
* :class:`PrivacyFilterMiddleware` — FastMCP middleware that wraps every
  tool response.
* :func:`install_privacy_filter` — one-call wiring for an :class:`AtlassianMCP`
  (or any :class:`fastmcp.FastMCP`) server. No-op when
  ``PRIVACY_FILTER_ENABLED`` is not truthy.

The module imports nothing from ``mcp_atlassian.{jira,confluence,models}``
and operates only on serialized tool output, so upstream model/mixin
refactors do not break the filter.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .config import DEFAULT_MASK_TOKEN, PrivacyConfig
from .middleware import PrivacyFilterMiddleware
from .pipeline import PrivacyPipeline
from .stats import FilterStats

if TYPE_CHECKING:
    from fastmcp import FastMCP

__all__ = [
    "DEFAULT_MASK_TOKEN",
    "FilterStats",
    "PrivacyConfig",
    "PrivacyFilterMiddleware",
    "PrivacyPipeline",
    "install_privacy_filter",
]

logger = logging.getLogger(__name__)


def install_privacy_filter(
    server: FastMCP[object],
    config: PrivacyConfig | None = None,
) -> bool:
    """Install the privacy filter on ``server`` if enabled in config.

    Args:
        server: The FastMCP server to attach the middleware to.
        config: Optional explicit config. Defaults to
            :meth:`PrivacyConfig.from_env`.

    Returns:
        ``True`` if the middleware was installed, ``False`` otherwise (the
        common case when ``PRIVACY_FILTER_ENABLED`` is unset/false).
    """
    resolved = config if config is not None else PrivacyConfig.from_env()
    if not resolved.enabled:
        return False
    pipeline = PrivacyPipeline(config=resolved)
    if pipeline.is_noop:
        logger.info("Privacy filter enabled but no rules configured; skipping install.")
        return False
    server.add_middleware(PrivacyFilterMiddleware(pipeline=pipeline))
    logger.info("Privacy filter middleware installed.")
    return True
