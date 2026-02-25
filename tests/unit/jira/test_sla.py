"""Tests for the Jira SLA mixin."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

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


class TestSLAConfig:
    """Tests for SLAConfig dataclass."""

    def test_default_working_days(self):
        """Test default working days are Monday-Friday."""
        config = SLAConfig(default_metrics=["cycle_time"])
        assert config.working_days == [1, 2, 3, 4, 5]

    def test_custom_working_days(self):
        """Test custom working days."""
        config = SLAConfig(
            default_metrics=["cycle_time"],
            working_days=[1, 2, 3],  # Mon-Wed
        )
        assert config.working_days == [1, 2, 3]

    def test_invalid_working_days_low(self):
        """Test validation rejects day 0."""
        with pytest.raises(ValueError) as exc_info:
            SLAConfig(default_metrics=["cycle_time"], working_days=[0, 1, 2])
        assert "Invalid working days" in str(exc_info.value)
        assert "0" in str(exc_info.value)

    def test_invalid_working_days_high(self):
        """Test validation rejects day 8."""
        with pytest.raises(ValueError) as exc_info:
            SLAConfig(default_metrics=["cycle_time"], working_days=[1, 2, 8])
        assert "Invalid working days" in str(exc_info.value)
        assert "8" in str(exc_info.value)

    def test_invalid_working_days_multiple(self):
        """Test validation rejects multiple invalid days."""
        with pytest.raises(ValueError) as exc_info:
            SLAConfig(default_metrics=["cycle_time"], working_days=[0, 8, 9])
        assert "Invalid working days" in str(exc_info.value)

    def test_from_env_defaults(self):
        """Test from_env with defaults."""
        with patch.dict("os.environ", {}, clear=True):
            config = SLAConfig.from_env()
            assert config.default_metrics == ["cycle_time", "time_in_status"]
            assert config.working_hours_only is False
            assert config.working_hours_start == "09:00"
            assert config.working_hours_end == "17:00"
            assert config.working_days == [1, 2, 3, 4, 5]
            assert config.timezone == "UTC"

    def test_from_env_custom_values(self):
        """Test from_env with custom environment variables."""
        env = {
            "JIRA_SLA_METRICS": "lead_time,resolution_time",
            "JIRA_SLA_WORKING_HOURS_ONLY": "true",
            "JIRA_SLA_WORKING_HOURS_START": "08:00",
            "JIRA_SLA_WORKING_HOURS_END": "18:00",
            "JIRA_SLA_WORKING_DAYS": "1,2,3,4",
            "JIRA_SLA_TIMEZONE": "America/New_York",
        }
        with patch.dict("os.environ", env, clear=True):
            config = SLAConfig.from_env()
            assert config.default_metrics == ["lead_time", "resolution_time"]
            assert config.working_hours_only is True
            assert config.working_hours_start == "08:00"
            assert config.working_hours_end == "18:00"
            assert config.working_days == [1, 2, 3, 4]
            assert config.timezone == "America/New_York"

    def test_from_env_invalid_working_days(self):
        """Test from_env raises error for invalid working days."""
        env = {"JIRA_SLA_WORKING_DAYS": "0,8,9"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ValueError) as exc_info:
                SLAConfig.from_env()
            assert "Invalid JIRA_SLA_WORKING_DAYS" in str(exc_info.value)


class TestSLAMixin:
    """Tests for the SLAMixin class."""

    @pytest.fixture
    def sla_mixin(self, jira_fetcher: JiraFetcher) -> SLAMixin:
        """Create an SLAMixin instance with mocked dependencies."""
        return jira_fetcher

    @pytest.fixture
    def mock_issue_dates(self) -> IssueDatesResponse:
        """Create mock issue dates response."""
        return IssueDatesResponse(
            issue_key="TEST-123",
            created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            updated=datetime(2023, 1, 15, 12, 0, tzinfo=timezone.utc),
            due_date=datetime(2023, 2, 1, 23, 59, tzinfo=timezone.utc),
            resolution_date=datetime(2023, 1, 20, 10, 0, tzinfo=timezone.utc),
            current_status="Done",
            status_changes=[
                StatusChangeEntry(
                    status="Open",
                    entered_at=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
                    exited_at=datetime(2023, 1, 2, 10, 0, tzinfo=timezone.utc),
                    duration_minutes=1440,
                ),
                StatusChangeEntry(
                    status="In Progress",
                    entered_at=datetime(2023, 1, 2, 10, 0, tzinfo=timezone.utc),
                    exited_at=datetime(2023, 1, 10, 10, 0, tzinfo=timezone.utc),
                    duration_minutes=11520,
                ),
                StatusChangeEntry(
                    status="Done",
                    entered_at=datetime(2023, 1, 10, 10, 0, tzinfo=timezone.utc),
                    exited_at=None,
                    duration_minutes=None,
                ),
            ],
            status_summary=[
                StatusTimeSummary(
                    status="Open",
                    total_duration_minutes=1440,
                    total_duration_formatted="1d 0h 0m",
                    visit_count=1,
                ),
                StatusTimeSummary(
                    status="In Progress",
                    total_duration_minutes=11520,
                    total_duration_formatted="8d 0h 0m",
                    visit_count=1,
                ),
            ],
        )

    def test_get_issue_sla_basic(
        self, sla_mixin: SLAMixin, mock_issue_dates: IssueDatesResponse
    ):
        """Test basic SLA calculation."""
        # Mock get_issue_dates to return our fixture
        sla_mixin.get_issue_dates = MagicMock(return_value=mock_issue_dates)

        result = sla_mixin.get_issue_sla(
            issue_key="TEST-123",
            metrics=["cycle_time", "lead_time"],
            working_hours_only=False,
        )

        assert isinstance(result, IssueSLAResponse)
        assert result.issue_key == "TEST-123"
        assert result.metrics.cycle_time is not None
        assert result.metrics.lead_time is not None

    def test_cycle_time_calculation(
        self, sla_mixin: SLAMixin, mock_issue_dates: IssueDatesResponse
    ):
        """Test cycle time calculation (created to resolved)."""
        sla_mixin.get_issue_dates = MagicMock(return_value=mock_issue_dates)

        result = sla_mixin.get_issue_sla(
            issue_key="TEST-123",
            metrics=["cycle_time"],
            working_hours_only=False,
        )

        assert result.metrics.cycle_time is not None
        assert result.metrics.cycle_time.calculated is True
        # 19 days from Jan 1 to Jan 20 = 27360 minutes
        assert result.metrics.cycle_time.value_minutes == 27360

    def test_cycle_time_not_resolved(self, sla_mixin: SLAMixin):
        """Test cycle time when issue not resolved."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            resolution_date=None,  # Not resolved
            current_status="In Progress",
        )
        sla_mixin.get_issue_dates = MagicMock(return_value=issue_dates)

        result = sla_mixin.get_issue_sla(
            issue_key="TEST-123",
            metrics=["cycle_time"],
            working_hours_only=False,
        )

        assert result.metrics.cycle_time.calculated is False
        assert "not resolved" in result.metrics.cycle_time.reason.lower()

    def test_due_date_compliance_met(
        self, sla_mixin: SLAMixin, mock_issue_dates: IssueDatesResponse
    ):
        """Test due date compliance when deadline met."""
        sla_mixin.get_issue_dates = MagicMock(return_value=mock_issue_dates)

        result = sla_mixin.get_issue_sla(
            issue_key="TEST-123",
            metrics=["due_date_compliance"],
            working_hours_only=False,
        )

        assert result.metrics.due_date_compliance is not None
        assert result.metrics.due_date_compliance.status == "met"
        assert "early" in result.metrics.due_date_compliance.formatted_margin

    def test_due_date_compliance_missed(self, sla_mixin: SLAMixin):
        """Test due date compliance when deadline missed."""
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            due_date=datetime(2023, 1, 15, 23, 59, tzinfo=timezone.utc),
            resolution_date=datetime(2023, 1, 20, 10, 0, tzinfo=timezone.utc),
            current_status="Done",
        )
        sla_mixin.get_issue_dates = MagicMock(return_value=issue_dates)

        result = sla_mixin.get_issue_sla(
            issue_key="TEST-123",
            metrics=["due_date_compliance"],
            working_hours_only=False,
        )

        assert result.metrics.due_date_compliance.status == "missed"
        assert "late" in result.metrics.due_date_compliance.formatted_margin

    def test_time_in_status(
        self, sla_mixin: SLAMixin, mock_issue_dates: IssueDatesResponse
    ):
        """Test time in status calculation."""
        sla_mixin.get_issue_dates = MagicMock(return_value=mock_issue_dates)

        result = sla_mixin.get_issue_sla(
            issue_key="TEST-123",
            metrics=["time_in_status"],
            working_hours_only=False,
        )

        assert result.metrics.time_in_status is not None
        assert len(result.metrics.time_in_status.statuses) >= 1

    def test_batch_get_issue_sla(
        self, sla_mixin: SLAMixin, mock_issue_dates: IssueDatesResponse
    ):
        """Test batch SLA calculation."""
        sla_mixin.get_issue_dates = MagicMock(return_value=mock_issue_dates)

        result = sla_mixin.batch_get_issue_sla(
            issue_keys=["TEST-1", "TEST-2", "TEST-3"],
            metrics=["cycle_time"],
            working_hours_only=False,
        )

        assert isinstance(result, IssueSLABatchResponse)
        assert result.total_count == 3
        assert result.success_count == 3
        assert result.error_count == 0

    def test_batch_get_issue_sla_with_errors(self, sla_mixin: SLAMixin):
        """Test batch SLA calculation with some errors."""

        def mock_get_dates(issue_key, **kwargs):
            if issue_key == "TEST-2":
                raise ValueError("Issue not found")
            return IssueDatesResponse(
                issue_key=issue_key,
                created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
                resolution_date=datetime(2023, 1, 20, 10, 0, tzinfo=timezone.utc),
                current_status="Done",
            )

        sla_mixin.get_issue_dates = MagicMock(side_effect=mock_get_dates)

        result = sla_mixin.batch_get_issue_sla(
            issue_keys=["TEST-1", "TEST-2", "TEST-3"],
            metrics=["cycle_time"],
            working_hours_only=False,
        )

        assert result.total_count == 3
        assert result.success_count == 2
        assert result.error_count == 1
        assert result.errors[0]["issue_key"] == "TEST-2"


class TestSLATimezones:
    """Tests for SLA timezone handling."""

    @pytest.fixture
    def sla_mixin(self, jira_fetcher: JiraFetcher) -> SLAMixin:
        """Create an SLAMixin instance with mocked dependencies."""
        return jira_fetcher

    def test_timezone_utc(self, sla_mixin: SLAMixin):
        """Test SLA calculation with UTC timezone."""
        sla_config = SLAConfig(
            default_metrics=["lead_time"],
            timezone="UTC",
        )
        tz = sla_mixin._get_sla_timezone(sla_config)
        assert str(tz) == "UTC"

    def test_timezone_new_york(self, sla_mixin: SLAMixin):
        """Test SLA calculation with America/New_York timezone."""
        sla_config = SLAConfig(
            default_metrics=["lead_time"],
            timezone="America/New_York",
        )
        tz = sla_mixin._get_sla_timezone(sla_config)
        assert str(tz) == "America/New_York"

    def test_timezone_asia_seoul(self, sla_mixin: SLAMixin):
        """Test SLA calculation with Asia/Seoul timezone."""
        sla_config = SLAConfig(
            default_metrics=["lead_time"],
            timezone="Asia/Seoul",
        )
        tz = sla_mixin._get_sla_timezone(sla_config)
        assert str(tz) == "Asia/Seoul"

    def test_timezone_invalid_fallback(self, sla_mixin: SLAMixin):
        """Test invalid timezone falls back to UTC."""
        sla_config = SLAConfig(
            default_metrics=["lead_time"],
            timezone="Invalid/Timezone",
        )
        tz = sla_mixin._get_sla_timezone(sla_config)
        assert str(tz) == "UTC"


class TestSLAWorkingHours:
    """Tests for SLA working hours calculation."""

    @pytest.fixture
    def sla_mixin(self, jira_fetcher: JiraFetcher) -> SLAMixin:
        """Create an SLAMixin instance with mocked dependencies."""
        return jira_fetcher

    def test_working_minutes_weekday(self, sla_mixin: SLAMixin):
        """Test working minutes on a single weekday."""
        sla_config = SLAConfig(
            default_metrics=["cycle_time"],
            working_hours_start="09:00",
            working_hours_end="17:00",
            working_days=[1, 2, 3, 4, 5],
            timezone="UTC",
        )

        # Monday 9am to 5pm = 8 hours = 480 minutes
        start = datetime(2023, 1, 2, 9, 0, tzinfo=timezone.utc)  # Monday
        end = datetime(2023, 1, 2, 17, 0, tzinfo=timezone.utc)

        result = sla_mixin._calculate_working_minutes(start, end, sla_config)
        assert result == 480

    def test_working_minutes_excludes_weekend(self, sla_mixin: SLAMixin):
        """Test working minutes excludes weekend days."""
        sla_config = SLAConfig(
            default_metrics=["cycle_time"],
            working_hours_start="09:00",
            working_hours_end="17:00",
            working_days=[1, 2, 3, 4, 5],
            timezone="UTC",
        )

        # Friday 9am to Monday 5pm should only count Friday and Monday
        start = datetime(2023, 1, 6, 9, 0, tzinfo=timezone.utc)  # Friday
        end = datetime(2023, 1, 9, 17, 0, tzinfo=timezone.utc)  # Monday

        result = sla_mixin._calculate_working_minutes(start, end, sla_config)
        # 8 hours Friday + 8 hours Monday = 960 minutes
        assert result == 960

    def test_working_minutes_partial_day(self, sla_mixin: SLAMixin):
        """Test working minutes for partial day."""
        sla_config = SLAConfig(
            default_metrics=["cycle_time"],
            working_hours_start="09:00",
            working_hours_end="17:00",
            working_days=[1, 2, 3, 4, 5],
            timezone="UTC",
        )

        # Monday 10am to 2pm = 4 hours = 240 minutes
        start = datetime(2023, 1, 2, 10, 0, tzinfo=timezone.utc)  # Monday
        end = datetime(2023, 1, 2, 14, 0, tzinfo=timezone.utc)

        result = sla_mixin._calculate_working_minutes(start, end, sla_config)
        assert result == 240

    def test_working_minutes_outside_hours(self, sla_mixin: SLAMixin):
        """Test working minutes when entirely outside working hours."""
        sla_config = SLAConfig(
            default_metrics=["cycle_time"],
            working_hours_start="09:00",
            working_hours_end="17:00",
            working_days=[1, 2, 3, 4, 5],
            timezone="UTC",
        )

        # Monday 6pm to 8pm = 0 minutes (after working hours)
        start = datetime(2023, 1, 2, 18, 0, tzinfo=timezone.utc)  # Monday
        end = datetime(2023, 1, 2, 20, 0, tzinfo=timezone.utc)

        result = sla_mixin._calculate_working_minutes(start, end, sla_config)
        assert result == 0


class TestSLAModels:
    """Tests for SLA Pydantic models."""

    def test_cycle_time_metric_calculated(self):
        """Test CycleTimeMetric serialization when calculated."""
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
        """Test CycleTimeMetric serialization when not calculated."""
        metric = CycleTimeMetric(
            calculated=False,
            reason="Issue not resolved",
        )

        result = metric.to_simplified_dict()

        assert result["calculated"] is False
        assert result["reason"] == "Issue not resolved"
        assert "value_minutes" not in result

    def test_lead_time_metric(self):
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

    def test_time_in_status_entry(self):
        """Test TimeInStatusEntry serialization."""
        entry = TimeInStatusEntry(
            status="In Progress",
            value_minutes=1440,
            formatted="1d 0h 0m",
            percentage=50.0,
            visit_count=2,
        )

        result = entry.to_simplified_dict()

        assert result["status"] == "In Progress"
        assert result["value_minutes"] == 1440
        assert result["percentage"] == 50.0
        assert result["visit_count"] == 2

    def test_due_date_compliance_met(self):
        """Test DueDateComplianceMetric serialization when met."""
        metric = DueDateComplianceMetric(
            status="met",
            margin_minutes=1440,
            formatted_margin="1d 0h 0m early",
        )

        result = metric.to_simplified_dict()

        assert result["status"] == "met"
        assert result["margin_minutes"] == 1440
        assert result["formatted_margin"] == "1d 0h 0m early"

    def test_due_date_compliance_no_due_date(self):
        """Test DueDateComplianceMetric when no due date."""
        metric = DueDateComplianceMetric(status="no_due_date")

        result = metric.to_simplified_dict()

        assert result["status"] == "no_due_date"
        assert "margin_minutes" not in result

    def test_issue_sla_response(self):
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
        assert result["metrics"]["cycle_time"]["calculated"] is True

    def test_issue_sla_batch_response(self):
        """Test IssueSLABatchResponse serialization."""
        response = IssueSLABatchResponse(
            issues=[
                IssueSLAResponse(
                    issue_key="TEST-1",
                    metrics=IssueSLAMetrics(),
                )
            ],
            total_count=2,
            success_count=1,
            error_count=1,
            errors=[{"issue_key": "TEST-2", "error": "Not found"}],
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

        assert result["total_count"] == 2
        assert result["success_count"] == 1
        assert result["error_count"] == 1
        assert len(result["issues"]) == 1
        assert len(result["errors"]) == 1
        assert result["working_hours_applied"] is True
        assert result["working_hours_config"]["start"] == "09:00"


class TestStatusCategoryCaching:
    """Tests for status category caching in SLA calculations."""

    @pytest.fixture
    def sla_mixin(self, jira_fetcher: JiraFetcher) -> SLAMixin:
        """Create an SLAMixin instance with mocked dependencies."""
        return jira_fetcher

    @pytest.fixture
    def mock_statuses(self) -> list[dict]:
        """Create mock status list from Jira API."""
        return [
            {
                "name": "Open",
                "statusCategory": {"key": "new"},
            },
            {
                "name": "In Progress",
                "statusCategory": {"key": "indeterminate"},
            },
            {
                "name": "In Development",
                "statusCategory": {"key": "indeterminate"},
            },
            {
                "name": "Done",
                "statusCategory": {"key": "done"},
            },
        ]

    def test_status_category_cache_called_once(
        self, sla_mixin: SLAMixin, mock_statuses: list[dict]
    ):
        """Test that get_all_statuses is only called once per instance."""
        sla_mixin.jira.get_all_statuses = MagicMock(return_value=mock_statuses)

        # Call multiple times
        sla_mixin._get_status_category_map()
        sla_mixin._get_status_category_map()
        sla_mixin._get_status_category_map()

        # Should only call API once
        assert sla_mixin.jira.get_all_statuses.call_count == 1

    def test_is_in_progress_uses_cache(
        self, sla_mixin: SLAMixin, mock_statuses: list[dict]
    ):
        """Test that _is_in_progress_status uses cached data."""
        sla_mixin.jira.get_all_statuses = MagicMock(return_value=mock_statuses)

        # Check multiple statuses
        assert sla_mixin._is_in_progress_status("TEST-1", "In Progress") is True
        assert sla_mixin._is_in_progress_status("TEST-1", "In Development") is True
        assert sla_mixin._is_in_progress_status("TEST-1", "Open") is False
        assert sla_mixin._is_in_progress_status("TEST-1", "Done") is False

        # Should only call API once despite multiple status checks
        assert sla_mixin.jira.get_all_statuses.call_count == 1

    def test_is_in_progress_case_insensitive(
        self, sla_mixin: SLAMixin, mock_statuses: list[dict]
    ):
        """Test that status lookup is case-insensitive."""
        sla_mixin.jira.get_all_statuses = MagicMock(return_value=mock_statuses)

        assert sla_mixin._is_in_progress_status("TEST-1", "in progress") is True
        assert sla_mixin._is_in_progress_status("TEST-1", "IN PROGRESS") is True
        assert sla_mixin._is_in_progress_status("TEST-1", "In Progress") is True

    def test_fallback_when_api_fails(self, sla_mixin: SLAMixin):
        """Test fallback to name-based check when API fails."""
        sla_mixin.jira.get_all_statuses = MagicMock(side_effect=Exception("API error"))

        # Should fallback to name-based check
        assert sla_mixin._is_in_progress_status("TEST-1", "in progress") is True
        assert sla_mixin._is_in_progress_status("TEST-1", "in development") is True
        assert sla_mixin._is_in_progress_status("TEST-1", "working") is True
        assert sla_mixin._is_in_progress_status("TEST-1", "open") is False

    def test_fallback_for_unknown_status(
        self, sla_mixin: SLAMixin, mock_statuses: list[dict]
    ):
        """Test fallback when status not in cache."""
        sla_mixin.jira.get_all_statuses = MagicMock(return_value=mock_statuses)

        # Unknown status not in cache falls back to name-based check
        assert sla_mixin._is_in_progress_status("TEST-1", "in progress") is True
        # "Custom Status" not in mock_statuses, falls back to name check
        assert sla_mixin._is_in_progress_status("TEST-1", "Custom Status") is False

    def test_cache_persists_across_resolution_time_calls(
        self, sla_mixin: SLAMixin, mock_statuses: list[dict]
    ):
        """Test cache persists when calculating resolution time for multiple issues."""
        sla_mixin.jira.get_all_statuses = MagicMock(return_value=mock_statuses)

        # Create mock issue dates with status changes
        issue_dates = IssueDatesResponse(
            issue_key="TEST-123",
            created=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            resolution_date=datetime(2023, 1, 20, 10, 0, tzinfo=timezone.utc),
            current_status="Done",
            status_changes=[
                StatusChangeEntry(
                    status="Open",
                    entered_at=datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
                    exited_at=datetime(2023, 1, 2, 10, 0, tzinfo=timezone.utc),
                    duration_minutes=1440,
                ),
                StatusChangeEntry(
                    status="In Progress",
                    entered_at=datetime(2023, 1, 2, 10, 0, tzinfo=timezone.utc),
                    exited_at=datetime(2023, 1, 10, 10, 0, tzinfo=timezone.utc),
                    duration_minutes=11520,
                ),
                StatusChangeEntry(
                    status="Done",
                    entered_at=datetime(2023, 1, 10, 10, 0, tzinfo=timezone.utc),
                    exited_at=None,
                    duration_minutes=None,
                ),
            ],
        )
        sla_mixin.get_issue_dates = MagicMock(return_value=issue_dates)

        # Calculate SLA for multiple issues
        sla_mixin.get_issue_sla("TEST-1", metrics=["resolution_time"])
        sla_mixin.get_issue_sla("TEST-2", metrics=["resolution_time"])
        sla_mixin.get_issue_sla("TEST-3", metrics=["resolution_time"])

        # API should only be called once across all issues
        assert sla_mixin.jira.get_all_statuses.call_count == 1
