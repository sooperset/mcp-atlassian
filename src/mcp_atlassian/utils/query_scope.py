"""Compose caller-supplied JQL/CQL with an operator allowlist safely.

``JIRA_PROJECTS_FILTER`` and ``CONFLUENCE_SPACES_FILTER`` are enforced on
search tools by ANDing an allowlist clause onto the caller's query. Wrapping
untrusted query text in parentheses is only a boundary when that text is a
single balanced expression: a stray ``)`` closes the wrapper early and lets a
following ``OR`` escape the allowlist. This module tokenizes the caller's
query the way the Jira and Confluence lexers do (quoted strings, backslash
escapes) and rejects anything that could change the boolean structure of the
composed query.
"""

from __future__ import annotations

import re

_ORDER_BY_RE = re.compile(r"ORDER\s+BY\b", re.IGNORECASE)
_QUOTES = frozenset({'"', "'"})
_PARENS = frozenset({"(", ")"})


class UnsafeQueryError(ValueError):
    """Raised when a caller query cannot be safely scoped to the allowlist."""


def _reject(language: str, reason: str) -> UnsafeQueryError:
    return UnsafeQueryError(
        f"{language} query rejected: {reason}. A query must be a single "
        "expression with balanced parentheses and closed quotes so the "
        "configured project/space filter can be applied."
    )


def split_scoped_query(query: str, language: str = "JQL") -> tuple[str, str]:
    """Validate a caller query and split off a trailing ``ORDER BY`` clause.

    The predicate part is guaranteed to be a single parenthesis-balanced
    expression outside string literals, so ``(predicate) AND (allowlist)``
    keeps the allowlist as a top-level conjunct.

    Args:
        query: Caller-supplied JQL or CQL.
        language: ``"JQL"`` or ``"CQL"``, used in error messages.

    Returns:
        ``(predicate, order_by)`` with both parts stripped. ``order_by`` is the
        ``ORDER BY ...`` clause or an empty string.

    Raises:
        UnsafeQueryError: If quotes are unterminated, parentheses are
            unbalanced, a parenthesis is backslash-escaped outside a string,
            or the ``ORDER BY`` clause contains parentheses.
    """
    depth = 0
    order_start: int | None = None
    i = 0
    length = len(query)
    while i < length:
        char = query[i]
        if char in _QUOTES:
            i += 1
            while i < length and query[i] != char:
                i += 2 if query[i] == "\\" else 1
            if i >= length:
                raise _reject(language, "unterminated string literal")
            i += 1
            continue
        if char == "\\":
            # Outside quotes a backslash escapes the next character into an
            # unquoted literal. An escaped parenthesis is not a valid escape in
            # either language; refuse it rather than guess how it is lexed.
            if i + 1 >= length or query[i + 1] in _PARENS:
                raise _reject(language, "invalid escape outside a string literal")
            i += 2
            continue
        if char in _PARENS and order_start is not None:
            raise _reject(language, "parentheses are not allowed in ORDER BY")
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise _reject(language, "unbalanced parentheses")
        elif (
            order_start is None
            and depth == 0
            and char in "oO"
            and (i == 0 or not (query[i - 1].isalnum() or query[i - 1] == "_"))
            and _ORDER_BY_RE.match(query, i)
        ):
            order_start = i
        i += 1

    if depth != 0:
        raise _reject(language, "unbalanced parentheses")

    if order_start is None:
        return query.strip(), ""
    return query[:order_start].strip(), query[order_start:].strip()


def and_scope_clause(
    query: str | None, scope_clause: str, language: str = "JQL"
) -> str:
    """AND an allowlist clause onto a caller query so it cannot be escaped.

    Args:
        query: Caller-supplied JQL or CQL (may be ``None``, empty, or only
            ``ORDER BY``).
        scope_clause: Operator allowlist expression built from quoted
            identifiers, e.g. ``project IN (A, B)``.
        language: ``"JQL"`` or ``"CQL"``, used in error messages.

    Returns:
        ``(predicate) AND (scope_clause) [ORDER BY ...]``, or just the scope
        clause (plus ``ORDER BY``) when the caller supplied no predicate.

    Raises:
        UnsafeQueryError: If the caller query fails validation.
    """
    predicate, order_by = split_scoped_query(query or "", language)
    composed = f"({predicate}) AND ({scope_clause})" if predicate else scope_clause
    return f"{composed} {order_by}" if order_by else composed
