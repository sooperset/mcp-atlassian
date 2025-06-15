"""Tests for Confluence constants.

Focused tests for Confluence constants, validating correct values and business logic.
"""

from mcp_atlassian.confluence.constants import RESERVED_CQL_WORDS


class TestReservedCqlWords:
    """Test suite for RESERVED_CQL_WORDS constant."""

    def test_type_and_structure(self):
        """Test that RESERVED_CQL_WORDS is a set of strings."""
        assert isinstance(RESERVED_CQL_WORDS, set)
        assert all(isinstance(word, str) for word in RESERVED_CQL_WORDS)
        assert len(RESERVED_CQL_WORDS) == 41

    def test_contains_expected_cql_words(self):
        """Test that RESERVED_CQL_WORDS contains the correct CQL reserved words."""
        expected_words = {
            "after",
            "and",
            "as",
            "avg",
            "before",
            "begin",
            "by",
            "commit",
            "contains",
            "count",
            "distinct",
            "else",
            "empty",
            "end",
            "explain",
            "from",
            "having",
            "if",
            "in",
            "inner",
            "insert",
            "into",
            "is",
            "isnull",
            "left",
            "like",
            "limit",
            "max",
            "min",
            "not",
            "null",
            "or",
            "order",
            "outer",
            "right",
            "select",
            "sum",
            "then",
            "was",
            "where",
            "update",
        }
        assert RESERVED_CQL_WORDS == expected_words

    def test_sql_keywords_coverage(self):
        """Test that common SQL keywords are included."""
        sql_keywords = {
            "select",
            "from",
            "where",
            "and",
            "or",
            "not",
            "in",
            "like",
            "is",
            "null",
            "order",
            "by",
            "having",
            "count",
        }
        assert sql_keywords.issubset(RESERVED_CQL_WORDS)

    def test_cql_specific_keywords(self):
        """Test that CQL-specific keywords are included."""
        cql_specific = {"contains", "after", "before", "was", "empty"}
        assert cql_specific.issubset(RESERVED_CQL_WORDS)

    def test_word_format_validity(self):
        """Test that reserved words are valid for CQL usage."""
        for word in RESERVED_CQL_WORDS:
            # Words should be non-empty, lowercase, alphabetic only
            assert word and word.islower() and word.isalpha()
            assert len(word) >= 2  # Shortest valid words like "as", "by"
            assert " " not in word and "\t" not in word
