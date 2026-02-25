"""Models for Jira SLA calculations."""

from typing import Any

from pydantic import BaseModel


class WorkingHoursConfig(BaseModel):
    """Configuration for working hours."""

    start: str  # Start time in HH:MM format
    end: str  # End time in HH:MM format
    days: list[int]  # Working days (1=Mon, 7=Sun)
    timezone: str  # IANA timezone


class CycleTimeMetric(BaseModel):
    """Cycle time metric (created to resolved)."""

    value_minutes: int | None = None
    formatted: str | None = None
    calculated: bool = False
    reason: str | None = None

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        result: dict[str, Any] = {"calculated": self.calculated}
        if self.calculated and self.value_minutes is not None:
            result["value_minutes"] = self.value_minutes
            result["formatted"] = self.formatted
        if self.reason:
            result["reason"] = self.reason
        return result


class LeadTimeMetric(BaseModel):
    """Lead time metric (created to now or resolved)."""

    value_minutes: int
    formatted: str
    is_resolved: bool = False

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        return {
            "value_minutes": self.value_minutes,
            "formatted": self.formatted,
            "is_resolved": self.is_resolved,
        }


class TimeInStatusEntry(BaseModel):
    """Time spent in a single status."""

    status: str
    value_minutes: int
    formatted: str
    percentage: float
    visit_count: int

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        return {
            "status": self.status,
            "value_minutes": self.value_minutes,
            "formatted": self.formatted,
            "percentage": round(self.percentage, 2),
            "visit_count": self.visit_count,
        }


class TimeInStatusMetric(BaseModel):
    """Time in status breakdown."""

    statuses: list[TimeInStatusEntry]
    total_minutes: int

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        return {
            "statuses": [s.to_simplified_dict() for s in self.statuses],
            "total_minutes": self.total_minutes,
        }


class DueDateComplianceMetric(BaseModel):
    """Due date compliance metric."""

    status: str  # "met", "missed", "no_due_date", "not_resolved"
    margin_minutes: int | None = None
    formatted_margin: str | None = None

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        result: dict[str, Any] = {"status": self.status}
        if self.margin_minutes is not None:
            result["margin_minutes"] = self.margin_minutes
            result["formatted_margin"] = self.formatted_margin
        return result


class ResolutionTimeMetric(BaseModel):
    """Resolution time metric (first in progress to resolved)."""

    value_minutes: int | None = None
    formatted: str | None = None
    calculated: bool = False
    reason: str | None = None

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        result: dict[str, Any] = {"calculated": self.calculated}
        if self.calculated and self.value_minutes is not None:
            result["value_minutes"] = self.value_minutes
            result["formatted"] = self.formatted
        if self.reason:
            result["reason"] = self.reason
        return result


class FirstResponseTimeMetric(BaseModel):
    """First response time metric."""

    value_minutes: int | None = None
    formatted: str | None = None
    calculated: bool = False
    response_type: str | None = None  # "transition", "comment", etc.

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        result: dict[str, Any] = {"calculated": self.calculated}
        if self.calculated and self.value_minutes is not None:
            result["value_minutes"] = self.value_minutes
            result["formatted"] = self.formatted
            if self.response_type:
                result["response_type"] = self.response_type
        return result


class IssueSLAMetrics(BaseModel):
    """Container for all SLA metrics."""

    cycle_time: CycleTimeMetric | None = None
    lead_time: LeadTimeMetric | None = None
    time_in_status: TimeInStatusMetric | None = None
    due_date_compliance: DueDateComplianceMetric | None = None
    resolution_time: ResolutionTimeMetric | None = None
    first_response_time: FirstResponseTimeMetric | None = None

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        result: dict[str, Any] = {}
        if self.cycle_time:
            result["cycle_time"] = self.cycle_time.to_simplified_dict()
        if self.lead_time:
            result["lead_time"] = self.lead_time.to_simplified_dict()
        if self.time_in_status:
            result["time_in_status"] = self.time_in_status.to_simplified_dict()
        if self.due_date_compliance:
            result["due_date_compliance"] = (
                self.due_date_compliance.to_simplified_dict()
            )
        if self.resolution_time:
            result["resolution_time"] = self.resolution_time.to_simplified_dict()
        if self.first_response_time:
            result["first_response_time"] = (
                self.first_response_time.to_simplified_dict()
            )
        return result


class IssueSLAResponse(BaseModel):
    """Response containing SLA metrics for a single issue."""

    issue_key: str
    metrics: IssueSLAMetrics
    raw_dates: dict[str, Any] | None = None

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        result: dict[str, Any] = {
            "issue_key": self.issue_key,
            "metrics": self.metrics.to_simplified_dict(),
        }
        if self.raw_dates:
            result["raw_dates"] = self.raw_dates
        return result


class IssueSLABatchResponse(BaseModel):
    """Response containing SLA metrics for multiple issues."""

    issues: list[IssueSLAResponse]
    total_count: int
    success_count: int
    error_count: int
    errors: list[dict[str, str]]
    metrics_calculated: list[str]
    working_hours_applied: bool
    working_hours_config: WorkingHoursConfig | None = None

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        result: dict[str, Any] = {
            "issues": [i.to_simplified_dict() for i in self.issues],
            "total_count": self.total_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "metrics_calculated": self.metrics_calculated,
            "working_hours_applied": self.working_hours_applied,
        }
        if self.errors:
            result["errors"] = self.errors
        if self.working_hours_config:
            result["working_hours_config"] = {
                "start": self.working_hours_config.start,
                "end": self.working_hours_config.end,
                "days": self.working_hours_config.days,
                "timezone": self.working_hours_config.timezone,
            }
        return result
