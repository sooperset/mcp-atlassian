"""Tests for JQL utility functions (reserved word quoting)."""

import pytest

from mcp_atlassian.jira.utils import (
    quote_jql_identifier_if_needed,
    sanitize_jql_reserved_words,
)


class TestJQLQuoting:
    """Tests for quote_jql_identifier_if_needed()."""

    @pytest.mark.parametrize(
        "identifier, expected",
        [
            # Reserved words get quoted
            ("IF", '"IF"'),
            ("AND", '"AND"'),
            ("OR", '"OR"'),
            ("NOT", '"NOT"'),
            ("ORDER", '"ORDER"'),
            ("IN", '"IN"'),
            # Case-insensitive reserved word detection
            ("and", '"and"'),
            ("if", '"if"'),
            ("or", '"or"'),
            # Normal identifiers pass through
            ("TEST", "TEST"),
            ("MYPROJECT", "MYPROJECT"),
            ("SCRUM", "SCRUM"),
            # Starts with digit → quoted
            ("123P", '"123P"'),
            ("1ABC", '"1ABC"'),
            # Internal quote escaping
            ('my"key', '"my\\"key"'),
            # Internal backslash escaping
            ("my\\key", '"my\\\\key"'),
        ],
        ids=[
            "reserved-IF",
            "reserved-AND",
            "reserved-OR",
            "reserved-NOT",
            "reserved-ORDER",
            "reserved-IN",
            "reserved-lower-and",
            "reserved-lower-if",
            "reserved-lower-or",
            "normal-TEST",
            "normal-MYPROJECT",
            "normal-SCRUM",
            "digit-start-123P",
            "digit-start-1ABC",
            "internal-quote",
            "internal-backslash",
        ],
    )
    def test_quoting(self, identifier: str, expected: str) -> None:
        assert quote_jql_identifier_if_needed(identifier) == expected


class TestSanitizeJQL:
    """Tests for sanitize_jql_reserved_words()."""

    @pytest.mark.parametrize(
        "input_jql, expected_jql",
        [
            # project = reserved word → quoted
            (
                "project = IF AND status = Open",
                'project = "IF" AND status = Open',
            ),
            # project IN with reserved words → only reserved words quoted
            (
                "project IN (IF, AND, TEST)",
                'project IN ("IF", "AND", TEST)',
            ),
            # Already quoted → unchanged
            (
                'project = "IF"',
                'project = "IF"',
            ),
            # Non-reserved word → unchanged
            (
                "project = TEST",
                "project = TEST",
            ),
            # Case-insensitive matching
            (
                "PROJECT = if",
                'PROJECT = "if"',
            ),
            # ORDER BY preserved
            (
                "project = IF ORDER BY created",
                'project = "IF" ORDER BY created',
            ),
            # No project clause → unchanged
            (
                "status = Open",
                "status = Open",
            ),
            # String literal containing project = IF → NOT modified
            (
                'summary ~ "project = IF"',
                'summary ~ "project = IF"',
            ),
            # None → None
            (None, None),
            # Empty string → empty string
            ("", ""),
            # IN with extra whitespace
            (
                "project IN ( IF , AND )",
                'project IN ( "IF" , "AND" )',
            ),
            # Multiple project clauses
            (
                "project = IF OR project = OR",
                'project = "IF" OR project = "OR"',
            ),
            # project != reserved word (operator variation)
            (
                "project != IF AND status = Open",
                'project != "IF" AND status = Open',
            ),
            # project NOT IN with reserved words
            (
                "project NOT IN (IF, AND)",
                'project NOT IN ("IF", "AND")',
            ),
            # Already-quoted values in IN clause → preserved
            (
                'project IN ("IF", AND, TEST)',
                'project IN ("IF", "AND", TEST)',
            ),
            # Single-quoted string literal → NOT modified
            (
                "summary ~ 'project = IF'",
                "summary ~ 'project = IF'",
            ),
            # Single-quoted value in IN clause → preserved
            (
                "project IN ('IF', AND)",
                "project IN ('IF', \"AND\")",
            ),
        ],
        ids=[
            "equals-reserved",
            "in-mixed-reserved",
            "already-quoted",
            "non-reserved",
            "case-insensitive",
            "order-by-preserved",
            "no-project-clause",
            "string-literal-untouched",
            "none-input",
            "empty-string",
            "in-extra-whitespace",
            "multiple-project-clauses",
            "not-equals-reserved",
            "not-in-reserved",
            "in-mixed-quoted-unquoted",
            "single-quote-literal-untouched",
            "single-quote-in-preserved",
        ],
    )
    def test_sanitize(self, input_jql: str | None, expected_jql: str | None) -> None:
        assert sanitize_jql_reserved_words(input_jql) == expected_jql
