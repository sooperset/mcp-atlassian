"""Tests for the Jira SLA mixin."""

from datetime import datetime, timezone

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import SLAConfig
from mcp_atlassian.jira.sla import SLAMixin
from mcp_atlassian.models.jira.metrics import (
    IssueDatesResponse,
    StatusChangeEntry,
    StatusTimeSummary,
)
from mcp_atlassian.models.jira.sla import (
    CycleTimeMetric,
    DueDateComplianceMetric,
    IssueSLABatchResponse,
    IssueSLAMetrics,
    IssueSLAResponse,
    LeadTimeMetric,
    TimeInStatusEntry,
    WorkingHoursConfig,
)


class TestSLAMixin:
    """Tests for the SLAMixin class."""

    @pytest.fixture
    def sla_mixin(self, jira_fetcher: JiraFetcher) -> SLAMixin:
        """Create a SLAMixin instance with mocked dependencies."""
        return jira_fetcher

    @pytest.fixture
    def default_sla_config(self) -> SLAConfig:
        """Create default SLA configuration."""
        return SLAConfig(
            default_metrics=["cycle_time", "time_in_status"],
            working_hours_only=False,
            working_hours_start="09:00",
            working_hours_end="17:00",
            working_days=[1, 2, 3, 4, 5],
            timezone="UTC",
        )

    def test_format_duration_zero_minutes(self, sla_mixin: SLAMixin):
        """Test formatting zero minutes."""
        result = sla_mixin._format_duration(0)
        assert result == "0m"

    def test_format_duration_negative_minutes(self, sla_mixin: SLAMixin):
        """Test formatting negative minutes."""
        result = sla_mixin._format_duration(-10)
        assert result == "0m"

    def test_format_duration_minutes_only(self, sla_mixin: SLAMixin):
        """Test formatting when only minutes are present."""
        result = sla_mixin._format_duration(45)
        assert result == "45m"

    def test_format_duration_hours_and_minutes(self, sla_mixin: SLAMixin):
        """Test formatting hours and minutes."""
        result = sla_mixin._format_duration(90)  # 1h 30m
        assert result == "1h 30m"

    def test_format_duration_days_hours_minutes(self, sla_mixin: SLAMixin):
        """Test formatting days, hours, and minutes."""
        result = sla_mixin._format_duration(1500)  # 1d 1h 0m
        assert result == "1d 1h 0m"

    def test_calculate_duration_calendar_time(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test calculating calendar duration (not working hours)."""
        start = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 1, 1, 12, 30, 0, tzinfo=timezone.utc)

        result = sla_mixin._calculate_duration(start, end, False, default_sla_config)
        assert result == 150  # 2h 30m = 150 minutes

    def test_calculate_working_minutes_same_day(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test working minutes calculation within same working day."""
        # Monday 10:00 to Monday 15:00
        start = datetime(2023, 1, 2, 10, 0, 0, tzinfo=timezone.utc)  # Monday
        end = datetime(2023, 1, 2, 15, 0, 0, tzinfo=timezone.utc)  # Monday

        result = sla_mixin._calculate_working_minutes(start, end, default_sla_config)
        assert result == 300  # 5 hours = 300 minutes

    def test_calculate_working_minutes_excludes_weekend(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test that weekends are excluded from working minutes."""
        # Friday 09:00 to Monday 17:00
        start = datetime(2023, 1, 6, 9, 0, 0, tzinfo=timezone.utc)  # Friday
        end = datetime(2023, 1, 9, 17, 0, 0, tzinfo=timezone.utc)  # Monday

        result = sla_mixin._calculate_working_minutes(start, end, default_sla_config)
        # Should be 2 full working days: Friday + Monday = 2 * 8h = 960 minutes
        assert result == 960

    def test_calculate_working_minutes_excludes_non_working_hours(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test that non-working hours are excluded."""
        # Monday 08:00 to Monday 18:00 (includes before 09:00 and after 17:00)
        start = datetime(2023, 1, 2, 8, 0, 0, tzinfo=timezone.utc)  # Monday
        end = datetime(2023, 1, 2, 18, 0, 0, tzinfo=timezone.utc)  # Monday

        result = sla_mixin._calculate_working_minutes(start, end, default_sla_config)
        # Should be 8 hours (09:00-17:00) = 480 minutes
        assert result == 480

    def test_calculate_working_minutes_partial_day(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test partial working day calculation."""
        # Monday 11:00 to Monday 14:00
        start = datetime(2023, 1, 2, 11, 0, 0, tzinfo=timezone.utc)  # Monday
        end = datetime(2023, 1, 2, 14, 0, 0, tzinfo=timezone.utc)  # Monday

        result = sla_mixin._calculate_working_minutes(start, end, default_sla_config)
        # Should be 3 hours = 180 minutes
        assert result == 180

    def test_calculate_working_minutes_multiple_days(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test working minutes across multiple working days."""
        # Monday 09:00 to Wednesday 17:00
        start = datetime(2023, 1, 2, 9, 0, 0, tzinfo=timezone.utc)  # Monday
        end = datetime(2023, 1, 4, 17, 0, 0, tzinfo=timezone.utc)  # Wednesday

        result = sla_mixin._calculate_working_minutes(start, end, default_sla_config)
        # Should be 3 full days = 3 * 8h = 1440 minutes
        assert result == 1440


class TestSLACalculations:
    """Tests for individual SLA metric calculations."""

    @pytest.fixture
    def sla_mixin(self, jira_fetcher: JiraFetcher) -> SLAMixin:
        """Create a SLAMixin instance with mocked dependencies."""
        return jira_fetcher

    @pytest.fixture
    def default_sla_config(self) -> SLAConfig:
        """Create default SLA configuration."""
        return SLAConfig(
            default_metrics=["cycle_time", "time_in_status"],
            working_hours_only=False,
        )

    def test_calculate_cycle_time_resolved_issue(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test cycle time for resolved issue."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            resolution_date=datetime(2023, 1, 2, 10, 0, tzinfo=timezone.utc),
            current_status="Done",
        )

        result = sla_mixin._calculate_cycle_time(issue_dates, False, default_sla_config)

        assert result.calculated is True
        assert result.value_minutes == 1440  # 24 hours = 1440 minutes
        assert result.formatted == "1d 0h 0m"

    def test_calculate_cycle_time_unresolved_issue(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test cycle time for unresolved issue."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            resolution_date=None,
            current_status="In Progress",
        )

        result = sla_mixin._calculate_cycle_time(issue_dates, False, default_sla_config)

        assert result.calculated is False
        assert result.reason == "Issue not resolved"

    def test_calculate_lead_time_resolved_issue(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test lead time for resolved issue."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            resolution_date=datetime(2023, 1, 3, 10, 0, tzinfo=timezone.utc),
            current_status="Done",
        )

        result = sla_mixin._calculate_lead_time(issue_dates, False, default_sla_config)

        assert result.is_resolved is True
        assert result.value_minutes == 2880  # 48 hours = 2880 minutes
        assert result.formatted == "2d 0h 0m"

    def test_calculate_due_date_compliance_met(self, sla_mixin: SLAMixin):
        """Test due date compliance when deadline was met."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            due_date=datetime(2023, 1, 5, tzinfo=timezone.utc),
            resolution_date=datetime(2023, 1, 4, 10, 0, tzinfo=timezone.utc),
            current_status="Done",
        )

        result = sla_mixin._calculate_due_date_compliance(issue_dates)

        assert result.status == "met"
        assert result.margin_minutes is not None
        assert result.margin_minutes > 0
        assert "early" in result.formatted_margin

    def test_calculate_due_date_compliance_missed(self, sla_mixin: SLAMixin):
        """Test due date compliance when deadline was missed."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            due_date=datetime(2023, 1, 4, tzinfo=timezone.utc),
            resolution_date=datetime(2023, 1, 6, 10, 0, tzinfo=timezone.utc),
            current_status="Done",
        )

        result = sla_mixin._calculate_due_date_compliance(issue_dates)

        assert result.status == "missed"
        assert result.margin_minutes is not None
        assert result.margin_minutes < 0
        assert "late" in result.formatted_margin

    def test_calculate_due_date_compliance_no_due_date(self, sla_mixin: SLAMixin):
        """Test due date compliance when no due date is set."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            due_date=None,
            resolution_date=datetime(2023, 1, 4, 10, 0, tzinfo=timezone.utc),
            current_status="Done",
        )

        result = sla_mixin._calculate_due_date_compliance(issue_dates)

        assert result.status == "no_due_date"

    def test_calculate_due_date_compliance_not_resolved(self, sla_mixin: SLAMixin):
        """Test due date compliance when issue is not resolved."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            due_date=datetime(2023, 1, 5, tzinfo=timezone.utc),
            resolution_date=None,
            current_status="In Progress",
        )

        result = sla_mixin._calculate_due_date_compliance(issue_dates)

        assert result.status == "not_resolved"

    def test_calculate_time_in_status(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test time in status calculation."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            current_status="Done",
            status_summary=[
                StatusTimeSummary(
                    status="Open",
                    total_duration_minutes=120,
                    total_duration_formatted="2h 0m",
                    visit_count=1,
                ),
                StatusTimeSummary(
                    status="In Progress",
                    total_duration_minutes=480,
                    total_duration_formatted="8h 0m",
                    visit_count=2,
                ),
            ],
        )

        result = sla_mixin._calculate_time_in_status(
            issue_dates, False, default_sla_config
        )

        assert result.total_minutes == 600  # 120 + 480
        assert len(result.statuses) == 2
        # Check sorted by time descending
        assert result.statuses[0].status == "In Progress"
        assert result.statuses[0].value_minutes == 480
        assert result.statuses[1].status == "Open"
        assert result.statuses[1].value_minutes == 120

    def test_calculate_resolution_time_resolved(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test resolution time for resolved issue with In Progress."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            resolution_date=datetime(2023, 1, 3, 10, 0, tzinfo=timezone.utc),
            current_status="Done",
            status_changes=[
                StatusChangeEntry(
                    status="Open",
                    entered_at=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
                    exited_at=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
                ),
                StatusChangeEntry(
                    status="In Progress",
                    entered_at=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
                    exited_at=datetime(2023, 1, 3, 10, 0, tzinfo=timezone.utc),
                ),
            ],
        )

        result = sla_mixin._calculate_resolution_time(
            issue_dates, False, default_sla_config
        )

        assert result.calculated is True
        # From In Progress (Jan 1 12:00) to resolution (Jan 3 10:00) = 46h = 2760 min
        assert result.value_minutes == 2760
        assert "1d" in result.formatted

    def test_calculate_resolution_time_no_in_progress(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test resolution time when no In Progress status found."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            resolution_date=datetime(2023, 1, 3, 10, 0, tzinfo=timezone.utc),
            current_status="Done",
            status_changes=[
                StatusChangeEntry(
                    status="Open",
                    entered_at=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
                    exited_at=datetime(2023, 1, 3, 10, 0, tzinfo=timezone.utc),
                ),
            ],
        )

        result = sla_mixin._calculate_resolution_time(
            issue_dates, False, default_sla_config
        )

        assert result.calculated is False
        assert "In Progress" in result.reason

    def test_calculate_first_response_time(
        self, sla_mixin: SLAMixin, default_sla_config: SLAConfig
    ):
        """Test first response time calculation."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            current_status="In Progress",
            status_changes=[
                StatusChangeEntry(
                    status="Open",
                    entered_at=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
                    exited_at=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
                ),
                StatusChangeEntry(
                    status="In Progress",
                    entered_at=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
                    exited_at=None,
                ),
            ],
        )

        result = sla_mixin._calculate_first_response_time(
            issue_dates, False, default_sla_config
        )

        assert result.calculated is True
        assert result.value_minutes == 120  # 2 hours
        assert result.response_type == "transition"


class TestSLAModels:
    """Tests for the SLA Pydantic models."""

    def test_cycle_time_metric_to_simplified_dict(self):
        """Test CycleTimeMetric serialization."""
        metric = CycleTimeMetric(
            value_minutes=1440,
            formatted="1d 0h 0m",
            calculated=True,
        )

        result = metric.to_simplified_dict()

        assert result["calculated"] is True
        assert result["value_minutes"] == 1440
        assert result["formatted"] == "1d 0h 0m"

    def test_cycle_time_metric_not_calculated(self):
        """Test CycleTimeMetric when not calculated."""
        metric = CycleTimeMetric(
            calculated=False,
            reason="Issue not resolved",
        )

        result = metric.to_simplified_dict()

        assert result["calculated"] is False
        assert result["reason"] == "Issue not resolved"
        assert "value_minutes" not in result

    def test_lead_time_metric_to_simplified_dict(self):
        """Test LeadTimeMetric serialization."""
        metric = LeadTimeMetric(
            value_minutes=2880,
            formatted="2d 0h 0m",
            is_resolved=True,
        )

        result = metric.to_simplified_dict()

        assert result["value_minutes"] == 2880
        assert result["formatted"] == "2d 0h 0m"
        assert result["is_resolved"] is True

    def test_time_in_status_entry_to_simplified_dict(self):
        """Test TimeInStatusEntry serialization."""
        entry = TimeInStatusEntry(
            status="In Progress",
            value_minutes=480,
            formatted="8h 0m",
            percentage=60.0,
            visit_count=2,
        )

        result = entry.to_simplified_dict()

        assert result["status"] == "In Progress"
        assert result["value_minutes"] == 480
        assert result["formatted"] == "8h 0m"
        assert result["percentage"] == 60.0
        assert result["visit_count"] == 2

    def test_due_date_compliance_metric_met(self):
        """Test DueDateComplianceMetric when met."""
        metric = DueDateComplianceMetric(
            status="met",
            margin_minutes=120,
            formatted_margin="2h 0m early",
        )

        result = metric.to_simplified_dict()

        assert result["status"] == "met"
        assert result["margin_minutes"] == 120
        assert result["formatted_margin"] == "2h 0m early"

    def test_due_date_compliance_metric_no_due_date(self):
        """Test DueDateComplianceMetric when no due date."""
        metric = DueDateComplianceMetric(status="no_due_date")

        result = metric.to_simplified_dict()

        assert result["status"] == "no_due_date"
        assert "margin_minutes" not in result

    def test_issue_sla_response_to_simplified_dict(self):
        """Test IssueSLAResponse serialization."""
        response = IssueSLAResponse(
            issue_key="TEST-123",
            metrics=IssueSLAMetrics(
                cycle_time=CycleTimeMetric(
                    value_minutes=1440,
                    formatted="1d 0h 0m",
                    calculated=True,
                )
            ),
        )

        result = response.to_simplified_dict()

        assert result["issue_key"] == "TEST-123"
        assert "metrics" in result
        assert "cycle_time" in result["metrics"]

    def test_issue_sla_batch_response_to_simplified_dict(self):
        """Test IssueSLABatchResponse serialization."""
        issues = [
            IssueSLAResponse(
                issue_key="TEST-1",
                metrics=IssueSLAMetrics(),
            ),
            IssueSLAResponse(
                issue_key="TEST-2",
                metrics=IssueSLAMetrics(),
            ),
        ]

        response = IssueSLABatchResponse(
            issues=issues,
            total_count=3,
            success_count=2,
            error_count=1,
            errors=[{"issue_key": "TEST-3", "error": "Not found"}],
            metrics_calculated=["cycle_time"],
            working_hours_applied=True,
            working_hours_config=WorkingHoursConfig(
                start="09:00",
                end="17:00",
                days=[1, 2, 3, 4, 5],
                timezone="UTC",
            ),
        )

        result = response.to_simplified_dict()

        assert result["total_count"] == 3
        assert result["success_count"] == 2
        assert result["error_count"] == 1
        assert len(result["issues"]) == 2
        assert len(result["errors"]) == 1
        assert result["metrics_calculated"] == ["cycle_time"]
        assert result["working_hours_applied"] is True
        assert "working_hours_config" in result


class TestSLAConfig:
    """Tests for the SLAConfig class."""

    def test_sla_config_defaults(self):
        """Test SLAConfig default values."""
        config = SLAConfig(
            default_metrics=["cycle_time"],
        )

        assert config.working_hours_only is False
        assert config.working_hours_start == "09:00"
        assert config.working_hours_end == "17:00"
        assert config.working_days == [1, 2, 3, 4, 5]  # Monday-Friday
        assert config.timezone == "UTC"

    def test_sla_config_custom_values(self):
        """Test SLAConfig with custom values."""
        config = SLAConfig(
            default_metrics=["cycle_time", "lead_time"],
            working_hours_only=True,
            working_hours_start="08:00",
            working_hours_end="18:00",
            working_days=[1, 2, 3, 4, 5, 6],  # Monday-Saturday
            timezone="America/New_York",
        )

        assert config.working_hours_only is True
        assert config.working_hours_start == "08:00"
        assert config.working_hours_end == "18:00"
        assert config.working_days == [1, 2, 3, 4, 5, 6]
        assert config.timezone == "America/New_York"
