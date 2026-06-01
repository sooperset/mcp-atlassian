"""Module for Jira sprint velocity and team performance analytics."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class VelocityMixin(JiraClient):
    """Mixin for Jira sprint velocity and team performance analytics."""

    def _get_story_points_field_id(self, board_id: str) -> str | None:
        """Get the story points custom field id configured for a board."""
        try:
            response = self.jira.get(
                path=f"rest/agile/1.0/board/{board_id}/configuration"
            )
            if not isinstance(response, dict):
                return None

            estimation = response.get("estimation")
            if not isinstance(estimation, dict):
                return None

            field = estimation.get("field")
            if not isinstance(field, dict):
                return None

            field_id = field.get("fieldId") or field.get("id")
            if not isinstance(field_id, str):
                return None

            if not field_id.startswith("customfield_"):
                return None

            return field_id
        except (HTTPError, ValueError, TypeError, KeyError) as error:
            logger.error(
                "Error retrieving board estimation field for board %s: %s",
                board_id,
                error,
            )
            return None

    def _get_sprint_details(self, sprint_id: str) -> dict[str, Any]:
        """Get sprint details by sprint id."""
        response = self.jira.get(path=f"rest/agile/1.0/sprint/{sprint_id}")
        if not isinstance(response, dict):
            return {}
        return response

    def _get_sprint_issues_raw(
        self,
        sprint_id: str,
        fields: list[str],
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch all issues for a sprint using Agile API pagination."""
        all_issues: list[dict[str, Any]] = []
        start_at = 0

        while True:
            response = self.jira.get(
                path=f"rest/agile/1.0/sprint/{sprint_id}/issue",
                params={
                    "startAt": start_at,
                    "maxResults": page_size,
                    "fields": ",".join(fields),
                },
            )
            if not isinstance(response, dict):
                break

            issues = response.get("issues", [])
            if not isinstance(issues, list):
                break

            valid_issues = [issue for issue in issues if isinstance(issue, dict)]
            all_issues.extend(valid_issues)

            if not issues:
                break

            is_last = response.get("isLast")
            total = response.get("total")
            start_at += len(issues)

            if is_last is True:
                break

            if isinstance(total, int) and start_at >= total:
                break

        return all_issues

    def _extract_story_points(self, issue: dict[str, Any], field_id: str) -> float:
        """Extract numeric story points from a Jira issue."""
        fields = issue.get("fields", {})
        if not isinstance(fields, dict):
            return 0.0

        raw_points = fields.get(field_id)
        if isinstance(raw_points, int | float):
            return float(raw_points)

        if isinstance(raw_points, str):
            try:
                return float(raw_points)
            except ValueError:
                return 0.0

        return 0.0

    def _is_completed_issue(self, issue: dict[str, Any]) -> bool:
        """Determine whether an issue is in a done status category."""
        fields = issue.get("fields", {})
        if not isinstance(fields, dict):
            return False

        status = fields.get("status")
        if not isinstance(status, dict):
            return False

        status_category = status.get("statusCategory")
        if not isinstance(status_category, dict):
            return False

        key = str(status_category.get("key", "")).lower()
        name = str(status_category.get("name", "")).lower()
        return key == "done" or name == "done"

    def get_sprint_velocity(self, board_id: str, sprint_id: str) -> dict[str, Any]:
        """Calculate committed vs completed story points for a sprint."""
        story_points_field = self._get_story_points_field_id(board_id)
        if not story_points_field:
            raise ValueError(
                "Could not determine Story Points field from board configuration."
            )

        sprint = self._get_sprint_details(sprint_id)
        issues = self._get_sprint_issues_raw(
            sprint_id=sprint_id,
            fields=["summary", "status", "assignee", story_points_field],
        )

        committed_points = 0.0
        completed_points = 0.0
        assignee_stats: dict[str, dict[str, float | int]] = {}

        for issue in issues:
            points = self._extract_story_points(issue, story_points_field)
            committed_points += points

            fields = issue.get("fields", {})
            if not isinstance(fields, dict):
                fields = {}

            assignee = fields.get("assignee")
            assignee_name = "Unassigned"
            if isinstance(assignee, dict):
                assignee_name = str(
                    assignee.get("displayName") or assignee.get("name") or "Unassigned"
                )

            if assignee_name not in assignee_stats:
                assignee_stats[assignee_name] = {
                    "issue_count": 0,
                    "committed_points": 0.0,
                    "completed_points": 0.0,
                }

            assignee_stats[assignee_name]["issue_count"] += 1
            assignee_stats[assignee_name]["committed_points"] += points

            if self._is_completed_issue(issue):
                completed_points += points
                assignee_stats[assignee_name]["completed_points"] += points

        completion_rate = (
            round((completed_points / committed_points) * 100, 2)
            if committed_points > 0
            else 0.0
        )

        per_assignee = [
            {
                "assignee": name,
                "issue_count": stats["issue_count"],
                "committed_points": round(float(stats["committed_points"]), 2),
                "completed_points": round(float(stats["completed_points"]), 2),
            }
            for name, stats in sorted(assignee_stats.items())
        ]

        return {
            "board_id": board_id,
            "sprint_id": sprint_id,
            "sprint_name": str(sprint.get("name", "")),
            "sprint_state": str(sprint.get("state", "")),
            "start_date": sprint.get("startDate"),
            "end_date": sprint.get("endDate"),
            "story_points_field": story_points_field,
            "issue_count": len(issues),
            "committed_points": round(committed_points, 2),
            "completed_points": round(completed_points, 2),
            "completion_rate": completion_rate,
            "per_assignee": per_assignee,
        }

    def _calculate_velocity_trend(self, sprint_data: list[dict[str, Any]]) -> str:
        """Calculate high-level velocity trend from first to last sprint."""
        if len(sprint_data) < 2:
            return "insufficient_data"

        first = float(sprint_data[0].get("completed_points", 0.0))
        last = float(sprint_data[-1].get("completed_points", 0.0))

        if first == 0 and last == 0:
            return "stable"
        if first == 0 and last > 0:
            return "increasing"

        delta_pct = ((last - first) / first) * 100
        if delta_pct > 5:
            return "increasing"
        if delta_pct < -5:
            return "decreasing"
        return "stable"

    def get_velocity_report(
        self,
        board_id: str,
        num_sprints: int = 3,
    ) -> dict[str, Any]:
        """Get velocity report for the latest closed sprints on a board."""
        if num_sprints < 1:
            raise ValueError("num_sprints must be at least 1")

        raw_sprints = self.get_all_sprints_from_board(
            board_id=board_id,
            state="closed",
            start=0,
            limit=max(50, num_sprints),
        )

        sorted_sprints = sorted(
            raw_sprints,
            key=lambda sprint: (
                str(sprint.get("completeDate", "")),
                str(sprint.get("endDate", "")),
                str(sprint.get("startDate", "")),
            ),
            reverse=True,
        )
        selected_sprints = list(reversed(sorted_sprints[:num_sprints]))

        report_rows = [
            self.get_sprint_velocity(board_id=board_id, sprint_id=str(sprint["id"]))
            for sprint in selected_sprints
            if isinstance(sprint, dict) and sprint.get("id") is not None
        ]

        if report_rows:
            avg_completed = round(
                sum(float(row.get("completed_points", 0.0)) for row in report_rows)
                / len(report_rows),
                2,
            )
            avg_completion_rate = round(
                sum(float(row.get("completion_rate", 0.0)) for row in report_rows)
                / len(report_rows),
                2,
            )
        else:
            avg_completed = 0.0
            avg_completion_rate = 0.0

        trend = self._calculate_velocity_trend(report_rows)

        return {
            "board_id": board_id,
            "num_sprints_requested": num_sprints,
            "num_sprints_analyzed": len(report_rows),
            "average_completed_points": avg_completed,
            "average_completion_rate": avg_completion_rate,
            "velocity_trend": trend,
            "sprints": report_rows,
        }

    def get_team_sprint_summary(
        self,
        board_id: str,
        num_sprints: int = 3,
    ) -> dict[str, Any]:
        """Get aggregated team performance summary for the latest sprints."""
        velocity_report = self.get_velocity_report(
            board_id=board_id,
            num_sprints=num_sprints,
        )

        assignee_totals: dict[str, dict[str, float | int]] = {}
        for sprint in velocity_report.get("sprints", []):
            assignees = sprint.get("per_assignee", [])
            if not isinstance(assignees, list):
                continue

            for assignee_data in assignees:
                if not isinstance(assignee_data, dict):
                    continue

                assignee = str(assignee_data.get("assignee", "Unassigned"))
                if assignee not in assignee_totals:
                    assignee_totals[assignee] = {
                        "issue_count": 0,
                        "committed_points": 0.0,
                        "completed_points": 0.0,
                    }

                assignee_totals[assignee]["issue_count"] += int(
                    assignee_data.get("issue_count", 0)
                )
                assignee_totals[assignee]["committed_points"] += float(
                    assignee_data.get("committed_points", 0.0)
                )
                assignee_totals[assignee]["completed_points"] += float(
                    assignee_data.get("completed_points", 0.0)
                )

        per_assignee = [
            {
                "assignee": name,
                "issue_count": int(values["issue_count"]),
                "committed_points": round(float(values["committed_points"]), 2),
                "completed_points": round(float(values["completed_points"]), 2),
            }
            for name, values in assignee_totals.items()
        ]
        per_assignee.sort(key=lambda value: value["completed_points"], reverse=True)

        return {
            "board_id": board_id,
            "num_sprints": velocity_report.get("num_sprints_analyzed", 0),
            "velocity": {
                "average_completed_points": velocity_report.get(
                    "average_completed_points", 0.0
                ),
                "average_completion_rate": velocity_report.get(
                    "average_completion_rate", 0.0
                ),
                "trend": velocity_report.get("velocity_trend", "insufficient_data"),
            },
            "per_assignee": per_assignee,
            "sprints": velocity_report.get("sprints", []),
        }
