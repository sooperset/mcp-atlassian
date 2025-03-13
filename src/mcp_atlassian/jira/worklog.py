"""Module for Jira worklog operations."""

import logging
import re
from typing import Any

from ..models import JiraWorklog
from .client import JiraClient
from .utils import parse_date_ymd

logger = logging.getLogger("mcp-jira")


class WorklogMixin(JiraClient):
    """Mixin for Jira worklog operations."""

    def _parse_time_spent(self, time_spent: str) -> int:
        """
        Parse time spent string into seconds.

        Args:
            time_spent: Time spent string (e.g. 1h 30m, 1d, etc.)

        Returns:
            Time spent in seconds
        """
        # Base case for direct specification in seconds
        if time_spent.endswith("s"):
            try:
                return int(time_spent[:-1])
            except ValueError:
                pass

        total_seconds = 0
        time_units = {
            "w": 7 * 24 * 60 * 60,  # weeks to seconds
            "d": 24 * 60 * 60,  # days to seconds
            "h": 60 * 60,  # hours to seconds
            "m": 60,  # minutes to seconds
        }

        # Regular expression to find time components like 1w, 2d, 3h, 4m
        pattern = r"(\d+)([wdhm])"
        matches = re.findall(pattern, time_spent)

        for value, unit in matches:
            # Convert value to int and multiply by the unit in seconds
            seconds = int(value) * time_units[unit]
            total_seconds += seconds

        if total_seconds == 0:
            # If we couldn't parse anything, try using the raw value
            try:
                return int(float(time_spent))  # Convert to float first, then to int
            except ValueError:
                # If all else fails, default to 60 seconds (1 minute)
                logger.warning(
                    f"Could not parse time: {time_spent}, defaulting to 60 seconds"
                )
                return 60

        return total_seconds

    def add_worklog(
        self,
        issue_key: str,
        time_spent: str,
        comment: str | None = None,
        started: str | None = None,
        original_estimate: str | None = None,
        remaining_estimate: str | None = None,
    ) -> dict[str, Any]:
        """
        Add a worklog entry to a Jira issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            time_spent: Time spent (e.g. '1h 30m', '3h', '1d')
            comment: Optional comment for the worklog
            started: Optional ISO8601 date time string for when work began
            original_estimate: Optional new value for the original estimate
            remaining_estimate: Optional new value for the remaining estimate

        Returns:
            Response data if successful

        Raises:
            Exception: If there's an error adding the worklog
        """
        try:
            # Convert time_spent string to seconds
            time_spent_seconds = self._parse_time_spent(time_spent)

            # Convert Markdown comment to Jira format if provided
            if comment:
                # Check if _markdown_to_jira is available (from CommentsMixin)
                if hasattr(self, "_markdown_to_jira"):
                    comment = self._markdown_to_jira(comment)

            # Step 1: Update original estimate if provided (separate API call)
            original_estimate_updated = False
            if original_estimate:
                try:
                    fields = {"timetracking": {"originalEstimate": original_estimate}}
                    self.jira.edit_issue(issue_id_or_key=issue_key, fields=fields)
                    original_estimate_updated = True
                    logger.info(f"Updated original estimate for issue {issue_key}")
                except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
                    logger.error(
                        f"Failed to update original estimate for issue {issue_key}: "
                        f"{str(e)}"
                    )
                    # Continue with worklog creation even if estimate update fails

            # Step 2: Prepare worklog data
            worklog_data = {"timeSpentSeconds": time_spent_seconds}
            if comment:
                worklog_data["comment"] = comment
            if started:
                worklog_data["started"] = started

            # Step 3: Prepare query parameters for remaining estimate
            params = {}
            remaining_estimate_updated = False
            if remaining_estimate:
                params["adjustEstimate"] = "new"
                params["newEstimate"] = remaining_estimate
                remaining_estimate_updated = True

            # Step 4: Add the worklog with remaining estimate adjustment
            base_url = self.jira.resource_url("issue")
            url = f"{base_url}/{issue_key}/worklog"
            result = self.jira.post(url, data=worklog_data, params=params)

            # Format and return the result
            return {
                "id": result.get("id"),
                "comment": self._clean_text(result.get("comment", "")),
                "created": self._parse_date(result.get("created", "")),
                "updated": self._parse_date(result.get("updated", "")),
                "started": self._parse_date(result.get("started", "")),
                "timeSpent": result.get("timeSpent", ""),
                "timeSpentSeconds": result.get("timeSpentSeconds", 0),
                "author": result.get("author", {}).get("displayName", "Unknown"),
                "original_estimate_updated": original_estimate_updated,
                "remaining_estimate_updated": remaining_estimate_updated,
            }
        except Exception as e:
            logger.error(f"Error adding worklog to issue {issue_key}: {str(e)}")
            raise Exception(f"Error adding worklog: {str(e)}") from e

    def get_worklog(self, issue_key: str) -> dict[str, Any]:
        """
        Get the worklog data for an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            Raw worklog data from the API
        """
        try:
            return self.jira.worklog(issue_key)
        except Exception as e:
            logger.warning(f"Error getting worklog for {issue_key}: {e}")
            return {"worklogs": []}

    def get_worklog_models(self, issue_key: str) -> list[JiraWorklog]:
        """
        Get all worklog entries for an issue as JiraWorklog models.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of JiraWorklog models
        """
        worklog_data = self.get_worklog(issue_key)
        result: list[JiraWorklog] = []

        if "worklogs" in worklog_data and worklog_data["worklogs"]:
            for log_data in worklog_data["worklogs"]:
                worklog = JiraWorklog.from_api_response(log_data)
                result.append(worklog)

        return result

    def get_worklogs(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all worklog entries for an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of worklog entries

        Raises:
            Exception: If there's an error getting the worklogs
        """
        try:
            result = self.jira.issue_get_worklog(issue_key)

            # Process the worklogs
            worklogs = []
            for worklog in result.get("worklogs", []):
                worklogs.append(
                    {
                        "id": worklog.get("id"),
                        "comment": self._clean_text(worklog.get("comment", "")),
                        "created": self._parse_date(worklog.get("created", "")),
                        "updated": self._parse_date(worklog.get("updated", "")),
                        "started": self._parse_date(worklog.get("started", "")),
                        "timeSpent": worklog.get("timeSpent", ""),
                        "timeSpentSeconds": worklog.get("timeSpentSeconds", 0),
                        "author": worklog.get("author", {}).get(
                            "displayName", "Unknown"
                        ),
                    }
                )

            return worklogs
        except Exception as e:
            logger.error(f"Error getting worklogs for issue {issue_key}: {str(e)}")
            raise Exception(f"Error getting worklogs: {str(e)}") from e

    def _parse_date(self, date_str: str | None) -> str:
        """
        Parse a date string from ISO format to a more readable format.

        Args:
            date_str: Date string in ISO format or None

        Returns:
            Formatted date string or empty string if date_str is None
        """
        # Use the common utility function for consistent formatting
        return parse_date_ymd(date_str)
