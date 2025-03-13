"""Tests for the Jira Search mixin."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira.search import SearchMixin
from mcp_atlassian.models.jira import JiraIssue


class TestSearchMixin:
    """Tests for the SearchMixin class."""

    @pytest.fixture
    def search_mixin(self, jira_client):
        """Create a SearchMixin instance with mocked dependencies."""
        mixin = SearchMixin(config=jira_client.config)
        mixin.jira = jira_client.jira

        # Mock methods that are typically provided by other mixins
        mixin._clean_text = MagicMock(side_effect=lambda text: text if text else "")

        return mixin

    def test_search_issues_basic(self, search_mixin):
        """Test basic search functionality."""
        # Setup mock response
        mock_issues = {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                        "description": "Issue description",
                        "created": "2024-01-01T10:00:00.000+0000",
                        "updated": "2024-01-01T11:00:00.000+0000",
                        "priority": {"name": "High"},
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        search_mixin.jira.jql.return_value = mock_issues
        search_mixin.config.url = "https://example.atlassian.net"

        # Call the method
        result = search_mixin.search_issues("project = TEST")

        # Verify
        search_mixin.jira.jql.assert_called_once_with(
            "project = TEST", fields="*all", start=0, limit=50, expand=None
        )

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 1
        assert all(isinstance(issue, JiraIssue) for issue in result)

        # Check the first issue
        issue = result[0]
        assert issue.key == "TEST-123"
        assert issue.summary == "Test issue"
        assert issue.description == "Issue description"
        assert issue.status is not None
        assert issue.status.name == "Open"
        assert issue.issue_type is not None
        assert issue.issue_type.name == "Bug"
        assert issue.priority is not None
        assert issue.priority.name == "High"

        # Remove backward compatibility checks
        assert "Issue description" in issue.description
        assert issue.key == "TEST-123"

    def test_search_issues_with_empty_description(self, search_mixin):
        """Test search with issues that have no description."""
        # Setup mock response
        mock_issues = {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                        "description": None,
                        "created": "2024-01-01T10:00:00.000+0000",
                        "updated": "2024-01-01T11:00:00.000+0000",
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        search_mixin.jira.jql.return_value = mock_issues

        # Call the method
        result = search_mixin.search_issues("project = TEST")

        # Verify results
        assert len(result) == 1
        assert isinstance(result[0], JiraIssue)
        assert result[0].key == "TEST-123"
        assert result[0].description is None
        assert result[0].summary == "Test issue"

        # Update to use direct properties instead of backward compatibility
        assert "Test issue" in result[0].summary

    def test_search_issues_with_missing_fields(self, search_mixin):
        """Test search with issues missing some fields."""
        # Setup mock response
        mock_issues = {
            "issues": [
                {
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        # Missing issuetype, status, etc.
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        search_mixin.jira.jql.return_value = mock_issues

        # Call the method
        result = search_mixin.search_issues("project = TEST")

        # Verify results
        assert len(result) == 1
        assert isinstance(result[0], JiraIssue)
        assert result[0].key == "TEST-123"
        assert result[0].summary == "Test issue"
        assert result[0].status is None
        assert result[0].issue_type is None

    def test_search_issues_with_empty_results(self, search_mixin):
        """Test search with no results."""
        # Setup mock response
        search_mixin.jira.jql.return_value = {"issues": []}

        # Call the method
        result = search_mixin.search_issues("project = NONEXISTENT")

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 0

    def test_search_issues_with_error(self, search_mixin):
        """Test search with API error."""
        # Setup mock to raise exception
        search_mixin.jira.jql.side_effect = Exception("API Error")

        # Call the method and verify it raises the expected exception
        with pytest.raises(Exception, match="Error searching issues"):
            search_mixin.search_issues("project = TEST")

    def test_get_project_issues(self, search_mixin):
        """Test get_project_issues method."""
        # Mock the search_issues method
        search_mixin.search_issues = MagicMock(
            return_value=[JiraIssue(key="TEST-123", summary="Test Issue")]
        )

        # Call the method
        result = search_mixin.get_project_issues("TEST", limit=20)

        # Verify
        search_mixin.search_issues.assert_called_once_with(
            "project = TEST ORDER BY created DESC", start=0, limit=20
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert all(isinstance(issue, JiraIssue) for issue in result)

    def test_get_epic_issues_success(self, search_mixin):
        """Test successful get_epic_issues call."""
        # Setup mock responses
        epic_data = {
            "id": "10001",
            "key": "EPIC-1",
            "fields": {"issuetype": {"name": "Epic"}},
        }
        search_mixin.jira.issue.return_value = epic_data

        # Mock search_issues to return test issues
        search_mixin.search_issues = MagicMock(
            return_value=[JiraIssue(key="TEST-123", summary="Test Issue")]
        )

        # Call the method
        result = search_mixin.get_epic_issues("EPIC-1")

        # Verify
        search_mixin.jira.issue.assert_called_once_with("EPIC-1")
        assert isinstance(result, list)
        assert len(result) == 1
        assert all(isinstance(issue, JiraIssue) for issue in result)

    def test_get_epic_issues_not_epic(self, search_mixin):
        """Test get_epic_issues with a non-epic issue."""
        # Setup mock response for a non-epic issue
        non_epic_data = {
            "id": "10001",
            "key": "STORY-1",
            "fields": {"issuetype": {"name": "Story"}},
        }
        search_mixin.jira.issue.return_value = non_epic_data

        # Verify it raises ValueError
        with pytest.raises(ValueError, match="is not an Epic"):
            search_mixin.get_epic_issues("STORY-1")

    def test_get_epic_issues_with_field_ids(self, search_mixin):
        """Test get_epic_issues using custom field IDs."""
        # Setup mock responses
        epic_data = {
            "id": "10001",
            "key": "EPIC-1",
            "fields": {"issuetype": {"name": "Epic"}},
        }
        search_mixin.jira.issue.return_value = epic_data

        # Add field_ids support
        search_mixin.get_jira_field_ids = MagicMock(
            return_value={"epic_link": "customfield_10014"}
        )

        # Mock search_issues with different responses depending on JQL
        def search_side_effect(jql, **kwargs):
            if "issueFunction" in jql:
                # First query fails
                raise Exception("issueFunction not supported")
            else:
                # Fallback query succeeds
                return [JiraIssue(key="TEST-123", summary="Test Issue")]

        search_mixin.search_issues = MagicMock(side_effect=search_side_effect)

        # Call the method
        result = search_mixin.get_epic_issues("EPIC-1")

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 1
        assert all(isinstance(issue, JiraIssue) for issue in result)

    def test_get_epic_issues_no_results(self, search_mixin):
        """Test get_epic_issues with no linked issues."""
        # Setup mock responses
        epic_data = {
            "id": "10001",
            "key": "EPIC-1",
            "fields": {"issuetype": {"name": "Epic"}},
        }
        search_mixin.jira.issue.return_value = epic_data

        # Mock search_issues to return empty list
        search_mixin.search_issues = MagicMock(return_value=[])

        # Call the method
        result = search_mixin.get_epic_issues("EPIC-1")

        # Verify
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_epic_issues_with_error(self, search_mixin):
        """Test get_epic_issues with general error."""
        # Setup mock to raise exception
        search_mixin.jira.issue.side_effect = Exception("API Error")

        # Verify it raises the wrapped exception
        with pytest.raises(Exception, match="Error getting epic issues"):
            search_mixin.get_epic_issues("EPIC-1")

    def test_parse_date(self, search_mixin):
        """Test the actual implementation of _parse_date."""
        # Test ISO format
        result = search_mixin._parse_date("2024-01-01T12:34:56.789+0000")
        assert result == "2024-01-01", f"Expected '2024-01-01' but got '{result}'"

        # Test invalid format
        result = search_mixin._parse_date("invalid date")
        assert result == "invalid date", f"Expected 'invalid date' but got '{result}'"

        # Test None value
        result = search_mixin._parse_date(None)
        assert result == "", f"Expected empty string but got '{result}'"
