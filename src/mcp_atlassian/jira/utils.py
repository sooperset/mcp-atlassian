"""Utility functions specific to Jira operations."""

import logging
import re

from .constants import RESERVED_JQL_WORDS

logger = logging.getLogger(__name__)


def quote_jql_identifier_if_needed(identifier: str) -> str:
    """Quotes a Jira identifier for safe use in JQL literals if required.

    Handles:
    - Identifiers matching reserved JQL words (case-insensitive).
    - Identifiers starting with a number.
    - Escapes internal quotes ('"') and backslashes ('\\') within the identifier
      before quoting.

    Args:
        identifier: The identifier string (e.g., project key).

    Returns:
        The identifier, correctly quoted and escaped if necessary,
        otherwise the original identifier.
    """
    needs_quoting = False
    identifier_lower = identifier.lower()

    # Rule 1: Is a reserved word (case-insensitive check)
    if identifier_lower in RESERVED_JQL_WORDS:
        needs_quoting = True
        logger.debug(f"Identifier '{identifier}' needs quoting (reserved word).")

    # Rule 2: Starts with a number
    elif identifier and identifier[0].isdigit():
        needs_quoting = True
        logger.debug(f"Identifier '{identifier}' needs quoting (starts with digit).")

    # Rule 3: Contains internal quotes or backslashes (always needs quoting+escaping)
    elif '"' in identifier or "\\" in identifier:
        needs_quoting = True
        logger.debug(
            f"Identifier '{identifier}' needs quoting (contains quotes/backslashes)."
        )

    if needs_quoting:
        # Escape internal backslashes first, then double quotes
        escaped_identifier = identifier.replace("\\", "\\\\").replace('"', '\\"')
        quoted_escaped = f'"{escaped_identifier}"'
        logger.debug(f"Quoted and escaped identifier: {quoted_escaped}")
        return quoted_escaped
    else:
        logger.debug(f"Identifier '{identifier}' does not need quoting.")
        return identifier


def sanitize_jql_reserved_words(jql: str | None) -> str | None:
    """Sanitize JQL by quoting reserved words used as project key values.

    Scans for ``project = VALUE`` and ``project IN (...)`` patterns in the JQL
    string and quotes any unquoted values that are JQL reserved words.

    String literals (content inside double quotes) are left untouched so that
    patterns like ``summary ~ "project = IF"`` are not modified.

    Args:
        jql: Raw JQL query string, or None.

    Returns:
        The sanitized JQL string with reserved project key values quoted,
        or the original value if no changes were needed.
    """
    if not jql:
        return jql

    # Use regex alternation so the engine consumes quoted strings before
    # attempting to match project patterns. This prevents modifying content
    # inside string literals and correctly handles quoted values within
    # IN (...) clauses.
    _pattern = re.compile(
        r"""("(?:[^"\\]|\\.)*")"""  # group 1: double-quoted string — consume and skip
        r"|('(?:[^'\\]|\\.)*')"  # group 2: single-quoted string — consume and skip
        r"|(project\s*(?:!=|=)\s*)(\w+)"  # groups 3,4: project =/!= VALUE
        r"|(project\s+(?:NOT\s+)?IN\s*\()([^)]*)\)",  # groups 5,6: project [NOT] IN (...)
        re.IGNORECASE,
    )

    def _replacer(m: re.Match[str]) -> str:
        if m.group(1) or m.group(2):  # quoted string — pass through unchanged
            return m.group(0)
        if m.group(3):  # project = VALUE
            return m.group(3) + _quote_if_reserved(m.group(4))
        if m.group(5):  # project [NOT] IN (...)
            return m.group(5) + _quote_in_list_values(m.group(6)) + ")"
        return m.group(0)  # pragma: no cover

    return _pattern.sub(_replacer, jql)


def _quote_if_reserved(value: str) -> str:
    """Quote a single identifier value if it's a JQL reserved word."""
    if value.lower() in RESERVED_JQL_WORDS:
        return f'"{value}"'
    return value


def _quote_in_list_values(values_str: str) -> str:
    """Quote reserved words within an IN (...) value list.

    Handles already-quoted values by leaving them untouched.
    """
    # Match each token: double-quoted, single-quoted, or unquoted word
    token_pattern = re.compile(r"""("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\w+)""")

    def replace_token(m: re.Match[str]) -> str:
        token = m.group(0)
        # Already quoted (single or double) → leave as is
        if token.startswith('"') or token.startswith("'"):
            return token
        return _quote_if_reserved(token)

    return token_pattern.sub(replace_token, values_str)
