"""Utility functions specific to Confluence operations."""

import logging

from .constants import RESERVED_CQL_WORDS

logger = logging.getLogger(__name__)


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
