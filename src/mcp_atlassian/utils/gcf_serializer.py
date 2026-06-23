"""Optional GCF (Graph Compact Format) serialization support.

GCF is an AI-native wire format that significantly reduces token usage
when sending structured data through MCP tool responses. When enabled,
list/tabular data (search results, issue lists, page lists) is encoded
using GCF's tabular encoding instead of JSON, typically saving 50-57%
of tokens.

Enable by setting the environment variable:
    MCP_ATLASSIAN_OUTPUT_FORMAT=gcf

Requires the optional ``gcf`` package:
    pip install gcf-python
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_GCF_AVAILABLE: bool | None = None
_OUTPUT_FORMAT: str | None = None

# Environment variable name
OUTPUT_FORMAT_ENV = "MCP_ATLASSIAN_OUTPUT_FORMAT"


def _check_gcf_available() -> bool:
    """Check if the gcf package is installed."""
    global _GCF_AVAILABLE  # noqa: PLW0603
    if _GCF_AVAILABLE is None:
        try:
            from gcf import encode_generic  # noqa: F401

            _GCF_AVAILABLE = True
        except ImportError:
            _GCF_AVAILABLE = False
    return _GCF_AVAILABLE


def _get_output_format() -> str:
    """Get the configured output format (cached)."""
    global _OUTPUT_FORMAT  # noqa: PLW0603
    if _OUTPUT_FORMAT is None:
        _OUTPUT_FORMAT = os.getenv(OUTPUT_FORMAT_ENV, "json").lower().strip()
    return _OUTPUT_FORMAT


def is_gcf_enabled() -> bool:
    """Check whether GCF output format is enabled and available.

    Returns True only if the env var is set to 'gcf' AND the gcf
    package is installed. Falls back to JSON silently if the package
    is missing.
    """
    if _get_output_format() != "gcf":
        return False
    if not _check_gcf_available():
        logger.warning(
            "MCP_ATLASSIAN_OUTPUT_FORMAT=gcf but gcf-python is not installed. "
            "Falling back to JSON. Install with: pip install gcf-python"
        )
        return False
    return True


def serialize(data: Any, *, indent: int = 2, ensure_ascii: bool = False) -> str:
    """Serialize data to JSON or GCF depending on configuration.

    This is the main entry point. It is a drop-in replacement for
    ``json.dumps(data, indent=2, ensure_ascii=False)`` throughout the
    server modules. When GCF is enabled, list-of-dict data is encoded
    with ``encode_generic``; all other shapes fall through to JSON.

    Args:
        data: The Python object to serialize.
        indent: JSON indent level (ignored when GCF is used).
        ensure_ascii: JSON ensure_ascii flag (ignored when GCF is used).

    Returns:
        Serialized string (either JSON or GCF).
    """
    if is_gcf_enabled():
        encoded = _try_gcf_encode(data)
        if encoded is not None:
            return encoded
    return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)


def _try_gcf_encode(data: Any) -> str | None:
    """Attempt to encode data with GCF.

    GCF's encode_generic handles all JSON-compatible data shapes natively:
    lists, dicts, nested structures, mixed types. No preprocessing needed.

    Returns:
        GCF-encoded string, or None if encoding fails or is unavailable.
    """
    try:
        from gcf import encode_generic
    except ImportError:
        return None

    try:
        gcf_str = encode_generic(data)
        # Only use GCF if it's actually smaller
        json_str = json.dumps(data, ensure_ascii=False)
        if len(gcf_str) >= len(json_str):
            return None
        return gcf_str
    except Exception:  # noqa: BLE001
        return None
