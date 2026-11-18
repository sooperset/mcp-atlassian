"""Tests for composing caller JQL/CQL with the project/space allowlist."""

import pytest

from mcp_atlassian.utils.query_scope import (
    UnsafeQueryError,
    and_scope_clause,
    split_scoped_query,
)

SCOPE = "project = ALLOWED"


@pytest.mark.parametrize(
    "query",
    [
        # Stray ")" + "(" closes the wrapper and ORs around the allowlist.
        'created >= "2020-01-01") OR (project = "RESTRICTED"',
        'created >= "1970/01/01") OR (created >= "1970/01/01"',
        "type = page) OR (space = SECRET",
        # Boolean absorption through an unbalanced close.
        "project = ALLOWED OR project = SECRET) OR (key = X",
        # Unbalanced in either direction.
        "(project = SECRET",
        "project = SECRET)",
        ")(",
        # The close hidden from a naive scanner behind an escaped quote.
        'summary ~ a\\" ) OR ( project = SECRET AND summary ~ \\"',
        # Escaped parentheses outside a string are not valid escapes.
        "summary ~ a\\) OR (project = SECRET",
        "summary ~ \\( ) OR ( project = SECRET",
        # Unterminated string literal swallows the rest of the composed query.
        'summary ~ "abc',
        "summary ~ 'abc",
        # Trailing backslash escapes the composed closing parenthesis.
        "summary ~ abc\\",
        # ORDER BY tail must not carry parentheses.
        "project = X ORDER BY created) OR (project = SECRET",
    ],
)
def test_rejects_queries_that_could_escape_the_allowlist(query: str) -> None:
    with pytest.raises(UnsafeQueryError):
        and_scope_clause(query, SCOPE)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", SCOPE),
        (None, SCOPE),
        ("status = Open", f"(status = Open) AND ({SCOPE})"),
        (
            "(status = Open OR status = Done) AND assignee = me",
            f"((status = Open OR status = Done) AND assignee = me) AND ({SCOPE})",
        ),
        # Parentheses inside string literals are content, not structure.
        (
            'summary ~ "a) OR (b"',
            f'(summary ~ "a) OR (b") AND ({SCOPE})',
        ),
        (
            "summary ~ 'it''s (x'",
            f"(summary ~ 'it''s (x') AND ({SCOPE})",
        ),
        (
            'summary ~ "quote \\" ) inside"',
            f'(summary ~ "quote \\" ) inside") AND ({SCOPE})',
        ),
        # JQL functions keep their own balanced parentheses.
        (
            'assignee in membersOf("devs") AND sprint in openSprints()',
            f'(assignee in membersOf("devs") AND sprint in openSprints()) '
            f"AND ({SCOPE})",
        ),
        ("ORDER BY created DESC", f"{SCOPE} ORDER BY created DESC"),
        (
            "status = Open order by updated ASC",
            f"(status = Open) AND ({SCOPE}) order by updated ASC",
        ),
        # ORDER BY inside a string is not the clause.
        (
            'summary ~ "x ORDER BY y"',
            f'(summary ~ "x ORDER BY y") AND ({SCOPE})',
        ),
        # Words that merely contain "order" are not the clause.
        ("reorder = 1", f"(reorder = 1) AND ({SCOPE})"),
    ],
)
def test_composes_safe_queries(query: str | None, expected: str) -> None:
    assert and_scope_clause(query, SCOPE) == expected


def test_split_returns_order_by_clause() -> None:
    assert split_scoped_query("a = 1 ORDER BY b") == ("a = 1", "ORDER BY b")


def test_error_names_the_language() -> None:
    with pytest.raises(UnsafeQueryError, match="CQL query rejected"):
        and_scope_clause("type = page) OR (space = X", "space = A", "CQL")
