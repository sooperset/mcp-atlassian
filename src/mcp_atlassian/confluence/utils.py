"""Utility functions specific to Confluence operations."""

import logging
from typing import Any

from .constants import RESERVED_CQL_WORDS

logger = logging.getLogger(__name__)


def extract_emoji_from_property(value: Any) -> str | None:
    """Extract emoji character from a Confluence content property value.

    The emoji property value can be in different formats:
    - Dict with 'fallback', 'shortName', or 'id' keys
    - Direct string value

    Args:
        value: The property value from the API

    Returns:
        The emoji character if found, None otherwise
    """
    if isinstance(value, dict):
        # Format: {"id": "1f4dd", "shortName": ":memo:", "fallback": "📝"}
        # Prefer fallback (actual emoji), then try to convert from id
        emoji = value.get("fallback")
        if emoji:
            return emoji

        # Try shortName (e.g., ":memo:")
        short_name = value.get("shortName")
        if short_name:
            return short_name

        # Try to convert from id (hex code point)
        emoji_id = value.get("id")
        if emoji_id:
            try:
                return chr(int(emoji_id, 16))
            except (ValueError, OverflowError):
                logger.debug(f"Could not convert emoji id '{emoji_id}' to unicode")

    elif isinstance(value, str):
        return value

    return None


def emoji_to_hex_id(emoji: str) -> str:
    """Convert an emoji character to its Unicode hex code point(s).

    For single code point emojis, returns the hex (e.g., "1f4dd" for 📝).
    For multi-codepoint emojis (like flags or skin tones), joins with hyphens.

    Args:
        emoji: The emoji character(s)

    Returns:
        Hex code point string (e.g., "1f4dd" or "1f1fa-1f1f8")
    """
    code_points = [f"{ord(char):x}" for char in emoji]
    return "-".join(code_points)


def quote_cql_identifier_if_needed(identifier: str) -> str:
    """
    Quotes a Confluence identifier for safe use in CQL literals if required.

    Handles:
    - Personal space keys starting with '~'.
    - Identifiers matching reserved CQL words (case-insensitive).
    - Identifiers starting with a number.
    - Escapes internal quotes ('"') and backslashes ('\\') within the identifier
      *before* quoting.

    Args:
        identifier: The identifier string (e.g., space key).

    Returns:
        The identifier, correctly quoted and escaped if necessary,
        otherwise the original identifier.
    """
    needs_quoting = False
    identifier_lower = identifier.lower()

    # Rule 1: Starts with ~ (Personal Space Key)
    if identifier.startswith("~"):
        needs_quoting = True
        logger.debug(f"Identifier '{identifier}' needs quoting (starts with ~).")

    # Rule 2: Is a reserved word (case-insensitive check)
    elif identifier_lower in RESERVED_CQL_WORDS:
        needs_quoting = True
        logger.debug(f"Identifier '{identifier}' needs quoting (reserved word).")

    # Rule 3: Starts with a number
    elif identifier and identifier[0].isdigit():
        needs_quoting = True
        logger.debug(f"Identifier '{identifier}' needs quoting (starts with digit).")

    # Rule 4: Contains internal quotes or backslashes (always needs quoting+escaping)
    elif '"' in identifier or "\\" in identifier:
        needs_quoting = True
        logger.debug(
            f"Identifier '{identifier}' needs quoting (contains quotes/backslashes)."
        )

    # Add more rules here if other characters prove problematic (e.g., spaces, hyphens)
    # elif ' ' in identifier or '-' in identifier:
    #    needs_quoting = True

    if needs_quoting:
        # Escape internal backslashes first, then double quotes
        escaped_identifier = identifier.replace("\\", "\\\\").replace('"', '\\"')
        quoted_escaped = f'"{escaped_identifier}"'
        logger.debug(f"Quoted and escaped identifier: {quoted_escaped}")
        return quoted_escaped
    else:
        # Return the original identifier if no quoting is needed
        logger.debug(f"Identifier '{identifier}' does not need quoting.")
        return identifier
