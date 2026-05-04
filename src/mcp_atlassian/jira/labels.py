"""Module for Jira label operations."""

import logging
from typing import Any

from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class LabelsMixin(JiraClient):
    """Mixin for Jira issue label operations."""

    def get_issue_labels(self, issue_key: str) -> dict[str, Any]:
        """Get labels for a specific issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123').

        Returns:
            Dictionary with issue_key and list of label strings.
        """
        result = self.jira.get_issue(issue_key, fields="labels")
        if not isinstance(result, dict):
            logger.error(
                "Unexpected response type from get_issue for labels: %s",
                type(result),
            )
            return {"issue_key": issue_key, "labels": []}

        labels: list[str] = result.get("fields", {}).get("labels", [])
        return {"issue_key": issue_key, "labels": labels}

    def add_issue_labels(
        self, issue_key: str, labels: list[str]
    ) -> dict[str, Any]:
        """Add labels to an issue without removing existing ones.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123').
            labels: List of label strings to add.

        Returns:
            Dictionary with issue_key, updated labels list, and added labels.
        """
        current = self.get_issue_labels(issue_key)
        existing: set[str] = set(current["labels"])
        added = sorted(set(labels) - existing)
        new_labels = sorted(existing | set(labels))
        self.jira.update_issue(
            issue_key=issue_key, update={"fields": {"labels": new_labels}}
        )
        return {"issue_key": issue_key, "labels": new_labels, "added": added}

    def remove_issue_labels(
        self, issue_key: str, labels: list[str]
    ) -> dict[str, Any]:
        """Remove specific labels from an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123').
            labels: List of label strings to remove.

        Returns:
            Dictionary with issue_key, updated labels list, removed labels,
            and any labels that were not present on the issue.
        """
        current = self.get_issue_labels(issue_key)
        to_remove: set[str] = set(labels)
        existing: set[str] = set(current["labels"])
        not_found = sorted(to_remove - existing)
        removed = sorted(to_remove & existing)
        new_labels = sorted(existing - to_remove)
        self.jira.update_issue(
            issue_key=issue_key, update={"fields": {"labels": new_labels}}
        )
        result: dict[str, Any] = {
            "issue_key": issue_key,
            "labels": new_labels,
            "removed": removed,
        }
        if not_found:
            result["not_found"] = not_found
        return result

    def set_issue_labels(
        self, issue_key: str, labels: list[str]
    ) -> dict[str, Any]:
        """Replace all labels on an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123').
            labels: New list of label strings (replaces existing labels).

        Returns:
            Dictionary with issue_key and updated labels list.
        """
        self.jira.update_issue(
            issue_key=issue_key, update={"fields": {"labels": labels}}
        )
        return {"issue_key": issue_key, "labels": labels}

    def get_available_labels(
        self,
        query: str | None = None,
        start_at: int = 0,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Get available labels from the Jira instance.

        Calls GET /rest/api/2/label with optional prefix filtering.
        Supported on both Jira Cloud and Server/Data Center.

        Args:
            query: Optional prefix string to filter labels by name.
            start_at: Index of the first label to return (for pagination).
            max_results: Maximum number of labels to return.

        Returns:
            Dictionary with labels list, total count, and pagination info.
        """
        params: dict[str, Any] = {
            "startAt": start_at,
            "maxResults": max_results,
        }
        if query:
            params["query"] = query

        result = self.jira.get("label", params=params)
        if not isinstance(result, dict):
            logger.error(
                "Unexpected response type from GET label endpoint: %s",
                type(result),
            )
            return {
                "labels": [],
                "total": 0,
                "start_at": start_at,
                "max_results": max_results,
                "is_last": True,
            }

        values: list[str] = result.get("values", [])
        return {
            "labels": values,
            "total": result.get("total", len(values)),
            "start_at": result.get("startAt", start_at),
            "max_results": result.get("maxResults", max_results),
            "is_last": result.get("isLast", True),
        }
