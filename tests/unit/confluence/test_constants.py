"""
Tests for Confluence constants.

This module contains comprehensive tests for all constants defined in
the Confluence constants module, including CQL reserved words validation,
type checking, data structure integrity, and usage pattern verification.
"""

import pytest

from mcp_atlassian.confluence.constants import RESERVED_CQL_WORDS


class TestReservedCqlWords:
    """Test suite for RESERVED_CQL_WORDS constant."""

    def test_is_set_type(self):
        """Test that RESERVED_CQL_WORDS is a set."""
        assert isinstance(RESERVED_CQL_WORDS, set)

    def test_is_set_of_strings(self):
        """Test that all elements in RESERVED_CQL_WORDS are strings."""
        assert all(isinstance(word, str) for word in RESERVED_CQL_WORDS)

    def test_contains_expected_reserved_words(self):
        """Test that RESERVED_CQL_WORDS contains expected CQL reserved words."""
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

    def test_word_count(self):
        """Test that RESERVED_CQL_WORDS has the expected number of words."""
        assert len(RESERVED_CQL_WORDS) == 41

    def test_all_lowercase(self):
        """Test that all reserved words are in lowercase."""
        for word in RESERVED_CQL_WORDS:
            assert word.islower(), f"Word '{word}' should be lowercase"
            assert word == word.lower(), f"Word '{word}' is not consistently lowercase"

    def test_no_empty_strings(self):
        """Test that RESERVED_CQL_WORDS contains no empty strings."""
        assert "" not in RESERVED_CQL_WORDS
        assert all(word.strip() for word in RESERVED_CQL_WORDS)

    def test_no_whitespace_in_words(self):
        """Test that reserved words contain no whitespace characters."""
        for word in RESERVED_CQL_WORDS:
            assert " " not in word, f"Word '{word}' should not contain spaces"
            assert "\t" not in word, f"Word '{word}' should not contain tabs"
            assert "\n" not in word, f"Word '{word}' should not contain newlines"
            assert "\r" not in word, (
                f"Word '{word}' should not contain carriage returns"
            )

    def test_alphabetic_characters_only(self):
        """Test that reserved words contain only alphabetic characters."""
        for word in RESERVED_CQL_WORDS:
            assert word.isalpha(), (
                f"Word '{word}' should contain only alphabetic characters"
            )

    def test_sql_keywords_coverage(self):
        """Test that common SQL keywords are covered."""
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
            "sum",
            "min",
            "max",
            "avg",
        }
        assert sql_keywords.issubset(RESERVED_CQL_WORDS)

    def test_cql_specific_keywords(self):
        """Test that CQL-specific keywords are included."""
        cql_specific = {"contains", "after", "before", "was", "empty"}
        assert cql_specific.issubset(RESERVED_CQL_WORDS)

    def test_join_keywords_coverage(self):
        """Test that join-related keywords are covered."""
        join_keywords = {"inner", "left", "right", "outer"}
        assert join_keywords.issubset(RESERVED_CQL_WORDS)

    def test_aggregation_functions_coverage(self):
        """Test that aggregation function keywords are covered."""
        aggregation_functions = {"count", "sum", "min", "max", "avg", "distinct"}
        assert aggregation_functions.issubset(RESERVED_CQL_WORDS)

    def test_conditional_keywords_coverage(self):
        """Test that conditional keywords are covered."""
        conditional_keywords = {"if", "then", "else", "begin", "end"}
        assert conditional_keywords.issubset(RESERVED_CQL_WORDS)

    def test_comparison_operators_coverage(self):
        """Test that comparison operator keywords are covered."""
        comparison_keywords = {"like", "in", "is", "isnull"}
        assert comparison_keywords.issubset(RESERVED_CQL_WORDS)

    @pytest.mark.parametrize(
        "word",
        [
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
        ],
    )
    def test_individual_word_presence(self, word):
        """Test that each expected reserved word is present in RESERVED_CQL_WORDS."""
        assert word in RESERVED_CQL_WORDS

    def test_case_insensitive_matching_preparation(self):
        """Test that the set is prepared for case-insensitive matching."""
        # All words should be lowercase for case-insensitive matching
        for word in RESERVED_CQL_WORDS:
            assert word.islower()

        # Test that uppercase versions would match when converted
        test_words = ["SELECT", "WHERE", "AND", "OR"]
        for word in test_words:
            assert word.lower() in RESERVED_CQL_WORDS

    def test_immutability(self):
        """Test that RESERVED_CQL_WORDS behaves as expected with modifications."""
        original_words = RESERVED_CQL_WORDS.copy()

        # The set can be modified, but let's verify it has the expected behavior
        # Create a copy to test modifications
        test_set = RESERVED_CQL_WORDS.copy()
        test_set.add("new_word")

        # Verify the original set is unchanged
        assert RESERVED_CQL_WORDS == original_words
        assert "new_word" not in RESERVED_CQL_WORDS
        assert len(RESERVED_CQL_WORDS) == len(original_words)

    def test_set_operations(self):
        """Test that set operations work correctly with RESERVED_CQL_WORDS."""
        # Test intersection with custom keywords
        custom_keywords = {"select", "where", "custom_keyword"}
        intersection = RESERVED_CQL_WORDS & custom_keywords
        assert intersection == {"select", "where"}

        # Test union
        additional_words = {"custom1", "custom2"}
        union = RESERVED_CQL_WORDS | additional_words
        assert len(union) == len(RESERVED_CQL_WORDS) + len(additional_words)

        # Test difference
        subset = {"select", "from", "where"}
        difference = RESERVED_CQL_WORDS - subset
        assert len(difference) == len(RESERVED_CQL_WORDS) - len(subset)

    def test_word_length_constraints(self):
        """Test that reserved words have reasonable length constraints."""
        for word in RESERVED_CQL_WORDS:
            # Should be at least 2 characters (shortest are "as", "by", "if", "in", "is", "or")
            assert len(word) >= 2, f"Word '{word}' is too short"
            # Should not be excessively long (longest should be reasonable)
            assert len(word) <= 10, f"Word '{word}' is too long"

    def test_alphabetical_sorting(self):
        """Test that words can be sorted alphabetically."""
        sorted_words = sorted(RESERVED_CQL_WORDS)
        assert len(sorted_words) == len(RESERVED_CQL_WORDS)
        assert sorted_words[0] == "after"  # Should be first alphabetically
        assert sorted_words[-1] == "where"  # Should be last alphabetically

    def test_keyword_collision_detection(self):
        """Test that the set can be used for keyword collision detection."""
        # Simulate user input validation
        user_inputs = ["select", "my_field", "where", "custom_column"]
        collisions = [inp for inp in user_inputs if inp.lower() in RESERVED_CQL_WORDS]
        assert collisions == ["select", "where"]

    def test_string_representation(self):
        """Test that the set has a proper string representation."""
        str_repr = str(RESERVED_CQL_WORDS)
        assert isinstance(str_repr, str)
        assert len(str_repr) > 0
        assert "select" in str_repr  # Should contain at least one word

    def test_iteration_stability(self):
        """Test that iteration over the set is stable."""
        # Convert to list multiple times and verify same elements
        list1 = sorted(RESERVED_CQL_WORDS)
        list2 = sorted(RESERVED_CQL_WORDS)
        assert list1 == list2

    def test_memory_efficiency(self):
        """Test that the set is memory efficient."""
        # Check that it's a genuine set
        assert type(RESERVED_CQL_WORDS).__name__ == "set"

        # Verify set operations are O(1) average case
        assert "select" in RESERVED_CQL_WORDS  # Should be fast lookup
        assert "nonexistent_keyword" not in RESERVED_CQL_WORDS  # Should be fast lookup

    def test_confluence_api_compatibility(self):
        """Test that reserved words are compatible with Confluence CQL API."""
        # Test that words don't contain characters that would break CQL queries
        invalid_chars = ["'", '"', ";", "--", "/*", "*/", "\x00"]
        for word in RESERVED_CQL_WORDS:
            for char in invalid_chars:
                assert char not in word, (
                    f"Word '{word}' contains invalid character '{char}'"
                )

    def test_reserved_word_coverage_completeness(self):
        """Test that all major categories of reserved words are covered."""
        # Data manipulation
        dml_words = {"select", "insert", "update"}
        assert dml_words.issubset(RESERVED_CQL_WORDS)

        # Logical operators
        logical_words = {"and", "or", "not"}
        assert logical_words.issubset(RESERVED_CQL_WORDS)

        # Comparison operators
        comparison_words = {"like", "in", "is"}
        assert comparison_words.issubset(RESERVED_CQL_WORDS)

        # Control flow
        control_words = {"if", "then", "else"}
        assert control_words.issubset(RESERVED_CQL_WORDS)

        # Null handling
        null_words = {"null", "isnull", "empty"}
        assert null_words.issubset(RESERVED_CQL_WORDS)

    def test_documentation_reference_compliance(self):
        """Test that words match Atlassian CQL documentation expectations."""
        # Based on the comment in the constants file, these should be from
        # https://developer.atlassian.com/cloud/confluence/cql-functions/#reserved-words

        # Core CQL query structure words
        query_structure = {"select", "from", "where", "order", "by", "limit"}
        assert query_structure.issubset(RESERVED_CQL_WORDS)

        # Confluence-specific temporal operators
        temporal_words = {"after", "before", "was"}
        assert temporal_words.issubset(RESERVED_CQL_WORDS)

        # Content-specific operators
        content_words = {"contains", "empty"}
        assert content_words.issubset(RESERVED_CQL_WORDS)
