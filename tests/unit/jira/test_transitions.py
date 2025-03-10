"""Tests for the Jira Transitions mixin."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira.transitions import TransitionsMixin
from mcp_atlassian.models.jira import (
    JiraIssue,
    JiraStatus,
    JiraStatusCategory,
    JiraTransition,
)


class TestTransitionsMixin:
    """Tests for the TransitionsMixin class."""

    @pytest.fixture
    def transitions_mixin(self, jira_client):
        """Create a TransitionsMixin instance with mocked dependencies."""
        mixin = TransitionsMixin(config=jira_client.config)
        mixin.jira = jira_client.jira

        # Create a get_issue method to allow returning JiraIssue
        mixin.get_issue = MagicMock(
            return_value=JiraIssue(
                id="12345",
                key="TEST-123",
                summary="Test Issue",
                description="Issue content",
                status=JiraStatus(
                    id="1",
                    name="Open",
                    category=JiraStatusCategory(
                        id=1, key="open", name="To Do", color_name="blue-gray"
                    ),
                ),
            )
        )

        # Set up mock for get_transitions_models
        mock_transitions = [
            JiraTransition(
                id="10",
                name="Start Progress",
                to_status=JiraStatus(id="2", name="In Progress"),
            )
        ]
        mixin.get_transitions_models = MagicMock(return_value=mock_transitions)

        return mixin

    def test_get_available_transitions_dict_format(self, transitions_mixin):
        """Test get_available_transitions with dict format response."""
        # Setup mock response - dictionary format with transitions key
        mock_transitions = {
            "transitions": [
                {"id": "10", "name": "In Progress", "to": {"name": "In Progress"}},
                {"id": "11", "name": "Done", "to": {"name": "Done"}},
            ]
        }
        transitions_mixin.jira.get_issue_transitions.return_value = mock_transitions

        # Call the method
        result = transitions_mixin.get_available_transitions("TEST-123")

        # Verify
        transitions_mixin.jira.get_issue_transitions.assert_called_once_with("TEST-123")
        assert len(result) == 2
        assert result[0]["id"] == "10"
        assert result[0]["name"] == "In Progress"
        assert result[0]["to_status"] == "In Progress"
        assert result[1]["id"] == "11"
        assert result[1]["name"] == "Done"
        assert result[1]["to_status"] == "Done"

    def test_get_available_transitions_list_format(self, transitions_mixin):
        """Test get_available_transitions with list format response."""
        # Setup mock response - list format
        mock_transitions = [
            {"id": "10", "name": "In Progress", "to_status": "In Progress"},
            {"id": "11", "name": "Done", "status": "Done"},
        ]
        transitions_mixin.jira.get_issue_transitions.return_value = mock_transitions

        # Call the method
        result = transitions_mixin.get_available_transitions("TEST-123")

        # Verify
        assert len(result) == 2
        assert result[0]["id"] == "10"
        assert result[0]["name"] == "In Progress"
        assert result[0]["to_status"] == "In Progress"
        assert result[1]["id"] == "11"
        assert result[1]["name"] == "Done"
        assert result[1]["to_status"] == "Done"

    def test_get_available_transitions_empty_response(self, transitions_mixin):
        """Test get_available_transitions with empty response."""
        # Setup mock response - empty
        transitions_mixin.jira.get_issue_transitions.return_value = {}

        # Call the method
        result = transitions_mixin.get_available_transitions("TEST-123")

        # Verify
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_available_transitions_invalid_format(self, transitions_mixin):
        """Test get_available_transitions with invalid format response."""
        # Setup mock response - invalid format
        transitions_mixin.jira.get_issue_transitions.return_value = "invalid"

        # Call the method
        result = transitions_mixin.get_available_transitions("TEST-123")

        # Verify
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_available_transitions_with_non_dict_transition(
        self, transitions_mixin
    ):
        """Test get_available_transitions with non-dict transition in list."""
        # Setup mock response with a non-dict transition
        mock_transitions = {
            "transitions": [
                {"id": "10", "name": "In Progress", "to": {"name": "In Progress"}},
                "invalid_transition",  # This should be skipped
                {"id": "11", "name": "Done", "to": {"name": "Done"}},
            ]
        }
        transitions_mixin.jira.get_issue_transitions.return_value = mock_transitions

        # Call the method
        result = transitions_mixin.get_available_transitions("TEST-123")

        # Verify
        assert len(result) == 2
        assert result[0]["id"] == "10"
        assert result[1]["id"] == "11"

    def test_get_available_transitions_with_error(self, transitions_mixin):
        """Test get_available_transitions error handling."""
        # Setup mock to raise exception
        transitions_mixin.jira.get_issue_transitions.side_effect = Exception(
            "Transition fetch error"
        )

        # Call the method and verify exception
        with pytest.raises(
            Exception, match="Error getting transitions: Transition fetch error"
        ):
            transitions_mixin.get_available_transitions("TEST-123")

    def test_transition_issue_basic(self, transitions_mixin):
        """Test basic functionality of transition_issue."""
        # Call the method
        result = transitions_mixin.transition_issue("TEST-123", "10")

        # Verify
        expected_transition_data = {"transition": {"id": "10"}}
        transitions_mixin.jira.issue_transition.assert_called_once_with(
            "TEST-123", expected_transition_data
        )
        transitions_mixin.get_issue.assert_called_once_with("TEST-123")
        assert isinstance(result, JiraIssue)
        assert result.key == "TEST-123"
        assert result.summary == "Test Issue"
        assert result.description == "Issue content"

    def test_transition_issue_with_int_id(self, transitions_mixin):
        """Test transition_issue with int transition ID."""
        # Call the method with int ID
        transitions_mixin.transition_issue("TEST-123", 10)

        # Verify ID was converted to string
        expected_transition_data = {"transition": {"id": "10"}}
        transitions_mixin.jira.issue_transition.assert_called_once_with(
            "TEST-123", expected_transition_data
        )

    def test_transition_issue_with_fields(self, transitions_mixin):
        """Test transition_issue with fields."""
        # Setup mock for _sanitize_transition_fields
        fields = {"resolution": {"name": "Fixed"}}
        transitions_mixin._sanitize_transition_fields = MagicMock(return_value=fields)

        # Call the method
        transitions_mixin.transition_issue("TEST-123", "10", fields=fields)

        # Verify
        transitions_mixin._sanitize_transition_fields.assert_called_once_with(fields)
        expected_transition_data = {"transition": {"id": "10"}, "fields": fields}
        transitions_mixin.jira.issue_transition.assert_called_once_with(
            "TEST-123", expected_transition_data
        )

    def test_transition_issue_with_empty_sanitized_fields(self, transitions_mixin):
        """Test transition_issue with empty sanitized fields."""
        # Setup mock for _sanitize_transition_fields to return empty dict
        fields = {"assignee": "someone"}
        transitions_mixin._sanitize_transition_fields = MagicMock(return_value={})

        # Call the method
        transitions_mixin.transition_issue("TEST-123", "10", fields=fields)

        # Verify
        transitions_mixin._sanitize_transition_fields.assert_called_once_with(fields)
        # Fields should not be in transition data if sanitized fields is empty
        expected_transition_data = {"transition": {"id": "10"}}
        transitions_mixin.jira.issue_transition.assert_called_once_with(
            "TEST-123", expected_transition_data
        )

    def test_transition_issue_with_comment(self, transitions_mixin):
        """Test transition_issue with comment."""
        # Setup mock for _add_comment_to_transition_data
        orig_add_comment = transitions_mixin._add_comment_to_transition_data
        transitions_mixin._add_comment_to_transition_data = MagicMock()

        # Call the method
        transitions_mixin.transition_issue("TEST-123", "10", comment="Test comment")

        # Verify
        transitions_mixin._add_comment_to_transition_data.assert_called_once()
        # Restore original method for other tests
        transitions_mixin._add_comment_to_transition_data = orig_add_comment

    def test_transition_issue_without_get_issue(self, transitions_mixin):
        """Test transition_issue without get_issue method."""
        # Remove get_issue method
        transitions_mixin.get_issue = None

        # Call the method
        result = transitions_mixin.transition_issue("TEST-123", "10")

        # Verify fallback behavior
        assert isinstance(result, JiraIssue)
        assert result.key == "TEST-123"
        assert result.summary == "Test Issue"
        assert result.description == "Issue content"

    def test_transition_issue_with_error(self, transitions_mixin):
        """Test transition_issue error handling."""
        # Setup mock to raise exception
        transitions_mixin.jira.issue_transition.side_effect = Exception(
            "Transition error"
        )

        # Call the method and verify exception
        with pytest.raises(
            ValueError,
            match="Error transitioning issue TEST-123 with transition ID 10: Transition error",
        ):
            transitions_mixin.transition_issue("TEST-123", "10")

    def test_normalize_transition_id(self, transitions_mixin):
        """Test _normalize_transition_id method."""
        # Test with string
        assert transitions_mixin._normalize_transition_id("10") == "10"

        # Test with int
        assert transitions_mixin._normalize_transition_id(10) == "10"

    def test_sanitize_transition_fields_basic(self, transitions_mixin):
        """Test _sanitize_transition_fields with basic fields."""
        # Simple fields
        fields = {"resolution": {"name": "Fixed"}, "priority": {"name": "High"}}

        result = transitions_mixin._sanitize_transition_fields(fields)

        # Fields should be passed through unchanged
        assert result == fields

    def test_sanitize_transition_fields_with_none_values(self, transitions_mixin):
        """Test _sanitize_transition_fields with None values."""
        # Fields with None values
        fields = {"resolution": {"name": "Fixed"}, "priority": None}

        result = transitions_mixin._sanitize_transition_fields(fields)

        # None values should be skipped
        assert "priority" not in result
        assert result["resolution"] == {"name": "Fixed"}

    def test_sanitize_transition_fields_with_assignee_and_get_account_id(
        self, transitions_mixin
    ):
        """Test _sanitize_transition_fields with assignee when _get_account_id is available."""
        # Setup mock for _get_account_id
        transitions_mixin._get_account_id = MagicMock(return_value="account-123")

        # Fields with assignee
        fields = {"assignee": "user.name"}

        result = transitions_mixin._sanitize_transition_fields(fields)

        # Assignee should be converted to account ID format
        transitions_mixin._get_account_id.assert_called_once_with("user.name")
        assert result["assignee"] == {"accountId": "account-123"}

    def test_sanitize_transition_fields_with_assignee_without_get_account_id(
        self, transitions_mixin
    ):
        """Test _sanitize_transition_fields with assignee when _get_account_id is not available."""
        # Remove _get_account_id method
        if hasattr(transitions_mixin, "_get_account_id"):
            delattr(transitions_mixin, "_get_account_id")

        # Fields with assignee
        fields = {"assignee": "user.name", "resolution": {"name": "Fixed"}}

        result = transitions_mixin._sanitize_transition_fields(fields)

        # Assignee should be skipped, resolution preserved
        assert "assignee" not in result
        assert result["resolution"] == {"name": "Fixed"}

    def test_sanitize_transition_fields_with_assignee_error(self, transitions_mixin):
        """Test _sanitize_transition_fields with assignee that causes error."""
        # Setup mock for _get_account_id to raise exception
        transitions_mixin._get_account_id = MagicMock(
            side_effect=Exception("User not found")
        )

        # Fields with assignee
        fields = {"assignee": "invalid.user", "resolution": {"name": "Fixed"}}

        result = transitions_mixin._sanitize_transition_fields(fields)

        # Assignee should be skipped due to error, resolution preserved
        assert "assignee" not in result
        assert result["resolution"] == {"name": "Fixed"}

    def test_add_comment_to_transition_data_with_string(self, transitions_mixin):
        """Test _add_comment_to_transition_data with string comment."""
        # Prepare transition data
        transition_data = {"transition": {"id": "10"}}

        # Call the method
        transitions_mixin._add_comment_to_transition_data(
            transition_data, "Test comment"
        )

        # Verify
        assert "update" in transition_data
        assert "comment" in transition_data["update"]
        assert len(transition_data["update"]["comment"]) == 1
        assert transition_data["update"]["comment"][0]["add"]["body"] == "Test comment"

    def test_add_comment_to_transition_data_with_non_string(self, transitions_mixin):
        """Test _add_comment_to_transition_data with non-string comment."""
        # Prepare transition data
        transition_data = {"transition": {"id": "10"}}

        # Call the method with int
        transitions_mixin._add_comment_to_transition_data(transition_data, 123)

        # Verify comment was converted to string
        assert transition_data["update"]["comment"][0]["add"]["body"] == "123"

    def test_add_comment_to_transition_data_with_markdown_to_jira(
        self, transitions_mixin
    ):
        """Test _add_comment_to_transition_data with _markdown_to_jira method."""
        # Add _markdown_to_jira method
        transitions_mixin._markdown_to_jira = MagicMock(
            return_value="Converted comment"
        )

        # Prepare transition data
        transition_data = {"transition": {"id": "10"}}

        # Call the method
        transitions_mixin._add_comment_to_transition_data(
            transition_data, "**Markdown** comment"
        )

        # Verify
        transitions_mixin._markdown_to_jira.assert_called_once_with(
            "**Markdown** comment"
        )
        assert (
            transition_data["update"]["comment"][0]["add"]["body"]
            == "Converted comment"
        )
