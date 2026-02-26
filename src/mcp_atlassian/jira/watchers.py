"""Module for Jira watcher operations."""

import logging
from typing import Any

from ..models.jira.common import JiraUser
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class WatchersMixin(JiraClient):
    """Mixin for Jira issue watcher operations."""

    def get_issue_watchers(self, issue_key: str) -> dict[str, Any]:
        """Get watchers for a specific issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123').

        Returns:
            Dictionary with watcher count, is_watching flag,
            and list of watchers.
        """
        result = self.jira.issue_get_watchers(issue_key)

        if not isinstance(result, dict):
            logger.error(
                "Unexpected response type from issue_get_watchers: %s",
                type(result),
            )
            return {
                "issue_key": issue_key,
                "watcher_count": 0,
                "is_watching": False,
                "watchers": [],
            }

        watchers = []
        for watcher_data in result.get("watchers", []):
            user = JiraUser.from_api_response(watcher_data)
            watchers.append(user.to_simplified_dict())

        return {
            "issue_key": issue_key,
            "watcher_count": result.get("watchCount", len(watchers)),
            "is_watching": result.get("isWatching", False),
            "watchers": watchers,
        }

    def add_watcher(self, issue_key: str, user_identifier: str) -> dict[str, Any]:
        """Add a user as a watcher to an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123').
            user_identifier: Account ID (Cloud) or username (Server/DC).

        Returns:
            Success confirmation dictionary.
        """
        self.jira.issue_add_watcher(issue_key, user_identifier)
        return {
            "success": True,
            "message": (f"User '{user_identifier}' added as watcher to {issue_key}"),
            "issue_key": issue_key,
            "user": user_identifier,
        }

    def remove_watcher(
        self,
        issue_key: str,
        username: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """Remove a user from watching an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123').
            username: Username to remove (Server/DC).
            account_id: Account ID to remove (Cloud).

        Returns:
            Success confirmation dictionary.

        Raises:
            ValueError: If neither username nor account_id is provided.
        """
        if not username and not account_id:
            raise ValueError("Either username or account_id must be provided")

        user_display = account_id or username
        self.jira.issue_delete_watcher(issue_key, user=username, account_id=account_id)
        return {
            "success": True,
            "message": (f"User '{user_display}' removed from watching {issue_key}"),
            "issue_key": issue_key,
            "user": user_display,
        }
