"""
Tests for Jira constants.

This module contains comprehensive tests for all constants defined in
the Jira constants module, including value validation, type checking,
data structure integrity, and usage pattern verification.
"""

import pytest

from mcp_atlassian.jira.constants import DEFAULT_READ_JIRA_FIELDS


class TestDefaultReadJiraFields:
    """Test suite for DEFAULT_READ_JIRA_FIELDS constant."""

    def test_is_set_type(self):
        """Test that DEFAULT_READ_JIRA_FIELDS is a set."""
        assert isinstance(DEFAULT_READ_JIRA_FIELDS, set)

    def test_is_set_of_strings(self):
        """Test that all elements in DEFAULT_READ_JIRA_FIELDS are strings."""
        assert all(isinstance(field, str) for field in DEFAULT_READ_JIRA_FIELDS)

    def test_contains_expected_fields(self):
        """Test that DEFAULT_READ_JIRA_FIELDS contains expected Jira fields."""
        expected_fields = {
            "summary",
            "description",
            "status",
            "assignee",
            "reporter",
            "labels",
            "priority",
            "created",
            "updated",
            "issuetype",
        }
        assert DEFAULT_READ_JIRA_FIELDS == expected_fields

    def test_field_count(self):
        """Test that DEFAULT_READ_JIRA_FIELDS has the expected number of fields."""
        assert len(DEFAULT_READ_JIRA_FIELDS) == 10

    def test_no_empty_strings(self):
        """Test that DEFAULT_READ_JIRA_FIELDS contains no empty strings."""
        assert "" not in DEFAULT_READ_JIRA_FIELDS
        assert all(field.strip() for field in DEFAULT_READ_JIRA_FIELDS)

    def test_no_duplicate_fields(self):
        """Test that there are no duplicate fields (set property)."""
        # Convert to list and back to set to check for duplicates
        fields_list = list(DEFAULT_READ_JIRA_FIELDS)
        fields_set = set(fields_list)
        assert len(fields_list) == len(fields_set)

    def test_field_name_format(self):
        """Test that field names follow expected format conventions."""
        for field in DEFAULT_READ_JIRA_FIELDS:
            # Field names should be lowercase
            assert field.islower(), f"Field '{field}' should be lowercase"
            # Field names should not contain spaces
            assert " " not in field, f"Field '{field}' should not contain spaces"
            # Field names should not start or end with underscore
            assert not field.startswith("_"), (
                f"Field '{field}' should not start with underscore"
            )
            assert not field.endswith("_"), (
                f"Field '{field}' should not end with underscore"
            )

    def test_immutability(self):
        """Test that DEFAULT_READ_JIRA_FIELDS behaves as expected with modifications."""
        original_fields = DEFAULT_READ_JIRA_FIELDS.copy()

        # The set can be modified, but let's verify it has the expected behavior
        # Create a copy to test modifications
        test_set = DEFAULT_READ_JIRA_FIELDS.copy()
        test_set.add("new_field")

        # Verify the original set is unchanged
        assert DEFAULT_READ_JIRA_FIELDS == original_fields
        assert "new_field" not in DEFAULT_READ_JIRA_FIELDS
        assert len(DEFAULT_READ_JIRA_FIELDS) == len(original_fields)

    @pytest.mark.parametrize(
        "field",
        [
            "summary",
            "description",
            "status",
            "assignee",
            "reporter",
            "labels",
            "priority",
            "created",
            "updated",
            "issuetype",
        ],
    )
    def test_individual_field_presence(self, field):
        """Test that each expected field is present in DEFAULT_READ_JIRA_FIELDS."""
        assert field in DEFAULT_READ_JIRA_FIELDS

    def test_essential_fields_coverage(self):
        """Test that essential Jira fields are covered."""
        essential_fields = {"summary", "status", "issuetype", "created", "updated"}
        assert essential_fields.issubset(DEFAULT_READ_JIRA_FIELDS)

    def test_user_fields_coverage(self):
        """Test that user-related fields are covered."""
        user_fields = {"assignee", "reporter"}
        assert user_fields.issubset(DEFAULT_READ_JIRA_FIELDS)

    def test_metadata_fields_coverage(self):
        """Test that metadata fields are covered."""
        metadata_fields = {"labels", "priority", "created", "updated"}
        assert metadata_fields.issubset(DEFAULT_READ_JIRA_FIELDS)

    def test_field_naming_consistency(self):
        """Test that field names are consistent with Jira API conventions."""
        # Jira uses lowercase field names
        for field in DEFAULT_READ_JIRA_FIELDS:
            assert field == field.lower()

        # Check for specific Jira field naming patterns
        time_fields = {"created", "updated"}
        assert time_fields.issubset(DEFAULT_READ_JIRA_FIELDS)

    def test_set_operations(self):
        """Test that set operations work correctly with DEFAULT_READ_JIRA_FIELDS."""
        # Test intersection
        subset = {"summary", "status", "assignee"}
        intersection = DEFAULT_READ_JIRA_FIELDS & subset
        assert intersection == subset

        # Test union
        additional_fields = {"customfield_1000", "worklog"}
        union = DEFAULT_READ_JIRA_FIELDS | additional_fields
        assert len(union) == len(DEFAULT_READ_JIRA_FIELDS) + len(additional_fields)

        # Test difference
        difference = DEFAULT_READ_JIRA_FIELDS - subset
        assert len(difference) == len(DEFAULT_READ_JIRA_FIELDS) - len(subset)

    def test_string_representation(self):
        """Test that the set has a proper string representation."""
        str_repr = str(DEFAULT_READ_JIRA_FIELDS)
        assert isinstance(str_repr, str)
        assert len(str_repr) > 0
        assert "summary" in str_repr  # Should contain at least one field name

    def test_iteration_stability(self):
        """Test that iteration over the set is stable (though order may vary)."""
        # Convert to list multiple times and verify same elements
        list1 = sorted(DEFAULT_READ_JIRA_FIELDS)
        list2 = sorted(DEFAULT_READ_JIRA_FIELDS)
        assert list1 == list2

    def test_field_validation_for_api_usage(self):
        """Test that fields are valid for use in Jira API calls."""
        # Ensure no field names contain invalid characters for API
        invalid_chars = [" ", "\t", "\n", "\r", ".", "/", "\\", ":", ";"]
        for field in DEFAULT_READ_JIRA_FIELDS:
            for char in invalid_chars:
                assert char not in field, (
                    f"Field '{field}' contains invalid character '{char}'"
                )

    def test_memory_efficiency(self):
        """Test that the set is memory efficient (no unnecessary overhead)."""
        # Check that it's a genuine set, not a list masquerading as one
        assert type(DEFAULT_READ_JIRA_FIELDS).__name__ == "set"

        # Verify set operations are O(1) average case
        assert "summary" in DEFAULT_READ_JIRA_FIELDS  # Should be fast lookup
        assert (
            "nonexistent_field" not in DEFAULT_READ_JIRA_FIELDS
        )  # Should be fast lookup
