"""Tests for the Jira statuses mixin."""

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.statuses import StatusesMixin


def test_get_statuses_returns_requested_fields(jira_fetcher: JiraFetcher) -> None:
    """Status results retain the requested category and description fields."""
    statuses_mixin: StatusesMixin = jira_fetcher
    statuses_mixin.jira.resource_url.return_value = (
        "https://jira.example.com/rest/api/2/status"
    )
    statuses_mixin.jira.get.return_value = [
        {
            "id": "3",
            "name": "In Progress",
            "description": "Work is underway.",
            "statusCategory": {"id": 4, "name": "In Progress"},
        }
    ]

    result = statuses_mixin.get_statuses()

    assert result == [
        {
            "id": "3",
            "name": "In Progress",
            "description": "Work is underway.",
            "statusCategory": {"id": 4, "name": "In Progress"},
        }
    ]
    statuses_mixin.jira.resource_url.assert_called_once_with("status", api_version="2")


def test_get_statuses_filters_by_name(jira_fetcher: JiraFetcher) -> None:
    """Status name filtering is case-insensitive and matches substrings."""
    statuses_mixin: StatusesMixin = jira_fetcher
    statuses_mixin.jira.get.return_value = [
        {"id": "1", "name": "To Do", "statusCategory": {}},
        {"id": "2", "name": "In Progress", "statusCategory": {}},
    ]

    result = statuses_mixin.get_statuses(name_filter="progress")

    assert [status["name"] for status in result] == ["In Progress"]
