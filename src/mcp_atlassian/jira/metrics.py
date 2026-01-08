"""Module for Jira issue metrics and date operations."""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from ..models.jira.common import JiraChangelog
from ..models.jira.metrics import (
    IssueDatesBatchResponse,
    IssueDatesResponse,
    StatusChangeEntry,
    StatusTimeSummary,
)
from ..utils import parse_date
from .client import JiraClient
from .protocols import IssueOperationsProto

logger = logging.getLogger("mcp-jira")


class MetricsMixin(JiraClient, IssueOperationsProto):
    """Mixin for Jira issue metrics and date operations."""

    def get_issue_dates(
        self,
        issue_key: str,
        include_created: bool = True,
        include_updated: bool = True,
        include_due_date: bool = True,
        include_resolution_date: bool = True,
        include_status_changes: bool = True,
        include_status_summary: bool = True,
    ) -> IssueDatesResponse:
        """
        Get raw date information for a single Jira issue.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)
            include_created: Include the created date
            include_updated: Include the updated date
            include_due_date: Include the due date
            include_resolution_date: Include the resolution date
            include_status_changes: Include status change history
            include_status_summary: Include aggregated time per status

        Returns:
            IssueDatesResponse with the requested date information

        Raises:
            ValueError: If the issue cannot be found
            Exception: If there is an error retrieving the issue
        """
        try:
            # Build fields list based on what we need
            fields_needed = ["status"]
            if include_created:
                fields_needed.append("created")
            if include_updated:
                fields_needed.append("updated")
            if include_due_date:
                fields_needed.append("duedate")
            if include_resolution_date:
                fields_needed.append("resolutiondate")

            # Get issue with changelog if status changes are needed
            expand = None
            if include_status_changes or include_status_summary:
                expand = "changelog"

            issue = self.jira.get_issue(
                issue_key,
                expand=expand,
                fields=",".join(fields_needed),
            )

            if not issue:
                raise ValueError(f"Issue {issue_key} not found")
            if not isinstance(issue, dict):
                raise TypeError(f"Unexpected return type: {type(issue)}")

            fields = issue.get("fields", {}) or {}

            # Parse dates
            created = None
            updated = None
            due_date = None
            resolution_date = None
            current_status = None

            if include_created and "created" in fields:
                created = parse_date(fields["created"])

            if include_updated and "updated" in fields:
                updated = parse_date(fields["updated"])

            if include_due_date and "duedate" in fields and fields["duedate"]:
                due_date = parse_date(fields["duedate"])

            if include_resolution_date and "resolutiondate" in fields:
                if fields["resolutiondate"]:
                    resolution_date = parse_date(fields["resolutiondate"])

            # Get current status
            status_field = fields.get("status", {})
            if status_field:
                current_status = status_field.get("name")

            # Parse changelog for status changes
            status_changes: list[StatusChangeEntry] = []
            status_summary: list[StatusTimeSummary] = []

            if include_status_changes or include_status_summary:
                changelog_data = issue.get("changelog", {})
                if changelog_data:
                    histories = changelog_data.get("histories", [])
                    changelogs = [JiraChangelog.from_api_response(h) for h in histories]

                    if include_status_changes:
                        status_changes = self._parse_changelog_to_status_changes(
                            issue_key, changelogs, created
                        )

                    if include_status_summary:
                        status_summary = self._aggregate_status_times(status_changes)

            return IssueDatesResponse(
                issue_key=issue_key,
                created=created,
                updated=updated,
                due_date=due_date,
                resolution_date=resolution_date,
                current_status=current_status,
                status_changes=status_changes,
                status_summary=status_summary,
            )

        except Exception as e:
            logger.error(f"Error getting dates for issue {issue_key}: {str(e)}")
            raise

    def batch_get_issue_dates(
        self,
        issue_keys: list[str],
        include_created: bool = True,
        include_updated: bool = True,
        include_due_date: bool = True,
        include_resolution_date: bool = True,
        include_status_changes: bool = True,
        include_status_summary: bool = True,
    ) -> IssueDatesBatchResponse:
        """
        Get raw date information for multiple Jira issues.

        Args:
            issue_keys: List of issue keys (e.g., ['PROJECT-123', 'PROJECT-456'])
            include_created: Include the created date
            include_updated: Include the updated date
            include_due_date: Include the due date
            include_resolution_date: Include the resolution date
            include_status_changes: Include status change history
            include_status_summary: Include aggregated time per status

        Returns:
            IssueDatesBatchResponse with results for all issues
        """
        issues: list[IssueDatesResponse] = []
        errors: list[dict[str, str]] = []

        for issue_key in issue_keys:
            try:
                issue_dates = self.get_issue_dates(
                    issue_key=issue_key,
                    include_created=include_created,
                    include_updated=include_updated,
                    include_due_date=include_due_date,
                    include_resolution_date=include_resolution_date,
                    include_status_changes=include_status_changes,
                    include_status_summary=include_status_summary,
                )
                issues.append(issue_dates)
            except Exception as e:
                logger.warning(f"Error getting dates for {issue_key}: {str(e)}")
                errors.append(
                    {
                        "issue_key": issue_key,
                        "error": str(e),
                    }
                )

        return IssueDatesBatchResponse(
            issues=issues,
            total_count=len(issue_keys),
            success_count=len(issues),
            error_count=len(errors),
            errors=errors,
        )

    def _parse_changelog_to_status_changes(
        self,
        issue_key: str,
        changelogs: list[JiraChangelog],
        created_date: datetime | None,
    ) -> list[StatusChangeEntry]:
        """
        Parse changelog to extract status transitions.

        Algorithm:
        1. Filter changelog items where field == "status"
        2. Sort by timestamp ascending
        3. For each status change, record:
           - status name (to_string)
           - entered_at (changelog.created)
           - exited_at (next changelog.created or None if current)
           - transitioned_by (changelog.author)
        4. Calculate duration_minutes for each entry

        Args:
            issue_key: The issue key for logging
            changelogs: List of JiraChangelog objects
            created_date: The issue creation date (for initial status)

        Returns:
            List of StatusChangeEntry objects in chronological order
        """
        # Collect all status changes from changelog
        status_transitions: list[dict[str, Any]] = []

        for changelog in changelogs:
            if not changelog.created:
                continue

            for item in changelog.items:
                if item.field.lower() == "status":
                    author_name = None
                    if changelog.author:
                        author_name = changelog.author.display_name

                    status_transitions.append(
                        {
                            "from_status": item.from_string,
                            "to_status": item.to_string,
                            "timestamp": changelog.created,
                            "transitioned_by": author_name,
                        }
                    )

        # Sort by timestamp ascending
        status_transitions.sort(key=lambda x: x["timestamp"])

        # Build status change entries
        entries: list[StatusChangeEntry] = []

        # Add initial status if we have a created date and status transitions
        if created_date and status_transitions:
            first_transition = status_transitions[0]
            initial_status = first_transition.get("from_status")
            if initial_status:
                first_timestamp = first_transition["timestamp"]
                duration_minutes = self._calculate_duration_minutes(
                    created_date, first_timestamp
                )
                entries.append(
                    StatusChangeEntry(
                        status=initial_status,
                        entered_at=created_date,
                        exited_at=first_timestamp,
                        duration_minutes=duration_minutes,
                        duration_formatted=self._format_duration(duration_minutes),
                        transitioned_by=None,  # Created by, not transitioned
                    )
                )

        # Process each status transition
        for i, transition in enumerate(status_transitions):
            to_status = transition.get("to_status")
            if not to_status:
                continue

            entered_at = transition["timestamp"]

            # Determine exit time (next transition or None if current)
            exited_at = None
            if i + 1 < len(status_transitions):
                exited_at = status_transitions[i + 1]["timestamp"]

            # Calculate duration
            duration_minutes = None
            duration_formatted = None
            if exited_at:
                duration_minutes = self._calculate_duration_minutes(
                    entered_at, exited_at
                )
                duration_formatted = self._format_duration(duration_minutes)

            entries.append(
                StatusChangeEntry(
                    status=to_status,
                    entered_at=entered_at,
                    exited_at=exited_at,
                    duration_minutes=duration_minutes,
                    duration_formatted=duration_formatted,
                    transitioned_by=transition.get("transitioned_by"),
                )
            )

        return entries

    def _aggregate_status_times(
        self,
        status_changes: list[StatusChangeEntry],
    ) -> list[StatusTimeSummary]:
        """
        Aggregate time spent in each status across all visits.

        Args:
            status_changes: List of StatusChangeEntry objects

        Returns:
            List of StatusTimeSummary objects, one per unique status
        """
        # Aggregate by status name
        status_times: defaultdict[str, dict[str, int]] = defaultdict(
            lambda: {"total_minutes": 0, "visit_count": 0}
        )

        for entry in status_changes:
            if entry.duration_minutes is not None:
                status_times[entry.status]["total_minutes"] += entry.duration_minutes
                status_times[entry.status]["visit_count"] += 1
            elif entry.exited_at is None:
                # Current status - count the visit but don't add duration
                status_times[entry.status]["visit_count"] += 1

        # Build summary list
        summaries: list[StatusTimeSummary] = []
        for status_name, data in status_times.items():
            summaries.append(
                StatusTimeSummary(
                    status=status_name,
                    total_duration_minutes=data["total_minutes"],
                    total_duration_formatted=self._format_duration(
                        data["total_minutes"]
                    ),
                    visit_count=data["visit_count"],
                )
            )

        # Sort by total duration descending
        summaries.sort(key=lambda x: x.total_duration_minutes, reverse=True)

        return summaries

    def _calculate_duration_minutes(
        self,
        start: datetime,
        end: datetime,
    ) -> int:
        """
        Calculate duration in minutes between two timestamps.

        Args:
            start: Start datetime
            end: End datetime

        Returns:
            Duration in minutes (rounded)
        """
        delta = end - start
        return int(delta.total_seconds() / 60)

    def _format_duration(self, minutes: int) -> str:
        """
        Format minutes into human-readable string.

        Examples:
        - 90 -> "1h 30m"
        - 1500 -> "1d 1h 0m"
        - 0 -> "0m"

        Rules:
        - 1 day = 24 hours (calendar time)
        - 1 hour = 60 minutes
        - Always show minutes
        - Omit days/hours if zero (except "0m")

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
        if hours > 0 or days > 0:  # Show hours if days are shown
            parts.append(f"{hours}h")
        parts.append(f"{mins}m")

        return " ".join(parts)
