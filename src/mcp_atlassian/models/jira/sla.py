"""
SLA metric models for Jira issues.

This module provides Pydantic models for SLA calculations including
cycle time, lead time, time in status, and due date compliance.
"""

from typing import Any, Literal

from pydantic import Field

from ..base import ApiModel


class CycleTimeMetric(ApiModel):
    """
    Model representing cycle time metric.

    Cycle time is the duration from issue creation to resolution.
    """

    value_minutes: int | None = Field(
        default=None, description="Cycle time in minutes (None if not resolved)"
    )
    formatted: str | None = Field(
        default=None, description="Human-readable duration (e.g., '5d 2h 30m')"
    )
    calculated: bool = Field(
        default=False, description="Whether the metric could be calculated"
    )
    reason: str | None = Field(
        default=None,
        description="Reason if not calculated (e.g., 'Issue not resolved')",
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "CycleTimeMetric":
        """Create a CycleTimeMetric from data."""
        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "calculated": self.calculated,
        }
        if self.calculated and self.value_minutes is not None:
            result["value_minutes"] = self.value_minutes
            result["formatted"] = self.formatted
        if self.reason:
            result["reason"] = self.reason
        return result


class LeadTimeMetric(ApiModel):
    """
    Model representing lead time metric.

    Lead time is the duration from issue creation to now (or resolution).
    """

    value_minutes: int = Field(description="Lead time in minutes")
    formatted: str = Field(description="Human-readable duration")
    is_resolved: bool = Field(
        default=False, description="Whether the issue is resolved"
    )

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "LeadTimeMetric":
        """Create a LeadTimeMetric from data."""
        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "value_minutes": self.value_minutes,
            "formatted": self.formatted,
            "is_resolved": self.is_resolved,
        }


class TimeInStatusEntry(ApiModel):
    """
    Model representing time spent in a specific status.
    """

    status: str = Field(description="The status name")
    value_minutes: int = Field(description="Time in minutes spent in this status")
    formatted: str = Field(description="Human-readable duration")
    percentage: float = Field(
        default=0.0, description="Percentage of total time spent in this status"
    )
    visit_count: int = Field(
        default=1, description="Number of times the issue was in this status"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "TimeInStatusEntry":
        """Create a TimeInStatusEntry from data."""
        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "status": self.status,
            "value_minutes": self.value_minutes,
            "formatted": self.formatted,
            "percentage": round(self.percentage, 2),
            "visit_count": self.visit_count,
        }


class TimeInStatusMetric(ApiModel):
    """
    Model representing aggregated time in each status.
    """

    statuses: list[TimeInStatusEntry] = Field(
        default_factory=list, description="Time breakdown by status"
    )
    total_minutes: int = Field(default=0, description="Total time across all statuses")

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "TimeInStatusMetric":
        """Create a TimeInStatusMetric from data."""
        statuses = [
            TimeInStatusEntry.from_api_response(s) for s in data.get("statuses", [])
        ]
        return cls(
            statuses=statuses,
            total_minutes=data.get("total_minutes", 0),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "statuses": [s.to_simplified_dict() for s in self.statuses],
            "total_minutes": self.total_minutes,
        }


class DueDateComplianceMetric(ApiModel):
    """
    Model representing due date compliance metric.
    """

    status: Literal["met", "missed", "no_due_date", "not_resolved"] = Field(
        description="Compliance status"
    )
    margin_minutes: int | None = Field(
        default=None, description="Minutes early (positive) or late (negative)"
    )
    formatted_margin: str | None = Field(
        default=None, description="Human-readable margin"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "DueDateComplianceMetric":
        """Create a DueDateComplianceMetric from data."""
        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "status": self.status,
        }
        if self.margin_minutes is not None:
            result["margin_minutes"] = self.margin_minutes
            result["formatted_margin"] = self.formatted_margin
        return result


class ResolutionTimeMetric(ApiModel):
    """
    Model representing resolution time metric.

    Time from first 'In Progress' transition to resolution.
    """

    value_minutes: int | None = Field(
        default=None, description="Resolution time in minutes"
    )
    formatted: str | None = Field(default=None, description="Human-readable duration")
    calculated: bool = Field(
        default=False, description="Whether the metric could be calculated"
    )
    reason: str | None = Field(default=None, description="Reason if not calculated")

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ResolutionTimeMetric":
        """Create a ResolutionTimeMetric from data."""
        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "calculated": self.calculated,
        }
        if self.calculated and self.value_minutes is not None:
            result["value_minutes"] = self.value_minutes
            result["formatted"] = self.formatted
        if self.reason:
            result["reason"] = self.reason
        return result


class FirstResponseTimeMetric(ApiModel):
    """
    Model representing first response time metric.

    Time from creation to first comment or transition.
    """

    value_minutes: int | None = Field(
        default=None, description="First response time in minutes"
    )
    formatted: str | None = Field(default=None, description="Human-readable duration")
    calculated: bool = Field(
        default=False, description="Whether the metric could be calculated"
    )
    response_type: str | None = Field(
        default=None, description="Type of first response (comment/transition)"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "FirstResponseTimeMetric":
        """Create a FirstResponseTimeMetric from data."""
        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "calculated": self.calculated,
        }
        if self.calculated and self.value_minutes is not None:
            result["value_minutes"] = self.value_minutes
            result["formatted"] = self.formatted
            if self.response_type:
                result["response_type"] = self.response_type
        return result


class IssueSLAMetrics(ApiModel):
    """
    Model containing all calculated SLA metrics for an issue.
    """

    cycle_time: CycleTimeMetric | None = Field(
        default=None, description="Cycle time metric"
    )
    lead_time: LeadTimeMetric | None = Field(
        default=None, description="Lead time metric"
    )
    time_in_status: TimeInStatusMetric | None = Field(
        default=None, description="Time in status breakdown"
    )
    due_date_compliance: DueDateComplianceMetric | None = Field(
        default=None, description="Due date compliance metric"
    )
    resolution_time: ResolutionTimeMetric | None = Field(
        default=None, description="Resolution time metric"
    )
    first_response_time: FirstResponseTimeMetric | None = Field(
        default=None, description="First response time metric"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "IssueSLAMetrics":
        """Create an IssueSLAMetrics from data."""
        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
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


class IssueSLAResponse(ApiModel):
    """
    Model representing SLA response for a single issue.
    """

    issue_key: str = Field(description="The Jira issue key")
    metrics: IssueSLAMetrics = Field(description="Calculated SLA metrics")
    raw_dates: dict[str, Any] | None = Field(
        default=None,
        description="Raw date values if requested (includes status_changes list)",
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "IssueSLAResponse":
        """Create an IssueSLAResponse from data."""
        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "issue_key": self.issue_key,
            "metrics": self.metrics.to_simplified_dict(),
        }
        if self.raw_dates:
            result["raw_dates"] = self.raw_dates
        return result


class WorkingHoursConfig(ApiModel):
    """
    Model representing working hours configuration used in calculation.
    """

    start: str = Field(description="Working hours start time")
    end: str = Field(description="Working hours end time")
    days: list[int] = Field(description="Working days (1=Monday)")
    timezone: str = Field(description="Timezone used for calculation")

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "WorkingHoursConfig":
        """Create a WorkingHoursConfig from data."""
        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "start": self.start,
            "end": self.end,
            "days": self.days,
            "timezone": self.timezone,
        }


class IssueSLABatchResponse(ApiModel):
    """
    Model representing batch SLA response for multiple issues.
    """

    issues: list[IssueSLAResponse] = Field(
        default_factory=list, description="List of issue SLA responses"
    )
    total_count: int = Field(default=0, description="Total number of issues processed")
    success_count: int = Field(
        default=0, description="Number of issues successfully processed"
    )
    error_count: int = Field(default=0, description="Number of issues that failed")
    errors: list[dict[str, str]] = Field(
        default_factory=list, description="List of errors for failed issues"
    )
    metrics_calculated: list[str] = Field(
        default_factory=list, description="List of metrics that were calculated"
    )
    working_hours_applied: bool = Field(
        default=False, description="Whether working hours filter was applied"
    )
    working_hours_config: WorkingHoursConfig | None = Field(
        default=None, description="Working hours configuration if applied"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "IssueSLABatchResponse":
        """Create an IssueSLABatchResponse from data."""
        issues = [
            IssueSLAResponse.from_api_response(issue)
            for issue in data.get("issues", [])
        ]
        working_config = None
        if data.get("working_hours_config"):
            working_config = WorkingHoursConfig.from_api_response(
                data["working_hours_config"]
            )
        return cls(
            issues=issues,
            total_count=data.get("total_count", len(issues)),
            success_count=data.get("success_count", len(issues)),
            error_count=data.get("error_count", 0),
            errors=data.get("errors", []),
            metrics_calculated=data.get("metrics_calculated", []),
            working_hours_applied=data.get("working_hours_applied", False),
            working_hours_config=working_config,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "total_count": self.total_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "issues": [issue.to_simplified_dict() for issue in self.issues],
            "metrics_calculated": self.metrics_calculated,
            "working_hours_applied": self.working_hours_applied,
        }
        if self.errors:
            result["errors"] = self.errors
        if self.working_hours_config:
            result["working_hours_config"] = (
                self.working_hours_config.to_simplified_dict()
            )
        return result
