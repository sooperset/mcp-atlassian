"""Tests for the Jira Issues mixin."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.jira.issues import IssuesMixin
from mcp_atlassian.models.jira import JiraIssue


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
            return_value=JiraIssue(id="123", key="TEST-123", summary="Test Issue")
        )

        return mixin

    def test_get_issue_basic(self, issues_mixin):
        """Test basic functionality of get_issue."""
        # Setup mock
        mock_issue = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "Test Issue\n\nThis is a test issue",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
            },
        }
        issues_mixin.jira.issue.return_value = mock_issue

        # Call the method
        result = issues_mixin.get_issue("TEST-123")

        # Verify API calls
        issues_mixin.jira.issue.assert_called_once_with("TEST-123", expand=None)

        # Verify result structure
        assert isinstance(result, JiraIssue)
        assert result.key == "TEST-123"
        assert result.summary == "Test Issue"
        assert result.description == "Test Issue\n\nThis is a test issue"

        # Check Jira fields mapping
        assert result.status is not None
        assert result.status.name == "Open"
        assert result.issue_type.name == "Bug"

    def test_get_issue_with_comments(self, issues_mixin):
        """Test get_issue with comments."""
        # Mock the issue data
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "Test Description",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "created": "2023-01-01T00:00:00.000+0000",
                "updated": "2023-01-02T00:00:00.000+0000",
            },
        }

        # Mock the comments data
        comments_data = {
            "comments": [
                {
                    "id": "1",
                    "body": "This is a comment",
                    "author": {"displayName": "John Doe"},
                    "created": "2023-01-02T00:00:00.000+0000",
                    "updated": "2023-01-02T00:00:00.000+0000",
                }
            ]
        }

        # Set up the mocked responses
        issues_mixin.jira.issue.return_value = issue_data
        issues_mixin.jira.issue_get_comments.return_value = comments_data

        # Call the method
        issue = issues_mixin.get_issue("TEST-123")

        # Verify the API calls
        issues_mixin.jira.issue.assert_called_once_with("TEST-123", expand=None)
        issues_mixin.jira.issue_get_comments.assert_called_once_with("TEST-123")

        # Verify the issue
        assert issue.id == "12345"
        assert issue.key == "TEST-123"
        assert issue.summary == "Test Issue"
        assert issue.description == "Test Description"

        # Verify the comments
        assert len(issue.comments) == 1
        assert issue.comments[0].id == "1"
        assert issue.comments[0].body == "This is a comment"
        assert issue.comments[0].author.display_name == "John Doe"

    def test_get_issue_with_epic_info(self, issues_mixin):
        """Test getting an issue with epic information."""
        # Mock the issue data
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "Test Description",
                "status": {"name": "Open"},
                "issuetype": {"name": "Story"},
                "created": "2023-01-01T00:00:00.000+0000",
                "updated": "2023-01-02T00:00:00.000+0000",
                "customfield_10014": "EPIC-456",  # Epic Link field
            },
        }

        # Mock the epic data
        epic_data = {
            "id": "67890",
            "key": "EPIC-456",
            "fields": {
                "summary": "Test Epic",
                "customfield_10011": "Epic Name",  # Epic Name field
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Epic"},
            },
        }

        # Mock the comments data
        comments_data = {"comments": []}

        # Get field IDs for epics
        mock_field_ids = {
            "epic_link": "customfield_10014",
            "epic_name": "customfield_10011",
        }
        with patch.object(
            issues_mixin, "get_jira_field_ids", return_value=mock_field_ids
        ):
            # Setup the mocked responses
            issues_mixin.jira.issue.side_effect = [issue_data, epic_data]
            issues_mixin.jira.issue_get_comments.return_value = comments_data

            # Call the method
            issue = issues_mixin.get_issue("TEST-123")

            # Verify the API calls
            issues_mixin.jira.issue.assert_any_call("TEST-123", expand=None)
            issues_mixin.jira.issue.assert_any_call("EPIC-456")

            # Verify the issue
            assert issue.id == "12345"
            assert issue.key == "TEST-123"
            assert issue.summary == "Test Issue"

            # Verify the epic info was added
            assert issue.epic_key == "EPIC-456"
            assert issue.epic_name == "Epic Name"

    def test_get_issue_error_handling(self, issues_mixin):
        """Test error handling when getting an issue."""
        # Make the API call raise an exception
        issues_mixin.jira.issue.side_effect = Exception("API error")

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
        create_response = {"id": "12345", "key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        # Mock the issue data for get_issue
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "This is a test issue",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
            },
        }
        issues_mixin.jira.issue.return_value = issue_data

        # Mock empty comments
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

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
        issues_mixin.jira.issue.assert_called_once_with("TEST-123")

        # Verify the result
        assert document.id == "12345"
        assert document.key == "TEST-123"
        assert document.summary == "Test Issue"

    def test_create_issue_with_assignee(self, issues_mixin):
        """Test creating an issue with an assignee."""
        # Mock create_issue response
        create_response = {"key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        # Mock get_issue response
        issues_mixin.get_issue = MagicMock(
            return_value=JiraIssue(key="TEST-123", description="", summary="Test Issue")
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
            return_value=JiraIssue(key="EPIC-123", description="", summary="Test Epic")
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
        # Mock the issue data for get_issue
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "summary": "Updated Summary",
                "description": "This is a test issue",
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Bug"},
            },
        }
        issues_mixin.jira.issue.return_value = issue_data

        # Mock empty comments
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call the method
        document = issues_mixin.update_issue(
            issue_key="TEST-123", fields={"summary": "Updated Summary"}
        )

        # Verify the API calls
        issues_mixin.jira.update_issue.assert_called_once_with(
            issue_key="TEST-123", update={"fields": {"summary": "Updated Summary"}}
        )
        issues_mixin.jira.issue.assert_called_once_with("TEST-123")

        # Verify the result
        assert document.id == "12345"
        assert document.key == "TEST-123"
        assert document.summary == "Updated Summary"

    def test_update_issue_with_status(self, issues_mixin):
        """Test updating an issue with a status change."""
        # Mock get_issue response
        issues_mixin.get_issue = MagicMock(
            return_value=JiraIssue(key="TEST-123", description="")
        )

        # Mock available transitions
        issues_mixin.get_available_transitions = MagicMock(
            return_value=[
                {
                    "id": "21",
                    "name": "In Progress",
                    "to": {"name": "In Progress", "id": "3"},
                }
            ]
        )

        # Call the method with status in kwargs instead of fields
        issues_mixin.update_issue(issue_key="TEST-123", status="In Progress")

    def test_delete_issue(self, issues_mixin):
        """Test deleting an issue."""
        # Call the method
        result = issues_mixin.delete_issue("TEST-123")

        # Verify the API call
        issues_mixin.jira.delete_issue.assert_called_once_with("TEST-123")
        assert result is True

    def test_delete_issue_error(self, issues_mixin):
        """Test error handling when deleting an issue."""
        # Setup mock to throw exception
        issues_mixin.jira.delete_issue.side_effect = Exception("Delete failed")

        # Call the method and verify exception is raised correctly
        with pytest.raises(
            Exception, match="Error deleting issue TEST-123: Delete failed"
        ):
            issues_mixin.delete_issue("TEST-123")

    def test_get_jira_field_ids_cached(self, issues_mixin):
        """Test get_jira_field_ids returns cached field IDs."""
        # Setup mock cached data
        issues_mixin._field_ids_cache = {"key1": "value1"}

        # Call the method
        result = issues_mixin.get_jira_field_ids()

        # Verify result is the cached data
        assert result == {"key1": "value1"}
        issues_mixin.jira.get_all_fields.assert_not_called()

    def test_get_jira_field_ids_from_server(self, issues_mixin):
        """Test get_jira_field_ids fetches and processes field data from server."""
        # Setup field data mock
        field_data = [
            {
                "id": "customfield_10100",
                "name": "Epic Link",
                "schema": {"custom": "com.pyxis.greenhopper.jira:gh-epic-link"},
            }
        ]
        issues_mixin.jira.get_all_fields.return_value = field_data

        # Call the method
        result = issues_mixin.get_jira_field_ids()

        # Verify result
        assert "Epic Link" in result
        assert result["Epic Link"] == "customfield_10100"
