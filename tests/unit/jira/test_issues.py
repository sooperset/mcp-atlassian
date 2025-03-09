"""Tests for the Jira Issues mixin."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.document_types import Document
from mcp_atlassian.jira.issues import IssuesMixin


class TestIssuesMixin:
    """Tests for the IssuesMixin class."""

    @pytest.fixture
    def issues_mixin(self, jira_client):
        """Create an IssuesMixin instance with mocked dependencies."""
        mixin = IssuesMixin(config=jira_client.config)
        mixin.jira = jira_client.jira

        # Add mock methods that would be provided by other mixins
        mixin._get_account_id = MagicMock(return_value="test-account-id")
        mixin.get_available_transitions = MagicMock(
            return_value=[{"id": "10", "name": "In Progress"}]
        )
        mixin.transition_issue = MagicMock(
            return_value=Document(page_content="", metadata={})
        )

        return mixin

    def test_get_issue_basic(self, issues_mixin):
        """Test getting an issue with basic settings."""
        # Setup mock response for issue
        mock_issue = {
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "This is a test issue",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "created": "2023-01-01T00:00:00.000+0000",
                "reporter": {"displayName": "Test User"},
                "assignee": {"displayName": "Assigned User"},
            },
        }
        issues_mixin.jira.get_issue.return_value = mock_issue

        # Mock comments response
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call the method
        document = issues_mixin.get_issue("TEST-123")

        # Verify the API calls
        issues_mixin.jira.get_issue.assert_called_once_with("TEST-123", expand=None)
        issues_mixin.jira.issue_get_comments.assert_called_once_with("TEST-123")

        # Verify the result
        assert isinstance(document, Document)
        assert "TEST-123: Test Issue" in document.page_content
        assert "**Type**: Bug" in document.page_content
        assert "**Status**: Open" in document.page_content
        assert "**Created**: January 01, 2023" in document.page_content
        assert "**Reporter**: Test User" in document.page_content
        assert "**Assignee**: Assigned User" in document.page_content
        assert "## Description" in document.page_content
        assert "This is a test issue" in document.page_content

        # Verify metadata
        assert document.metadata["key"] == "TEST-123"
        assert document.metadata["title"] == "Test Issue"
        assert document.metadata["status"] == "Open"
        assert document.metadata["type"] == "Bug"
        assert document.metadata["created"] == "January 01, 2023"
        assert document.metadata["assignee"] == "Assigned User"
        assert document.metadata["comment_count"] == 0

    def test_get_issue_with_comments(self, issues_mixin):
        """Test getting an issue with comments."""
        # Setup mock response for issue
        mock_issue = {
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "This is a test issue",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "created": "2023-01-01T00:00:00.000+0000",
            },
        }
        issues_mixin.jira.get_issue.return_value = mock_issue

        # Mock comments response
        mock_comments = [
            {
                "author": {"displayName": "Comment Author"},
                "body": "This is a comment",
                "created": "2023-01-02T00:00:00.000+0000",
            }
        ]
        issues_mixin.jira.issue_get_comments.return_value = {"comments": mock_comments}

        # Call the method
        document = issues_mixin.get_issue("TEST-123")

        # Verify the result
        assert "## Comments" in document.page_content
        assert "**Comment Author** (January 02, 2023):" in document.page_content
        assert "This is a comment" in document.page_content
        assert document.metadata["comment_count"] == 1

    def test_get_issue_with_epic_info(self, issues_mixin):
        """Test getting an issue with epic information."""
        # Setup mock response for issue
        mock_issue = {
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "This is a test issue",
                "status": {"name": "Open"},
                "issuetype": {"name": "Story"},
                "created": "2023-01-01T00:00:00.000+0000",
                "customfield_10014": "EPIC-456",  # Epic Link field
            },
        }
        issues_mixin.jira.get_issue.return_value = mock_issue

        # Mock epic response
        mock_epic = {
            "key": "EPIC-456",
            "fields": {
                "summary": "Test Epic",
                "customfield_10011": "Epic Name",  # Epic Name field
            },
        }
        issues_mixin.jira.get_issue.side_effect = [mock_issue, mock_epic]

        # Mock comments response
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call the method
        document = issues_mixin.get_issue("TEST-123")

        # Verify the result
        assert "**Epic**: [EPIC-456] Test Epic" in document.page_content
        assert document.metadata["epic_key"] == "EPIC-456"
        assert document.metadata["epic_name"] == "Epic Name"
        assert document.metadata["epic_summary"] == "Test Epic"

    def test_get_issue_error_handling(self, issues_mixin):
        """Test error handling when getting an issue."""
        # Make the API call raise an exception
        issues_mixin.jira.get_issue.side_effect = Exception("API error")

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception, match="Error retrieving issue TEST-123: API error"
        ):
            issues_mixin.get_issue("TEST-123")

    def test_normalize_comment_limit(self, issues_mixin):
        """Test normalizing comment limit."""
        # Test with None
        assert issues_mixin._normalize_comment_limit(None) is None

        # Test with integer
        assert issues_mixin._normalize_comment_limit(5) == 5

        # Test with "all"
        assert issues_mixin._normalize_comment_limit("all") is None

        # Test with string number
        assert issues_mixin._normalize_comment_limit("10") == 10

        # Test with invalid string
        assert issues_mixin._normalize_comment_limit("invalid") == 10

    def test_create_issue_basic(self, issues_mixin):
        """Test creating a basic issue."""
        # Mock create_issue response
        create_response = {"key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        # Mock get_issue response for the newly created issue
        issues_mixin.get_issue = MagicMock(
            return_value=Document(page_content="", metadata={"key": "TEST-123"})
        )

        # Call the method
        document = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
        )

        # Verify the API calls
        issues_mixin.jira.create_issue.assert_called_once()
        expected_fields = {
            "project": {"key": "TEST"},
            "summary": "Test Issue",
            "issuetype": {"name": "Bug"},
            "description": "This is a test issue",
        }
        actual_fields = issues_mixin.jira.create_issue.call_args[1]["fields"]
        for key, value in expected_fields.items():
            assert actual_fields[key] == value

        # Verify get_issue was called to retrieve the created issue
        issues_mixin.get_issue.assert_called_once_with("TEST-123")

        # Verify the result
        assert document.metadata["key"] == "TEST-123"

    def test_create_issue_with_assignee(self, issues_mixin):
        """Test creating an issue with an assignee."""
        # Mock create_issue response
        create_response = {"key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        # Mock get_issue response
        issues_mixin.get_issue = MagicMock(
            return_value=Document(page_content="", metadata={"key": "TEST-123"})
        )

        # Use a config with is_cloud = True - can't directly set property
        issues_mixin.config = MagicMock()
        issues_mixin.config.is_cloud = True

        # Call the method
        issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            assignee="testuser",
        )

        # Verify the assignee was properly set
        fields = issues_mixin.jira.create_issue.call_args[1]["fields"]
        assert fields["assignee"] == {"accountId": "test-account-id"}

    def test_create_epic(self, issues_mixin):
        """Test creating an epic."""
        # Mock responses
        create_response = {"key": "EPIC-123"}
        issues_mixin.jira.create_issue.return_value = create_response
        issues_mixin.get_issue = MagicMock(
            return_value=Document(page_content="", metadata={"key": "EPIC-123"})
        )

        # Mock get_jira_field_ids
        with patch.object(
            issues_mixin,
            "get_jira_field_ids",
            return_value={"Epic Name": "customfield_10011"},
        ):
            # Call the method
            issues_mixin.create_issue(
                project_key="TEST",
                summary="Test Epic",
                issue_type="Epic",
            )

            # Verify epic fields were properly set
            fields = issues_mixin.jira.create_issue.call_args[1]["fields"]
            assert fields["customfield_10011"] == "Test Epic"

    def test_update_issue_basic(self, issues_mixin):
        """Test updating an issue with basic fields."""
        # Mock get_issue response
        issues_mixin.get_issue = MagicMock(
            return_value=Document(page_content="", metadata={"key": "TEST-123"})
        )

        # Call the method
        issues_mixin.update_issue(
            issue_key="TEST-123", fields={"summary": "Updated Summary"}
        )

        # Verify the API calls
        issues_mixin.jira.update_issue.assert_called_once_with(
            "TEST-123", fields={"summary": "Updated Summary"}
        )
        issues_mixin.get_issue.assert_called_once_with("TEST-123")

    def test_update_issue_with_status(self, issues_mixin):
        """Test updating an issue with a status change."""
        # Mock get_issue response
        issues_mixin.get_issue = MagicMock(
            return_value=Document(page_content="", metadata={"key": "TEST-123"})
        )

        # Call the method with status in kwargs instead of fields
        issues_mixin.update_issue(issue_key="TEST-123", status="In Progress")

        # Verify transition_issue was called
        issues_mixin.get_available_transitions.assert_called_once_with("TEST-123")
        issues_mixin.transition_issue.assert_called_once_with("TEST-123", "10")

    def test_delete_issue(self, issues_mixin):
        """Test deleting an issue."""
        # Call the method
        result = issues_mixin.delete_issue("TEST-123")

        # Verify the API call
        issues_mixin.jira.delete_issue.assert_called_once_with("TEST-123")
        assert result is True

    def test_delete_issue_error(self, issues_mixin):
        """Test error handling when deleting an issue."""
        # Make the API call raise an exception
        issues_mixin.jira.delete_issue.side_effect = Exception("API error")

        # Call the method and verify it raises the expected exception
        with pytest.raises(Exception, match="Error deleting issue TEST-123: API error"):
            issues_mixin.delete_issue("TEST-123")

    def test_get_jira_field_ids_cached(self, issues_mixin):
        """Test get_jira_field_ids returns cached values if available."""
        # Set up cached field IDs
        issues_mixin._field_ids_cache = {
            "Summary": "summary",
            "Description": "description",
        }

        # Call the method
        field_ids = issues_mixin.get_jira_field_ids()

        # Verify the result
        assert field_ids == {"Summary": "summary", "Description": "description"}
        assert issues_mixin.jira.get_all_fields.call_count == 0

    def test_get_jira_field_ids_from_server(self, issues_mixin):
        """Test get_jira_field_ids fetches from server if cache is empty."""
        # Ensure cache is empty
        issues_mixin._field_ids_cache = {}

        # Mock get_all_fields response
        issues_mixin.jira.get_all_fields.return_value = [
            {"id": "summary", "name": "Summary"},
            {"id": "description", "name": "Description"},
        ]

        # Call the method
        field_ids = issues_mixin.get_jira_field_ids()

        # Verify the result
        assert field_ids == {"Summary": "summary", "Description": "description"}
        assert issues_mixin.jira.get_all_fields.call_count == 1

    def test_link_issue_to_epic(self, issues_mixin):
        """Test linking an issue to an epic."""
        # Mock get_issue responses
        issue_response = {"key": "TEST-123"}
        epic_response = {"key": "EPIC-456", "fields": {"issuetype": {"name": "Epic"}}}
        issues_mixin.jira.get_issue.side_effect = [issue_response, epic_response]

        # Mock get_jira_field_ids to return the Epic Link field
        with patch.object(
            issues_mixin,
            "get_jira_field_ids",
            return_value={"Epic Link": "customfield_10014"},
        ):
            # Mock get_issue for the return value
            issues_mixin.get_issue = MagicMock(
                return_value=Document(page_content="", metadata={"key": "TEST-123"})
            )

            # Call the method
            document = issues_mixin.link_issue_to_epic("TEST-123", "EPIC-456")

            # Verify the API calls
            assert issues_mixin.jira.get_issue.call_count == 2
            issues_mixin.jira.update_issue.assert_called_once_with(
                "TEST-123", fields={"customfield_10014": "EPIC-456"}
            )
            issues_mixin.get_issue.assert_called_once_with("TEST-123")

            # Verify the result
            assert isinstance(document, Document)

    def test_link_issue_to_invalid_epic(self, issues_mixin):
        """Test error when linking to an invalid epic."""
        # Mock get_issue responses to return a non-epic
        issue_response = {"key": "TEST-123"}
        non_epic_response = {
            "key": "TEST-456",
            "fields": {"issuetype": {"name": "Story"}},  # Not an epic
        }
        issues_mixin.jira.get_issue.side_effect = [issue_response, non_epic_response]

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception, match="Error linking issue to epic: TEST-456 is not an Epic"
        ):
            issues_mixin.link_issue_to_epic("TEST-123", "TEST-456")
