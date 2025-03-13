"""Tests for the Jira Worklog mixin."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira.worklog import WorklogMixin


class TestWorklogMixin:
    """Tests for the WorklogMixin class."""

    @pytest.fixture
    def worklog_mixin(self, jira_client):
        """Create a WorklogMixin instance with mocked dependencies."""
        mixin = WorklogMixin(config=jira_client.config)
        mixin.jira = jira_client.jira

        # Mock methods that are typically provided by other mixins
        mixin._clean_text = MagicMock(side_effect=lambda text: text if text else "")

        return mixin

    def test_parse_time_spent_with_seconds(self, worklog_mixin):
        """Test parsing time spent with seconds specification."""
        assert worklog_mixin._parse_time_spent("60s") == 60
        assert worklog_mixin._parse_time_spent("3600s") == 3600

    def test_parse_time_spent_with_minutes(self, worklog_mixin):
        """Test parsing time spent with minutes."""
        assert worklog_mixin._parse_time_spent("1m") == 60
        assert worklog_mixin._parse_time_spent("30m") == 1800

    def test_parse_time_spent_with_hours(self, worklog_mixin):
        """Test parsing time spent with hours."""
        assert worklog_mixin._parse_time_spent("1h") == 3600
        assert worklog_mixin._parse_time_spent("2h") == 7200

    def test_parse_time_spent_with_days(self, worklog_mixin):
        """Test parsing time spent with days."""
        assert worklog_mixin._parse_time_spent("1d") == 86400
        assert worklog_mixin._parse_time_spent("2d") == 172800

    def test_parse_time_spent_with_weeks(self, worklog_mixin):
        """Test parsing time spent with weeks."""
        assert worklog_mixin._parse_time_spent("1w") == 604800
        assert worklog_mixin._parse_time_spent("2w") == 1209600

    def test_parse_time_spent_with_mixed_units(self, worklog_mixin):
        """Test parsing time spent with mixed units."""
        assert worklog_mixin._parse_time_spent("1h 30m") == 5400
        assert worklog_mixin._parse_time_spent("1d 6h") == 108000
        assert worklog_mixin._parse_time_spent("1w 2d 3h 4m") == 788640

    def test_parse_time_spent_with_invalid_input(self, worklog_mixin):
        """Test parsing time spent with invalid input."""
        # Should default to 60 seconds
        assert worklog_mixin._parse_time_spent("invalid") == 60

    def test_parse_time_spent_with_numeric_input(self, worklog_mixin):
        """Test parsing time spent with numeric input."""
        assert worklog_mixin._parse_time_spent("60") == 60
        assert worklog_mixin._parse_time_spent("3600") == 3600

    def test_get_worklogs_basic(self, worklog_mixin):
        """Test basic functionality of get_worklogs."""
        # Setup mock response
        mock_result = {
            "worklogs": [
                {
                    "id": "10001",
                    "comment": "Work item 1",
                    "created": "2024-01-01T10:00:00.000+0000",
                    "updated": "2024-01-01T10:30:00.000+0000",
                    "started": "2024-01-01T09:00:00.000+0000",
                    "timeSpent": "1h",
                    "timeSpentSeconds": 3600,
                    "author": {"displayName": "Test User"},
                }
            ]
        }
        worklog_mixin.jira.issue_get_worklog.return_value = mock_result

        # Call the method
        result = worklog_mixin.get_worklogs("TEST-123")

        # Verify
        worklog_mixin.jira.issue_get_worklog.assert_called_once_with("TEST-123")
        assert len(result) == 1
        assert result[0]["id"] == "10001"
        assert result[0]["comment"] == "Work item 1"
        assert result[0]["timeSpent"] == "1h"
        assert result[0]["timeSpentSeconds"] == 3600
        assert result[0]["author"] == "Test User"

    def test_get_worklogs_with_multiple_entries(self, worklog_mixin):
        """Test get_worklogs with multiple worklog entries."""
        # Setup mock response with multiple entries
        mock_result = {
            "worklogs": [
                {
                    "id": "10001",
                    "comment": "Work item 1",
                    "created": "2024-01-01T10:00:00.000+0000",
                    "timeSpent": "1h",
                    "timeSpentSeconds": 3600,
                    "author": {"displayName": "User 1"},
                },
                {
                    "id": "10002",
                    "comment": "Work item 2",
                    "created": "2024-01-02T10:00:00.000+0000",
                    "timeSpent": "2h",
                    "timeSpentSeconds": 7200,
                    "author": {"displayName": "User 2"},
                },
            ]
        }
        worklog_mixin.jira.issue_get_worklog.return_value = mock_result

        # Call the method
        result = worklog_mixin.get_worklogs("TEST-123")

        # Verify
        assert len(result) == 2
        assert result[0]["id"] == "10001"
        assert result[1]["id"] == "10002"
        assert result[0]["timeSpentSeconds"] == 3600
        assert result[1]["timeSpentSeconds"] == 7200

    def test_get_worklogs_with_missing_fields(self, worklog_mixin):
        """Test get_worklogs with missing fields."""
        # Setup mock response with missing fields
        mock_result = {
            "worklogs": [
                {
                    "id": "10001",
                    # Missing comment
                    "created": "2024-01-01T10:00:00.000+0000",
                    # Missing other fields
                }
            ]
        }
        worklog_mixin.jira.issue_get_worklog.return_value = mock_result

        # Call the method
        result = worklog_mixin.get_worklogs("TEST-123")

        # Verify
        assert len(result) == 1
        assert result[0]["id"] == "10001"
        assert result[0]["comment"] == ""
        assert result[0]["timeSpent"] == ""
        assert result[0]["timeSpentSeconds"] == 0
        assert result[0]["author"] == "Unknown"

    def test_get_worklogs_with_empty_response(self, worklog_mixin):
        """Test get_worklogs with empty response."""
        # Setup mock response with no worklogs
        worklog_mixin.jira.issue_get_worklog.return_value = {}

        # Call the method
        result = worklog_mixin.get_worklogs("TEST-123")

        # Verify
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_worklogs_with_error(self, worklog_mixin):
        """Test get_worklogs error handling."""
        # Setup mock to raise exception
        worklog_mixin.jira.issue_get_worklog.side_effect = Exception(
            "Worklog fetch error"
        )

        # Call the method and verify exception
        with pytest.raises(
            Exception, match="Error getting worklogs: Worklog fetch error"
        ):
            worklog_mixin.get_worklogs("TEST-123")

    def test_add_worklog_basic(self, worklog_mixin):
        """Test basic functionality of add_worklog."""
        # Setup mock response
        mock_result = {
            "id": "10001",
            "comment": "Added work",
            "created": "2024-01-01T10:00:00.000+0000",
            "updated": "2024-01-01T10:00:00.000+0000",
            "started": "2024-01-01T09:00:00.000+0000",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
            "author": {"displayName": "Test User"},
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Call the method
        result = worklog_mixin.add_worklog("TEST-123", "1h", comment="Added work")

        # Verify
        worklog_mixin.jira.resource_url.assert_called_once_with("issue")
        worklog_mixin.jira.post.assert_called_once()
        assert result["id"] == "10001"
        assert result["comment"] == "Added work"
        assert result["timeSpent"] == "1h"
        assert result["timeSpentSeconds"] == 3600
        assert result["author"] == "Test User"
        assert result["original_estimate_updated"] is False
        assert result["remaining_estimate_updated"] is False

    def test_add_worklog_with_original_estimate(self, worklog_mixin):
        """Test add_worklog with original estimate update."""
        # Setup mocks
        mock_result = {
            "id": "10001",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Call the method
        result = worklog_mixin.add_worklog("TEST-123", "1h", original_estimate="4h")

        # Verify
        worklog_mixin.jira.edit_issue.assert_called_once_with(
            issue_id_or_key="TEST-123",
            fields={"timetracking": {"originalEstimate": "4h"}},
        )
        assert result["original_estimate_updated"] is True

    def test_add_worklog_with_remaining_estimate(self, worklog_mixin):
        """Test add_worklog with remaining estimate update."""
        # Setup mocks
        mock_result = {
            "id": "10001",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Call the method
        result = worklog_mixin.add_worklog("TEST-123", "1h", remaining_estimate="3h")

        # Verify post call has correct parameters
        call_args = worklog_mixin.jira.post.call_args
        assert call_args is not None
        args, kwargs = call_args

        # Check that adjustEstimate=new and newEstimate=3h are in params
        assert "params" in kwargs
        assert kwargs["params"]["adjustEstimate"] == "new"
        assert kwargs["params"]["newEstimate"] == "3h"

        assert result["remaining_estimate_updated"] is True

    def test_add_worklog_with_started_time(self, worklog_mixin):
        """Test add_worklog with started time."""
        # Setup mocks
        mock_result = {
            "id": "10001",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Setup started time
        started_time = "2024-01-01T09:00:00.000+0000"

        # Call the method
        worklog_mixin.add_worklog("TEST-123", "1h", started=started_time)

        # Verify worklog data contains started time
        call_args = worklog_mixin.jira.post.call_args
        assert call_args is not None
        args, kwargs = call_args

        assert "data" in kwargs
        assert kwargs["data"]["started"] == started_time

    def test_add_worklog_with_markdown_to_jira_available(self, worklog_mixin):
        """Test add_worklog with _markdown_to_jira conversion."""
        # Setup mocks
        mock_result = {
            "id": "10001",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Add _markdown_to_jira method
        worklog_mixin._markdown_to_jira = MagicMock(return_value="Converted comment")

        # Call the method
        worklog_mixin.add_worklog("TEST-123", "1h", comment="**Markdown** comment")

        # Verify _markdown_to_jira was called
        worklog_mixin._markdown_to_jira.assert_called_once_with("**Markdown** comment")

        # Verify converted comment was used
        call_args = worklog_mixin.jira.post.call_args
        assert call_args is not None
        args, kwargs = call_args

        assert "data" in kwargs
        assert kwargs["data"]["comment"] == "Converted comment"

    def test_add_worklog_with_error(self, worklog_mixin):
        """Test add_worklog error handling."""
        # Setup mock to raise exception
        worklog_mixin.jira.post.side_effect = Exception("Worklog add error")
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Call the method and verify exception
        with pytest.raises(Exception, match="Error adding worklog: Worklog add error"):
            worklog_mixin.add_worklog("TEST-123", "1h")

    def test_add_worklog_with_original_estimate_error(self, worklog_mixin):
        """Test add_worklog with original estimate update error."""
        # Setup mocks
        mock_result = {
            "id": "10001",
            "timeSpent": "1h",
            "timeSpentSeconds": 3600,
        }
        worklog_mixin.jira.post.return_value = mock_result
        worklog_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )

        # Make edit_issue raise an exception
        worklog_mixin.jira.edit_issue.side_effect = Exception("Estimate update error")

        # Call the method - should continue despite estimate update error
        result = worklog_mixin.add_worklog("TEST-123", "1h", original_estimate="4h")

        # Verify post was still called (worklog added despite estimate error)
        worklog_mixin.jira.post.assert_called_once()
        assert result["original_estimate_updated"] is False

    def test_parse_date(self, worklog_mixin):
        """Test the actual implementation of _parse_date."""
        # Test ISO format
        result = worklog_mixin._parse_date("2024-01-01T10:00:00.000+0000")
        assert result == "2024-01-01", f"Expected '2024-01-01' but got '{result}'"

        # Test invalid format
        result = worklog_mixin._parse_date("invalid date")
        assert result == "invalid date", f"Expected 'invalid date' but got '{result}'"

        # Test None value
        result = worklog_mixin._parse_date(None)
        assert result == "", f"Expected empty string but got '{result}'"
