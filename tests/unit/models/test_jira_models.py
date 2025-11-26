"""
Tests for the Jira Pydantic models.

These tests validate the conversion of Jira API responses to structured models
and the simplified dictionary conversion for API responses.
"""

import json
import os
import re
from datetime import datetime, timezone

import pytest

from src.mcp_atlassian.models.constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
    JIRA_DEFAULT_PROJECT,
    UNKNOWN,
)
from src.mcp_atlassian.models.jira import (
    JiraComment,
    JiraIssue,
    JiraIssueLink,
    JiraIssueLinkType,
    JiraIssueType,
    JiraLinkedIssue,
    JiraLinkedIssueFields,
    JiraPriority,
    JiraProject,
    JiraResolution,
    JiraSearchResult,
    JiraStatus,
    JiraStatusCategory,
    JiraTimetracking,
    JiraTransition,
    JiraUser,
    JiraWorklog,
)
from src.mcp_atlassian.models.jira.common import JiraChangelog

# Optional: Import real API client for optional real-data testing
try:
    from atlassian import Jira

    from src.mcp_atlassian.jira import JiraConfig, JiraFetcher
    from src.mcp_atlassian.jira.issues import IssuesMixin
    from src.mcp_atlassian.jira.projects import ProjectsMixin
    from src.mcp_atlassian.jira.transitions import TransitionsMixin
    from src.mcp_atlassian.jira.worklog import WorklogMixin

    real_api_available = True
except ImportError:
    real_api_available = False

    # Create a module-level namespace for dummy classes
    class _DummyClasses:
        """Namespace for dummy classes when real imports fail."""

        class JiraFetcher:
            pass

        class JiraConfig:
            @staticmethod
            def from_env():
                return None

        class IssuesMixin:
            pass

        class ProjectsMixin:
            pass

        class TransitionsMixin:
            pass

        class WorklogMixin:
            pass

        class Jira:
            pass

    # Assign dummy classes to module namespace
    JiraFetcher = _DummyClasses.JiraFetcher
    JiraConfig = _DummyClasses.JiraConfig
    IssuesMixin = _DummyClasses.IssuesMixin
    ProjectsMixin = _DummyClasses.ProjectsMixin
    TransitionsMixin = _DummyClasses.TransitionsMixin
    WorklogMixin = _DummyClasses.WorklogMixin
    Jira = _DummyClasses.Jira


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


class TestJiraComment:
    """Tests for the JiraComment model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraComment from valid API data."""
        data = {
            "id": "10000",
            "body": "This is a test comment",
            "created": "2024-01-01T12:00:00.000+0000",
            "updated": "2024-01-01T12:00:00.000+0000",
            "author": {
                "accountId": "user123",
                "displayName": "Comment User",
                "active": True,
            },
        }
        comment = JiraComment.from_api_response(data)
        assert comment.id == "10000"
        assert comment.body == "This is a test comment"
        assert comment.created == "2024-01-01T12:00:00.000+0000"
        assert comment.updated == "2024-01-01T12:00:00.000+0000"
        assert comment.author is not None
        assert comment.author.display_name == "Comment User"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraComment from empty data."""
        comment = JiraComment.from_api_response({})
        assert comment.id == JIRA_DEFAULT_ID
        assert comment.body == EMPTY_STRING
        assert comment.created == EMPTY_STRING
        assert comment.updated == EMPTY_STRING
        assert comment.author is None

    def test_to_simplified_dict(self):
        """Test converting JiraComment to a simplified dictionary."""
        comment = JiraComment(
            id="10000",
            body="This is a test comment",
            created="2024-01-01T12:00:00.000+0000",
            updated="2024-01-01T12:00:00.000+0000",
            author=JiraUser(account_id="user123", display_name="Comment User"),
        )
        simplified = comment.to_simplified_dict()
        assert isinstance(simplified, dict)
        assert "body" in simplified
        assert simplified["body"] == "This is a test comment"
        assert "created" in simplified
        assert isinstance(simplified["created"], str)
        assert "author" in simplified
        assert isinstance(simplified["author"], dict)
        assert simplified["author"]["display_name"] == "Comment User"


class TestJiraTimetracking:
    """Tests for the JiraTimetracking model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraTimetracking from valid API data."""
        data = {
            "originalEstimate": "2h",
            "remainingEstimate": "1h 30m",
            "timeSpent": "30m",
            "originalEstimateSeconds": 7200,
            "remainingEstimateSeconds": 5400,
            "timeSpentSeconds": 1800,
        }
        timetracking = JiraTimetracking.from_api_response(data)
        assert timetracking.original_estimate == "2h"
        assert timetracking.remaining_estimate == "1h 30m"
        assert timetracking.time_spent == "30m"
        assert timetracking.original_estimate_seconds == 7200
        assert timetracking.remaining_estimate_seconds == 5400
        assert timetracking.time_spent_seconds == 1800

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraTimetracking from empty data."""
        timetracking = JiraTimetracking.from_api_response({})
        assert timetracking.original_estimate is None
        assert timetracking.remaining_estimate is None
        assert timetracking.time_spent is None
        assert timetracking.original_estimate_seconds is None
        assert timetracking.remaining_estimate_seconds is None
        assert timetracking.time_spent_seconds is None

    def test_from_api_response_with_none_data(self):
        """Test creating a JiraTimetracking from None data."""
        timetracking = JiraTimetracking.from_api_response(None)
        assert timetracking is not None
        assert timetracking.original_estimate is None
        assert timetracking.remaining_estimate is None
        assert timetracking.time_spent is None
        assert timetracking.original_estimate_seconds is None
        assert timetracking.remaining_estimate_seconds is None
        assert timetracking.time_spent_seconds is None

    def test_to_simplified_dict(self):
        """Test converting JiraTimetracking to a simplified dictionary."""
        timetracking = JiraTimetracking(
            original_estimate="2h",
            remaining_estimate="1h 30m",
            time_spent="30m",
            original_estimate_seconds=7200,
            remaining_estimate_seconds=5400,
            time_spent_seconds=1800,
        )
        simplified = timetracking.to_simplified_dict()
        assert isinstance(simplified, dict)
        assert simplified["original_estimate"] == "2h"
        assert simplified["remaining_estimate"] == "1h 30m"
        assert simplified["time_spent"] == "30m"
        assert "original_estimate_seconds" not in simplified
        assert "remaining_estimate_seconds" not in simplified
        assert "time_spent_seconds" not in simplified


class TestJiraIssue:
    """Tests for the JiraIssue model."""

    def test_from_api_response_with_valid_data(self, jira_issue_data):
        """Test creating a JiraIssue from valid API data."""
        issue = JiraIssue.from_api_response(jira_issue_data)

        assert issue.id == "12345"
        assert issue.key == "PROJ-123"
        assert issue.summary == "Test Issue Summary"
        assert issue.description == "This is a test issue description"
        assert issue.created == "2024-01-01T10:00:00.000+0000"
        assert issue.updated == "2024-01-02T15:30:00.000+0000"

        assert issue.status is not None
        assert issue.status.name == "In Progress"
        assert issue.status.category is not None
        assert issue.status.category.name == "In Progress"

        assert issue.issue_type is not None
        assert issue.issue_type.name == "Task"

        assert issue.priority is not None
        assert issue.priority.name == "Medium"

        assert issue.assignee is not None
        assert issue.assignee.display_name == "Test User"

        assert issue.reporter is not None
        assert issue.reporter.display_name == "Reporter User"

        assert len(issue.labels) == 1
        assert issue.labels[0] == "test-label"

        assert len(issue.comments) == 1
        assert issue.comments[0].body == "This is a test comment"

        assert isinstance(issue.fix_versions, list)
        assert "v1.0" in issue.fix_versions

        assert isinstance(issue.attachments, list)
        assert len(issue.attachments) == 1
        assert issue.attachments[0].filename == "test_attachment.txt"

        assert isinstance(issue.timetracking, JiraTimetracking)
        assert issue.timetracking.original_estimate == "1d"

        assert issue.project is not None
        assert issue.project.key == "PROJ"
        assert issue.project.name == "Test Project"
        assert issue.resolution is not None
        assert issue.resolution.name == "Fixed"
        assert issue.duedate == "2024-12-31"
        assert issue.resolutiondate == "2024-01-15T11:00:00.000+0000"
        assert issue.parent is not None
        assert issue.parent["key"] == "PROJ-122"
        assert issue.subtasks is not None
        assert len(issue.subtasks) == 1
        assert issue.subtasks[0]["key"] == "PROJ-124"
        assert issue.security is not None
        assert issue.security["name"] == "Internal"
        assert issue.worklog is not None
        assert issue.worklog["total"] == 0
        assert issue.worklog["maxResults"] == 20

        # Verify custom_fields structure after from_api_response
        assert "customfield_10001" in issue.custom_fields
        assert issue.custom_fields["customfield_10001"] == {
            "value": "Custom Text Field Value",
            "name": "My Custom Text Field",
        }
        assert "customfield_10002" in issue.custom_fields
        assert issue.custom_fields["customfield_10002"] == {
            "value": {"value": "Custom Select Value"},  # Original value is a dict
            "name": "My Custom Select",
        }

    def test_from_api_response_with_new_fields(self):
        """Test creating a JiraIssue focusing on parsing the new fields."""
        # Construct local mock data including the new fields
        local_issue_data = {
            "id": "9999",
            "key": "NEW-1",
            "fields": {
                "summary": "Issue testing new fields",
                "project": {
                    "id": "10001",
                    "key": "NEWPROJ",
                    "name": "New Project",
                    "avatarUrls": {"48x48": "url"},
                },
                "resolution": {"id": "10002", "name": "Fixed"},
                "duedate": "2025-01-31",
                "resolutiondate": "2024-08-01T12:00:00.000+0000",
                "parent": {
                    "id": "9998",
                    "key": "NEW-0",
                    "fields": {"summary": "Parent Task"},
                },
                "subtasks": [
                    {"id": "10000", "key": "NEW-2", "fields": {"summary": "Subtask 1"}},
                    {"id": "10001", "key": "NEW-3", "fields": {"summary": "Subtask 2"}},
                ],
                "security": {"id": "10003", "name": "Dev Only"},
                "worklog": {"total": 2, "maxResults": 20, "worklogs": []},
            },
        }
        issue = JiraIssue.from_api_response(local_issue_data)

        assert issue.id == "9999"
        assert issue.key == "NEW-1"
        assert issue.summary == "Issue testing new fields"

        # Assertions for new fields using LOCAL data
        assert isinstance(issue.project, JiraProject)
        assert issue.project.key == "NEWPROJ"
        assert issue.project.name == "New Project"
        assert isinstance(issue.resolution, JiraResolution)
        assert issue.resolution.name == "Fixed"
        assert issue.duedate == "2025-01-31"
        assert issue.resolutiondate == "2024-08-01T12:00:00.000+0000"
        assert isinstance(issue.parent, dict)
        assert issue.parent["key"] == "NEW-0"
        assert isinstance(issue.subtasks, list)
        assert len(issue.subtasks) == 2
        assert issue.subtasks[0]["key"] == "NEW-2"
        assert isinstance(issue.security, dict)
        assert issue.security["name"] == "Dev Only"
        assert isinstance(issue.worklog, dict)
        assert issue.worklog["total"] == 2

    def test_from_api_response_with_issuelinks(self, jira_issue_data):
        """Test creating a JiraIssue with issue links."""
        # Augment jira_issue_data with mock issuelinks
        mock_issuelinks_data = [
            {
                "id": "10000",
                "type": {
                    "id": "10000",
                    "name": "Blocks",
                    "inward": "is blocked by",
                    "outward": "blocks",
                },
                "outwardIssue": {
                    "id": "10001",
                    "key": "PROJ-789",
                    "self": "https://example.atlassian.net/rest/api/2/issue/10001",
                    "fields": {
                        "summary": "Blocked Issue",
                        "status": {"name": "Open"},
                        "priority": {"name": "High"},
                        "issuetype": {"name": "Task"},
                    },
                },
            },
            {
                "id": "10001",
                "type": {
                    "id": "10001",
                    "name": "Relates to",
                    "inward": "relates to",
                    "outward": "relates to",
                },
                "inwardIssue": {
                    "id": "10002",
                    "key": "PROJ-111",
                    "self": "https://example.atlassian.net/rest/api/2/issue/10002",
                    "fields": {
                        "summary": "Related Issue",
                        "status": {"name": "In Progress"},
                        "priority": {"name": "Medium"},
                        "issuetype": {"name": "Story"},
                    },
                },
            },
        ]
        jira_issue_data_with_links = jira_issue_data.copy()
        # Ensure fields dictionary exists
        if "fields" not in jira_issue_data_with_links:
            jira_issue_data_with_links["fields"] = {}
        jira_issue_data_with_links["fields"]["issuelinks"] = mock_issuelinks_data

        issue = JiraIssue.from_api_response(
            jira_issue_data_with_links, requested_fields="*all"
        )

        assert issue.issuelinks is not None
        assert len(issue.issuelinks) == 2
        assert isinstance(issue.issuelinks[0], JiraIssueLink)

        # Check first link (outward)
        assert issue.issuelinks[0].id == "10000"
        assert issue.issuelinks[0].type is not None
        assert issue.issuelinks[0].type.name == "Blocks"
        assert issue.issuelinks[0].outward_issue is not None
        assert issue.issuelinks[0].outward_issue.key == "PROJ-789"
        assert issue.issuelinks[0].outward_issue.fields is not None
        assert issue.issuelinks[0].outward_issue.fields.summary == "Blocked Issue"
        assert issue.issuelinks[0].inward_issue is None

        # Test simplified dict output
        simplified = issue.to_simplified_dict()
        assert "issuelinks" in simplified
        assert len(simplified["issuelinks"]) == 2
        assert simplified["issuelinks"][0]["type"]["name"] == "Blocks"
        assert simplified["issuelinks"][0]["outward_issue"]["key"] == "PROJ-789"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraIssue from empty data."""
        issue = JiraIssue.from_api_response({})
        assert issue.id == JIRA_DEFAULT_ID
        assert issue.key == "UNKNOWN-0"
        assert issue.summary == EMPTY_STRING
        assert issue.description is None
        assert issue.created == EMPTY_STRING
        assert issue.updated == EMPTY_STRING
        assert issue.status is None
        assert issue.issue_type is None
        assert issue.priority is None
        assert issue.assignee is None
        assert issue.reporter is None
        assert len(issue.labels) == 0
        assert len(issue.comments) == 0
        assert issue.project is None
        assert issue.resolution is None
        assert issue.duedate is None
        assert issue.resolutiondate is None
        assert issue.parent is None
        assert issue.subtasks == []
        assert issue.security is None
        assert issue.worklog is None

    def test_to_simplified_dict(self, jira_issue_data):
        """Test converting a JiraIssue to a simplified dictionary."""
        issue = JiraIssue.from_api_response(jira_issue_data)
        simplified = issue.to_simplified_dict()

        # Essential fields from original test
        assert isinstance(simplified, dict)
        assert "key" in simplified
        assert simplified["key"] == "PROJ-123"
        assert "summary" in simplified
        assert simplified["summary"] == "Test Issue Summary"

        assert "created" in simplified
        assert isinstance(simplified["created"], str)
        assert "updated" in simplified
        assert isinstance(simplified["updated"], str)

        if isinstance(simplified["status"], str):
            assert simplified["status"] == "In Progress"
        elif isinstance(simplified["status"], dict):
            assert simplified["status"]["name"] == "In Progress"

        if isinstance(simplified["issue_type"], str):
            assert simplified["issue_type"] == "Task"
        elif isinstance(simplified["issue_type"], dict):
            assert simplified["issue_type"]["name"] == "Task"

        if isinstance(simplified["priority"], str):
            assert simplified["priority"] == "Medium"
        elif isinstance(simplified["priority"], dict):
            assert simplified["priority"]["name"] == "Medium"

        assert "assignee" in simplified
        assert "reporter" in simplified

        # Test with "*all"
        issue_all = JiraIssue.from_api_response(
            jira_issue_data, requested_fields="*all"
        )
        simplified_all = issue_all.to_simplified_dict()

        # Check keys for all standard fields (new and old) are present
        all_standard_keys = {
            "id",
            "key",
            "summary",
            "description",
            "created",
            "updated",
            "status",
            "issue_type",
            "priority",
            "assignee",
            "reporter",
            "labels",
            "components",
            "timetracking",
            "comments",
            "attachments",
            "url",
            "epic_key",
            "epic_name",
            "fix_versions",
            "project",
            "resolution",
            "duedate",
            "resolutiondate",
            "parent",
            "subtasks",
            "security",
            "worklog",
            # Custom fields present in the mock data should be at the root level when requesting *all
            "customfield_10011",
            "customfield_10014",
            "customfield_10001",
            "customfield_10002",
            "customfield_10003",
        }
        assert all_standard_keys.issubset(simplified_all.keys())

        # Check values for new fields based on mock data
        assert simplified_all["project"]["key"] == "PROJ"
        assert simplified_all["resolution"]["name"] == "Fixed"
        assert simplified_all["duedate"] == "2024-12-31"
        assert simplified_all["resolutiondate"] == "2024-01-15T11:00:00.000+0000"
        assert simplified_all["parent"]["key"] == "PROJ-122"
        assert len(simplified_all["subtasks"]) == 1
        assert simplified_all["security"]["name"] == "Internal"
        assert isinstance(simplified_all["worklog"], dict)

        requested = [
            "key",
            "summary",
            "project",
            "resolution",
            "subtasks",
            "customfield_10011",
        ]
        issue_specific = JiraIssue.from_api_response(
            jira_issue_data, requested_fields=requested
        )
        simplified_specific = issue_specific.to_simplified_dict()

        # Check the requested keys are present
        assert set(simplified_specific.keys()) == {
            "id",
            "key",
            "summary",
            "project",
            "resolution",
            "subtasks",
            "customfield_10011",
        }

        # Check values based on mock data
        assert simplified_specific["project"]["key"] == "PROJ"
        assert simplified_specific["resolution"]["name"] == "Fixed"
        assert len(simplified_specific["subtasks"]) == 1
        # Check custom field output
        assert (
            simplified_specific["customfield_10011"]
            == {
                "value": "Epic Name Example",
                "name": "Epic Name",  # Comes from the "names" map in MOCK_JIRA_ISSUE_RESPONSE
            }
        )

    def test_find_custom_field_in_api_response(self):
        """Test the _find_custom_field_in_api_response method with different field patterns."""
        fields = {
            "customfield_10014": "EPIC-123",
            "customfield_10011": "Epic Name Test",
            "customfield_10000": "Another value",
            "schema": {
                "fields": {
                    "customfield_10014": {"name": "Epic Link", "type": "string"},
                    "customfield_10011": {"name": "Epic Name", "type": "string"},
                    "customfield_10000": {"name": "Custom Field", "type": "string"},
                }
            },
        }

        result = JiraIssue._find_custom_field_in_api_response(fields, ["Epic Link"])
        assert result == "EPIC-123"

        result = JiraIssue._find_custom_field_in_api_response(fields, ["Epic Name"])
        assert result == "Epic Name Test"

        result = JiraIssue._find_custom_field_in_api_response(fields, ["epic link"])
        assert result == "EPIC-123"

        result = JiraIssue._find_custom_field_in_api_response(
            fields, ["epic-link", "epiclink"]
        )
        assert result == "EPIC-123"

        result = JiraIssue._find_custom_field_in_api_response(
            fields, ["Non Existent Field"]
        )
        assert result is None

        result = JiraIssue._find_custom_field_in_api_response({}, ["Epic Link"])
        assert result is None

        result = JiraIssue._find_custom_field_in_api_response(None, ["Epic Link"])
        assert result is None

    def test_epic_field_extraction_different_field_ids(self):
        """Test finding epic fields with different customfield IDs."""
        test_data = {
            "id": "12345",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test Issue",
                "customfield_20100": "EPIC-456",
                "customfield_20200": "My Epic Name",
                "schema": {
                    "fields": {
                        "customfield_20100": {"name": "Epic Link", "type": "string"},
                        "customfield_20200": {"name": "Epic Name", "type": "string"},
                    }
                },
            },
        }
        issue = JiraIssue.from_api_response(test_data)
        assert issue.epic_key == "EPIC-456"
        assert issue.epic_name == "My Epic Name"

    def test_epic_field_extraction_fallback(self):
        """Test using common field names without relying on metadata."""
        test_data = {
            "id": "12345",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test Issue",
                "customfield_10014": "EPIC-456",
                "customfield_10011": "My Epic Name",
            },
        }

        original_method = JiraIssue._find_custom_field_in_api_response
        try:

            def mocked_find_field(fields, name_patterns):
                normalized_patterns = []
                for pattern in name_patterns:
                    norm_pattern = pattern.lower()
                    norm_pattern = re.sub(r"[_\-\s]", "", norm_pattern)
                    normalized_patterns.append(norm_pattern)

                if any("epiclink" in p for p in normalized_patterns):
                    return fields.get("customfield_10014")
                if any("epicname" in p for p in normalized_patterns):
                    return fields.get("customfield_10011")
                return None

            JiraIssue._find_custom_field_in_api_response = staticmethod(
                mocked_find_field
            )

            issue = JiraIssue.from_api_response(test_data)
            assert issue.epic_key == "EPIC-456"
            assert issue.epic_name == "My Epic Name"
        finally:
            JiraIssue._find_custom_field_in_api_response = staticmethod(original_method)

    def test_epic_field_extraction_advanced_patterns(self):
        """Test finding epic fields using various naming patterns."""
        test_data = {
            "id": "12345",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test Issue",
                "customfield_12345": "EPIC-456",
                "customfield_67890": "Epic Name Value",
                "schema": {
                    "fields": {
                        "customfield_12345": {
                            "name": "Epic-Link Field",
                            "type": "string",
                        },
                        "customfield_67890": {"name": "EpicName", "type": "string"},
                    }
                },
            },
        }
        issue = JiraIssue.from_api_response(test_data)
        assert issue.epic_key == "EPIC-456"
        assert issue.epic_name == "Epic Name Value"

    def test_fields_with_names(self):
        """Test using the names to find fields."""

        fields = {
            "customfield_55555": "EPIC-789",
            "customfield_66666": "Special Epic Name",
            "names": {
                "customfield_55555": "Epic Link",
                "customfield_66666": "Epic Name",
            },
        }

        result = JiraIssue._find_custom_field_in_api_response(fields, ["Epic Link"])
        assert result == "EPIC-789"

        test_data = {"id": "12345", "key": "PROJ-123", "fields": fields}
        issue = JiraIssue.from_api_response(test_data)
        assert issue.epic_key == "EPIC-789"
        assert issue.epic_name == "Special Epic Name"

    def test_jira_issue_with_custom_fields(self, jira_issue_data):
        """Test JiraIssue handling of custom fields."""
        issue = JiraIssue.from_api_response(jira_issue_data)
        simplified = issue.to_simplified_dict()
        assert simplified["key"] == "PROJ-123"
        assert simplified["summary"] == "Test Issue Summary"
        # By default (no requested_fields or default set), custom fields are not included
        # unless they are part of DEFAULT_READ_JIRA_FIELDS (which they are not).
        # So, this assertion should be that they are NOT present.
        assert "customfield_10001" not in simplified
        assert "customfield_10002" not in simplified
        assert "customfield_10003" not in simplified

        issue = JiraIssue.from_api_response(
            jira_issue_data, requested_fields="summary,customfield_10001"
        )
        simplified = issue.to_simplified_dict()
        assert "key" in simplified
        assert "summary" in simplified
        assert "customfield_10001" in simplified
        assert simplified["customfield_10001"]["value"] == "Custom Text Field Value"
        assert simplified["customfield_10001"]["name"] == "My Custom Text Field"
        assert "customfield_10002" not in simplified

        issue = JiraIssue.from_api_response(
            jira_issue_data, requested_fields=["key", "customfield_10002"]
        )
        simplified = issue.to_simplified_dict()
        assert "key" in simplified
        assert "customfield_10002" in simplified
        assert "summary" not in simplified
        assert "customfield_10001" not in simplified
        assert simplified["customfield_10002"]["value"] == "Custom Select Value"
        assert simplified["customfield_10002"]["name"] == "My Custom Select"

        issue = JiraIssue.from_api_response(jira_issue_data, requested_fields="*all")
        simplified = issue.to_simplified_dict()
        assert "key" in simplified
        assert "summary" in simplified
        assert "customfield_10001" in simplified
        assert simplified["customfield_10001"]["value"] == "Custom Text Field Value"
        assert simplified["customfield_10001"]["name"] == "My Custom Text Field"
        assert "customfield_10002" in simplified
        assert simplified["customfield_10002"]["value"] == "Custom Select Value"
        assert simplified["customfield_10002"]["name"] == "My Custom Select"
        assert "customfield_10003" in simplified

        issue_specific = JiraIssue.from_api_response(
            jira_issue_data, requested_fields="key,customfield_10014"
        )
        simplified_specific = issue_specific.to_simplified_dict()
        assert "customfield_10014" in simplified_specific
        assert simplified_specific.get("customfield_10014") == {
            "value": "EPIC-KEY-1",
            "name": "Epic Link",
        }

    def test_jira_issue_with_default_fields(self, jira_issue_data):
        """Test that JiraIssue returns only essential fields by default."""
        issue = JiraIssue.from_api_response(jira_issue_data)
        simplified = issue.to_simplified_dict()
        # Check essential fields ARE present
        essential_keys = {
            "id",
            "key",
            "summary",
            "url",
            "description",
            "status",
            "issue_type",
            "priority",
            "project",
            "resolution",
            "duedate",
            "resolutiondate",
            "parent",
            "subtasks",
            "security",
            "worklog",
            "assignee",
            "reporter",
            "labels",
            "components",
            "fix_versions",
            "epic_key",
            "epic_name",
            "timetracking",
            "created",
            "updated",
            "comments",
            "attachments",
        }
        # We check if the key is present; value might be None if not in source data
        for key in essential_keys:
            assert key in simplified, (
                f"Essential key '{key}' missing from default simplified dict"
            )
        assert "customfield_10001" not in simplified
        assert "customfield_10002" not in simplified

        issue = JiraIssue.from_api_response(jira_issue_data, requested_fields="*all")
        simplified = issue.to_simplified_dict()
        assert "customfield_10001" in simplified
        assert "customfield_10002" in simplified

    def test_timetracking_field_processing(self, jira_issue_data):
        """Test that timetracking data is properly processed."""
        issue = JiraIssue.from_api_response(jira_issue_data)
        assert issue.timetracking is not None
        assert issue.timetracking.original_estimate == "1d"
        assert issue.timetracking.remaining_estimate == "4h"
        assert issue.timetracking.time_spent == "4h"
        assert issue.timetracking.original_estimate_seconds == 28800
        assert issue.timetracking.remaining_estimate_seconds == 14400
        assert issue.timetracking.time_spent_seconds == 14400

        issue.requested_fields = "*all"
        simplified = issue.to_simplified_dict()
        assert "timetracking" in simplified
        assert simplified["timetracking"]["original_estimate"] == "1d"

        issue.requested_fields = ["summary", "timetracking"]
        simplified = issue.to_simplified_dict()
        assert "timetracking" in simplified
        assert simplified["timetracking"]["original_estimate"] == "1d"


class TestJiraSearchResult:
    """Tests for the JiraSearchResult model."""

    def test_from_api_response_with_valid_data(self, jira_search_data):
        """Test creating a JiraSearchResult from valid API data."""
        search_result = JiraSearchResult.from_api_response(jira_search_data)
        assert search_result.total == 34
        assert search_result.start_at == 0
        assert search_result.max_results == 5
        assert len(search_result.issues) == 1

        issue = search_result.issues[0]
        assert isinstance(issue, JiraIssue)
        assert issue.key == "PROJ-123"
        assert issue.summary == "Test Issue Summary"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraSearchResult from empty data."""
        result = JiraSearchResult.from_api_response({})
        assert result.total == 0
        assert result.start_at == 0
        assert result.max_results == 0
        assert result.issues == []

    def test_from_api_response_missing_metadata(self, jira_search_data):
        """Test creating a JiraSearchResult when API is missing metadata."""
        # Remove total, startAt, maxResults from mock data
        api_data = dict(jira_search_data)
        api_data.pop("total", None)
        api_data.pop("startAt", None)
        api_data.pop("maxResults", None)

        search_result = JiraSearchResult.from_api_response(api_data)
        # Verify that -1 is used for missing metadata
        assert search_result.total == -1
        assert search_result.start_at == -1
        assert search_result.max_results == -1
        assert len(search_result.issues) == 1  # Assuming mock data has issues

    def test_to_simplified_dict(self, jira_search_data):
        """Test converting JiraSearchResult to a simplified dictionary."""
        search_result = JiraSearchResult.from_api_response(jira_search_data)
        simplified = search_result.to_simplified_dict()

        # Verify the structure and basic metadata
        assert isinstance(simplified, dict)
        assert "total" in simplified
        assert "start_at" in simplified
        assert "max_results" in simplified
        assert "issues" in simplified

        # Verify metadata values
        assert simplified["total"] == 34
        assert simplified["start_at"] == 0
        assert simplified["max_results"] == 5

        # Verify issues array
        assert isinstance(simplified["issues"], list)
        assert len(simplified["issues"]) == 1

        # Verify that each issue is a simplified dict (not a JiraIssue object)
        issue = simplified["issues"][0]
        assert isinstance(issue, dict)
        assert issue["key"] == "PROJ-123"
        assert issue["summary"] == "Test Issue Summary"

        # Verify that the issues are properly simplified (calling to_simplified_dict on each)
        # This ensures field filtering works properly
        assert "id" in issue  # ID is included in simplified version
        assert "expand" not in issue  # Should be filtered out in simplified version

        # Verify that issue contains expected fields
        assert "assignee" in issue
        assert "created" in issue
        assert "updated" in issue

    def test_to_simplified_dict_empty_result(self):
        """Test converting an empty JiraSearchResult to a simplified dictionary."""
        search_result = JiraSearchResult()
        simplified = search_result.to_simplified_dict()

        assert isinstance(simplified, dict)
        assert simplified["total"] == 0
        assert simplified["start_at"] == 0
        assert simplified["max_results"] == 0
        assert simplified["issues"] == []

    def test_to_simplified_dict_with_multiple_issues(self):
        """Test converting JiraSearchResult with multiple issues to a simplified dictionary."""
        # Create mock data with multiple issues
        mock_data = {
            "total": 2,
            "startAt": 0,
            "maxResults": 10,
            "issues": [
                {
                    "id": "12345",
                    "key": "PROJ-123",
                    "fields": {
                        "summary": "First Issue",
                        "status": {"name": "In Progress"},
                    },
                },
                {
                    "id": "12346",
                    "key": "PROJ-124",
                    "fields": {
                        "summary": "Second Issue",
                        "status": {"name": "Done"},
                    },
                },
            ],
        }

        search_result = JiraSearchResult.from_api_response(mock_data)
        simplified = search_result.to_simplified_dict()

        # Verify metadata
        assert simplified["total"] == 2
        assert simplified["start_at"] == 0
        assert simplified["max_results"] == 10

        # Verify issues
        assert len(simplified["issues"]) == 2
        assert simplified["issues"][0]["key"] == "PROJ-123"
        assert simplified["issues"][0]["summary"] == "First Issue"
        assert simplified["issues"][1]["key"] == "PROJ-124"
        assert simplified["issues"][1]["summary"] == "Second Issue"


class TestJiraProject:
    """Tests for the JiraProject model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraProject from valid API data."""
        project_data = {
            "id": "10000",
            "key": "TEST",
            "name": "Test Project",
            "description": "This is a test project",
            "lead": {
                "accountId": "5b10a2844c20165700ede21g",
                "displayName": "John Doe",
                "active": True,
            },
            "self": "https://example.atlassian.net/rest/api/3/project/10000",
            "projectCategory": {
                "id": "10100",
                "name": "Software Projects",
                "description": "Software development projects",
            },
            "avatarUrls": {
                "48x48": "https://example.atlassian.net/secure/projectavatar?pid=10000&avatarId=10011",
                "24x24": "https://example.atlassian.net/secure/projectavatar?pid=10000&size=small&avatarId=10011",
            },
        }
        project = JiraProject.from_api_response(project_data)
        assert project.id == "10000"
        assert project.key == "TEST"
        assert project.name == "Test Project"
        assert project.description == "This is a test project"
        assert project.lead is not None
        assert project.lead.display_name == "John Doe"
        assert project.url == "https://example.atlassian.net/rest/api/3/project/10000"
        assert project.category_name == "Software Projects"
        assert (
            project.avatar_url
            == "https://example.atlassian.net/secure/projectavatar?pid=10000&avatarId=10011"
        )

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraProject from empty data."""
        project = JiraProject.from_api_response({})
        assert project.id == JIRA_DEFAULT_PROJECT
        assert project.key == EMPTY_STRING
        assert project.name == UNKNOWN
        assert project.description is None
        assert project.lead is None
        assert project.url is None
        assert project.category_name is None
        assert project.avatar_url is None

    def test_to_simplified_dict(self):
        """Test converting a JiraProject to a simplified dictionary."""
        project_data = {
            "id": "10000",
            "key": "TEST",
            "name": "Test Project",
            "description": "This is a test project",
            "lead": {
                "accountId": "5b10a2844c20165700ede21g",
                "displayName": "John Doe",
                "active": True,
            },
            "self": "https://example.atlassian.net/rest/api/3/project/10000",
            "projectCategory": {
                "name": "Software Projects",
            },
        }
        project = JiraProject.from_api_response(project_data)
        simplified = project.to_simplified_dict()
        assert simplified["key"] == "TEST"
        assert simplified["name"] == "Test Project"
        assert simplified["description"] == "This is a test project"
        assert simplified["lead"] is not None
        assert simplified["lead"]["display_name"] == "John Doe"
        assert simplified["category"] == "Software Projects"
        assert "id" not in simplified
        assert "url" not in simplified
        assert "avatar_url" not in simplified


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


class TestJiraIssueLinkType:
    """Tests for the JiraIssueLinkType model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraIssueLinkType from valid API data."""
        data = {
            "id": "10001",
            "name": "Blocks",
            "inward": "is blocked by",
            "outward": "blocks",
            "self": "https://example.atlassian.net/rest/api/3/issueLinkType/10001",
        }
        link_type = JiraIssueLinkType.from_api_response(data)
        assert link_type.id == "10001"
        assert link_type.name == "Blocks"
        assert link_type.inward == "is blocked by"
        assert link_type.outward == "blocks"
        assert (
            link_type.self_url
            == "https://example.atlassian.net/rest/api/3/issueLinkType/10001"
        )

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraIssueLinkType from empty data."""
        link_type = JiraIssueLinkType.from_api_response({})
        assert link_type.id == JIRA_DEFAULT_ID
        assert link_type.name == UNKNOWN
        assert link_type.inward == EMPTY_STRING
        assert link_type.outward == EMPTY_STRING
        assert link_type.self_url is None

    def test_from_api_response_with_none_data(self):
        """Test creating a JiraIssueLinkType from None data."""
        link_type = JiraIssueLinkType.from_api_response(None)
        assert link_type.id == JIRA_DEFAULT_ID
        assert link_type.name == UNKNOWN
        assert link_type.inward == EMPTY_STRING
        assert link_type.outward == EMPTY_STRING
        assert link_type.self_url is None

    def test_to_simplified_dict(self):
        """Test converting JiraIssueLinkType to a simplified dictionary."""
        link_type = JiraIssueLinkType(
            id="10001",
            name="Blocks",
            inward="is blocked by",
            outward="blocks",
            self_url="https://example.atlassian.net/rest/api/3/issueLinkType/10001",
        )
        simplified = link_type.to_simplified_dict()
        assert isinstance(simplified, dict)
        assert simplified["id"] == "10001"
        assert simplified["name"] == "Blocks"
        assert simplified["inward"] == "is blocked by"
        assert simplified["outward"] == "blocks"
        assert "self" in simplified
        assert (
            simplified["self"]
            == "https://example.atlassian.net/rest/api/3/issueLinkType/10001"
        )


class TestJiraLinkedIssueFields:
    """Tests for the JiraLinkedIssueFields model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraLinkedIssueFields from valid API data."""
        data = {
            "summary": "Linked Issue Summary",
            "status": {
                "id": "10000",
                "name": "In Progress",
                "statusCategory": {
                    "id": 4,
                    "key": "indeterminate",
                    "name": "In Progress",
                    "colorName": "yellow",
                },
            },
            "priority": {
                "id": "3",
                "name": "Medium",
                "description": "Medium priority",
                "iconUrl": "https://example.com/medium-priority.png",
            },
            "issuetype": {
                "id": "10000",
                "name": "Task",
                "description": "A task that needs to be done.",
                "iconUrl": "https://example.com/task-icon.png",
            },
        }
        fields = JiraLinkedIssueFields.from_api_response(data)
        assert fields.summary == "Linked Issue Summary"
        assert fields.status is not None
        assert fields.status.name == "In Progress"
        assert fields.priority is not None
        assert fields.priority.name == "Medium"
        assert fields.issuetype is not None
        assert fields.issuetype.name == "Task"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraLinkedIssueFields from empty data."""
        fields = JiraLinkedIssueFields.from_api_response({})
        assert fields.summary == EMPTY_STRING
        assert fields.status is None
        assert fields.priority is None
        assert fields.issuetype is None

    def test_to_simplified_dict(self):
        """Test converting JiraLinkedIssueFields to a simplified dictionary."""
        fields = JiraLinkedIssueFields(
            summary="Linked Issue Summary",
            status=JiraStatus(name="In Progress"),
            priority=JiraPriority(name="Medium"),
            issuetype=JiraIssueType(name="Task"),
        )
        simplified = fields.to_simplified_dict()
        assert simplified["summary"] == "Linked Issue Summary"
        assert simplified["status"]["name"] == "In Progress"
        assert simplified["priority"]["name"] == "Medium"
        assert simplified["issuetype"]["name"] == "Task"


class TestJiraLinkedIssue:
    """Tests for the JiraLinkedIssue model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraLinkedIssue from valid API data."""
        data = {
            "id": "10001",
            "key": "PROJ-456",
            "self": "https://example.atlassian.net/rest/api/2/issue/10001",
            "fields": {
                "summary": "Linked Issue Summary",
                "status": {
                    "id": "10000",
                    "name": "In Progress",
                },
                "priority": {
                    "id": "3",
                    "name": "Medium",
                },
                "issuetype": {
                    "id": "10000",
                    "name": "Task",
                },
            },
        }
        linked_issue = JiraLinkedIssue.from_api_response(data)
        assert linked_issue.id == "10001"
        assert linked_issue.key == "PROJ-456"
        assert (
            linked_issue.self_url
            == "https://example.atlassian.net/rest/api/2/issue/10001"
        )
        assert linked_issue.fields is not None
        assert linked_issue.fields.summary == "Linked Issue Summary"
        assert linked_issue.fields.status is not None
        assert linked_issue.fields.status.name == "In Progress"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraLinkedIssue from empty data."""
        linked_issue = JiraLinkedIssue.from_api_response({})
        assert linked_issue.id == JIRA_DEFAULT_ID
        assert linked_issue.key == EMPTY_STRING
        assert linked_issue.self_url is None
        assert linked_issue.fields is None

    def test_to_simplified_dict(self):
        """Test converting JiraLinkedIssue to a simplified dictionary."""
        linked_issue = JiraLinkedIssue(
            id="10001",
            key="PROJ-456",
            self_url="https://example.atlassian.net/rest/api/2/issue/10001",
            fields=JiraLinkedIssueFields(
                summary="Linked Issue Summary",
                status=JiraStatus(name="In Progress"),
                priority=JiraPriority(name="Medium"),
                issuetype=JiraIssueType(name="Task"),
            ),
        )
        simplified = linked_issue.to_simplified_dict()
        assert simplified["id"] == "10001"
        assert simplified["key"] == "PROJ-456"
        assert (
            simplified["self"] == "https://example.atlassian.net/rest/api/2/issue/10001"
        )
        assert simplified["fields"]["summary"] == "Linked Issue Summary"
        assert simplified["fields"]["status"]["name"] == "In Progress"


class TestJiraIssueLink:
    """Tests for the JiraIssueLink model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraIssueLink from valid API data."""
        data = {
            "id": "10001",
            "type": {
                "id": "10000",
                "name": "Blocks",
                "inward": "is blocked by",
                "outward": "blocks",
                "self": "https://example.atlassian.net/rest/api/2/issueLinkType/10000",
            },
            "inwardIssue": {
                "id": "10002",
                "key": "PROJ-789",
                "self": "https://example.atlassian.net/rest/api/2/issue/10002",
                "fields": {
                    "summary": "Inward Issue Summary",
                    "status": {
                        "id": "10000",
                        "name": "In Progress",
                    },
                },
            },
        }
        issue_link = JiraIssueLink.from_api_response(data)
        assert issue_link.id == "10001"
        assert issue_link.type is not None
        assert issue_link.type.name == "Blocks"
        assert issue_link.inward_issue is not None
        assert issue_link.inward_issue.key == "PROJ-789"
        assert issue_link.outward_issue is None

    def test_from_api_response_with_outward_issue(self):
        """Test creating a JiraIssueLink with an outward issue."""
        data = {
            "id": "10001",
            "type": {
                "id": "10000",
                "name": "Blocks",
                "inward": "is blocked by",
                "outward": "blocks",
            },
            "outwardIssue": {
                "id": "10003",
                "key": "PROJ-101",
                "fields": {
                    "summary": "Outward Issue Summary",
                    "status": {
                        "id": "10000",
                        "name": "In Progress",
                    },
                },
            },
        }
        issue_link = JiraIssueLink.from_api_response(data)
        assert issue_link.id == "10001"
        assert issue_link.type is not None
        assert issue_link.type.name == "Blocks"
        assert issue_link.inward_issue is None
        assert issue_link.outward_issue is not None
        assert issue_link.outward_issue.key == "PROJ-101"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraIssueLink from empty data."""
        issue_link = JiraIssueLink.from_api_response({})
        assert issue_link.id == JIRA_DEFAULT_ID
        assert issue_link.type is None
        assert issue_link.inward_issue is None
        assert issue_link.outward_issue is None

    def test_to_simplified_dict(self):
        """Test converting JiraIssueLink to a simplified dictionary."""
        issue_link = JiraIssueLink(
            id="10001",
            type=JiraIssueLinkType(
                id="10000",
                name="Blocks",
                inward="is blocked by",
                outward="blocks",
            ),
            inward_issue=JiraLinkedIssue(
                id="10002",
                key="PROJ-789",
                fields=JiraLinkedIssueFields(
                    summary="Inward Issue Summary",
                    status=JiraStatus(name="In Progress"),
                ),
            ),
        )
        simplified = issue_link.to_simplified_dict()
        assert simplified["id"] == "10001"
        assert simplified["type"]["name"] == "Blocks"
        assert simplified["inward_issue"]["key"] == "PROJ-789"
        assert "outward_issue" not in simplified


class TestJiraWorklog:
    """Tests for the JiraWorklog model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraWorklog from valid API data."""
        worklog_data = {
            "id": "100023",
            "author": {
                "accountId": "5b10a2844c20165700ede21g",
                "displayName": "John Doe",
                "active": True,
            },
            "comment": "Worked on the issue today",
            "created": "2023-05-01T10:00:00.000+0000",
            "updated": "2023-05-01T10:30:00.000+0000",
            "started": "2023-05-01T09:00:00.000+0000",
            "timeSpent": "2h 30m",
            "timeSpentSeconds": 9000,
        }
        worklog = JiraWorklog.from_api_response(worklog_data)
        assert worklog.id == "100023"
        assert worklog.author is not None
        assert worklog.author.display_name == "John Doe"
        assert worklog.comment == "Worked on the issue today"
        assert worklog.created == "2023-05-01T10:00:00.000+0000"
        assert worklog.updated == "2023-05-01T10:30:00.000+0000"
        assert worklog.started == "2023-05-01T09:00:00.000+0000"
        assert worklog.time_spent == "2h 30m"
        assert worklog.time_spent_seconds == 9000

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraWorklog from empty data."""
        worklog = JiraWorklog.from_api_response({})
        assert worklog.id == JIRA_DEFAULT_ID
        assert worklog.author is None
        assert worklog.comment is None
        assert worklog.created == EMPTY_STRING
        assert worklog.updated == EMPTY_STRING
        assert worklog.started == EMPTY_STRING
        assert worklog.time_spent == EMPTY_STRING
        assert worklog.time_spent_seconds == 0

    def test_to_simplified_dict(self):
        """Test converting a JiraWorklog to a simplified dictionary."""
        worklog_data = {
            "id": "100023",
            "author": {
                "accountId": "5b10a2844c20165700ede21g",
                "displayName": "John Doe",
                "active": True,
            },
            "comment": "Worked on the issue today",
            "created": "2023-05-01T10:00:00.000+0000",
            "updated": "2023-05-01T10:30:00.000+0000",
            "started": "2023-05-01T09:00:00.000+0000",
            "timeSpent": "2h 30m",
            "timeSpentSeconds": 9000,
        }
        worklog = JiraWorklog.from_api_response(worklog_data)
        simplified = worklog.to_simplified_dict()
        assert simplified["time_spent"] == "2h 30m"
        assert simplified["time_spent_seconds"] == 9000
        assert simplified["author"] is not None
        assert simplified["author"]["display_name"] == "John Doe"
        assert simplified["comment"] == "Worked on the issue today"
        assert "created" in simplified
        assert "updated" in simplified
        assert "started" in simplified


class TestRealJiraData:
    """Tests using real Jira data (optional)."""

    # Helper to get client/config
    def _get_client(self) -> IssuesMixin | None:
        if not real_api_available:
            return None
        try:
            config = JiraConfig.from_env()
            return JiraFetcher(config=config)
        except ValueError:
            pytest.skip("Real Jira environment not configured")
            return None

    def _get_project_client(self) -> ProjectsMixin | None:
        if not real_api_available:
            return None
        try:
            config = JiraConfig.from_env()

            return JiraFetcher(config=config)
        except ValueError:
            pytest.skip("Real Jira environment not configured")
            return None

    def _get_transition_client(self) -> TransitionsMixin | None:
        if not real_api_available:
            return None
        try:
            config = JiraConfig.from_env()
            return JiraFetcher(config=config)
        except ValueError:
            pytest.skip("Real Jira environment not configured")
            return None

    def _get_worklog_client(self) -> WorklogMixin | None:
        if not real_api_available:
            return None
        try:
            config = JiraConfig.from_env()
            return JiraFetcher(config=config)
        except ValueError:
            pytest.skip("Real Jira environment not configured")
            return None

    def _get_base_jira_client(self) -> Jira | None:
        if not real_api_available:
            return None
        try:
            config = JiraConfig.from_env()
            if config.auth_type == "basic":
                return Jira(
                    url=config.url,
                    username=config.username,
                    password=config.api_token,
                    cloud=config.is_cloud,
                )
            else:  # token
                return Jira(
                    url=config.url, token=config.personal_token, cloud=config.is_cloud
                )
        except ValueError:
            pytest.skip("Real Jira environment not configured")
            return None

    def test_real_jira_issue(self, use_real_jira_data, default_jira_issue_key):
        """Test that the JiraIssue model works with real Jira API data."""
        if not use_real_jira_data:
            pytest.skip("Skipping real Jira data test")
        issues_client = self._get_client()
        if not issues_client or not default_jira_issue_key:
            pytest.skip("Real Jira client/issue key not available")

        try:
            issue = issues_client.get_issue(default_jira_issue_key)
            assert isinstance(issue, JiraIssue)
            assert issue.key == default_jira_issue_key
            assert issue.id is not None
            assert issue.summary is not None

            assert hasattr(issue, "project")
            assert issue.project is None or isinstance(issue.project, JiraProject)
            assert hasattr(issue, "resolution")
            assert issue.resolution is None or isinstance(
                issue.resolution, JiraResolution
            )
            assert hasattr(issue, "duedate")
            assert issue.duedate is None or isinstance(issue.duedate, str)
            assert hasattr(issue, "resolutiondate")
            assert issue.resolutiondate is None or isinstance(issue.resolutiondate, str)
            assert hasattr(issue, "parent")
            assert issue.parent is None or isinstance(issue.parent, dict)
            assert hasattr(issue, "subtasks")
            assert isinstance(issue.subtasks, list)
            if issue.subtasks:
                assert isinstance(issue.subtasks[0], dict)
            assert hasattr(issue, "security")
            assert issue.security is None or isinstance(issue.security, dict)
            assert hasattr(issue, "worklog")
            assert issue.worklog is None or isinstance(issue.worklog, dict)

            simplified = issue.to_simplified_dict()
            assert simplified["key"] == default_jira_issue_key
        except Exception as e:
            pytest.fail(f"Error testing real Jira issue: {e}")

    def test_real_jira_project(self, use_real_jira_data):
        """Test that the JiraProject model works with real Jira API data."""
        if not use_real_jira_data:
            pytest.skip("Skipping real Jira data test")
        projects_client = self._get_project_client()
        if not projects_client:
            pytest.skip("Real Jira client not available")

        # Check for JIRA_TEST_ISSUE_KEY explicitly
        if not os.environ.get("JIRA_TEST_ISSUE_KEY"):
            pytest.skip("JIRA_TEST_ISSUE_KEY environment variable not set")

        default_issue_key = os.environ.get("JIRA_TEST_ISSUE_KEY")
        project_key = default_issue_key.split("-")[0]

        if not project_key:
            pytest.skip("Could not extract project key from JIRA_TEST_ISSUE_KEY")

        try:
            project = projects_client.get_project_model(project_key)

            if project is None:
                pytest.skip(f"Could not get project model for {project_key}")

            assert isinstance(project, JiraProject)
            assert project.key == project_key
            assert project.id is not None
            assert project.name is not None

            simplified = project.to_simplified_dict()
            assert simplified["key"] == project_key
        except (AttributeError, TypeError, ValueError) as e:
            pytest.skip(f"Error parsing project data: {e}")
        except Exception as e:
            pytest.fail(f"Error testing real Jira project: {e}")

    def test_real_jira_transitions(self, use_real_jira_data, default_jira_issue_key):
        """Test that the JiraTransition model works with real Jira API data."""
        if not use_real_jira_data:
            pytest.skip("Skipping real Jira data test")
        transitions_client = self._get_transition_client()
        if not transitions_client or not default_jira_issue_key:
            pytest.skip("Real Jira client/issue key not available")

        # Use the underlying Atlassian API client directly for raw data
        jira = self._get_base_jira_client()
        if not jira:
            pytest.skip("Base Jira client failed")

        transitions_data = None  # Initialize
        try:
            transitions_data = jira.get_issue_transitions(default_jira_issue_key)

            actual_transitions_list = []
            if isinstance(transitions_data, list):
                actual_transitions_list = transitions_data
            else:
                # Handle unexpected format with test failure
                pytest.fail(
                    f"Unexpected transitions data format received from API: "
                    f"{type(transitions_data)}. Data: {transitions_data}"
                )

            # Verify transitions list is actually a list
            assert isinstance(actual_transitions_list, list)

            if not actual_transitions_list:
                pytest.skip(f"No transitions found for issue {default_jira_issue_key}")

            transition_item = actual_transitions_list[0]
            assert isinstance(transition_item, dict)

            # Check for essential keys in the raw data
            assert "id" in transition_item
            assert "name" in transition_item
            assert "to" in transition_item

            # Only check 'to' field name if it's a dictionary
            if isinstance(transition_item["to"], dict):
                assert "name" in transition_item["to"]

            # Convert to model
            transition = JiraTransition.from_api_response(transition_item)
            assert isinstance(transition, JiraTransition)
            assert transition.id == str(transition_item["id"])  # Ensure ID is string
            assert transition.name == transition_item["name"]

            simplified = transition.to_simplified_dict()
            assert simplified["id"] == str(transition_item["id"])
            assert simplified["name"] == transition_item["name"]

        except Exception as e:
            # Include data type details in error message
            error_details = f"Received data type: {type(transitions_data)}"
            if transitions_data is not None:
                error_details += (
                    f", Data: {str(transitions_data)[:200]}..."  # Show partial data
                )

            pytest.fail(
                f"Error testing real Jira transitions for issue {default_jira_issue_key}: {e}. {error_details}"
            )

    def test_real_jira_worklog(self, use_real_jira_data, default_jira_issue_key):
        """Test that the JiraWorklog model works with real Jira API data."""
        if not use_real_jira_data:
            pytest.skip("Skipping real Jira data test")
        worklog_client = self._get_worklog_client()
        if not worklog_client or not default_jira_issue_key:
            pytest.skip("Real Jira client/issue key not available")

        try:
            # Get worklogs using the model method
            worklogs = worklog_client.get_worklog_models(default_jira_issue_key)
            assert isinstance(worklogs, list)

            if not worklogs:
                pytest.skip(f"Issue {default_jira_issue_key} has no worklogs to test.")

            # Test the first worklog
            worklog = worklogs[0]
            assert isinstance(worklog, JiraWorklog)
            assert worklog.id is not None
            assert worklog.time_spent_seconds >= 0
            if worklog.author:
                assert isinstance(worklog.author, JiraUser)

            simplified = worklog.to_simplified_dict()
            assert "id" in simplified
            assert "time_spent" in simplified

        except Exception as e:
            pytest.fail(f"Error testing real Jira worklog: {e}")


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
