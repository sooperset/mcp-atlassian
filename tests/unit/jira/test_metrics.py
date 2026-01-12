"""Tests for the Jira Metrics mixin."""

from datetime import datetime, timezone

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.metrics import MetricsMixin
from mcp_atlassian.models.jira.metrics import (
    IssueDatesBatchResponse,
    IssueDatesResponse,
    StatusChangeEntry,
    StatusTimeSummary,
)


class TestMetricsMixin:
    """Tests for the MetricsMixin class."""

    @pytest.fixture
    def metrics_mixin(self, jira_fetcher: JiraFetcher) -> MetricsMixin:
        """Create a MetricsMixin instance with mocked dependencies."""
        return jira_fetcher

    def test_format_duration_zero_minutes(self, metrics_mixin: MetricsMixin):
        """Test formatting zero minutes."""
        result = metrics_mixin._format_duration(0)
        assert result == "0m"

    def test_format_duration_negative_minutes(self, metrics_mixin: MetricsMixin):
        """Test formatting negative minutes."""
        result = metrics_mixin._format_duration(-10)
        assert result == "0m"

    def test_format_duration_minutes_only(self, metrics_mixin: MetricsMixin):
        """Test formatting when only minutes are present."""
        result = metrics_mixin._format_duration(45)
        assert result == "45m"

    def test_format_duration_hours_and_minutes(self, metrics_mixin: MetricsMixin):
        """Test formatting hours and minutes."""
        result = metrics_mixin._format_duration(90)  # 1h 30m
        assert result == "1h 30m"

    def test_format_duration_days_hours_minutes(self, metrics_mixin: MetricsMixin):
        """Test formatting days, hours, and minutes."""
        result = metrics_mixin._format_duration(1500)  # 1d 1h 0m
        assert result == "1d 1h 0m"

    def test_format_duration_multiple_days(self, metrics_mixin: MetricsMixin):
        """Test formatting multiple days."""
        result = metrics_mixin._format_duration(4320)  # 3 days
        assert result == "3d 0h 0m"

    def test_calculate_duration_minutes(self, metrics_mixin: MetricsMixin):
        """Test calculating duration between two timestamps."""
        start = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 1, 1, 11, 30, 0, tzinfo=timezone.utc)

        result = metrics_mixin._calculate_duration_minutes(start, end)
        assert result == 90  # 1.5 hours = 90 minutes

    def test_get_issue_dates_basic(self, metrics_mixin: MetricsMixin):
        """Test getting basic date information for an issue."""
        # Mock the API response
        metrics_mixin.jira.get_issue.return_value = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {
                "created": "2023-01-01T00:00:00.000+0000",
                "updated": "2023-01-15T12:00:00.000+0000",
                "duedate": "2023-02-01",
                "resolutiondate": "2023-01-20T10:00:00.000+0000",
                "status": {"name": "Done"},
            },
        }

        result = metrics_mixin.get_issue_dates("TEST-123")

        assert isinstance(result, IssueDatesResponse)
        assert result.issue_key == "TEST-123"
        assert result.created is not None
        assert result.updated is not None
        assert result.current_status == "Done"

    def test_get_issue_dates_with_changelog(self, metrics_mixin: MetricsMixin):
        """Test getting date information with changelog."""
        # Mock the API response with changelog
        metrics_mixin.jira.get_issue.return_value = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {
                "created": "2023-01-01T00:00:00.000+0000",
                "updated": "2023-01-15T12:00:00.000+0000",
                "status": {"name": "In Progress"},
            },
            "changelog": {
                "histories": [
                    {
                        "id": "1001",
                        "created": "2023-01-02T10:00:00.000+0000",
                        "author": {"displayName": "Test User"},
                        "items": [
                            {
                                "field": "status",
                                "fieldtype": "jira",
                                "fromString": "Open",
                                "toString": "In Progress",
                            }
                        ],
                    }
                ],
            },
        }

        result = metrics_mixin.get_issue_dates("TEST-123")

        assert isinstance(result, IssueDatesResponse)
        assert result.issue_key == "TEST-123"
        assert result.current_status == "In Progress"
        assert len(result.status_changes) >= 1
        # Should have the transition from Open to In Progress

    def test_get_issue_dates_excludes_optional_fields(
        self, metrics_mixin: MetricsMixin
    ):
        """Test getting dates with some fields excluded."""
        metrics_mixin.jira.get_issue.return_value = {
            "id": "10001",
            "key": "TEST-123",
            "fields": {
                "created": "2023-01-01T00:00:00.000+0000",
                "status": {"name": "Open"},
            },
        }

        result = metrics_mixin.get_issue_dates(
            "TEST-123",
            include_created=True,
            include_updated=False,
            include_due_date=False,
            include_resolution_date=False,
            include_status_changes=False,
            include_status_summary=False,
        )

        assert isinstance(result, IssueDatesResponse)
        assert result.created is not None
        assert result.status_changes == []
        assert result.status_summary == []

    def test_batch_get_issue_dates(self, metrics_mixin: MetricsMixin):
        """Test batch getting dates for multiple issues."""

        def mock_get_issue(issue_key, **kwargs):
            return {
                "id": f"1000{issue_key[-1]}",
                "key": issue_key,
                "fields": {
                    "created": "2023-01-01T00:00:00.000+0000",
                    "updated": "2023-01-15T12:00:00.000+0000",
                    "status": {"name": "Open"},
                },
            }

        metrics_mixin.jira.get_issue.side_effect = mock_get_issue

        result = metrics_mixin.batch_get_issue_dates(
            ["TEST-1", "TEST-2", "TEST-3"],
            include_status_changes=False,
            include_status_summary=False,
        )

        assert isinstance(result, IssueDatesBatchResponse)
        assert result.total_count == 3
        assert result.success_count == 3
        assert result.error_count == 0
        assert len(result.issues) == 3

    def test_batch_get_issue_dates_with_errors(self, metrics_mixin: MetricsMixin):
        """Test batch operation handling errors gracefully."""

        def mock_get_issue(issue_key, **kwargs):
            if issue_key == "TEST-2":
                raise ValueError("Issue not found")
            return {
                "id": f"1000{issue_key[-1]}",
                "key": issue_key,
                "fields": {
                    "created": "2023-01-01T00:00:00.000+0000",
                    "status": {"name": "Open"},
                },
            }

        metrics_mixin.jira.get_issue.side_effect = mock_get_issue

        result = metrics_mixin.batch_get_issue_dates(
            ["TEST-1", "TEST-2", "TEST-3"],
            include_status_changes=False,
            include_status_summary=False,
        )

        assert isinstance(result, IssueDatesBatchResponse)
        assert result.total_count == 3
        assert result.success_count == 2
        assert result.error_count == 1
        assert len(result.errors) == 1
        assert result.errors[0]["issue_key"] == "TEST-2"

    def test_aggregate_status_times(self, metrics_mixin: MetricsMixin):
        """Test aggregating time spent in each status."""
        status_changes = [
            StatusChangeEntry(
                status="Open",
                entered_at=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
                exited_at=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
                duration_minutes=120,
            ),
            StatusChangeEntry(
                status="In Progress",
                entered_at=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
                exited_at=datetime(2023, 1, 2, 12, 0, tzinfo=timezone.utc),
                duration_minutes=1440,
            ),
            StatusChangeEntry(
                status="Open",
                entered_at=datetime(2023, 1, 2, 12, 0, tzinfo=timezone.utc),
                exited_at=datetime(2023, 1, 2, 13, 0, tzinfo=timezone.utc),
                duration_minutes=60,
            ),
        ]

        result = metrics_mixin._aggregate_status_times(status_changes)

        assert len(result) == 2  # Open and In Progress

        # Find the Open status summary
        open_summary = next((s for s in result if s.status == "Open"), None)
        assert open_summary is not None
        assert open_summary.total_duration_minutes == 180  # 120 + 60
        assert open_summary.visit_count == 2

        # Find the In Progress status summary
        in_progress_summary = next(
            (s for s in result if s.status == "In Progress"), None
        )
        assert in_progress_summary is not None
        assert in_progress_summary.total_duration_minutes == 1440
        assert in_progress_summary.visit_count == 1


class TestMetricsModels:
    """Tests for the metrics Pydantic models."""

    def test_status_change_entry_to_simplified_dict(self):
        """Test StatusChangeEntry serialization."""
        entry = StatusChangeEntry(
            status="In Progress",
            entered_at=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            exited_at=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
            duration_minutes=120,
            duration_formatted="2h 0m",
            transitioned_by="Test User",
        )

        result = entry.to_simplified_dict()

        assert result["status"] == "In Progress"
        assert "entered_at" in result
        assert "exited_at" in result
        assert result["duration_minutes"] == 120
        assert result["duration_formatted"] == "2h 0m"
        assert result["transitioned_by"] == "Test User"

    def test_status_change_entry_without_exit(self):
        """Test StatusChangeEntry for current status (no exit)."""
        entry = StatusChangeEntry(
            status="In Progress",
            entered_at=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            exited_at=None,
        )

        result = entry.to_simplified_dict()

        assert result["status"] == "In Progress"
        assert "entered_at" in result
        assert "exited_at" not in result

    def test_status_time_summary_to_simplified_dict(self):
        """Test StatusTimeSummary serialization."""
        summary = StatusTimeSummary(
            status="In Progress",
            total_duration_minutes=2880,
            total_duration_formatted="2d 0h 0m",
            visit_count=3,
        )

        result = summary.to_simplified_dict()

        assert result["status"] == "In Progress"
        assert result["total_duration_minutes"] == 2880
        assert result["total_duration_formatted"] == "2d 0h 0m"
        assert result["visit_count"] == 3

    def test_issue_dates_response_to_simplified_dict(self):
        """Test IssueDatesResponse serialization."""
        response = IssueDatesResponse(
            issue_key="TEST-123",
            created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            updated=datetime(2023, 1, 15, 12, 0, tzinfo=timezone.utc),
            current_status="Done",
        )

        result = response.to_simplified_dict()

        assert result["issue_key"] == "TEST-123"
        assert "created" in result
        assert "updated" in result
        assert result["current_status"] == "Done"

    def test_issue_dates_batch_response_to_simplified_dict(self):
        """Test IssueDatesBatchResponse serialization."""
        issues = [
            IssueDatesResponse(
                issue_key="TEST-1",
                current_status="Open",
            ),
            IssueDatesResponse(
                issue_key="TEST-2",
                current_status="Done",
            ),
        ]

        response = IssueDatesBatchResponse(
            issues=issues,
            total_count=3,
            success_count=2,
            error_count=1,
            errors=[{"issue_key": "TEST-3", "error": "Not found"}],
        )

        result = response.to_simplified_dict()

        assert result["total_count"] == 3
        assert result["success_count"] == 2
        assert result["error_count"] == 1
        assert len(result["issues"]) == 2
        assert len(result["errors"]) == 1
