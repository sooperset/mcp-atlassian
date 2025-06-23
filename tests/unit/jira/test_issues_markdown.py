"""Tests for markdown conversion in Jira issue operations."""

from unittest.mock import MagicMock, Mock

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.issues import IssuesMixin


class TestIssuesMarkdownConversion:
    """Tests for markdown to Jira conversion in issue operations."""

    @pytest.fixture
    def issues_mixin(self, jira_fetcher: JiraFetcher) -> IssuesMixin:
        """Create an IssuesMixin instance with mocked dependencies."""
        mixin = jira_fetcher

        # Mock the markdown conversion method
        mixin._markdown_to_jira = Mock(side_effect=lambda x: f"[CONVERTED] {x}")

        # Add other mock methods
        mixin._get_account_id = MagicMock(return_value="test-account-id")

        return mixin

    def test_create_issue_converts_markdown_description(
        self, issues_mixin: IssuesMixin
    ):
        """Test that create_issue converts markdown description to Jira format."""
        # Mock create_issue response
        create_response = {"key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        # Mock get_issue response
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "[CONVERTED] # Markdown Description",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Create issue with markdown description
        markdown_description = "# Markdown Description\n\nThis is **bold** text."
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description=markdown_description,
        )

        # Verify markdown conversion was called
        issues_mixin._markdown_to_jira.assert_called_once_with(markdown_description)

        # Verify the converted description was passed to API
        expected_fields = {
            "project": {"key": "TEST"},
            "summary": "Test Issue",
            "issuetype": {"name": "Bug"},
            "description": f"[CONVERTED] {markdown_description}",
        }
        issues_mixin.jira.create_issue.assert_called_once_with(fields=expected_fields)

        # Verify result
        assert issue.key == "TEST-123"

    def test_create_issue_with_empty_description(self, issues_mixin: IssuesMixin):
        """Test that create_issue handles empty description correctly."""
        # Mock create_issue response
        create_response = {"key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        # Mock get_issue response
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Create issue without description
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="",
        )

        # Verify markdown conversion was not called (empty string)
        issues_mixin._markdown_to_jira.assert_not_called()

        # Verify no description field was added
        call_args = issues_mixin.jira.create_issue.call_args[1]
        assert "description" not in call_args["fields"]

        # Verify result
        assert issue.key == "TEST-123"

    def test_update_issue_converts_markdown_in_fields(self, issues_mixin: IssuesMixin):
        """Test that update_issue converts markdown description when passed in fields dict."""
        # Mock the issue data for get_issue
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Updated Issue",
                "description": "[CONVERTED] # Updated Description",
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Bug"},
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Update issue with markdown description in fields
        markdown_description = "# Updated Description\n\nThis is *italic* text."
        issue = issues_mixin.update_issue(
            issue_key="TEST-123",
            fields={"description": markdown_description, "summary": "Updated Issue"},
        )

        # Verify markdown conversion was called
        issues_mixin._markdown_to_jira.assert_called_once_with(markdown_description)

        # Verify the converted description was passed to API
        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123",
            update={
                "fields": {
                    "description": f"[CONVERTED] {markdown_description}",
                    "summary": "Updated Issue",
                }
            },
        )

        # Verify result
        assert issue.key == "TEST-123"

    def test_update_issue_converts_markdown_in_kwargs(self, issues_mixin: IssuesMixin):
        """Test that update_issue converts markdown description when passed as kwarg."""
        # Mock the issue data for get_issue
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "[CONVERTED] ## Updated via kwargs",
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Bug"},
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Update issue with markdown description as kwarg
        markdown_description = (
            "## Updated via kwargs\n\nWith a [link](http://example.com)"
        )
        issue = issues_mixin.update_issue(
            issue_key="TEST-123", description=markdown_description
        )

        # Verify markdown conversion was called
        issues_mixin._markdown_to_jira.assert_called_once_with(markdown_description)

        # Verify the converted description was passed to API
        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123",
            update={"fields": {"description": f"[CONVERTED] {markdown_description}"}},
        )

        # Verify result
        assert issue.key == "TEST-123"

    def test_update_issue_with_multiple_fields_including_description(
        self, issues_mixin: IssuesMixin
    ):
        """Test update_issue with multiple fields including description."""
        # Mock the issue data for get_issue
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Updated Summary",
                "description": "[CONVERTED] Updated description",
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Update issue with multiple fields
        markdown_description = "Updated description with **emphasis**"
        issue = issues_mixin.update_issue(
            issue_key="TEST-123",
            fields={
                "summary": "Updated Summary",
                "priority": {"name": "High"},
            },
            description=markdown_description,  # As kwarg
        )

        # Verify markdown conversion was called
        issues_mixin._markdown_to_jira.assert_called_once_with(markdown_description)

        # Verify all fields were updated correctly
        expected_fields = {
            "summary": "Updated Summary",
            "priority": {"name": "High"},
            "description": f"[CONVERTED] {markdown_description}",
        }
        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123", update={"fields": expected_fields}
        )

        # Verify result
        assert issue.key == "TEST-123"

    def test_markdown_conversion_preserves_none_values(self, issues_mixin: IssuesMixin):
        """Test that None descriptions are not converted."""
        # Reset the mock to check for actual None handling
        issues_mixin._markdown_to_jira = Mock(
            side_effect=lambda x: f"[CONVERTED] {x}" if x else ""
        )

        # Mock create response
        create_response = {"key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        # Mock get_issue response
        issues_mixin.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {"summary": "Test", "issuetype": {"name": "Task"}},
        }

        # Create issue with None description (shouldn't add description field)
        issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Task",
            # description not provided (defaults to "")
        )

        # Verify markdown conversion was not called
        issues_mixin._markdown_to_jira.assert_not_called()

        # Verify no description field was added
        call_args = issues_mixin.jira.create_issue.call_args[1]
        assert "description" not in call_args["fields"]

    def test_create_issue_with_markdown_in_additional_fields(
        self, issues_mixin: IssuesMixin
    ):
        """Test that descriptions in additional_fields are NOT converted (edge case)."""
        # Mock field map for additional fields processing
        issues_mixin._generate_field_map = Mock(
            return_value={"mydescription": "customfield_10001"}
        )
        issues_mixin.get_field_by_id = Mock(
            return_value={"name": "MyDescription", "schema": {"type": "string"}}
        )

        # Mock create response
        create_response = {"key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response
        issues_mixin.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {"summary": "Test", "issuetype": {"name": "Task"}},
        }

        # Create issue with a custom field that happens to be named 'description'
        # This should NOT be converted as it's a different field
        issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Task",
            description="# Main Description",  # This SHOULD be converted
            mydescription="# Custom Field Description",  # This should NOT be converted
        )

        # Verify the main description was converted
        calls = issues_mixin._markdown_to_jira.call_args_list
        assert len(calls) == 1
        assert calls[0][0][0] == "# Main Description"

        # Verify fields
        create_call = issues_mixin.jira.create_issue.call_args[1]["fields"]
        assert create_call["description"] == "[CONVERTED] # Main Description"
        # Custom field should not be converted
        assert "customfield_10001" in create_call
        assert create_call["customfield_10001"] == "# Custom Field Description"
