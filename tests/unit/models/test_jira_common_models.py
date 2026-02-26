"""
Tests for common Jira Pydantic models.

Tests for JiraUser, JiraStatusCategory, JiraStatus, JiraIssueType,
JiraPriority, and JiraChangelog models.
"""

import json
from datetime import datetime, timezone

from mcp_atlassian.models.constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
    UNKNOWN,
)
from mcp_atlassian.models.jira import (
    JiraIssueType,
    JiraPriority,
    JiraStatus,
    JiraStatusCategory,
    JiraUser,
)
from mcp_atlassian.models.jira.common import JiraChangelog


class TestJiraUser:
    """Tests for the JiraUser model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraUser from valid API data."""
        user_data = {
            "accountId": "user123",
            "displayName": "Test User",
            "emailAddress": "test@example.com",
            "active": True,
            "avatarUrls": {
                "48x48": "https://example.com/avatar.png",
                "24x24": "https://example.com/avatar-small.png",
            },
            "timeZone": "UTC",
        }
        user = JiraUser.from_api_response(user_data)
        assert user.account_id == "user123"
        assert user.display_name == "Test User"
        assert user.email == "test@example.com"
        assert user.active is True
        assert user.avatar_url == "https://example.com/avatar.png"
        assert user.time_zone == "UTC"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraUser from empty data."""
        user = JiraUser.from_api_response({})
        assert user.account_id is None
        assert user.display_name == "Unassigned"
        assert user.email is None
        assert user.active is True
        assert user.avatar_url is None
        assert user.time_zone is None

    def test_from_api_response_with_none_data(self):
        """Test creating a JiraUser from None data."""
        user = JiraUser.from_api_response(None)
        assert user.account_id is None
        assert user.display_name == "Unassigned"
        assert user.email is None
        assert user.active is True
        assert user.avatar_url is None
        assert user.time_zone is None

    def test_to_simplified_dict(self):
        """Test converting JiraUser to a simplified dictionary."""
        user = JiraUser(
            account_id="user123",
            display_name="Test User",
            email="test@example.com",
            active=True,
            avatar_url="https://example.com/avatar.png",
            time_zone="UTC",
        )
        simplified = user.to_simplified_dict()
        assert isinstance(simplified, dict)
        assert simplified["display_name"] == "Test User"
        assert simplified["email"] == "test@example.com"
        assert simplified["avatar_url"] == "https://example.com/avatar.png"
        assert "account_id" not in simplified
        assert "time_zone" not in simplified


class TestJiraStatusCategory:
    """Tests for the JiraStatusCategory model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraStatusCategory from valid API data."""
        data = {
            "id": 4,
            "key": "indeterminate",
            "name": "In Progress",
            "colorName": "yellow",
        }
        category = JiraStatusCategory.from_api_response(data)
        assert category.id == 4
        assert category.key == "indeterminate"
        assert category.name == "In Progress"
        assert category.color_name == "yellow"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraStatusCategory from empty data."""
        category = JiraStatusCategory.from_api_response({})
        assert category.id == 0
        assert category.key == EMPTY_STRING
        assert category.name == UNKNOWN
        assert category.color_name == EMPTY_STRING


class TestJiraStatus:
    """Tests for the JiraStatus model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraStatus from valid API data."""
        data = {
            "id": "10000",
            "name": "In Progress",
            "description": "Work is in progress",
            "iconUrl": "https://example.com/icon.png",
            "statusCategory": {
                "id": 4,
                "key": "indeterminate",
                "name": "In Progress",
                "colorName": "yellow",
            },
        }
        status = JiraStatus.from_api_response(data)
        assert status.id == "10000"
        assert status.name == "In Progress"
        assert status.description == "Work is in progress"
        assert status.icon_url == "https://example.com/icon.png"
        assert status.category is not None
        assert status.category.id == 4
        assert status.category.name == "In Progress"
        assert status.category.color_name == "yellow"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraStatus from empty data."""
        status = JiraStatus.from_api_response({})
        assert status.id == JIRA_DEFAULT_ID
        assert status.name == UNKNOWN
        assert status.description is None
        assert status.icon_url is None
        assert status.category is None

    def test_to_simplified_dict(self):
        """Test converting JiraStatus to a simplified dictionary."""
        status = JiraStatus(
            id="10000",
            name="In Progress",
            description="Work is in progress",
            icon_url="https://example.com/icon.png",
            category=JiraStatusCategory(
                id=4, key="indeterminate", name="In Progress", color_name="yellow"
            ),
        )
        simplified = status.to_simplified_dict()
        assert isinstance(simplified, dict)
        assert simplified["name"] == "In Progress"
        assert "category" in simplified
        assert simplified["category"] == "In Progress"
        assert "color" in simplified
        assert simplified["color"] == "yellow"
        assert "description" not in simplified


class TestJiraIssueType:
    """Tests for the JiraIssueType model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraIssueType from valid API data."""
        data = {
            "id": "10000",
            "name": "Task",
            "description": "A task that needs to be done.",
            "iconUrl": "https://example.com/task-icon.png",
        }
        issue_type = JiraIssueType.from_api_response(data)
        assert issue_type.id == "10000"
        assert issue_type.name == "Task"
        assert issue_type.description == "A task that needs to be done."
        assert issue_type.icon_url == "https://example.com/task-icon.png"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraIssueType from empty data."""
        issue_type = JiraIssueType.from_api_response({})
        assert issue_type.id == JIRA_DEFAULT_ID
        assert issue_type.name == UNKNOWN
        assert issue_type.description is None
        assert issue_type.icon_url is None

    def test_to_simplified_dict(self):
        """Test converting JiraIssueType to a simplified dictionary."""
        issue_type = JiraIssueType(
            id="10000",
            name="Task",
            description="A task that needs to be done.",
            icon_url="https://example.com/task-icon.png",
        )
        simplified = issue_type.to_simplified_dict()
        assert isinstance(simplified, dict)
        assert simplified["name"] == "Task"
        assert "id" not in simplified
        assert "description" not in simplified
        assert "icon_url" not in simplified


class TestJiraPriority:
    """Tests for the JiraPriority model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraPriority from valid API data."""
        data = {
            "id": "3",
            "name": "Medium",
            "description": "Medium priority",
            "iconUrl": "https://example.com/medium-priority.png",
        }
        priority = JiraPriority.from_api_response(data)
        assert priority.id == "3"
        assert priority.name == "Medium"
        assert priority.description == "Medium priority"
        assert priority.icon_url == "https://example.com/medium-priority.png"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraPriority from empty data."""
        priority = JiraPriority.from_api_response({})
        assert priority.id == JIRA_DEFAULT_ID
        assert priority.name == "None"  # Default for priority is 'None'
        assert priority.description is None
        assert priority.icon_url is None

    def test_to_simplified_dict(self):
        """Test converting JiraPriority to a simplified dictionary."""
        priority = JiraPriority(
            id="3",
            name="Medium",
            description="Medium priority",
            icon_url="https://example.com/medium-priority.png",
        )
        simplified = priority.to_simplified_dict()
        assert isinstance(simplified, dict)
        assert simplified["name"] == "Medium"
        assert "id" not in simplified
        assert "description" not in simplified
        assert "icon_url" not in simplified


class TestJiraChangelog:
    """Tests for JiraChangelog datetime serialization (fixes #749)."""

    def test_created_datetime_serialization(self):
        """Test that datetime created field serializes to JSON properly."""
        changelog = JiraChangelog(
            id="12345",
            created=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            items=[],
        )

        # model_dump should serialize datetime to ISO string
        dumped = changelog.model_dump(mode="json")
        assert isinstance(dumped["created"], str)
        assert "2024-01-15" in dumped["created"]

        # to_simplified_dict should also work
        simplified = changelog.to_simplified_dict()
        assert isinstance(simplified["created"], str)

        # Final json.dumps should not raise
        json_str = json.dumps(simplified)
        assert "2024-01-15" in json_str

    def test_from_api_response_with_changelog(self):
        """Test JiraChangelog.from_api_response handles dates correctly."""
        data = {
            "id": "100",
            "created": "2024-01-15T10:30:00.000+0000",
            "author": {"displayName": "Test User"},
            "items": [{"field": "status", "fromString": "Open", "toString": "Done"}],
        }

        changelog = JiraChangelog.from_api_response(data)
        assert isinstance(changelog.created, datetime)

        # Should serialize cleanly to JSON
        simplified = changelog.to_simplified_dict()
        json_str = json.dumps(simplified)
        assert "2024-01-15" in json_str
