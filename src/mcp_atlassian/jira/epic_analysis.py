"""Module for Jira epic analysis operations."""

import logging
from collections import Counter
from typing import Any

from requests.exceptions import HTTPError

from ..utils.decorators import handle_auth_errors
from .client import JiraClient

logger = logging.getLogger("mcp-jira")

_LOCALIZED_EPIC_NAMES: set[str] = {"에픽", "エピック"}


def _is_epic_type(type_name: str) -> bool:
    """Check whether an issue type name refers to an Epic.

    Handles the English name (case-insensitive) and known
    localized names used by Jira in non-English locales.
    """
    return "epic" in type_name.lower() or type_name in _LOCALIZED_EPIC_NAMES


class EpicAnalysisMixin(JiraClient):
    """Mixin for Jira epic summary and analysis."""

    @handle_auth_errors("Jira API")
    def get_epic_summary(
        self,
        epic_key: str,
        include_children: bool = True,
        max_children: int = 200,
    ) -> dict[str, Any]:
        """Summarise an epic: metadata, child counts, and aggregations.

        Fetches the epic issue and its children, then groups the children
        by status, assignee, and issue type with a completion percentage.

        Args:
            epic_key: The key of the epic issue (e.g. ``PROJ-123``).
            include_children: When *True* the individual child issue list
                is included in the response.
            max_children: Upper bound on the number of children fetched.

        Returns:
            Dict with ``epic`` metadata, ``summary`` aggregations, and
            optionally ``children`` list.

        Raises:
            ValueError: If the issue is not an Epic.
            MCPAtlassianAuthenticationError: If authentication fails.
            Exception: On API or query errors.
        """
        epic_issue = self.get_issue(epic_key)  # type: ignore[attr-defined]

        type_name = ""
        if epic_issue.issue_type:
            type_name = epic_issue.issue_type.name
        if not _is_epic_type(type_name):
            raise ValueError(
                f"{epic_key} is a {type_name or 'unknown type'}, not an Epic"
            )

        epic_info: dict[str, Any] = {
            "key": epic_issue.key,
            "summary": epic_issue.summary,
            "status": (epic_issue.status.name if epic_issue.status else None),
            "assignee": (
                epic_issue.assignee.display_name
                if epic_issue.assignee
                else "Unassigned"
            ),
        }

        children = self._fetch_epic_children(epic_key, max_children)

        by_status: Counter[str] = Counter()
        by_assignee: Counter[str] = Counter()
        by_type: Counter[str] = Counter()
        done_count = 0

        children_output: list[dict[str, Any]] = []

        for child in children:
            status_name = "Unknown"
            if child.status:
                status_name = child.status.name
                if child.status.category and child.status.category.key == "done":
                    done_count += 1
            by_status[status_name] += 1

            assignee_name = "Unassigned"
            if child.assignee:
                assignee_name = child.assignee.display_name
            by_assignee[assignee_name] += 1

            type_label = "Unknown"
            if child.issue_type:
                type_label = child.issue_type.name
            by_type[type_label] += 1

            if include_children:
                children_output.append(
                    {
                        "key": child.key,
                        "summary": child.summary,
                        "status": status_name,
                        "assignee": assignee_name,
                        "issue_type": type_label,
                    }
                )

        total = len(children)
        completion = round(done_count / total * 100, 1) if total else 0.0

        return {
            "epic": epic_info,
            "summary": {
                "total_children": total,
                "by_status": dict(by_status),
                "by_assignee": dict(by_assignee),
                "by_type": dict(by_type),
                "completion_percentage": completion,
            },
            "children": children_output,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_epic_children(
        self,
        epic_key: str,
        max_children: int,
    ) -> list:
        """Fetch children of an epic using the full fallback chain.

        Delegates to ``EpicsMixin.get_epic_issues`` which tries 6
        strategies (issuesScopedToEpic, parent field, discovered
        custom fields, Epic Link name, issue links, common field
        IDs) so this works across Cloud, Server/DC, and instances
        with non-standard epic field configurations.

        On Server/DC, ``search_issues`` caps each response at 50.
        Cloud paginates internally so the first call returns up to
        ``max_children``.  On Server/DC we page with ``start``
        until we have enough or a page comes back short.

        Args:
            epic_key: The epic's issue key.
            max_children: Maximum children to return.

        Returns:
            List of JiraIssue objects.
        """
        try:
            page_size = 50
            issues = self.get_epic_issues(  # type: ignore[attr-defined]
                epic_key, start=0, limit=max_children
            )

            if not self.config.is_cloud:
                while len(issues) < max_children and len(issues) % page_size == 0:
                    if not issues:
                        break
                    page = self.get_epic_issues(  # type: ignore[attr-defined]
                        epic_key, start=len(issues), limit=page_size
                    )
                    if not page:
                        break
                    issues.extend(page)

            return issues[:max_children]
        except (ValueError, HTTPError):
            raise
        except Exception:
            logger.warning("Failed to fetch children for epic %s", epic_key)
            return []
