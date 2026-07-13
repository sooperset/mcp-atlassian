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
        mixin._post_api3 = MagicMock()

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
        # Call the method
        result = transitions_mixin.transition_issue("TEST-123", "10")

        # Verify POST to the Cloud v3 endpoint with a minimal payload
        transitions_mixin._post_api3.assert_called_once_with(
            "issue/TEST-123/transitions",
            {"transition": {"id": "10"}},
        )
        transitions_mixin.get_issue.assert_called_once_with("TEST-123")
        assert isinstance(result, JiraIssue)
        assert result.key == "TEST-123"
        assert result.summary == "Test Issue"
        assert result.description == "Issue content"

    def test_transition_issue_with_int_id(self, transitions_mixin: TransitionsMixin):
        """Test transition_issue with int transition ID."""
        # Call the method with int ID
        transitions_mixin.transition_issue("TEST-123", 10)

        # Verify the transition ID is stringified in the payload
        transitions_mixin._post_api3.assert_called_once_with(
            "issue/TEST-123/transitions",
            {"transition": {"id": "10"}},
        )

    def test_transition_issue_with_fields(self, transitions_mixin: TransitionsMixin):
        """Test transition_issue with fields."""
        # Mock _sanitize_transition_fields to return the fields
        transitions_mixin._sanitize_transition_fields = MagicMock(
            return_value={"summary": "Updated"}
        )

        # Call the method with fields
        fields = {"summary": "Updated"}
        transitions_mixin.transition_issue("TEST-123", "10", fields=fields)

        # Verify fields are included in the POST payload
        transitions_mixin._post_api3.assert_called_once_with(
            "issue/TEST-123/transitions",
            {
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

        # Call the method with fields that will be sanitized to empty
        fields = {"invalid": "field"}
        transitions_mixin.transition_issue("TEST-123", "10", fields=fields)

        # Empty sanitized fields should result in no "fields" key in the payload
        transitions_mixin._post_api3.assert_called_once_with(
            "issue/TEST-123/transitions",
            {"transition": {"id": "10"}},
        )

    def test_transition_issue_with_comment(self, transitions_mixin: TransitionsMixin):
        """Test transition_issue with comment."""
        comment = "Test comment"

        # Call the method with comment
        transitions_mixin.transition_issue("TEST-123", "10", comment=comment)

        # Cloud sends the converted ADF comment through REST v3.
        transitions_mixin._post_api3.assert_called_once()
        resource, payload = transitions_mixin._post_api3.call_args.args
        assert resource == "issue/TEST-123/transitions"
        assert payload["transition"] == {"id": "10"}
        body = payload["update"]["comment"][0]["add"]["body"]
        assert body["version"] == 1
        assert body["type"] == "doc"
        assert body["content"][0]["content"][0]["text"] == comment

    # --- JIRA_INTERNAL_ONLY_PROJECTS guard on transition comments ---

    def test_transition_comment_internal_only_project_rejected(
        self, transitions_mixin: TransitionsMixin
    ):
        """A transition comment on a listed project is rejected before any
        API call (a transition comment is a standard, potentially
        customer-visible Jira comment that cannot be forced internal)."""
        transitions_mixin.config.internal_only_projects = frozenset({"CC"})

        with pytest.raises(ValueError, match="internal-only"):
            transitions_mixin.transition_issue("CC-1", "10", comment="Client update")

        transitions_mixin._post_api3.assert_not_called()

    def test_transition_comment_internal_only_whitespace_padded_key_rejected(
        self, transitions_mixin: TransitionsMixin
    ):
        """Whitespace-padded issue keys do not bypass the transition guard."""
        transitions_mixin.config.internal_only_projects = frozenset({"CC"})

        with pytest.raises(ValueError, match="internal-only"):
            transitions_mixin.transition_issue(" CC-1", "10", comment="Client update")

    def test_transition_comment_unlisted_project_unaffected(
        self, transitions_mixin: TransitionsMixin
    ):
        """A comment on an unlisted project transitions normally even with
        the guard configured for another project."""
        transitions_mixin.config.internal_only_projects = frozenset({"CC"})

        transitions_mixin.transition_issue("TEST-123", "10", comment="Test comment")

        transitions_mixin._post_api3.assert_called_once()

    def test_transition_without_comment_internal_only_project_unaffected(
        self, transitions_mixin: TransitionsMixin
    ):
        """A transition WITHOUT a comment on a listed project is allowed —
        the guard only blocks the comment, not the transition itself."""
        transitions_mixin.config.internal_only_projects = frozenset({"CC"})

        transitions_mixin.transition_issue("CC-1", "10")

        transitions_mixin._post_api3.assert_called_once_with(
            "issue/CC-1/transitions",
            {"transition": {"id": "10"}},
        )

    def test_transition_issue_with_error(self, transitions_mixin: TransitionsMixin):
        """Test transition_issue error handling."""
        # Setup mock to raise exception on the POST
        transitions_mixin._post_api3.side_effect = Exception("Transition error")

        # Call the method and verify exception
        with pytest.raises(
            ValueError,
            match=(
                "Error transitioning issue TEST-123 with transition ID 10: "
                "Transition error"
            ),
        ):
            transitions_mixin.transition_issue("TEST-123", "10")

    def test_transition_issue_without_status_name(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test transition_issue when target status name is not available."""
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
        # Call the method
        result = transitions_mixin.transition_issue("TEST-123", "10")

        # Verify the unified POST still happens with the transition id
        transitions_mixin._post_api3.assert_called_once_with(
            "issue/TEST-123/transitions",
            {"transition": {"id": "10"}},
        )

        # Verify result
        transitions_mixin.get_issue.assert_called_once_with("TEST-123")
        assert isinstance(result, JiraIssue)

    def test_transition_issue_uses_v3_on_cloud(
        self, transitions_mixin: TransitionsMixin
    ):
        """Regression test for issue #1262.

        Cloud transition comments are converted to ADF, so their atomic
        transition payload must use REST v3.
        """
        transitions_mixin.transition_issue("TEST-123", "10", comment="Required")

        transitions_mixin._post_api3.assert_called_once()
        transitions_mixin.jira.post.assert_not_called()

    def test_transition_issue_uses_v2_on_data_center(
        self, transitions_mixin: TransitionsMixin
    ):
        """Server/DC sends wiki markup through the dependency's REST v2 URL."""
        transitions_mixin.config.url = "https://jira.example.com"
        transitions_mixin._markdown_to_jira = MagicMock(return_value="*Required*")
        transitions_mixin.jira.resource_url = MagicMock(
            return_value="https://jira.example.com/rest/api/2/issue"
        )

        transitions_mixin.transition_issue("TEST-123", "10", comment="**Required**")

        transitions_mixin.jira.resource_url.assert_called_once_with("issue")
        transitions_mixin.jira.post.assert_called_once_with(
            "https://jira.example.com/rest/api/2/issue/TEST-123/transitions",
            data={
                "transition": {"id": "10"},
                "update": {
                    "comment": [{"add": {"body": "*Required*"}}],
                },
            },
        )
        transitions_mixin._post_api3.assert_not_called()

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

        This verifies that get_issue_transitions_full returns complete 'to'
        objects and the JiraTransition models are created with proper to_status.
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

        After the unification onto a single direct POST path, this is verified
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
        transitions_mixin._post_api3.assert_called_once_with(
            "issue/TEST-123/transitions",
            {
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
        """Test assignee sanitization when _get_account_id is available."""
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
