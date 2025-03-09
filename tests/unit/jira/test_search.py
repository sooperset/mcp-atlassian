"""Tests for the Jira Search mixin."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.document_types import Document
from mcp_atlassian.jira.search import SearchMixin


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
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                        "description": "Issue description",
                        "created": "2024-01-01T10:00:00.000+0000",
                        "priority": {"name": "High"},
                    },
                }
            ]
        }
        search_mixin.jira.jql.return_value = mock_issues

        # Call the method
        result = search_mixin.search_issues("project = TEST")

        # Verify
        search_mixin.jira.jql.assert_called_once_with(
            "project = TEST", fields="*all", start=0, limit=50, expand=None
        )

        assert len(result) == 1
        assert isinstance(result[0], Document)
        assert result[0].page_content == "Issue description"
        assert result[0].metadata["key"] == "TEST-123"
        assert result[0].metadata["title"] == "Test issue"
        assert result[0].metadata["type"] == "Bug"
        assert result[0].metadata["status"] == "Open"
        assert result[0].metadata["priority"] == "High"
        assert "link" in result[0].metadata

    def test_search_issues_with_empty_description(self, search_mixin):
        """Test search with empty description uses summary as content."""
        # Setup mock response
        mock_issues = {
            "issues": [
                {
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                        "description": None,
                        "created": "2024-01-01T10:00:00.000+0000",
                    },
                }
            ]
        }
        search_mixin.jira.jql.return_value = mock_issues

        # Call the method
        result = search_mixin.search_issues("project = TEST")

        # Verify that summary is used as content when description is empty
        assert len(result) == 1
        assert result[0].page_content == "Test issue [Open]"

    def test_search_issues_with_missing_fields(self, search_mixin):
        """Test search with missing fields uses fallback values."""
        # Setup mock response with missing fields
        mock_issues = {
            "issues": [
                {
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue"
                        # No issuetype, status, description, etc.
                    },
                }
            ]
        }
        search_mixin.jira.jql.return_value = mock_issues

        # Call the method
        result = search_mixin.search_issues("project = TEST")

        # Verify fallback values
        assert len(result) == 1
        assert result[0].page_content == "Test issue [Unknown]"
        assert result[0].metadata["type"] == "Unknown"
        assert result[0].metadata["status"] == "Unknown"
        assert result[0].metadata["created_date"] == ""
        assert result[0].metadata["priority"] == "None"

    def test_search_issues_with_empty_results(self, search_mixin):
        """Test search with no results returns empty list."""
        # Setup mock response with no issues
        search_mixin.jira.jql.return_value = {"issues": []}

        # Call the method
        result = search_mixin.search_issues("project = TEST")

        # Verify
        assert isinstance(result, list)
        assert len(result) == 0

    def test_search_issues_with_error(self, search_mixin):
        """Test search with error raises exception."""
        # Setup mock to raise exception
        search_mixin.jira.jql.side_effect = Exception("Search error")

        # Call the method and verify exception
        with pytest.raises(Exception, match="Error searching issues: Search error"):
            search_mixin.search_issues("project = TEST")

    def test_get_project_issues(self, search_mixin):
        """Test getting project issues calls search_issues with correct JQL."""
        # Mock search_issues
        search_mixin.search_issues = MagicMock(return_value=[])

        # Call the method
        search_mixin.get_project_issues("TEST", start=5, limit=10)

        # Verify search_issues was called with correct parameters
        search_mixin.search_issues.assert_called_once_with(
            "project = TEST ORDER BY created DESC", start=5, limit=10
        )

    def test_get_epic_issues_success(self, search_mixin):
        """Test getting epic issues with a valid epic."""
        # Setup mocks
        epic_mock = {"fields": {"issuetype": {"name": "Epic"}}}
        search_mixin.jira.issue.return_value = epic_mock
        search_mixin.search_issues = MagicMock(
            return_value=[
                Document(page_content="Issue 1", metadata={"key": "TEST-124"}),
                Document(page_content="Issue 2", metadata={"key": "TEST-125"}),
            ]
        )

        # Call the method
        result = search_mixin.get_epic_issues("TEST-123", limit=10)

        # Verify
        search_mixin.jira.issue.assert_called_once_with("TEST-123")
        assert len(result) == 2
        # Verify it called search_issues at least once
        assert search_mixin.search_issues.call_count >= 1

    def test_get_epic_issues_not_epic(self, search_mixin):
        """Test getting epic issues with a non-epic issue type."""
        # Setup mock to return a non-epic issue
        epic_mock = {"fields": {"issuetype": {"name": "Story"}}}
        search_mixin.jira.issue.return_value = epic_mock

        # Call the method and verify exception
        with pytest.raises(ValueError, match="Issue TEST-123 is not an Epic"):
            search_mixin.get_epic_issues("TEST-123")

    def test_get_epic_issues_with_field_ids(self, search_mixin):
        """Test getting epic issues uses field IDs when available."""
        # Setup mocks
        epic_mock = {"fields": {"issuetype": {"name": "Epic"}}}
        search_mixin.jira.issue.return_value = epic_mock

        # Mock field IDs
        search_mixin.get_jira_field_ids = MagicMock(
            return_value={"epic_link": "customfield_10014"}
        )

        # Mock search to return results only for one specific JQL
        def search_side_effect(jql, **kwargs):
            if "customfield_10014" in jql:
                return [Document(page_content="Epic Issue", metadata={})]
            return []

        search_mixin.search_issues = MagicMock(side_effect=search_side_effect)

        # Call the method
        result = search_mixin.get_epic_issues("TEST-123")

        # Verify
        assert len(result) == 1
        search_mixin.get_jira_field_ids.assert_called_once()

    def test_get_epic_issues_no_results(self, search_mixin):
        """Test getting epic issues with no results returns empty list."""
        # Setup mocks
        epic_mock = {"fields": {"issuetype": {"name": "Epic"}}}
        search_mixin.jira.issue.return_value = epic_mock

        # Mock search to return no results
        search_mixin.search_issues = MagicMock(return_value=[])

        # Call the method
        result = search_mixin.get_epic_issues("TEST-123")

        # Verify
        assert isinstance(result, list)
        assert len(result) == 0
        # Should try multiple JQL queries
        assert search_mixin.search_issues.call_count > 1

    def test_get_epic_issues_with_error(self, search_mixin):
        """Test getting epic issues with an error raises exception."""
        # Setup mock to raise exception
        search_mixin.jira.issue.side_effect = Exception("Epic error")

        # Call the method and verify exception
        with pytest.raises(Exception, match="Error getting epic issues: Epic error"):
            search_mixin.get_epic_issues("TEST-123")

    def test_parse_date(self, search_mixin):
        """Test date parsing with various formats."""
        # Test ISO format
        assert search_mixin._parse_date("2024-01-01T10:00:00.000+0000") == "2024-01-01"

        # Test invalid format
        assert search_mixin._parse_date("invalid date") == "invalid date"

        # Test empty string
        assert search_mixin._parse_date("") == ""
