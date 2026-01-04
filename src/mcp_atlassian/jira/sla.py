"""Module for Jira SLA calculations."""

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..models.jira.metrics import IssueDatesResponse
from ..models.jira.sla import (
    CycleTimeMetric,
    DueDateComplianceMetric,
    FirstResponseTimeMetric,
    IssueSLABatchResponse,
    IssueSLAMetrics,
    IssueSLAResponse,
    LeadTimeMetric,
    ResolutionTimeMetric,
    TimeInStatusEntry,
    TimeInStatusMetric,
    WorkingHoursConfig,
)
from .client import JiraClient
from .config import SLAConfig
from .protocols import MetricsOperationsProto

logger = logging.getLogger("mcp-jira")

# Available SLA metrics
AVAILABLE_METRICS = [
    "cycle_time",
    "lead_time",
    "time_in_status",
    "due_date_compliance",
    "resolution_time",
    "first_response_time",
]


class SLAMixin(JiraClient, MetricsOperationsProto):
    """Mixin for Jira SLA calculations."""

    def get_issue_sla(
        self,
        issue_key: str,
        metrics: list[str] | None = None,
        working_hours_only: bool | None = None,
        include_raw_dates: bool = False,
    ) -> IssueSLAResponse:
        """
        Calculate SLA metrics for a single Jira issue.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)
            metrics: List of metrics to calculate (defaults to config)
            working_hours_only: Whether to use working hours only (defaults to config)
            include_raw_dates: Whether to include raw date values

        Returns:
            IssueSLAResponse with calculated metrics

        Raises:
            ValueError: If the issue cannot be found
        """
        # Get SLA config
        sla_config = self._get_sla_config()

        # Determine which metrics to calculate
        if metrics is None:
            metrics = sla_config.default_metrics
        metrics = [m for m in metrics if m in AVAILABLE_METRICS]

        # Determine working hours setting
        if working_hours_only is None:
            working_hours_only = sla_config.working_hours_only

        # Get raw dates from the metrics mixin
        issue_dates = self.get_issue_dates(
            issue_key=issue_key,
            include_created=True,
            include_updated=True,
            include_due_date=True,
            include_resolution_date=True,
            include_status_changes=True,
            include_status_summary=True,
        )

        # Calculate requested metrics
        sla_metrics = self._calculate_metrics(
            issue_dates=issue_dates,
            metrics=metrics,
            working_hours_only=working_hours_only,
            sla_config=sla_config,
        )

        # Build raw dates if requested
        raw_dates = None
        if include_raw_dates:
            # Build status changes with timestamps
            status_changes_data = []
            for change in issue_dates.status_changes:
                change_entry = {
                    "status": change.status,
                    "entered_at": change.entered_at.isoformat(),
                }
                if change.exited_at:
                    change_entry["exited_at"] = change.exited_at.isoformat()
                if change.transitioned_by:
                    change_entry["transitioned_by"] = change.transitioned_by
                status_changes_data.append(change_entry)

            raw_dates = {
                "created": (
                    issue_dates.created.isoformat() if issue_dates.created else None
                ),
                "updated": (
                    issue_dates.updated.isoformat() if issue_dates.updated else None
                ),
                "due_date": (
                    issue_dates.due_date.isoformat() if issue_dates.due_date else None
                ),
                "resolution_date": (
                    issue_dates.resolution_date.isoformat()
                    if issue_dates.resolution_date
                    else None
                ),
                "current_status": issue_dates.current_status,
                "status_changes": status_changes_data,
            }

        return IssueSLAResponse(
            issue_key=issue_key,
            metrics=sla_metrics,
            raw_dates=raw_dates,
        )

    def batch_get_issue_sla(
        self,
        issue_keys: list[str],
        metrics: list[str] | None = None,
        working_hours_only: bool | None = None,
        include_raw_dates: bool = False,
    ) -> IssueSLABatchResponse:
        """
        Calculate SLA metrics for multiple Jira issues.

        Args:
            issue_keys: List of issue keys
            metrics: List of metrics to calculate (defaults to config)
            working_hours_only: Whether to use working hours only (defaults to config)
            include_raw_dates: Whether to include raw date values

        Returns:
            IssueSLABatchResponse with results for all issues
        """
        # Get SLA config
        sla_config = self._get_sla_config()

        # Determine which metrics to calculate
        if metrics is None:
            metrics = sla_config.default_metrics
        metrics = [m for m in metrics if m in AVAILABLE_METRICS]

        # Determine working hours setting
        if working_hours_only is None:
            working_hours_only = sla_config.working_hours_only

        issues: list[IssueSLAResponse] = []
        errors: list[dict[str, str]] = []

        for issue_key in issue_keys:
            try:
                issue_sla = self.get_issue_sla(
                    issue_key=issue_key,
                    metrics=metrics,
                    working_hours_only=working_hours_only,
                    include_raw_dates=include_raw_dates,
                )
                issues.append(issue_sla)
            except Exception as e:
                logger.warning(f"Error calculating SLA for {issue_key}: {str(e)}")
                errors.append(
                    {
                        "issue_key": issue_key,
                        "error": str(e),
                    }
                )

        # Build working hours config if applied
        working_config = None
        if working_hours_only:
            working_config = WorkingHoursConfig(
                start=sla_config.working_hours_start,
                end=sla_config.working_hours_end,
                days=sla_config.working_days or [1, 2, 3, 4, 5],
                timezone=sla_config.timezone,
            )

        return IssueSLABatchResponse(
            issues=issues,
            total_count=len(issue_keys),
            success_count=len(issues),
            error_count=len(errors),
            errors=errors,
            metrics_calculated=metrics,
            working_hours_applied=working_hours_only,
            working_hours_config=working_config,
        )

    def _get_sla_config(self) -> SLAConfig:
        """Get SLA configuration from JiraConfig or create default."""
        if self.config.sla_config:
            return self.config.sla_config
        return SLAConfig.from_env()

    def _calculate_metrics(
        self,
        issue_dates: IssueDatesResponse,
        metrics: list[str],
        working_hours_only: bool,
        sla_config: SLAConfig,
    ) -> IssueSLAMetrics:
        """
        Calculate requested SLA metrics.

        Args:
            issue_dates: Raw date information from get_issue_dates
            metrics: List of metric IDs to calculate
            working_hours_only: Whether to filter by working hours
            sla_config: SLA configuration

        Returns:
            IssueSLAMetrics with calculated metrics
        """
        result = IssueSLAMetrics()

        if "cycle_time" in metrics:
            result.cycle_time = self._calculate_cycle_time(
                issue_dates, working_hours_only, sla_config
            )

        if "lead_time" in metrics:
            result.lead_time = self._calculate_lead_time(
                issue_dates, working_hours_only, sla_config
            )

        if "time_in_status" in metrics:
            result.time_in_status = self._calculate_time_in_status(
                issue_dates, working_hours_only, sla_config
            )

        if "due_date_compliance" in metrics:
            result.due_date_compliance = self._calculate_due_date_compliance(
                issue_dates
            )

        if "resolution_time" in metrics:
            result.resolution_time = self._calculate_resolution_time(
                issue_dates, working_hours_only, sla_config
            )

        if "first_response_time" in metrics:
            result.first_response_time = self._calculate_first_response_time(
                issue_dates, working_hours_only, sla_config
            )

        return result

    def _calculate_cycle_time(
        self,
        issue_dates: IssueDatesResponse,
        working_hours_only: bool,
        sla_config: SLAConfig,
    ) -> CycleTimeMetric:
        """Calculate cycle time (created to resolved)."""
        if not issue_dates.created or not issue_dates.resolution_date:
            return CycleTimeMetric(
                calculated=False,
                reason="Issue not resolved"
                if issue_dates.created
                else "No created date",
            )

        minutes = self._calculate_duration(
            issue_dates.created,
            issue_dates.resolution_date,
            working_hours_only,
            sla_config,
        )

        return CycleTimeMetric(
            value_minutes=minutes,
            formatted=self._format_duration(minutes),
            calculated=True,
        )

    def _calculate_lead_time(
        self,
        issue_dates: IssueDatesResponse,
        working_hours_only: bool,
        sla_config: SLAConfig,
    ) -> LeadTimeMetric:
        """Calculate lead time (created to now or resolved)."""
        if not issue_dates.created:
            return LeadTimeMetric(
                value_minutes=0,
                formatted="0m",
                is_resolved=False,
            )

        end_time = issue_dates.resolution_date or datetime.now(
            tz=issue_dates.created.tzinfo
        )

        minutes = self._calculate_duration(
            issue_dates.created,
            end_time,
            working_hours_only,
            sla_config,
        )

        return LeadTimeMetric(
            value_minutes=minutes,
            formatted=self._format_duration(minutes),
            is_resolved=issue_dates.resolution_date is not None,
        )

    def _calculate_time_in_status(
        self,
        issue_dates: IssueDatesResponse,
        working_hours_only: bool,
        sla_config: SLAConfig,
    ) -> TimeInStatusMetric:
        """Calculate time spent in each status."""
        if not issue_dates.status_summary:
            return TimeInStatusMetric(statuses=[], total_minutes=0)

        entries: list[TimeInStatusEntry] = []
        total_minutes = 0

        for summary in issue_dates.status_summary:
            # Recalculate with working hours if needed
            if working_hours_only and issue_dates.status_changes:
                # Find all entries for this status and recalculate
                status_minutes = 0
                visit_count = 0
                for change in issue_dates.status_changes:
                    if change.status == summary.status and change.exited_at:
                        minutes = self._calculate_duration(
                            change.entered_at,
                            change.exited_at,
                            working_hours_only,
                            sla_config,
                        )
                        status_minutes += minutes
                        visit_count += 1
                    elif change.status == summary.status and not change.exited_at:
                        # Current status - calculate to now
                        now = datetime.now(tz=change.entered_at.tzinfo)
                        minutes = self._calculate_duration(
                            change.entered_at,
                            now,
                            working_hours_only,
                            sla_config,
                        )
                        status_minutes += minutes
                        visit_count += 1

                if status_minutes > 0 or visit_count > 0:
                    total_minutes += status_minutes
                    entries.append(
                        TimeInStatusEntry(
                            status=summary.status,
                            value_minutes=status_minutes,
                            formatted=self._format_duration(status_minutes),
                            percentage=0.0,  # Calculate after total
                            visit_count=max(visit_count, summary.visit_count),
                        )
                    )
            else:
                # Use existing summary data
                total_minutes += summary.total_duration_minutes
                entries.append(
                    TimeInStatusEntry(
                        status=summary.status,
                        value_minutes=summary.total_duration_minutes,
                        formatted=summary.total_duration_formatted,
                        percentage=0.0,  # Calculate after total
                        visit_count=summary.visit_count,
                    )
                )

        # Calculate percentages
        if total_minutes > 0:
            for entry in entries:
                entry.percentage = (entry.value_minutes / total_minutes) * 100

        # Sort by time descending
        entries.sort(key=lambda x: x.value_minutes, reverse=True)

        return TimeInStatusMetric(
            statuses=entries,
            total_minutes=total_minutes,
        )

    def _calculate_due_date_compliance(
        self,
        issue_dates: IssueDatesResponse,
    ) -> DueDateComplianceMetric:
        """Calculate due date compliance."""
        if not issue_dates.due_date:
            return DueDateComplianceMetric(status="no_due_date")

        if not issue_dates.resolution_date:
            return DueDateComplianceMetric(status="not_resolved")

        # Compare resolution date to due date
        # Due date is typically just a date (no time), so compare at end of day
        due_datetime = datetime.combine(
            issue_dates.due_date.date()
            if isinstance(issue_dates.due_date, datetime)
            else issue_dates.due_date,
            time(23, 59, 59),
            tzinfo=issue_dates.resolution_date.tzinfo,
        )

        margin_minutes = int(
            (due_datetime - issue_dates.resolution_date).total_seconds() / 60
        )

        if margin_minutes >= 0:
            return DueDateComplianceMetric(
                status="met",
                margin_minutes=margin_minutes,
                formatted_margin=f"{self._format_duration(margin_minutes)} early",
            )
        else:
            return DueDateComplianceMetric(
                status="missed",
                margin_minutes=margin_minutes,
                formatted_margin=f"{self._format_duration(abs(margin_minutes))} late",
            )

    def _calculate_resolution_time(
        self,
        issue_dates: IssueDatesResponse,
        working_hours_only: bool,
        sla_config: SLAConfig,
    ) -> ResolutionTimeMetric:
        """Calculate resolution time (first in progress to resolved)."""
        if not issue_dates.resolution_date:
            return ResolutionTimeMetric(
                calculated=False,
                reason="Issue not resolved",
            )

        # Find first "In Progress" transition
        first_in_progress = None
        for change in issue_dates.status_changes:
            if change.status.lower() in ("in progress", "in development", "working"):
                first_in_progress = change.entered_at
                break

        if not first_in_progress:
            return ResolutionTimeMetric(
                calculated=False,
                reason="No 'In Progress' status found",
            )

        minutes = self._calculate_duration(
            first_in_progress,
            issue_dates.resolution_date,
            working_hours_only,
            sla_config,
        )

        return ResolutionTimeMetric(
            value_minutes=minutes,
            formatted=self._format_duration(minutes),
            calculated=True,
        )

    def _calculate_first_response_time(
        self,
        issue_dates: IssueDatesResponse,
        working_hours_only: bool,
        sla_config: SLAConfig,
    ) -> FirstResponseTimeMetric:
        """Calculate first response time (created to first transition)."""
        if not issue_dates.created:
            return FirstResponseTimeMetric(calculated=False)

        if not issue_dates.status_changes:
            return FirstResponseTimeMetric(calculated=False)

        # Find first transition (after the initial status)
        first_transition = None
        for i, change in enumerate(issue_dates.status_changes):
            if i > 0:  # Skip the initial status
                first_transition = change.entered_at
                break

        if not first_transition:
            return FirstResponseTimeMetric(calculated=False)

        minutes = self._calculate_duration(
            issue_dates.created,
            first_transition,
            working_hours_only,
            sla_config,
        )

        return FirstResponseTimeMetric(
            value_minutes=minutes,
            formatted=self._format_duration(minutes),
            calculated=True,
            response_type="transition",
        )

    def _calculate_duration(
        self,
        start: datetime,
        end: datetime,
        working_hours_only: bool,
        sla_config: SLAConfig,
    ) -> int:
        """
        Calculate duration in minutes, optionally filtering by working hours.

        Args:
            start: Start datetime
            end: End datetime
            working_hours_only: Whether to only count working hours
            sla_config: SLA configuration with working hours settings

        Returns:
            Duration in minutes
        """
        if not working_hours_only:
            # Simple calendar time calculation
            delta = end - start
            return max(0, int(delta.total_seconds() / 60))

        # Working hours calculation
        return self._calculate_working_minutes(start, end, sla_config)

    def _calculate_working_minutes(
        self,
        start: datetime,
        end: datetime,
        sla_config: SLAConfig,
    ) -> int:
        """
        Calculate working minutes between two timestamps.

        Algorithm:
        1. Convert times to configured timezone
        2. Iterate day by day from start to end
        3. For each day:
           a. Skip if not in working_days
           b. Calculate overlap with working hours
           c. Add to total
        4. Return total working minutes

        Args:
            start: Start datetime
            end: End datetime
            sla_config: SLA configuration

        Returns:
            Working minutes between start and end
        """
        if end <= start:
            return 0

        # Get timezone
        try:
            tz = ZoneInfo(sla_config.timezone)
        except Exception:
            logger.warning(f"Invalid timezone {sla_config.timezone}, using UTC")
            tz = ZoneInfo("UTC")

        # Convert to configured timezone
        start_local = start.astimezone(tz)
        end_local = end.astimezone(tz)

        # Parse working hours
        work_start_parts = sla_config.working_hours_start.split(":")
        work_end_parts = sla_config.working_hours_end.split(":")
        work_start_time = time(int(work_start_parts[0]), int(work_start_parts[1]))
        work_end_time = time(int(work_end_parts[0]), int(work_end_parts[1]))

        working_days = set(sla_config.working_days or [1, 2, 3, 4, 5])

        total_minutes = 0
        current_date = start_local.date()
        end_date = end_local.date()

        while current_date <= end_date:
            # Check if it's a working day (isoweekday: 1=Mon, 7=Sun)
            if current_date.isoweekday() not in working_days:
                current_date += timedelta(days=1)
                continue

            # Calculate day boundaries
            day_start = datetime.combine(current_date, work_start_time, tzinfo=tz)
            day_end = datetime.combine(current_date, work_end_time, tzinfo=tz)

            # Calculate overlap with actual time range
            period_start = max(day_start, start_local)
            period_end = min(day_end, end_local)

            if period_end > period_start:
                minutes = int((period_end - period_start).total_seconds() / 60)
                total_minutes += minutes

            current_date += timedelta(days=1)

        return total_minutes

    def _format_duration(self, minutes: int) -> str:
        """
        Format minutes into human-readable string.

        Examples:
        - 90 -> "1h 30m"
        - 1500 -> "1d 1h 0m"
        - 0 -> "0m"

        Args:
            minutes: Duration in minutes

        Returns:
            Formatted duration string
        """
        if minutes <= 0:
            return "0m"

        days = minutes // (24 * 60)
        remaining = minutes % (24 * 60)
        hours = remaining // 60
        mins = remaining % 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours}h")
        parts.append(f"{mins}m")

        return " ".join(parts)
