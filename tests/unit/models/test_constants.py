"""Tests for model constants.

Focused tests for model constants, validating correct values and business logic.
"""

from mcp_atlassian.models.constants import (
    # Confluence defaults
    CONFLUENCE_DEFAULT_ID,
    CONFLUENCE_DEFAULT_SPACE,
    CONFLUENCE_DEFAULT_VERSION,
    # Date/Time defaults
    DEFAULT_TIMESTAMP,
    # Common defaults
    EMPTY_STRING,
    # Jira defaults
    JIRA_DEFAULT_ID,
    JIRA_DEFAULT_ISSUE_TYPE,
    JIRA_DEFAULT_KEY,
    JIRA_DEFAULT_PRIORITY,
    JIRA_DEFAULT_PROJECT,
    JIRA_DEFAULT_STATUS,
    NONE_VALUE,
    UNASSIGNED,
    UNKNOWN,
)


class TestCommonDefaults:
    """Test suite for common default constants."""

    def test_string_constants_values(self):
        """Test that common string constants have expected values."""
        assert EMPTY_STRING == ""
        assert UNKNOWN == "Unknown"
        assert UNASSIGNED == "Unassigned"
        assert NONE_VALUE == "None"

    def test_string_constants_types(self):
        """Test that all string constants are strings."""
        assert isinstance(EMPTY_STRING, str)
        assert isinstance(UNKNOWN, str)
        assert isinstance(UNASSIGNED, str)
        assert isinstance(NONE_VALUE, str)


class TestJiraDefaults:
    """Test suite for Jira default constants."""

    def test_jira_id_and_key_values(self):
        """Test Jira ID and key default values."""
        assert JIRA_DEFAULT_ID == "0"
        assert JIRA_DEFAULT_KEY == "UNKNOWN-0"
        assert JIRA_DEFAULT_PROJECT == "0"

    def test_jira_default_dict_structures(self):
        """Test that Jira default dictionaries have correct structure."""
        # Status
        assert isinstance(JIRA_DEFAULT_STATUS, dict)
        assert JIRA_DEFAULT_STATUS == {"name": UNKNOWN, "id": JIRA_DEFAULT_ID}

        # Priority
        assert isinstance(JIRA_DEFAULT_PRIORITY, dict)
        assert JIRA_DEFAULT_PRIORITY == {"name": NONE_VALUE, "id": JIRA_DEFAULT_ID}

        # Issue Type
        assert isinstance(JIRA_DEFAULT_ISSUE_TYPE, dict)
        assert JIRA_DEFAULT_ISSUE_TYPE == {"name": UNKNOWN, "id": JIRA_DEFAULT_ID}

    def test_jira_key_format(self):
        """Test that Jira key follows expected format."""
        parts = JIRA_DEFAULT_KEY.split("-")
        assert len(parts) == 2
        assert parts[0] == "UNKNOWN"
        assert parts[1] == "0"


class TestConfluenceDefaults:
    """Test suite for Confluence default constants."""

    def test_confluence_id_value(self):
        """Test Confluence default ID value."""
        assert CONFLUENCE_DEFAULT_ID == "0"

    def test_confluence_default_space_structure(self):
        """Test that Confluence default space has correct structure."""
        assert isinstance(CONFLUENCE_DEFAULT_SPACE, dict)
        expected_space = {
            "key": EMPTY_STRING,
            "name": UNKNOWN,
            "id": CONFLUENCE_DEFAULT_ID,
        }
        assert CONFLUENCE_DEFAULT_SPACE == expected_space

    def test_confluence_default_version_structure(self):
        """Test that Confluence default version has correct structure."""
        assert isinstance(CONFLUENCE_DEFAULT_VERSION, dict)
        expected_version = {"number": 0, "when": EMPTY_STRING}
        assert CONFLUENCE_DEFAULT_VERSION == expected_version
        assert isinstance(CONFLUENCE_DEFAULT_VERSION["number"], int)


class TestDateTimeDefaults:
    """Test suite for date/time default constants."""

    def test_default_timestamp_format(self):
        """Test that DEFAULT_TIMESTAMP has expected format."""
        assert DEFAULT_TIMESTAMP == "1970-01-01T00:00:00.000+0000"
        assert isinstance(DEFAULT_TIMESTAMP, str)
        assert DEFAULT_TIMESTAMP.startswith("1970-01-01T")
        assert "+0000" in DEFAULT_TIMESTAMP


class TestCrossReferenceConsistency:
    """Test suite for consistency between related constants."""

    def test_id_consistency(self):
        """Test that default IDs are consistent across structures."""
        assert JIRA_DEFAULT_STATUS["id"] == JIRA_DEFAULT_ID
        assert JIRA_DEFAULT_PRIORITY["id"] == JIRA_DEFAULT_ID
        assert JIRA_DEFAULT_ISSUE_TYPE["id"] == JIRA_DEFAULT_ID
        assert CONFLUENCE_DEFAULT_SPACE["id"] == CONFLUENCE_DEFAULT_ID

    def test_semantic_usage_consistency(self):
        """Test that semantically similar fields use consistent values."""
        # UNKNOWN used for required fields with unknown values
        assert JIRA_DEFAULT_STATUS["name"] == UNKNOWN
        assert JIRA_DEFAULT_ISSUE_TYPE["name"] == UNKNOWN
        assert CONFLUENCE_DEFAULT_SPACE["name"] == UNKNOWN

        # NONE_VALUE used for nullable/optional fields
        assert JIRA_DEFAULT_PRIORITY["name"] == NONE_VALUE

        # EMPTY_STRING used for optional string fields
        assert CONFLUENCE_DEFAULT_SPACE["key"] == EMPTY_STRING
        assert CONFLUENCE_DEFAULT_VERSION["when"] == EMPTY_STRING
