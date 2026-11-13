"""Module for Jira worklog operations."""

import logging
import re
from typing import Any

from ..models import JiraWorklog
from ..models.jira.adf import adf_to_text
from ..utils import parse_date
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class WorklogMixin(JiraClient):
    """Mixin for Jira worklog operations."""

    def _build_time_spent_payload(self, time_spent: str) -> dict[str, Any]:
        """
        Build the time spent part of a worklog request body.

        Duration strings such as ``1d 2h`` are sent to Jira as ``timeSpent`` so
        Jira converts them with the instance's time tracking settings (hours per
        day, days per week). Converting them here with fixed 24h days and 7d
        weeks would log ``1d`` as 24h on an instance where a day is 8h.
        Plain seconds (``3600`` or ``3600s``) are sent as ``timeSpentSeconds``.

        Args:
            time_spent: Time spent string (e.g. 1h 30m, 1d, 3600s)

        Returns:
            Dict with either ``timeSpentSeconds`` or ``timeSpent``
        """
        value = time_spent.strip()

        # Base case for direct specification in seconds
        if re.fullmatch(r"\d+s", value):
            return {"timeSpentSeconds": int(value[:-1])}
        try:
            return {"timeSpentSeconds": int(float(value))}
        except ValueError:
            return {"timeSpent": value}

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
            # Convert Markdown comment to Jira format if provided
            if comment:
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
            worklog_data = self._build_time_spent_payload(time_spent)
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
            if isinstance(worklog_data.get("comment"), dict) and self.config.is_cloud:
                result = self._post_api3(
                    f"issue/{issue_key}/worklog",
                    data=worklog_data,
                    params=params or None,
                )
            else:
                base_url = self.jira.resource_url("issue")
                url = f"{base_url}/{issue_key}/worklog"
                result = self.jira.post(url, data=worklog_data, params=params)
            if not isinstance(result, dict):
                msg = f"Unexpected return value type from `jira.post`: {type(result)}"
                logger.error(msg)
                raise TypeError(msg)

            # Format and return the result
            comment_raw = result.get("comment", "")
            comment_text = (
                adf_to_text(comment_raw)
                if isinstance(comment_raw, dict)
                else comment_raw
            )
            return {
                "id": result.get("id"),
                "comment": self._clean_text(comment_text or ""),
                "created": str(parse_date(result.get("created", ""))),
                "updated": str(parse_date(result.get("updated", ""))),
                "started": str(parse_date(result.get("started", ""))),
                "time_spent": result.get("timeSpent", ""),
                "time_spent_seconds": result.get("timeSpentSeconds", 0),
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
            return self.jira.worklog(issue_key)  # type: ignore[attr-defined]
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
            # `jira.issue_get_worklog()` calls GET /issue/{key}/worklog without
            # pagination parameters, so Jira returns at most 20 entries by default.
            # We paginate explicitly to retrieve all worklogs regardless of count.
            base_url = self.jira.resource_url("issue")
            url = f"{base_url}/{issue_key}/worklog"
            page_size = 100
            start_at = 0
            worklogs = []

            while True:
                result = self.jira.get(
                    url, params={"maxResults": page_size, "startAt": start_at}
                )
                if not isinstance(result, dict):
                    msg = (
                        f"Unexpected return value type from worklog API: {type(result)}"
                    )
                    logger.error(msg)
                    raise TypeError(msg)

                page = result.get("worklogs", [])
                for worklog in page:
                    worklogs.append(
                        {
                            "id": worklog.get("id"),
                            "comment": self._clean_text(worklog.get("comment", "")),
                            "created": str(parse_date(worklog.get("created", ""))),
                            "updated": str(parse_date(worklog.get("updated", ""))),
                            "started": str(parse_date(worklog.get("started", ""))),
                            "time_spent": worklog.get("timeSpent", ""),
                            "time_spent_seconds": worklog.get("timeSpentSeconds", 0),
                            "author": worklog.get("author", {}).get(
                                "displayName", "Unknown"
                            ),
                        }
                    )

                start_at += len(page)
                if start_at >= result.get("total", 0) or not page:
                    break

            return worklogs
        except Exception as e:
            logger.error(f"Error getting worklogs for issue {issue_key}: {str(e)}")
            raise Exception(f"Error getting worklogs: {str(e)}") from e
