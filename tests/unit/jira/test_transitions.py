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
        # Setup mock response - via get_issue_transitions_full
        mock_response = {
            "transitions": [
                {
                    "id": "10",
                    "name": "In Progress",
                    "to": {"name": "In Progress"},
                    "hasScreen": False,
                },
                {
                    "id": "11",
                    "name": "Done",
                    "to": {"name": "Done"},
                    "hasScreen": True,
                    "fields": {
                        "resolution": {
                            "required": True,
                            "name": "Resolution",
                            "schema": {"type": "resolution", "system": "resolution"},
                            "allowedValues": [
                                {"id": "1", "name": "Fixed"},
                                {"id": "2", "name": "Won't Fix"},
                            ],
                        }
                    },
                },
            ],
        }
        transitions_mixin.jira.get_issue_transitions_full.return_value = mock_response

        # Call the method
        result = transitions_mixin.get_available_transitions(
            "TEST-123", expand_fields=True
        )

        # Verify
        assert len(result) == 2
        assert result[0]["id"] == "10"
        assert result[0]["name"] == "In Progress"
        assert result[0]["to_status"] == "In Progress"
        assert result[0]["to"]["name"] == "In Progress"
        assert result[0]["has_screen"] is False
        assert "required_fields" not in result[0]

        assert result[1]["id"] == "11"
        assert result[1]["name"] == "Done"
        assert result[1]["has_screen"] is True
        required_fields = result[1]["required_fields"]
        assert len(required_fields) == 1
        assert required_fields[0]["key"] == "resolution"
        assert required_fields[0]["name"] == "Resolution"
        assert required_fields[0]["schema"]["type"] == "resolution"
        allowed = required_fields[0]["allowed_values"]
        assert len(allowed) == 2
        assert allowed[0]["name"] == "Fixed"

    def test_get_available_transitions_empty_response(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test get_available_transitions with empty response."""
        # Setup mock response - empty via get_issue_transitions_full
        transitions_mixin.jira.get_issue_transitions_full.return_value = {}

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
        transitions_mixin.jira.get_issue_transitions_full.return_value = "invalid"

        # Call the method
        result = transitions_mixin.get_available_transitions("TEST-123")

        # Verify
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_available_transitions_invalid_transitions_value(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test get_available_transitions handles a malformed transitions value."""
        transitions_mixin.jira.get_issue_transitions_full.return_value = {
            "transitions": "invalid"
        }

        assert transitions_mixin.get_available_transitions("TEST-123") == []

    def test_get_available_transitions_with_error(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test get_available_transitions error handling."""
        # Setup mock to raise exception
        transitions_mixin.jira.get_issue_transitions_full.side_effect = Exception(
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

        # Verify
        transitions_mixin.jira.set_issue_status.assert_called_once_with(
            issue_key="TEST-123", status_name="In Progress", fields=None, update=None
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

        # Verify status name is used instead of ID
        transitions_mixin.jira.set_issue_status.assert_called_once_with(
            issue_key="TEST-123", status_name="In Progress", fields=None, update=None
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

        # Verify fields were passed correctly
        transitions_mixin.jira.set_issue_status.assert_called_once_with(
            issue_key="TEST-123",
            status_name="In Progress",
            fields={"summary": "Updated"},
            update=None,
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

        # Verify fields were passed as None
        transitions_mixin.jira.set_issue_status.assert_called_once_with(
            issue_key="TEST-123", status_name="In Progress", fields=None, update=None
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

        # Call the method with comment
        transitions_mixin.transition_issue("TEST-123", "10", comment=comment)

        # Verify _add_comment_to_transition_data was called
        transitions_mixin._add_comment_to_transition_data.assert_called_once()

        # Verify set_issue_status was called with the right parameters
        transitions_mixin.jira.set_issue_status.assert_called_once_with(
            issue_key="TEST-123",
            status_name="In Progress",
            fields=None,
            update={"comment": [{"add": {"body": comment}}]},
        )

    def test_transition_issue_with_error(self, transitions_mixin: TransitionsMixin):
        """Test transition_issue error handling."""
        # Setup mock to raise exception
        transitions_mixin.jira.set_issue_status.side_effect = Exception(
            "Transition error"
        )

        # Call the method and verify exception
        with pytest.raises(
            ValueError,
            match="Error transitioning issue TEST-123 with transition ID 10: Transition error",
        ):
            transitions_mixin.transition_issue("TEST-123", "10")

    def test_transition_issue_without_status_name(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test transition_issue when status name is not available."""
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

        # Add mock for set_issue_status_by_transition_id
        transitions_mixin.jira.set_issue_status_by_transition_id = MagicMock()

        # Call the method
        result = transitions_mixin.transition_issue("TEST-123", "10")

        # Verify direct transition ID was used
        transitions_mixin.jira.set_issue_status_by_transition_id.assert_called_once_with(
            issue_key="TEST-123", transition_id=10
        )

        # Verify standard status call was not made
        transitions_mixin.jira.set_issue_status.assert_not_called()

        # Verify result
        transitions_mixin.get_issue.assert_called_once_with("TEST-123")
        assert isinstance(result, JiraIssue)

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
        """Test transition_issue with resolution field uses correct code path.

        This is the end-to-end test for issue #602 - when transitioning with fields
        like resolution, the to_status should be available (from get_issue_transitions_full)
        so set_issue_status is used which properly includes fields.
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

        # Verify set_issue_status was called (not set_issue_status_by_transition_id)
        # because to_status should now be available
        transitions_mixin.jira.set_issue_status.assert_called_once_with(
            issue_key="TEST-123",
            status_name="Closed",
            fields={"resolution": {"id": "10001"}},
            update=None,
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

        # Test with None raises ValueError
        with pytest.raises(ValueError, match="transition_id cannot be None"):
            transitions_mixin._normalize_transition_id(None)

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

    def test_transition_comment_format_cloud_adf(
        self, transitions_mixin: TransitionsMixin
    ):
        """Transition comment payload carries ADF dict on Cloud."""
        transitions_mixin._markdown_to_jira = MagicMock(
            return_value={"version": 1, "type": "doc", "content": []}
        )
        transitions_mixin._add_comment_to_transition_data = MagicMock(
            wraps=TransitionsMixin._add_comment_to_transition_data.__get__(
                transitions_mixin, type(transitions_mixin)
            )
        )

        transitions_mixin.transition_issue("TEST-123", "10", comment="Fixed")

        transitions_mixin.jira.set_issue_status.assert_called_once()
        call_kwargs = transitions_mixin.jira.set_issue_status.call_args.kwargs
        update = call_kwargs["update"]
        body = update["comment"][0]["add"]["body"]
        assert isinstance(body, dict)
        assert body["type"] == "doc"

    def test_transition_comment_format_dc_wiki(
        self, transitions_mixin: TransitionsMixin
    ):
        """Transition comment payload carries wiki markup on Server/DC."""
        transitions_mixin._markdown_to_jira = MagicMock(return_value="h2. Fixed")
        transitions_mixin._add_comment_to_transition_data = MagicMock(
            wraps=TransitionsMixin._add_comment_to_transition_data.__get__(
                transitions_mixin, type(transitions_mixin)
            )
        )

        transitions_mixin.transition_issue("TEST-123", "10", comment="Fixed")

        transitions_mixin.jira.set_issue_status.assert_called_once()
        call_kwargs = transitions_mixin.jira.set_issue_status.call_args.kwargs
        update = call_kwargs["update"]
        body = update["comment"][0]["add"]["body"]
        assert isinstance(body, str)
        assert "h2." in body

    def test_extract_required_fields_with_resolution(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test _extract_required_fields with resolution field."""
        fields = {
            "resolution": {
                "required": True,
                "name": "Resolution",
                "schema": {"type": "resolution", "system": "resolution"},
                "allowedValues": [
                    {"id": "1", "name": "Fixed"},
                    {"id": "3", "name": "Done"},
                ],
            },
            "summary": {
                "required": False,
                "name": "Summary",
                "schema": {"type": "string", "system": "summary"},
            },
        }

        result = TransitionsMixin._extract_required_fields(fields)

        assert len(result) == 1
        assert result[0]["key"] == "resolution"
        assert result[0]["name"] == "Resolution"
        assert result[0]["schema"]["type"] == "resolution"
        assert len(result[0]["allowed_values"]) == 2
        assert result[0]["allowed_values"][0]["id"] == "1"
        assert result[0]["allowed_values"][0]["name"] == "Fixed"

    def test_extract_required_fields_with_timetracking(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test _extract_required_fields with numeric custom field (e.g. Time Spent)."""
        fields = {
            "customfield_10000": {
                "required": True,
                "name": "Time Spent",
                "schema": {
                    "type": "number",
                    "custom": (
                        "com.atlassian.jira.plugin.system.customfieldtypes:float"
                    ),
                    "customId": 10000,
                },
            }
        }

        result = TransitionsMixin._extract_required_fields(fields)

        assert len(result) == 1
        assert result[0]["key"] == "customfield_10000"
        assert result[0]["name"] == "Time Spent"
        assert result[0]["schema"]["type"] == "number"
        assert "allowed_values" not in result[0]

    def test_extract_required_fields_empty(self):
        """Test _extract_required_fields with no required fields."""
        assert TransitionsMixin._extract_required_fields({}) == []

        fields = {
            "summary": {"required": False, "name": "Summary"},
        }
        assert TransitionsMixin._extract_required_fields(fields) == []

    def test_normalize_allowed_value_scalar(self):
        """Test _normalize_allowed_value preserves scalar choices."""
        result = TransitionsMixin._normalize_allowed_value("Fixed")
        assert result == "Fixed"

    def test_normalize_allowed_value_int_scalar(self):
        """Test _normalize_allowed_value preserves numeric scalar choices."""
        result = TransitionsMixin._normalize_allowed_value(42)
        assert result == 42

    def test_normalize_allowed_value_with_id_and_value(self):
        """Test _normalize_allowed_value exposes a value label as name."""
        result = TransitionsMixin._normalize_allowed_value(
            {"id": "1", "value": "Fixed"}
        )
        assert result == {"id": "1", "value": "Fixed", "name": "Fixed"}

    def test_normalize_allowed_value_with_id_and_name(self):
        """Test _normalize_allowed_value preserves a named option."""
        result = TransitionsMixin._normalize_allowed_value(
            {"id": "2", "name": "Won't Fix"}
        )
        assert result == {"id": "2", "name": "Won't Fix"}

    def test_normalize_allowed_value_with_option_id(self):
        """Test _normalize_allowed_value preserves optionId-shaped data."""
        result = TransitionsMixin._normalize_allowed_value(
            {"optionId": "100", "value": "Option A"}
        )
        assert result == {
            "optionId": "100",
            "value": "Option A",
            "name": "Option A",
        }

    def test_normalize_allowed_value_empty_dict(self):
        """Test _normalize_allowed_value preserves an empty option mapping."""
        result = TransitionsMixin._normalize_allowed_value({})
        assert result == {}

    def test_normalize_allowed_value_with_description(self):
        """Test _normalize_allowed_value preserves extra option metadata."""
        result = TransitionsMixin._normalize_allowed_value(
            {"id": "1", "name": "Fixed", "description": "A fix has been implemented"}
        )
        assert result == {
            "id": "1",
            "name": "Fixed",
            "description": "A fix has been implemented",
        }

    def test_normalize_allowed_value_with_empty_description(self):
        """Test _normalize_allowed_value preserves an empty description."""
        result = TransitionsMixin._normalize_allowed_value(
            {"id": "2", "name": "Done", "description": ""}
        )
        assert result == {"id": "2", "name": "Done", "description": ""}

    def test_extract_required_fields_with_scalar_allowed_values(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test _extract_required_fields with scalar allowed values."""
        fields = {
            "customfield_10001": {
                "required": True,
                "name": "Category",
                "schema": {"type": "option", "custom": "..."},
                "allowedValues": ["Fixed", "Won't Fix", 42],
            }
        }

        result = TransitionsMixin._extract_required_fields(fields)

        assert len(result) == 1
        allowed = result[0]["allowed_values"]
        assert len(allowed) == 3
        assert allowed[0] == "Fixed"
        assert allowed[2] == 42

    def test_extract_required_fields_with_id_value_allowed_values(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test _extract_required_fields with {id, value} allowed values."""
        fields = {
            "versions": {
                "required": True,
                "name": "Fix Versions",
                "schema": {"type": "array", "items": "version"},
                "allowedValues": [
                    {"id": "10001", "value": "v1.0"},
                    {"id": "10002", "value": "v2.0"},
                ],
            }
        }

        result = TransitionsMixin._extract_required_fields(fields)

        assert len(result) == 1
        allowed = result[0]["allowed_values"]
        assert len(allowed) == 2
        assert allowed[0] == {"id": "10001", "value": "v1.0", "name": "v1.0"}
        assert allowed[1] == {"id": "10002", "value": "v2.0", "name": "v2.0"}

    def test_extract_required_fields_with_mixed_allowed_values(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test _extract_required_fields with mixed shapes."""
        fields = {
            "customfield_10002": {
                "required": True,
                "name": "Mixed Field",
                "allowedValues": [
                    "Scalar",
                    {"id": "1", "name": "Named"},
                    {"id": "2", "value": "Valued"},
                ],
            }
        }

        result = TransitionsMixin._extract_required_fields(fields)

        assert len(result) == 1
        allowed = result[0]["allowed_values"]
        assert len(allowed) == 3
        assert allowed[0] == "Scalar"
        assert allowed[1] == {"id": "1", "name": "Named"}
        assert allowed[2] == {"id": "2", "value": "Valued", "name": "Valued"}

    def test_get_available_transitions_no_expand_by_default(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test get_available_transitions uses lightweight call by default."""
        mock_response = {"transitions": []}
        transitions_mixin.jira.get_issue_transitions_full.return_value = mock_response

        transitions_mixin.get_available_transitions("TEST-123")

        transitions_mixin.jira.get_issue_transitions_full.assert_called_once_with(
            "TEST-123"
        )

    def test_get_available_transitions_with_expand(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test get_available_transitions opts into field expansion."""
        mock_response = {"transitions": []}
        transitions_mixin.jira.get_issue_transitions_full.return_value = mock_response

        transitions_mixin.get_available_transitions("TEST-123", expand_fields=True)

        transitions_mixin.jira.get_issue_transitions_full.assert_called_once_with(
            "TEST-123", expand="transitions.fields"
        )

    def test_get_available_transitions_with_timetracking_field(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test get_available_transitions with Time Spent (timetracking) required."""
        mock_response = {
            "transitions": [
                {
                    "id": "51",
                    "name": "Resolve Issue",
                    "to": {"name": "Resolved", "id": "5"},
                    "hasScreen": True,
                    "fields": {
                        "timetracking": {
                            "required": True,
                            "name": "Time Spent",
                            "schema": {
                                "type": "timetracking",
                                "system": "timetracking",
                            },
                        },
                        "resolution": {
                            "required": True,
                            "name": "Resolution",
                            "schema": {"type": "resolution", "system": "resolution"},
                            "allowedValues": [
                                {"id": "1", "name": "Fixed"},
                            ],
                        },
                    },
                }
            ]
        }
        transitions_mixin.jira.get_issue_transitions_full.return_value = mock_response

        result = transitions_mixin.get_available_transitions("TEST-123")

        assert len(result) == 1
        assert result[0]["has_screen"] is True
        required = result[0]["required_fields"]
        assert len(required) == 2

        # Verify timetracking field
        tt = next(r for r in required if r["key"] == "timetracking")
        assert tt["name"] == "Time Spent"
        assert tt["schema"]["type"] == "timetracking"

        # Verify resolution field
        res = next(r for r in required if r["key"] == "resolution")
        assert res["name"] == "Resolution"
        assert len(res["allowed_values"]) == 1

    def test_transition_issue_with_update_data(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test transition_issue with update_data (worklog)."""
        # Call with update_data containing worklog
        update_data = {"worklog": [{"add": {"timeSpent": "1h", "comment": "Resolved"}}]}
        transitions_mixin.transition_issue("TEST-123", "10", update_data=update_data)

        # Verify set_issue_status was called with update
        transitions_mixin.jira.set_issue_status.assert_called_once_with(
            issue_key="TEST-123",
            status_name="In Progress",
            fields=None,
            update={"worklog": [{"add": {"timeSpent": "1h", "comment": "Resolved"}}]},
        )

    def test_transition_issue_with_comment_and_update_data(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test transition_issue with both comment and update_data."""

        # Setup mock for _add_comment_to_transition_data
        def add_comment_side_effect(transition_data, comment_text):
            transition_data.setdefault("update", {}).setdefault("comment", []).append(
                {"add": {"body": comment_text}}
            )

        transitions_mixin._add_comment_to_transition_data = MagicMock(
            side_effect=add_comment_side_effect
        )

        # Call with both comment and update_data
        update_data = {"worklog": [{"add": {"timeSpent": "2h"}}]}
        transitions_mixin.transition_issue(
            "TEST-123", "10", comment="Done", update_data=update_data
        )

        # Verify update contains both comment and worklog
        transitions_mixin.jira.set_issue_status.assert_called_once_with(
            issue_key="TEST-123",
            status_name="In Progress",
            fields=None,
            update={
                "comment": [{"add": {"body": "Done"}}],
                "worklog": [{"add": {"timeSpent": "2h"}}],
            },
        )

    def test_transition_issue_preserves_update_data_comments(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test comment combines with comment operations in update_data."""
        transitions_mixin._markdown_to_jira = MagicMock(return_value="New comment")
        existing_comment = {"add": {"body": "Existing comment"}}

        transitions_mixin.transition_issue(
            "TEST-123",
            "10",
            comment="New comment",
            update_data={"comment": [existing_comment]},
        )

        transitions_mixin.jira.set_issue_status.assert_called_once_with(
            issue_key="TEST-123",
            status_name="In Progress",
            fields=None,
            update={"comment": [existing_comment, {"add": {"body": "New comment"}}]},
        )

    def test_transition_issue_with_update_data_no_status_name(
        self, transitions_mixin: TransitionsMixin
    ):
        """Test transition_issue with update_data when no status name."""
        # Setup - transition without to_status
        mock_transitions = [
            JiraTransition(id="10", name="Start Progress", to_status=None)
        ]
        transitions_mixin.get_transitions_models = MagicMock(
            return_value=mock_transitions
        )
        transitions_mixin.jira.set_issue_status_by_transition_id = MagicMock()
        transitions_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        update_data = {"worklog": [{"add": {"timeSpent": "1h"}}]}
        transitions_mixin.transition_issue("TEST-123", "10", update_data=update_data)

        # Verify a single atomic request includes the transition and update data.
        transitions_mixin.jira.set_issue_status_by_transition_id.assert_not_called()
        transitions_mixin.jira.post.assert_called_once_with(
            "https://jira.example.com/rest/api/2/issue/TEST-123/transitions",
            data={
                "transition": {"id": "10"},
                "update": {"worklog": [{"add": {"timeSpent": "1h"}}]},
            },
        )

    def test_get_available_transitions_to_object_with_status_category(
        self, transitions_mixin: TransitionsMixin
    ):
        """get_available_transitions returns structured 'to' with statusCategory."""
        mock_response = {
            "transitions": [
                {
                    "id": "41",
                    "name": "Send to team",
                    "to": {
                        "id": "3",
                        "name": "In Progress",
                        "statusCategory": {
                            "id": 4,
                            "key": "indeterminate",
                            "name": "In Progress",
                        },
                    },
                    "hasScreen": False,
                },
            ],
        }
        transitions_mixin.jira.get_issue_transitions_full.return_value = mock_response

        result = transitions_mixin.get_available_transitions("TEST-123")

        assert len(result) == 1
        # Backward-compatible string
        assert result[0]["to_status"] == "In Progress"
        # Structured object
        to_obj = result[0]["to"]
        assert to_obj["id"] == "3"
        assert to_obj["name"] == "In Progress"
        assert to_obj["statusCategory"]["id"] == "4"
        assert to_obj["statusCategory"]["key"] == "indeterminate"
        assert to_obj["statusCategory"]["name"] == "In Progress"

    def test_get_available_transitions_to_object_no_status_category(
        self, transitions_mixin: TransitionsMixin
    ):
        """'to' object without statusCategory omits the key."""
        mock_response = {
            "transitions": [
                {
                    "id": "51",
                    "name": "Resolve",
                    "to": {"id": "5", "name": "Resolved"},
                    "hasScreen": True,
                },
            ],
        }
        transitions_mixin.jira.get_issue_transitions_full.return_value = mock_response

        result = transitions_mixin.get_available_transitions("TEST-123")

        assert len(result) == 1
        assert result[0]["to_status"] == "Resolved"
        assert result[0]["to"]["id"] == "5"
        assert result[0]["to"]["name"] == "Resolved"
        assert "statusCategory" not in result[0]["to"]
