"""Module for Jira watcher operations."""

import logging
from typing import Any

from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class WatchersMixin(JiraClient):
    """Mixin for Jira watcher operations."""

    def get_issue_watchers(self, issue_key: str) -> dict[str, Any]:
        """
        Get watchers for a specific issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            Dictionary with watcher count and list of watchers

        Raises:
            Exception: If there is an error getting watchers
        """
        try:
            result = self.jira.issue_get_watchers(issue_key)

            if not isinstance(result, dict):
                msg = f"Unexpected return value type from `jira.issue_get_watchers`: {type(result)}"
                logger.error(msg)
                raise TypeError(msg)

            # Process the watchers list
            watchers = []
            for watcher in result.get("watchers", []):
                processed_watcher = {
                    "account_id": watcher.get("accountId"),
                    "display_name": watcher.get("displayName", "Unknown"),
                    "email": watcher.get("emailAddress"),
                    "active": watcher.get("active", True),
                }
                watchers.append(processed_watcher)

            return {
                "issue_key": issue_key,
                "watcher_count": result.get("watchCount", len(watchers)),
                "is_watching": result.get("isWatching", False),
                "watchers": watchers,
            }
        except Exception as e:
            logger.error(f"Error getting watchers for issue {issue_key}: {str(e)}")
            raise Exception(f"Error getting watchers: {str(e)}") from e

    def add_watcher(self, issue_key: str, user_identifier: str) -> dict[str, Any]:
        """
        Add a user as a watcher to an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            user_identifier: The user to add as watcher. For Jira Cloud, this should be
                           the account ID. For Jira Server/DC, this should be the username.

        Returns:
            Success confirmation

        Raises:
            Exception: If there is an error adding the watcher
        """
        try:
            # The atlassian library's issue_add_watcher expects the user parameter
            self.jira.issue_add_watcher(issue_key, user_identifier)

            return {
                "success": True,
                "message": f"User '{user_identifier}' added as watcher to {issue_key}",
                "issue_key": issue_key,
                "user": user_identifier,
            }
        except Exception as e:
            logger.error(
                f"Error adding watcher '{user_identifier}' to issue {issue_key}: {str(e)}"
            )
            raise Exception(f"Error adding watcher: {str(e)}") from e

    def remove_watcher(
        self,
        issue_key: str,
        username: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Remove a user from watching an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            username: The username to remove (for Jira Server/DC)
            account_id: The account ID to remove (for Jira Cloud)

        Returns:
            Success confirmation

        Raises:
            ValueError: If neither username nor account_id is provided
            Exception: If there is an error removing the watcher
        """
        if not username and not account_id:
            raise ValueError("Either username or account_id must be provided")

        try:
            self.jira.issue_delete_watcher(
                issue_key, user=username, account_id=account_id
            )

            user_display = account_id or username
            return {
                "success": True,
                "message": f"User '{user_display}' removed from watching {issue_key}",
                "issue_key": issue_key,
                "user": user_display,
            }
        except Exception as e:
            user_display = account_id or username
            logger.error(
                f"Error removing watcher '{user_display}' from issue {issue_key}: {str(e)}"
            )
            raise Exception(f"Error removing watcher: {str(e)}") from e
