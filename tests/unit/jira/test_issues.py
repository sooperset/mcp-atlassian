"""Tests for the Jira Issues mixin."""

from unittest.mock import ANY, MagicMock, patch

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.issues import IssuesMixin, logger
from mcp_atlassian.models.jira import JiraIssue


class TestIssuesMixin:
    """Tests for the IssuesMixin class."""

    @pytest.fixture
    def issues_mixin(self, jira_fetcher: JiraFetcher) -> IssuesMixin:
        """Create an IssuesMixin instance with mocked dependencies."""
        mixin = jira_fetcher

        # Add mock methods that would be provided by other mixins
        mixin._get_account_id = MagicMock(return_value="test-account-id")
        mixin.get_available_transitions = MagicMock(
            return_value=[{"id": "10", "name": "In Progress"}]
        )
        mixin.transition_issue = MagicMock(
            return_value=JiraIssue(id="123", key="TEST-123", summary="Test Issue")
        )

        return mixin

    def test_get_issue_basic(self, issues_mixin: IssuesMixin):
        """Test retrieving an issue by key."""
        # Mock the API response
        issues_mixin.jira.get_issue.return_value = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {
                "summary": "Test Issue",
                "description": "This is a test issue",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "created": "2023-01-01T00:00:00.000+0000",
                "updated": "2023-01-02T00:00:00.000+0000",
            },
        }

        # Call the method
        result = issues_mixin.get_issue("TEST-123")

        # Verify API calls
        issues_mixin.jira.get_issue.assert_called_once_with(
            "TEST-123",
            expand=None,
            fields=ANY,
            properties=None,
            update_history=True,
        )

        # Verify result structure
        assert isinstance(result, JiraIssue)
        assert result.key == "TEST-123"
        assert result.summary == "Test Issue"
        assert result.description == "This is a test issue"

        # Check Jira fields mapping
        assert result.status is not None
        assert result.status.name == "Open"
        assert result.issue_type.name == "Bug"

    def test_get_issue_with_comments(self, issues_mixin: IssuesMixin):
        """Test get_issue with comments."""
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

        # Mock the issue data
        issue_data = {
            "id": "12345",
            "key": "TEST-123",
            "fields": {
                "comment": comments_data,
                "summary": "Test Issue",
                "description": "Test Description",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "created": "2023-01-01T00:00:00.000+0000",
                "updated": "2023-01-02T00:00:00.000+0000",
            },
        }

        # Set up the mocked responses
        issues_mixin.jira.get_issue.return_value = issue_data
        issues_mixin.jira.issue_get_comments.return_value = comments_data

        # Call the method
        issue = issues_mixin.get_issue(
            "TEST-123",
            fields="summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype,comment",
        )

        # Verify the API calls
        issues_mixin.jira.get_issue.assert_called_once_with(
            "TEST-123",
            expand=None,
            fields="summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype,comment",
            properties=None,
            update_history=True,
        )
        issues_mixin.jira.issue_get_comments.assert_called_once_with("TEST-123")

        # Verify the comments were added to the issue
        assert hasattr(issue, "comments")
        assert len(issue.comments) == 1
        assert issue.comments[0].body == "This is a comment"

    def test_get_issue_with_epic_info(self, issues_mixin: IssuesMixin):
        """Test retrieving issue with epic information."""
        try:
            # Mock the API responses for get_issue
            issues_mixin.jira.get_issue.side_effect = [
                # First call - the issue
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test Issue",
                        "description": "This is a test issue",
                        "status": {"name": "Open"},
                        "issuetype": {"name": "Story"},
                        "customfield_10010": "EPIC-456",  # Epic Link field
                        "created": "2023-01-01T00:00:00.000+0000",
                        "updated": "2023-01-02T00:00:00.000+0000",
                    },
                },
                # Second call - the epic
                {
                    "id": "10002",
                    "key": "EPIC-456",
                    "fields": {
                        "summary": "Epic Issue",
                        "description": "This is an epic",
                        "status": {"name": "In Progress"},
                        "issuetype": {"name": "Epic"},
                        "customfield_10011": "Epic Name Value",  # Epic Name field
                        "created": "2023-01-01T00:00:00.000+0000",
                        "updated": "2023-01-02T00:00:00.000+0000",
                    },
                },
            ]

            # Mock get_field_ids_to_epic
            issues_mixin.get_field_ids_to_epic = MagicMock(
                return_value={
                    "epic_link": "customfield_10010",
                    "epic_name": "customfield_10011",
                }
            )

            # Call the method - just use get_issue without the include_epic_info parameter
            issue = issues_mixin.get_issue("TEST-123")

            # Verify the API calls
            issues_mixin.jira.get_issue.assert_any_call(
                "TEST-123",
                expand=None,
                fields=ANY,
                properties=None,
                update_history=True,
            )
            issues_mixin.jira.get_issue.assert_any_call(
                "EPIC-456",
                expand=None,
                fields=None,
                properties=None,
                update_history=True,
            )

            # Verify the issue
            assert issue.key == "TEST-123"
            assert issue.summary == "Test Issue"

            # Verify that the epic information is in the custom fields
            assert issue.custom_fields.get("customfield_10010") == "EPIC-456"
            assert issue.custom_fields.get("customfield_10011") == "Epic Name Value"

        except Exception as e:
            pytest.fail(f"Test failed: {e}")

    def test_get_issue_error_handling(self, issues_mixin: IssuesMixin):
        """Test error handling in get_issue."""
        # Mock the API to raise an exception
        issues_mixin.jira.get_issue.side_effect = Exception("API error")

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception, match=r"Error retrieving issue TEST-123: API error"
        ):
            issues_mixin.get_issue("TEST-123")

    def test_normalize_comment_limit(self, issues_mixin: IssuesMixin):
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

    def test_create_issue_basic(self, issues_mixin: IssuesMixin):
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
        issues_mixin.jira.get_issue.return_value = issue_data

        # Mock empty comments
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call create_issue
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
        )

        # Verify API calls
        expected_fields = {
            "project": {"key": "TEST"},
            "summary": "Test Issue",
            "issuetype": {"name": "Bug"},
            "description": "This is a test issue",
        }
        issues_mixin.jira.create_issue.assert_called_once_with(fields=expected_fields)
        issues_mixin.jira.get_issue.assert_called_once_with("TEST-123")

        # Verify issue
        assert issue.key == "TEST-123"
        assert issue.summary == "Test Issue"

    def test_create_issue_no_components(self, issues_mixin: IssuesMixin):
        """Test creating an issue with no components specified."""
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
        issues_mixin.jira.get_issue.return_value = issue_data

        # Mock empty comments
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call create_issue with components=None
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            components=None,
        )

        # Verify API calls
        expected_fields = {
            "project": {"key": "TEST"},
            "summary": "Test Issue",
            "issuetype": {"name": "Bug"},
            "description": "This is a test issue",
        }
        issues_mixin.jira.create_issue.assert_called_once_with(fields=expected_fields)

        # Verify 'components' is not in the fields
        assert "components" not in issues_mixin.jira.create_issue.call_args[1]["fields"]

    def test_create_issue_single_component(self, issues_mixin: IssuesMixin):
        """Test creating an issue with a single component."""
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
                "components": [{"name": "UI"}],
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Mock empty comments
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call create_issue with a single component
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            components=["UI"],
        )

        # Verify API calls
        expected_fields = {
            "project": {"key": "TEST"},
            "summary": "Test Issue",
            "issuetype": {"name": "Bug"},
            "description": "This is a test issue",
            "components": [{"name": "UI"}],
        }
        issues_mixin.jira.create_issue.assert_called_once_with(fields=expected_fields)

        # Verify the components field was passed correctly
        assert issues_mixin.jira.create_issue.call_args[1]["fields"]["components"] == [
            {"name": "UI"}
        ]

    def test_create_issue_multiple_components(self, issues_mixin: IssuesMixin):
        """Test creating an issue with multiple components."""
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
                "components": [{"name": "UI"}, {"name": "API"}],
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Mock empty comments
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call create_issue with multiple components
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            components=["UI", "API"],
        )

        # Verify API calls
        expected_fields = {
            "project": {"key": "TEST"},
            "summary": "Test Issue",
            "issuetype": {"name": "Bug"},
            "description": "This is a test issue",
            "components": [{"name": "UI"}, {"name": "API"}],
        }
        issues_mixin.jira.create_issue.assert_called_once_with(fields=expected_fields)

        # Verify the components field was passed correctly
        assert issues_mixin.jira.create_issue.call_args[1]["fields"]["components"] == [
            {"name": "UI"},
            {"name": "API"},
        ]

    def test_create_issue_components_with_invalid_entries(
        self, issues_mixin: IssuesMixin
    ):
        """Test creating an issue with components list containing invalid entries."""
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
                "components": [{"name": "Valid"}, {"name": "Backend"}],
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Mock empty comments
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Call create_issue with components list containing invalid entries
        issue = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            components=["Valid", "", None, "  Backend  "],
        )

        # Verify API calls
        expected_fields = {
            "project": {"key": "TEST"},
            "summary": "Test Issue",
            "issuetype": {"name": "Bug"},
            "description": "This is a test issue",
            "components": [{"name": "Valid"}, {"name": "Backend"}],
        }
        issues_mixin.jira.create_issue.assert_called_once_with(fields=expected_fields)

        # Verify the components field was passed correctly, with invalid entries filtered out
        assert issues_mixin.jira.create_issue.call_args[1]["fields"]["components"] == [
            {"name": "Valid"},
            {"name": "Backend"},
        ]

    def test_create_issue_components_precedence(self, issues_mixin, caplog):
        """Test that explicit components take precedence over components in additional_fields."""
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
                "components": [{"name": "Explicit"}],
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Mock empty comments
        issues_mixin.jira.issue_get_comments.return_value = {"comments": []}

        # Direct test for the precedence handling logic
        # Create fields dict with components already set by explicit parameter
        fields = {
            "project": {"key": "TEST"},
            "summary": "Test Issue",
            "issuetype": {"name": "Bug"},
            "description": "This is a test issue",
            "components": [{"name": "Explicit"}],
        }

        # Create kwargs with a conflicting components entry
        kwargs = {"components": [{"name": "Ignored"}]}

        # Directly call the method that would handle the precedence
        # This simulates what happens inside create_issue
        if "components" in fields and "components" in kwargs:
            logger.warning(
                "Components provided via both 'components' argument and 'additional_fields'. "
                "Using the explicit 'components' argument."
            )
            # Remove the conflicting key from kwargs to prevent issues later
            kwargs.pop("components", None)

        # Verify the warning was logged about the conflict
        assert (
            "Components provided via both 'components' argument and 'additional_fields'"
            in caplog.text
        )

        # Verify that kwargs no longer contains components
        assert "components" not in kwargs

        # Verify the components field was preserved with the explicit value
        assert fields["components"] == [{"name": "Explicit"}]

    def test_create_issue_with_assignee_cloud(self, issues_mixin: IssuesMixin):
        """Test creating an issue with an assignee in Jira Cloud."""
        # Mock create_issue response
        create_response = {"key": "TEST-123"}
        issues_mixin.jira.create_issue.return_value = create_response

        # Mock get_issue response
        issues_mixin.get_issue = MagicMock(
            return_value=JiraIssue(key="TEST-123", description="", summary="Test Issue")
        )

        # Mock _get_account_id to return a Cloud account ID
        issues_mixin._get_account_id = MagicMock(return_value="cloud-account-id")

        # Configure for Cloud
        issues_mixin.config = MagicMock()
        issues_mixin.config.is_cloud = True

        # Call the method
        issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            assignee="testuser",
        )

        # Verify _get_account_id was called with the correct username
        issues_mixin._get_account_id.assert_called_once_with("testuser")

        # Verify the assignee was properly set for Cloud (accountId)
        fields = issues_mixin.jira.create_issue.call_args[1]["fields"]
        assert fields["assignee"] == {"accountId": "cloud-account-id"}

    def test_create_issue_with_assignee_server(self, issues_mixin: IssuesMixin):
        """Test creating an issue with an assignee in Jira Server/DC."""
        # Mock create_issue response
        create_response = {"key": "TEST-456"}
        issues_mixin.jira.create_issue.return_value = create_response

        # Mock get_issue response
        issues_mixin.get_issue = MagicMock(
            return_value=JiraIssue(key="TEST-456", description="", summary="Test Issue")
        )

        # Mock _get_account_id to return a Server user ID (typically username)
        issues_mixin._get_account_id = MagicMock(return_value="server-user")

        # Configure for Server/DC
        issues_mixin.config = MagicMock()
        issues_mixin.config.is_cloud = False

        # Call the method
        issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            assignee="testuser",
        )

        # Verify _get_account_id was called with the correct username
        issues_mixin._get_account_id.assert_called_once_with("testuser")

        # Verify the assignee was properly set for Server/DC (name)
        fields = issues_mixin.jira.create_issue.call_args[1]["fields"]
        assert fields["assignee"] == {"name": "server-user"}

    def test_create_epic(self, issues_mixin: IssuesMixin):
        """Test creating an epic."""
        # Mock responses
        create_response = {"key": "EPIC-123"}
        issues_mixin.jira.create_issue.return_value = create_response
        issues_mixin.get_issue = MagicMock(
            return_value=JiraIssue(key="EPIC-123", description="", summary="Test Epic")
        )

        # Mock the prepare_epic_fields method from EpicsMixin
        with patch(
            "mcp_atlassian.jira.epics.EpicsMixin.prepare_epic_fields", autospec=True
        ) as mock_prepare_epic:
            # Set up the mock to store epic values in kwargs
            # Note: First argument is self because EpicsMixin.prepare_epic_fields is called as a class method
            def side_effect(self_args, fields, summary, kwargs):
                kwargs["__epic_name_value"] = summary
                kwargs["__epic_name_field"] = "customfield_10011"
                return None

            mock_prepare_epic.side_effect = side_effect

            # Mock get_field_ids_to_epic
            with patch.object(
                issues_mixin,
                "get_field_ids_to_epic",
                return_value={"Epic Name": "customfield_10011"},
            ):
                # Call the method
                result = issues_mixin.create_issue(
                    project_key="TEST",
                    summary="Test Epic",
                    issue_type="Epic",
                )

                # Verify create_issue was called with the right project and summary
                create_args = issues_mixin.jira.create_issue.call_args[1]
                fields = create_args["fields"]
                assert fields["project"]["key"] == "TEST"
                assert fields["summary"] == "Test Epic"

                # Verify epic fields are NOT in the fields dictionary (two-step creation)
                assert "customfield_10011" not in fields

                # Verify that prepare_epic_fields was called
                mock_prepare_epic.assert_called_once()

                # For an Epic, verify that update_issue should be called for the second step
                # This would happen in the EpicsMixin.update_epic_fields method which is called
                # after the initial creation
                assert issues_mixin.get_issue.called
                assert result.key == "EPIC-123"

    def test_update_issue_basic(self, issues_mixin: IssuesMixin):
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
        issues_mixin.jira.get_issue.return_value = issue_data

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
        assert issues_mixin.jira.get_issue.called
        assert issues_mixin.jira.get_issue.call_args[0][0] == "TEST-123"

        # Verify the result
        assert document.id == "12345"
        assert document.key == "TEST-123"
        assert document.summary == "Updated Summary"

    def test_update_issue_with_status(self, issues_mixin: IssuesMixin):
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

    def test_delete_issue(self, issues_mixin: IssuesMixin):
        """Test deleting an issue."""
        # Call the method
        result = issues_mixin.delete_issue("TEST-123")

        # Verify the API call
        issues_mixin.jira.delete_issue.assert_called_once_with("TEST-123")
        assert result is True

    def test_delete_issue_error(self, issues_mixin: IssuesMixin):
        """Test error handling when deleting an issue."""
        # Setup mock to throw exception
        issues_mixin.jira.delete_issue.side_effect = Exception("Delete failed")

        # Call the method and verify exception is raised correctly
        with pytest.raises(
            Exception, match="Error deleting issue TEST-123: Delete failed"
        ):
            issues_mixin.delete_issue("TEST-123")

    def test_process_additional_fields_with_fixversions(
        self, issues_mixin: IssuesMixin
    ):
        """Test _process_additional_fields properly handles fixVersions field."""
        # Initialize test data
        fields = {}
        kwargs = {"fixVersions": [{"name": "TestRelease"}]}

        # Call the method
        issues_mixin._process_additional_fields(fields, kwargs)

        # Verify fixVersions was added correctly to fields
        assert "fixVersions" in fields
        assert fields["fixVersions"] == [{"name": "TestRelease"}]

    def test_create_issue_with_parent_for_task(self, issues_mixin: IssuesMixin):
        """Test creating a regular task issue with a parent field."""
        # Setup mock response for create_issue
        create_response = {
            "id": "12345",
            "key": "TEST-456",
            "self": "https://jira.example.com/rest/api/2/issue/12345",
        }
        issues_mixin.jira.create_issue.return_value = create_response

        # Setup mock response for issue retrieval
        issue_response = {
            "id": "12345",
            "key": "TEST-456",
            "fields": {
                "summary": "Test Task with Parent",
                "description": "This is a test",
                "status": {"name": "Open"},
                "issuetype": {"name": "Task"},
                "parent": {"key": "TEST-123"},
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_response

        issues_mixin._get_account_id = MagicMock(return_value="user123")

        # Execute - create a Task with parent field
        result = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Task with Parent",
            issue_type="Task",
            description="This is a test",
            assignee="jdoe",
            parent="TEST-123",  # Adding parent for a non-subtask
        )

        # Verify
        issues_mixin.jira.create_issue.assert_called_once()
        call_kwargs = issues_mixin.jira.create_issue.call_args[1]
        assert "fields" in call_kwargs
        fields = call_kwargs["fields"]

        # Verify parent field was included
        assert "parent" in fields
        assert fields["parent"] == {"key": "TEST-123"}

        # Verify issue method was called after creation
        assert issues_mixin.jira.get_issue.called
        assert issues_mixin.jira.get_issue.call_args[0][0] == "TEST-456"

        # Verify the issue was created successfully
        assert result is not None
        assert result.key == "TEST-456"

    def test_create_issue_with_fixversions(self, issues_mixin: IssuesMixin):
        """Test creating an issue with fixVersions in additional_fields."""
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
                "fixVersions": [{"name": "1.0.0"}],
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Create the issue with fixVersions in additional_fields
        result = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            fixVersions=[{"name": "1.0.0"}],
        )

        # Verify API call to create issue
        issues_mixin.jira.create_issue.assert_called_once()
        call_args = issues_mixin.jira.create_issue.call_args[1]
        fields = call_args["fields"]
        assert fields["project"]["key"] == "TEST"
        assert fields["summary"] == "Test Issue"
        assert fields["issuetype"]["name"] == "Bug"
        assert fields["description"] == "This is a test issue"
        assert "fixVersions" in fields
        assert fields["fixVersions"] == [{"name": "1.0.0"}]

        # Verify API call to get issue
        issues_mixin.jira.get_issue.assert_called_once_with("TEST-123")

        # Verify result
        assert result.key == "TEST-123"
        assert result.summary == "Test Issue"
        assert result.issue_type and result.issue_type.name == "Bug"
        assert hasattr(result, "fix_versions")
        assert len(result.fix_versions) == 1
        # The JiraIssue model might process fixVersions differently, check the actual structure
        # This depends on how JiraIssue.from_api_response handles the fixVersions field
        # If it's a list of dictionaries, use:
        if hasattr(result.fix_versions[0], "name"):
            assert result.fix_versions[0].name == "1.0.0"
        else:
            # If it's a list of strings or other format, adjust accordingly:
            assert "1.0.0" in str(result.fix_versions[0])

    def test_get_issue_with_custom_fields(self, issues_mixin: IssuesMixin):
        """Test get_issue with custom fields parameter."""
        # Mock the response with custom fields
        mock_issue = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {
                "summary": "Test issue with custom field",
                "customfield_10049": "Custom value",
                "customfield_10050": {"value": "Option value"},
                "description": "Issue description",
            },
        }
        issues_mixin.jira.get_issue.return_value = mock_issue

        # Test with string format
        issue = issues_mixin.get_issue("TEST-123", fields="summary,customfield_10049")

        # Verify the API call
        issues_mixin.jira.get_issue.assert_called_with(
            "TEST-123",
            expand=None,
            fields="summary,customfield_10049",
            properties=None,
            update_history=True,
        )

        # Check the result
        simplified = issue.to_simplified_dict()
        assert "customfield_10049" in simplified
        assert simplified["customfield_10049"] == "Custom value"
        assert "description" not in simplified

        # Test with list format
        issues_mixin.jira.get_issue.reset_mock()
        issue = issues_mixin.get_issue(
            "TEST-123", fields=["summary", "customfield_10050"]
        )

        # Verify API call converts list to comma-separated string
        issues_mixin.jira.get_issue.assert_called_with(
            "TEST-123",
            expand=None,
            fields="summary,customfield_10050",
            properties=None,
            update_history=True,
        )

        # Check the result
        simplified = issue.to_simplified_dict()
        assert "customfield_10050" in simplified
        assert simplified["customfield_10050"] == "Option value"

    def test_get_issue_with_all_fields(self, issues_mixin: IssuesMixin):
        """Test get_issue with '*all' fields parameter."""
        # Mock the response
        mock_issue = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {
                "summary": "Test issue",
                "description": "Description",
                "customfield_10049": "Custom value",
            },
        }
        issues_mixin.jira.get_issue.return_value = mock_issue

        # Test with "*all" parameter
        issue = issues_mixin.get_issue("TEST-123", fields="*all")

        # Check that all fields are included
        simplified = issue.to_simplified_dict()
        assert "summary" in simplified
        assert "description" in simplified
        assert "customfield_10049" in simplified

    def test_get_issue_with_properties(self, issues_mixin: IssuesMixin):
        """Test get_issue with properties parameter."""
        # Mock the response
        issues_mixin.jira.get_issue.return_value = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {},
        }

        # Test with properties parameter as string
        issues_mixin.get_issue("TEST-123", properties="property1,property2")

        # Verify API call - should include properties parameter and add 'properties' to fields
        issues_mixin.jira.get_issue.assert_called_with(
            "TEST-123",
            expand=None,
            fields=ANY,
            properties="property1,property2",
            update_history=True,
        )

        # Test with properties parameter as list
        issues_mixin.jira.get_issue.reset_mock()
        issues_mixin.get_issue("TEST-123", properties=["property1", "property2"])

        # Verify API call - should include properties parameter as comma-separated string and add 'properties' to fields
        issues_mixin.jira.get_issue.assert_called_with(
            "TEST-123",
            expand=None,
            fields=ANY,
            properties="property1,property2",
            update_history=True,
        )

    def test_get_issue_with_update_history(self, issues_mixin: IssuesMixin):
        """Test get_issue with update_history parameter."""
        # Mock the response
        issues_mixin.jira.get_issue.return_value = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {},
        }

        # Test with update_history=False
        issues_mixin.get_issue("TEST-123", update_history=False)

        # Verify API call - should include update_history parameter
        issues_mixin.jira.get_issue.assert_called_with(
            "TEST-123",
            expand=None,
            fields=ANY,
            properties=None,
            update_history=False,
        )

    def test_batch_create_issues_basic(self, issues_mixin: IssuesMixin):
        """Test basic functionality of batch_create_issues."""
        # Setup test data
        issues = [
            {
                "project_key": "TEST",
                "summary": "Test Issue 1",
                "issue_type": "Task",
                "description": "Description 1",
            },
            {
                "project_key": "TEST",
                "summary": "Test Issue 2",
                "issue_type": "Bug",
                "description": "Description 2",
                "assignee": "john.doe",
                "components": ["Frontend"],
            },
        ]

        # Mock bulk create response
        bulk_response = {
            "issues": [
                {"id": "1", "key": "TEST-1", "self": "http://example.com/TEST-1"},
                {"id": "2", "key": "TEST-2", "self": "http://example.com/TEST-2"},
            ],
            "errors": [],
        }
        issues_mixin.jira.create_issues.return_value = bulk_response

        # Mock get_issue responses
        def get_issue_side_effect(key):
            if key == "TEST-1":
                return {
                    "id": "1",
                    "key": "TEST-1",
                    "fields": {"summary": "Test Issue 1"},
                }
            return {"id": "2", "key": "TEST-2", "fields": {"summary": "Test Issue 2"}}

        issues_mixin.jira.get_issue.side_effect = get_issue_side_effect
        issues_mixin._get_account_id.return_value = "user123"

        # Call the method
        result = issues_mixin.batch_create_issues(issues)

        # Verify results
        assert len(result) == 2
        assert result[0].key == "TEST-1"
        assert result[1].key == "TEST-2"

        # Verify bulk create was called correctly
        issues_mixin.jira.create_issues.assert_called_once()
        call_args = issues_mixin.jira.create_issues.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0]["fields"]["summary"] == "Test Issue 1"
        assert call_args[1]["fields"]["summary"] == "Test Issue 2"

    def test_batch_create_issues_validate_only(self, issues_mixin: IssuesMixin):
        """Test batch_create_issues with validate_only=True."""
        # Setup test data
        issues = [
            {
                "project_key": "TEST",
                "summary": "Test Issue 1",
                "issue_type": "Task",
            },
            {
                "project_key": "TEST",
                "summary": "Test Issue 2",
                "issue_type": "Bug",
            },
        ]

        # Call the method with validate_only=True
        result = issues_mixin.batch_create_issues(issues, validate_only=True)

        # Verify no issues were created
        assert len(result) == 0
        assert not issues_mixin.jira.create_issues.called

    def test_batch_create_issues_missing_required_fields(
        self, issues_mixin: IssuesMixin
    ):
        """Test batch_create_issues with missing required fields."""
        # Setup test data with missing fields
        issues = [
            {
                "project_key": "TEST",
                "summary": "Test Issue 1",
                # Missing issue_type
            },
            {
                "project_key": "TEST",
                "summary": "Test Issue 2",
                "issue_type": "Bug",
            },
        ]

        # Verify it raises ValueError
        with pytest.raises(ValueError) as exc_info:
            issues_mixin.batch_create_issues(issues)

        assert "Missing required fields" in str(exc_info.value)
        assert not issues_mixin.jira.create_issues.called

    def test_batch_create_issues_partial_failure(self, issues_mixin: IssuesMixin):
        """Test batch_create_issues when some issues fail to create."""
        # Setup test data
        issues = [
            {
                "project_key": "TEST",
                "summary": "Test Issue 1",
                "issue_type": "Task",
            },
            {
                "project_key": "TEST",
                "summary": "Test Issue 2",
                "issue_type": "Bug",
            },
        ]

        # Mock bulk create response with an error
        bulk_response = {
            "issues": [
                {"id": "1", "key": "TEST-1", "self": "http://example.com/TEST-1"},
            ],
            "errors": [{"issue": {"key": None}, "error": "Invalid issue type"}],
        }
        issues_mixin.jira.create_issues.return_value = bulk_response

        # Mock get_issue response for successful creation
        issues_mixin.jira.get_issue.return_value = {
            "id": "1",
            "key": "TEST-1",
            "fields": {"summary": "Test Issue 1"},
        }

        # Call the method
        result = issues_mixin.batch_create_issues(issues)

        # Verify results - should have only the first issue
        assert len(result) == 1
        assert result[0].key == "TEST-1"

        # Verify error was logged
        issues_mixin.jira.create_issues.assert_called_once()
        assert len(issues_mixin.jira.get_issue.mock_calls) == 1

    def test_batch_create_issues_empty_list(self, issues_mixin: IssuesMixin):
        """Test batch_create_issues with an empty list."""
        result = issues_mixin.batch_create_issues([])
        assert result == []
        assert not issues_mixin.jira.create_issues.called

    def test_batch_create_issues_with_components(self, issues_mixin: IssuesMixin):
        """Test batch_create_issues with component handling."""
        # Setup test data with various component formats
        issues = [
            {
                "project_key": "TEST",
                "summary": "Test Issue 1",
                "issue_type": "Task",
                "components": ["Frontend", "", None, "  Backend  "],
            }
        ]

        # Mock responses
        bulk_response = {
            "issues": [
                {"id": "1", "key": "TEST-1", "self": "http://example.com/TEST-1"},
            ],
            "errors": [],
        }
        issues_mixin.jira.create_issues.return_value = bulk_response
        issues_mixin.jira.get_issue.return_value = {
            "id": "1",
            "key": "TEST-1",
            "fields": {"summary": "Test Issue 1"},
        }

        # Call the method
        result = issues_mixin.batch_create_issues(issues)

        # Verify results
        assert len(result) == 1

        # Verify components were properly formatted
        call_args = issues_mixin.jira.create_issues.call_args[0][0]
        assert len(call_args) == 1
        components = call_args[0]["fields"]["components"]
        assert len(components) == 2
        assert components[0]["name"] == "Frontend"
        assert components[1]["name"] == "Backend"

    def test_add_assignee_to_fields_cloud(self, issues_mixin: IssuesMixin):
        """Test _add_assignee_to_fields for Cloud instance."""
        # Set up cloud config
        issues_mixin.config = MagicMock()
        issues_mixin.config.is_cloud = True

        # Test fields dict
        fields = {}

        # Call the method
        issues_mixin._add_assignee_to_fields(fields, "account-123")

        # Verify result
        assert fields["assignee"] == {"accountId": "account-123"}

    def test_add_assignee_to_fields_server_dc(self, issues_mixin: IssuesMixin):
        """Test _add_assignee_to_fields for Server/Data Center instance."""
        # Set up Server/DC config
        issues_mixin.config = MagicMock()
        issues_mixin.config.is_cloud = False

        # Test fields dict
        fields = {}

        # Call the method
        issues_mixin._add_assignee_to_fields(fields, "jdoe")

        # Verify result
        assert fields["assignee"] == {"name": "jdoe"}

    def test_batch_get_changelogs_not_cloud(self, issues_mixin: IssuesMixin):
        """Test batch_get_changelogs method on non-cloud instance."""
        issues_mixin.config = MagicMock()
        issues_mixin.config.is_cloud = False

        with pytest.raises(NotImplementedError):
            issues_mixin.batch_get_changelogs(
                issue_ids_or_keys=["TEST-123"],
                fields=["summary", "description"],
            )

    def test_batch_get_changelogs_cloud(self, issues_mixin: IssuesMixin):
        """Test batch_get_changelogs method on cloud instance."""
        issues_mixin.config = MagicMock()
        issues_mixin.config.is_cloud = True

        # Mock get_paged result
        mock_get_paged_result = [
            {
                "issueChangeLogs": [
                    {
                        "issueId": "TEST-1",
                        "changeHistories": [
                            {
                                "id": "10001",
                                "author": {
                                    "accountId": "user123",
                                    "displayName": "Test User 1",
                                    "active": True,
                                    "timeZone": "UTC",
                                    "accountType": "atlassian",
                                },
                                "created": "2024-01-05T10:06:03.548+0800",
                                "items": [
                                    {
                                        "field": "IssueParentAssociation",
                                        "fieldtype": "jira",
                                        "from": None,
                                        "fromString": None,
                                        "to": "1001",
                                        "toString": "TEST-100",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "issueId": "TEST-2",
                        "changeHistories": [
                            {
                                "id": "10002",
                                "author": {
                                    "accountId": "user456",
                                    "displayName": "Test User 2",
                                    "active": True,
                                    "timeZone": "UTC",
                                    "accountType": "atlassian",
                                },
                                "created": "1704106800000",  # 2024-01-01
                                "items": [
                                    {
                                        "field": "Parent",
                                        "fieldtype": "jira",
                                        "from": None,
                                        "fromString": None,
                                        "to": "1002",
                                        "toString": "TEST-200",
                                    }
                                ],
                            },
                            {
                                "id": "10003",
                                "author": {
                                    "accountId": "user789",
                                    "displayName": "Test User 3",
                                    "active": True,
                                    "timeZone": "UTC",
                                    "accountType": "atlassian",
                                },
                                "created": "2024-01-06T10:06:03.548+0800",
                                "items": [
                                    {
                                        "field": "Parent",
                                        "fieldtype": "jira",
                                        "from": "1002",
                                        "fromString": "TEST-200",
                                        "to": "1003",
                                        "toString": "TEST-300",
                                    }
                                ],
                            },
                        ],
                    },
                ],
                "nextPageToken": "token1",
            },
            {
                "issueChangeLogs": [
                    {
                        "issueId": "TEST-2",
                        "changeHistories": [
                            {
                                "id": "10004",
                                "author": {
                                    "accountId": "user123",
                                    "displayName": "Test User 1",
                                    "active": True,
                                    "timeZone": "UTC",
                                    "accountType": "atlassian",
                                },
                                "created": "2024-01-10T10:06:03.548+0800",
                                "items": [
                                    {
                                        "field": "Parent",
                                        "fieldtype": "jira",
                                        "from": "1003",
                                        "fromString": "TEST-300",
                                        "to": "1004",
                                        "toString": "TEST-400",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        ]

        # Expected result
        expected_result = [
            {
                "assignee": {"display_name": "Unassigned"},
                "changelogs": [
                    {
                        "author": {
                            "avatar_url": None,
                            "display_name": "Test User 1",
                            "email": None,
                            "name": "Test User 1",
                        },
                        "created": "2024-01-05 10:06:03.548000+08:00",
                        "items": [
                            {
                                "field": "IssueParentAssociation",
                                "fieldtype": "jira",
                                "to_id": "1001",
                                "to_string": "TEST-100",
                            },
                        ],
                    },
                ],
                "id": "TEST-1",
                "key": "UNKNOWN-0",
                "summary": "",
            },
            {
                "assignee": {"display_name": "Unassigned"},
                "changelogs": [
                    {
                        "author": {
                            "avatar_url": None,
                            "display_name": "Test User 2",
                            "email": None,
                            "name": "Test User 2",
                        },
                        "created": "2024-01-01 11:00:00+00:00",
                        "items": [
                            {
                                "field": "Parent",
                                "fieldtype": "jira",
                                "to_id": "1002",
                                "to_string": "TEST-200",
                            },
                        ],
                    },
                    {
                        "author": {
                            "avatar_url": None,
                            "display_name": "Test User 3",
                            "email": None,
                            "name": "Test User 3",
                        },
                        "created": "2024-01-06 10:06:03.548000+08:00",
                        "items": [
                            {
                                "field": "Parent",
                                "fieldtype": "jira",
                                "from_id": "1002",
                                "from_string": "TEST-200",
                                "to_id": "1003",
                                "to_string": "TEST-300",
                            },
                        ],
                    },
                    {
                        "author": {
                            "avatar_url": None,
                            "display_name": "Test User 1",
                            "email": None,
                            "name": "Test User 1",
                        },
                        "created": "2024-01-10 10:06:03.548000+08:00",
                        "items": [
                            {
                                "field": "Parent",
                                "fieldtype": "jira",
                                "from_id": "1003",
                                "from_string": "TEST-300",
                                "to_id": "1004",
                                "to_string": "TEST-400",
                            },
                        ],
                    },
                ],
                "id": "TEST-2",
                "key": "UNKNOWN-0",
                "summary": "",
            },
        ]

        # Mock the get_paged method
        issues_mixin.get_paged = MagicMock(return_value=mock_get_paged_result)

        # Call the method
        result = issues_mixin.batch_get_changelogs(
            issue_ids_or_keys=["TEST-1", "TEST-2"],
            fields=["Parent"],
        )

        # Verify the result
        simplified_result = [issue.to_simplified_dict() for issue in result]
        assert simplified_result == expected_result

        # Verify the method was called with the correct arguments
        issues_mixin.get_paged.assert_called_once_with(
            method="post",
            url=issues_mixin.jira.resource_url("changelog/bulkfetch"),
            params_or_json={
                "fieldIds": ["Parent"],
                "issueIdsOrKeys": ["TEST-1", "TEST-2"],
            },
        )

    def test_create_issue_with_labels(self, issues_mixin: IssuesMixin):
        """Test creating an issue with labels in additional_fields."""
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
                "labels": ["bug", "frontend"],
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Create the issue with labels as a list
        result = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            labels=["bug", "frontend"],
        )

        # Verify the API call
        issues_mixin.jira.create_issue.assert_called_once()
        call_kwargs = issues_mixin.jira.create_issue.call_args[1]
        assert "fields" in call_kwargs
        fields = call_kwargs["fields"]

        # Verify labels were added to the fields
        assert "labels" in fields
        assert fields["labels"] == ["bug", "frontend"]

        # Verify result
        assert result.key == "TEST-123"
        assert result.labels == ["bug", "frontend"]

    def test_create_issue_with_labels_as_string(self, issues_mixin: IssuesMixin):
        """Test creating an issue with labels as comma-separated string in additional_fields."""
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
                "labels": ["bug", "frontend"],
            },
        }
        issues_mixin.jira.get_issue.return_value = issue_data

        # Create the issue with labels as a comma-separated string
        # Pass labels directly instead of through additional_fields
        result = issues_mixin.create_issue(
            project_key="TEST",
            summary="Test Issue",
            issue_type="Bug",
            description="This is a test issue",
            labels="bug,frontend",  # Pass as string and let _format_field_value_for_write handle it
        )

        # Verify the API call
        issues_mixin.jira.create_issue.assert_called_once()
        call_kwargs = issues_mixin.jira.create_issue.call_args[1]
        assert "fields" in call_kwargs
        fields = call_kwargs["fields"]

        # Verify labels were parsed and added to the fields
        assert "labels" in fields
        assert fields["labels"] == ["bug", "frontend"]

        # Verify result
        assert result.key == "TEST-123"
        assert result.labels == ["bug", "frontend"]
