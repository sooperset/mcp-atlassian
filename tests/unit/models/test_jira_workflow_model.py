"""
Tests for the JiraTransition Pydantic model.
"""

from mcp_atlassian.models.constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
)
from mcp_atlassian.models.jira import (
    JiraTransition,
)


class TestJiraTransition:
    """Tests for the JiraTransition model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraTransition from valid API data."""
        transition_data = {
            "id": "10",
            "name": "Start Progress",
            "to": {
                "id": "3",
                "name": "In Progress",
                "statusCategory": {
                    "id": 4,
                    "key": "indeterminate",
                    "name": "In Progress",
                    "colorName": "yellow",
                },
            },
            "hasScreen": True,
            "isGlobal": False,
            "isInitial": False,
            "isConditional": True,
        }
        transition = JiraTransition.from_api_response(transition_data)
        assert transition.id == "10"
        assert transition.name == "Start Progress"
        assert transition.to_status is not None
        assert transition.to_status.id == "3"
        assert transition.to_status.name == "In Progress"
        assert transition.to_status.category is not None
        assert transition.to_status.category.name == "In Progress"
        assert transition.has_screen is True
        assert transition.is_global is False
        assert transition.is_initial is False
        assert transition.is_conditional is True

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraTransition from empty data."""
        transition = JiraTransition.from_api_response({})
        assert transition.id == JIRA_DEFAULT_ID
        assert transition.name == EMPTY_STRING
        assert transition.to_status is None
        assert transition.has_screen is False
        assert transition.is_global is False
        assert transition.is_initial is False
        assert transition.is_conditional is False

    def test_to_simplified_dict(self):
        """Test converting a JiraTransition to a simplified dictionary."""
        transition_data = {
            "id": "10",
            "name": "Start Progress",
            "to": {
                "id": "3",
                "name": "In Progress",
                "statusCategory": {
                    "id": 4,
                    "key": "indeterminate",
                    "name": "In Progress",
                    "colorName": "yellow",
                },
            },
            "hasScreen": True,
        }
        transition = JiraTransition.from_api_response(transition_data)
        simplified = transition.to_simplified_dict()
        assert simplified["id"] == "10"
        assert simplified["name"] == "Start Progress"
        assert simplified["to_status"] is not None
        assert simplified["to_status"]["name"] == "In Progress"
        assert "has_screen" not in simplified
        assert "is_global" not in simplified
