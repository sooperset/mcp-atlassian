"""Tests for the Jira Transitions mixin."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira import JiraFetcher
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
    def transitions_mixin(self, jira_fetcher: JiraFetcher) -> TransitionsMixin:
        """Create a TransitionsMixin instance with mocked dependencies."""
        mixin = jira_fetcher

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

    def test_get_available_transitions_list_format(
        self, transitions_mixin: TransitionsMixin
    ):
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

    def test_get_available_transitions_empty_response(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test get_available_transitions with empty response."""
        # Setup mock response - empty
        transitions_mixin.jira.get_issue_transitions.return_value = {}

        # Call the method
        result = transitions_mixin.get_available_transitions("TEST-123")

        # Verify
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_available_transitions_invalid_format(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test get_available_transitions with invalid format response."""
        # Setup mock response - invalid format
        transitions_mixin.jira.get_issue_transitions.return_value = "invalid"

        # Call the method
        result = transitions_mixin.get_available_transitions("TEST-123")

        # Verify
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_available_transitions_with_error(
        self, transitions_mixin: TransitionsMixin
    ):
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

    def test_transition_issue_basic(self, transitions_mixin: TransitionsMixin):
        """Test transition_issue with basic parameters."""
        # Client configured for v3 (Jira Cloud default)
        transitions_mixin.jira.resource_url = MagicMock(
            return_value="https://jira.example.com/rest/api/3/issue"
        )

        # Call the method
        result = transitions_mixin.transition_issue("TEST-123", "10")

        # Verify POST to the v2 transitions endpoint with a minimal payload
        transitions_mixin.jira.post.assert_called_once_with(
            "https://jira.example.com/rest/api/2/issue/TEST-123/transitions",
            json={"transition": {"id": "10"}},
        )
        transitions_mixin.get_issue.assert_called_once_with("TEST-123")
        assert isinstance(result, JiraIssue)
        assert result.key == "TEST-123"
        assert result.summary == "Test Issue"
        assert result.description == "Issue content"

    def test_transition_issue_with_int_id(self, transitions_mixin: TransitionsMixin):
        """Test transition_issue with int transition ID."""
        transitions_mixin.jira.resource_url = MagicMock(
            return_value="https://jira.example.com/rest/api/3/issue"
        )

        # Call the method with int ID
        transitions_mixin.transition_issue("TEST-123", 10)

        # Verify the transition ID is stringified in the payload
        transitions_mixin.jira.post.assert_called_once_with(
            "https://jira.example.com/rest/api/2/issue/TEST-123/transitions",
            json={"transition": {"id": "10"}},
        )

    def test_transition_issue_with_fields(self, transitions_mixin: TransitionsMixin):
        """Test transition_issue with fields."""
        # Mock _sanitize_transition_fields to return the fields
        transitions_mixin._sanitize_transition_fields = MagicMock(
            return_value={"summary": "Updated"}
        )
        transitions_mixin.jira.resource_url = MagicMock(
            return_value="https://jira.example.com/rest/api/3/issue"
        )

        # Call the method with fields
        fields = {"summary": "Updated"}
        transitions_mixin.transition_issue("TEST-123", "10", fields=fields)

        # Verify fields are included in the POST payload
        transitions_mixin.jira.post.assert_called_once_with(
            "https://jira.example.com/rest/api/2/issue/TEST-123/transitions",
            json={
                "transition": {"id": "10"},
                "fields": {"summary": "Updated"},
            },
        )

    def test_transition_issue_with_empty_sanitized_fields(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test transition_issue with empty sanitized fields."""
        # Mock _sanitize_transition_fields to return empty dict
        transitions_mixin._sanitize_transition_fields = MagicMock(return_value={})
        transitions_mixin.jira.resource_url = MagicMock(
            return_value="https://jira.example.com/rest/api/3/issue"
        )

        # Call the method with fields that will be sanitized to empty
        fields = {"invalid": "field"}
        transitions_mixin.transition_issue("TEST-123", "10", fields=fields)

        # Empty sanitized fields should result in no "fields" key in the payload
        transitions_mixin.jira.post.assert_called_once_with(
            "https://jira.example.com/rest/api/2/issue/TEST-123/transitions",
            json={"transition": {"id": "10"}},
        )

    def test_transition_issue_with_comment(self, transitions_mixin: TransitionsMixin):
        """Test transition_issue with comment."""
        # Setup
        comment = "Test comment"

        # Define a side effect to record what's passed to _add_comment_to_transition_data
        def add_comment_side_effect(transition_data, comment_text):
            transition_data["update"] = {"comment": [{"add": {"body": comment_text}}]}

        # Mock _add_comment_to_transition_data
        transitions_mixin._add_comment_to_transition_data = MagicMock(
            side_effect=add_comment_side_effect
        )
        transitions_mixin.jira.resource_url = MagicMock(
            return_value="https://jira.example.com/rest/api/3/issue"
        )

        # Call the method with comment
        transitions_mixin.transition_issue("TEST-123", "10", comment=comment)

        # Verify _add_comment_to_transition_data was called
        transitions_mixin._add_comment_to_transition_data.assert_called_once()

        # Verify the comment update is included in the POST payload, sent to v2
        transitions_mixin.jira.post.assert_called_once_with(
            "https://jira.example.com/rest/api/2/issue/TEST-123/transitions",
            json={
                "transition": {"id": "10"},
                "update": {"comment": [{"add": {"body": comment}}]},
            },
        )

    def test_transition_issue_with_error(self, transitions_mixin: TransitionsMixin):
        """Test transition_issue error handling."""
        transitions_mixin.jira.resource_url = MagicMock(
            return_value="https://jira.example.com/rest/api/3/issue"
        )
        # Setup mock to raise exception on the POST
        transitions_mixin.jira.post.side_effect = Exception("Transition error")

        # Call the method and verify exception
        with pytest.raises(
            ValueError,
            match="Error transitioning issue TEST-123 with transition ID 10: Transition error",
        ):
            transitions_mixin.transition_issue("TEST-123", "10")

    def test_transition_issue_without_status_name(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test transition_issue when target status name is not available.

        After the unification onto a single v2 POST path, the absence of a
        resolvable target status name no longer affects behavior -- the
        transition still succeeds using the transition_id alone.
        """
        # Setup - create a transition without to_status
        mock_transitions = [
            JiraTransition(
                id="10",
                name="Start Progress",
                to_status=None,
            )
        ]
        transitions_mixin.get_transitions_models = MagicMock(
            return_value=mock_transitions
        )
        transitions_mixin.jira.resource_url = MagicMock(
            return_value="https://jira.example.com/rest/api/3/issue"
        )

        # Call the method
        result = transitions_mixin.transition_issue("TEST-123", "10")

        # Verify the unified POST still happens with the transition id
        transitions_mixin.jira.post.assert_called_once_with(
            "https://jira.example.com/rest/api/2/issue/TEST-123/transitions",
            json={"transition": {"id": "10"}},
        )

        # Verify result
        transitions_mixin.get_issue.assert_called_once_with("TEST-123")
        assert isinstance(result, JiraIssue)

    def test_transition_issue_forces_v2_on_cloud(
        self, transitions_mixin: TransitionsMixin
    ):
        """Regression test for issue #1262.

        The v3 transitions endpoint rejects update.comment[].add.body when it
        is a wiki-markup string (it expects ADF). _markdown_to_jira produces
        wiki-markup. Forcing v2 here avoids the impedance mismatch without
        needing a markdown->ADF conversion path.
        """
        # Client configured for v3 (Jira Cloud default)
        transitions_mixin.jira.resource_url = MagicMock(
            return_value="https://jira.example.com/rest/api/3/issue"
        )

        transitions_mixin.transition_issue("TEST-123", "10")

        # The URL must have been rewritten to /api/2/
        call_args = transitions_mixin.jira.post.call_args
        url = call_args.args[0]
        assert "/rest/api/2/issue/TEST-123/transitions" in url
        assert "/api/3/" not in url

    def test_transition_issue_v2_url_passthrough(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test that a v2 URL from the client is passed through unchanged.

        This is the Server / Data Center case, where the client is already
        configured for v2. The string-replace from /api/3/ to /api/2/ is a
        no-op when /api/3/ is not present.
        """
        transitions_mixin.jira.resource_url = MagicMock(
            return_value="https://jira.example.com/rest/api/2/issue"
        )

        transitions_mixin.transition_issue("TEST-123", "10")

        transitions_mixin.jira.post.assert_called_once_with(
            "https://jira.example.com/rest/api/2/issue/TEST-123/transitions",
            json={"transition": {"id": "10"}},
        )

    def test_get_transitions_uses_full_api(self, transitions_mixin: TransitionsMixin):
        """Test that get_transitions uses get_issue_transitions_full for complete data.

        This is the fix for issue #602 - we need the full 'to' object from the API,
        not the simplified version that only contains the status name as a string.
        """
        # Setup mock response matching real Jira API format
        mock_response = {
            "expand": "transitions",
            "transitions": [
                {
                    "id": "731",
                    "name": "Close Issue",
                    "to": {
                        "self": "https://jira.example.com/rest/api/2/status/6",
                        "name": "Closed",
                        "id": "6",
                        "statusCategory": {
                            "id": 3,
                            "key": "done",
                            "name": "Done",
                        },
                    },
                },
                {
                    "id": "711",
                    "name": "Wait",
                    "to": {
                        "name": "Waiting",
                        "id": "10100",
                    },
                },
            ],
        }
        transitions_mixin.jira.get_issue_transitions_full = MagicMock(
            return_value=mock_response
        )

        # Call the method
        result = transitions_mixin.get_transitions("TEST-123")

        # Verify get_issue_transitions_full was called (not get_issue_transitions)
        transitions_mixin.jira.get_issue_transitions_full.assert_called_once_with(
            "TEST-123"
        )

        # Verify we get the full transitions list with complete 'to' objects
        assert len(result) == 2
        assert result[0]["id"] == "731"
        assert result[0]["name"] == "Close Issue"
        assert isinstance(result[0]["to"], dict)  # Full dict, not string!
        assert result[0]["to"]["name"] == "Closed"
        assert result[0]["to"]["id"] == "6"

    def test_get_transitions_models_with_full_to_status(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test that get_transitions_models correctly parses full 'to' status objects.

        This verifies that when get_issue_transitions_full returns complete 'to' objects,
        the JiraTransition models are created with proper to_status.
        """
        # Setup mock response matching real Jira API format
        mock_response = {
            "transitions": [
                {
                    "id": "731",
                    "name": "Close Issue",
                    "to": {
                        "name": "Closed",
                        "id": "6",
                        "statusCategory": {
                            "id": 3,
                            "key": "done",
                            "name": "Done",
                            "colorName": "success",
                        },
                    },
                },
            ],
        }
        transitions_mixin.jira.get_issue_transitions_full = MagicMock(
            return_value=mock_response
        )

        # Use real implementation, not the mocked one from fixture
        transitions_mixin.get_transitions_models = (
            TransitionsMixin.get_transitions_models.__get__(
                transitions_mixin, type(transitions_mixin)
            )
        )
        transitions_mixin.get_transitions = TransitionsMixin.get_transitions.__get__(
            transitions_mixin, type(transitions_mixin)
        )

        # Call the method
        result = transitions_mixin.get_transitions_models("TEST-123")

        # Verify the model has proper to_status
        assert len(result) == 1
        assert result[0].id == "731"
        assert result[0].name == "Close Issue"
        assert result[0].to_status is not None  # Should NOT be None!
        assert result[0].to_status.name == "Closed"
        assert result[0].to_status.id == "6"

    def test_transition_issue_with_resolution_field(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test transition_issue with resolution field includes it in the payload.

        Regression test for issue #602 - the fields parameter (e.g. resolution)
        must be sent atomically with the transition so the resolution is set
        as part of the status change rather than dropped.

        After the unification onto a single v2 POST path, this is verified
        directly by inspecting the request payload.
        """
        # Setup mock for get_issue_transitions_full (used by get_transitions)
        mock_response = {
            "transitions": [
                {
                    "id": "731",
                    "name": "Close Issue",
                    "to": {
                        "name": "Closed",
                        "id": "6",
                    },
                },
            ],
        }
        transitions_mixin.jira.get_issue_transitions_full = MagicMock(
            return_value=mock_response
        )
        transitions_mixin.jira.resource_url = MagicMock(
            return_value="https://jira.example.com/rest/api/3/issue"
        )

        # Don't mock get_transitions_models - let it use real implementation
        # to test the full flow
        transitions_mixin.get_transitions_models = (
            TransitionsMixin.get_transitions_models.__get__(
                transitions_mixin, type(transitions_mixin)
            )
        )
        transitions_mixin.get_transitions = TransitionsMixin.get_transitions.__get__(
            transitions_mixin, type(transitions_mixin)
        )

        # Call with resolution field
        transitions_mixin.transition_issue(
            "TEST-123",
            "731",
            fields={"resolution": {"id": "10001"}},
        )

        # Verify the resolution field is present in the POST payload alongside
        # the transition id, so Jira sets it atomically with the status change
        transitions_mixin.jira.post.assert_called_once_with(
            "https://jira.example.com/rest/api/2/issue/TEST-123/transitions",
            json={
                "transition": {"id": "731"},
                "fields": {"resolution": {"id": "10001"}},
            },
        )

    def test_normalize_transition_id(self, transitions_mixin: TransitionsMixin):
        """Test _normalize_transition_id with various input types."""
        # Test with string
        assert transitions_mixin._normalize_transition_id("10") == 10

        # Test with non-digit string
        assert transitions_mixin._normalize_transition_id("workflow") == "workflow"

        # Test with int
        assert transitions_mixin._normalize_transition_id(10) == 10

        # Test with dict containing id
        assert transitions_mixin._normalize_transition_id({"id": "10"}) == 10

        # Test with dict containing int id
        assert transitions_mixin._normalize_transition_id({"id": 10}) == 10

        # Test with None
        assert transitions_mixin._normalize_transition_id(None) == 0

    def test_sanitize_transition_fields_basic(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test _sanitize_transition_fields with basic fields."""
        # Simple fields
        fields = {"resolution": {"name": "Fixed"}, "priority": {"name": "High"}}

        result = transitions_mixin._sanitize_transition_fields(fields)

        # Fields should be passed through unchanged
        assert result == fields

    def test_sanitize_transition_fields_with_none_values(
        self, transitions_mixin: TransitionsMixin
    ):
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

    def test_sanitize_transition_fields_with_assignee_error(
        self, transitions_mixin: TransitionsMixin
    ):
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

    def test_add_comment_to_transition_data_with_string(
        self, transitions_mixin: TransitionsMixin
    ):
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
        # On Cloud, body is ADF dict (not plain string)
        body = transition_data["update"]["comment"][0]["add"]["body"]
        assert isinstance(body, dict)
        assert body["version"] == 1
        assert body["type"] == "doc"

    def test_add_comment_to_transition_data_with_non_string(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test _add_comment_to_transition_data with non-string comment."""
        # Prepare transition data
        transition_data = {"transition": {"id": "10"}}

        # Call the method with int
        transitions_mixin._add_comment_to_transition_data(transition_data, 123)

        # On Cloud, converted "123" becomes ADF dict
        body = transition_data["update"]["comment"][0]["add"]["body"]
        assert isinstance(body, dict)
        assert body["version"] == 1

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
