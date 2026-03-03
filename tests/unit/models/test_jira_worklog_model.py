"""
Tests for Jira worklog and timetracking Pydantic models.

Tests for JiraWorklog and JiraTimetracking models.
"""

from mcp_atlassian.models.constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
)
from mcp_atlassian.models.jira import (
    JiraTimetracking,
    JiraWorklog,
)


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
