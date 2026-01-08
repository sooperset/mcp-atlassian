"""
Metrics data models for Jira issue dates and status changes.

This module provides Pydantic models for issue date information,
status change history, and aggregated time tracking data.
"""

from datetime import datetime
from typing import Any

from pydantic import Field

from ..base import ApiModel


class StatusChangeEntry(ApiModel):
    """
    Model representing a single status transition for an issue.

    Tracks when an issue entered and exited a specific status,
    including duration spent in that status.
    """

    status: str = Field(description="The name of the status")
    entered_at: datetime = Field(description="When the issue entered this status")
    exited_at: datetime | None = Field(
        default=None,
        description="When the issue exited this status (None if current status)",
    )
    duration_minutes: int | None = Field(
        default=None, description="Total minutes spent in this status"
    )
    duration_formatted: str | None = Field(
        default=None, description="Human-readable duration (e.g., '2d 3h 15m')"
    )
    transitioned_by: str | None = Field(
        default=None, description="Display name of the user who made the transition"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "StatusChangeEntry":
        """Create a StatusChangeEntry from data."""
        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "status": self.status,
            "entered_at": self.entered_at.isoformat(),
        }
        if self.exited_at:
            result["exited_at"] = self.exited_at.isoformat()
        if self.duration_minutes is not None:
            result["duration_minutes"] = self.duration_minutes
        if self.duration_formatted:
            result["duration_formatted"] = self.duration_formatted
        if self.transitioned_by:
            result["transitioned_by"] = self.transitioned_by
        return result


class StatusTimeSummary(ApiModel):
    """
    Model representing aggregated time spent in a specific status.

    Used to provide a summary of total time an issue has spent
    in each status across all transitions.
    """

    status: str = Field(description="The name of the status")
    total_duration_minutes: int = Field(
        description="Total minutes spent in this status across all visits"
    )
    total_duration_formatted: str = Field(description="Human-readable total duration")
    visit_count: int = Field(
        default=1, description="Number of times the issue was in this status"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "StatusTimeSummary":
        """Create a StatusTimeSummary from data."""
        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "status": self.status,
            "total_duration_minutes": self.total_duration_minutes,
            "total_duration_formatted": self.total_duration_formatted,
            "visit_count": self.visit_count,
        }


class IssueDatesResponse(ApiModel):
    """
    Model representing raw date information for a single issue.

    This is the response model for the jira_get_issue_dates tool,
    providing both core dates and optional status change history.
    """

    issue_key: str = Field(description="The Jira issue key (e.g., 'PROJ-123')")
    created: datetime | None = Field(
        default=None, description="When the issue was created"
    )
    updated: datetime | None = Field(
        default=None, description="When the issue was last updated"
    )
    due_date: datetime | None = Field(
        default=None, description="The due date for the issue"
    )
    resolution_date: datetime | None = Field(
        default=None, description="When the issue was resolved"
    )
    current_status: str | None = Field(
        default=None, description="The current status of the issue"
    )
    status_changes: list[StatusChangeEntry] = Field(
        default_factory=list, description="History of status transitions"
    )
    status_summary: list[StatusTimeSummary] = Field(
        default_factory=list, description="Aggregated time spent in each status"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "IssueDatesResponse":
        """Create an IssueDatesResponse from data."""
        status_changes = [
            StatusChangeEntry.from_api_response(sc)
            for sc in data.get("status_changes", [])
        ]
        status_summary = [
            StatusTimeSummary.from_api_response(ss)
            for ss in data.get("status_summary", [])
        ]
        return cls(
            issue_key=data["issue_key"],
            created=data.get("created"),
            updated=data.get("updated"),
            due_date=data.get("due_date"),
            resolution_date=data.get("resolution_date"),
            current_status=data.get("current_status"),
            status_changes=status_changes,
            status_summary=status_summary,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "issue_key": self.issue_key,
        }

        if self.created:
            result["created"] = self.created.isoformat()
        if self.updated:
            result["updated"] = self.updated.isoformat()
        if self.due_date:
            result["due_date"] = self.due_date.isoformat()
        if self.resolution_date:
            result["resolution_date"] = self.resolution_date.isoformat()
        if self.current_status:
            result["current_status"] = self.current_status

        if self.status_changes:
            result["status_changes"] = [
                sc.to_simplified_dict() for sc in self.status_changes
            ]
        if self.status_summary:
            result["status_summary"] = [
                ss.to_simplified_dict() for ss in self.status_summary
            ]

        return result


class IssueDatesBatchResponse(ApiModel):
    """
    Model representing batch response for multiple issues.

    Wraps multiple IssueDatesResponse objects with metadata
    about the batch operation.
    """

    issues: list[IssueDatesResponse] = Field(
        default_factory=list, description="List of issue date responses"
    )
    total_count: int = Field(default=0, description="Total number of issues processed")
    success_count: int = Field(
        default=0, description="Number of issues successfully processed"
    )
    error_count: int = Field(
        default=0, description="Number of issues that failed to process"
    )
    errors: list[dict[str, str]] = Field(
        default_factory=list, description="List of errors for failed issues"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "IssueDatesBatchResponse":
        """Create an IssueDatesBatchResponse from data."""
        issues = [
            IssueDatesResponse.from_api_response(issue)
            for issue in data.get("issues", [])
        ]
        return cls(
            issues=issues,
            total_count=data.get("total_count", len(issues)),
            success_count=data.get("success_count", len(issues)),
            error_count=data.get("error_count", 0),
            errors=data.get("errors", []),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "total_count": self.total_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "issues": [issue.to_simplified_dict() for issue in self.issues],
        }
        if self.errors:
            result["errors"] = self.errors
        return result
