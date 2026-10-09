"""Tests for Jira constants.

Focused tests for Jira constants, validating correct values and business logic.
"""

from mcp_atlassian.jira.constants import DEFAULT_READ_JIRA_FIELDS


class TestDefaultReadJiraFields:
    """Test suite for DEFAULT_READ_JIRA_FIELDS constant."""

    def test_type_and_structure(self):
        """Test that DEFAULT_READ_JIRA_FIELDS is a set of strings."""
        assert isinstance(DEFAULT_READ_JIRA_FIELDS, set)
        assert all(isinstance(field, str) for field in DEFAULT_READ_JIRA_FIELDS)
        assert len(DEFAULT_READ_JIRA_FIELDS) == 11

    def test_contains_expected_jira_fields(self):
        """Test that DEFAULT_READ_JIRA_FIELDS contains the correct Jira fields."""
        expected_fields = {
            "summary",
            "description",
            "status",
            "assignee",
            "reporter",
            "labels",
            "versions",
            "priority",
            "created",
            "updated",
            "issuetype",
        }
        assert DEFAULT_READ_JIRA_FIELDS == expected_fields

    def test_essential_fields_present(self):
        """Test that essential Jira fields are included."""
        essential_fields = {"summary", "status", "issuetype"}
        assert essential_fields.issubset(DEFAULT_READ_JIRA_FIELDS)

    def test_field_format_validity(self):
        """Test that field names are valid for API usage."""
        for field in DEFAULT_READ_JIRA_FIELDS:
            # Fields should be non-empty, lowercase, no spaces
            assert field and field.islower()
            assert " " not in field
            assert not field.startswith("_")
            assert not field.endswith("_")

    def test_joined_default_is_alphabetically_sorted(self):
        """Regression test for #1662.

        Every call site that turns DEFAULT_READ_JIRA_FIELDS into the "fields"
        default of a tool schema must sort it first. DEFAULT_READ_JIRA_FIELDS is
        a set, so plain `",".join(DEFAULT_READ_JIRA_FIELDS)` iterates in an order
        that depends on the process's (randomised) hash seed: two worker
        processes of the same version then advertise two different tool
        schemas for jira_search/jira_get_issue/jira_get_board_issues/
        jira_get_sprint_issues, which MCP clients that fingerprint the tool
        catalog (e.g. GitHub Copilot CLI) treat as the catalog having changed
        mid-session, aborting the call.
        """
        joined = ",".join(sorted(DEFAULT_READ_JIRA_FIELDS))
        assert joined == (
            "assignee,created,description,issuetype,labels,priority,"
            "reporter,status,summary,updated,versions"
        )
        assert joined == ",".join(sorted(joined.split(",")))
