"""Jira watcher management."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from ..exceptions import MCPAtlassianAuthenticationError
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class WatchersMixin(JiraClient):
    """Mixin for Jira watcher operations."""

    def add_watcher(self, issue_key: str, user: str) -> dict[str, Any]:
        """
        Add a watcher to a Jira issue.

        Args:
            issue_key: The key of the issue (e.g., 'PROJ-123')
            user: The username or account ID to add as a watcher

        Returns:
            Dictionary with the result of the operation

        Raises:
            ValueError: If required fields are missing
            MCPAtlassianAuthenticationError: If authentication fails with the Jira API (401/403)
            Exception: If there is an error adding the watcher
        """
        # Validate required fields
        if not issue_key:
            raise ValueError("Issue key is required")
        if not user:
            raise ValueError("User is required")

        try:
            # Add the watcher using the Jira API
            endpoint = f"rest/api/3/issue/{issue_key}/watchers"
            self.jira.post(endpoint, json=user)

            # Return a response indicating success
            response = {
                "success": True,
                "message": f"Watcher '{user}' added to issue {issue_key}",
                "issue_key": issue_key,
                "user": user,
            }

            return response

        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code in [
                401,
                403,
            ]:
                error_msg = (
                    f"Authentication failed for Jira API "
                    f"({http_err.response.status_code}). "
                    "Token may be expired or invalid. Please verify credentials."
                )
                logger.error(error_msg)
                raise MCPAtlassianAuthenticationError(error_msg) from http_err
            else:
                logger.error(f"HTTP error during API call: {http_err}", exc_info=True)
                raise Exception(f"Error adding watcher: {http_err}") from http_err
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error adding watcher: {error_msg}", exc_info=True)
            raise Exception(f"Error adding watcher: {error_msg}") from e

    def remove_watcher(self, issue_key: str, user: str) -> dict[str, Any]:
        """
        Remove a watcher from a Jira issue.

        Args:
            issue_key: The key of the issue (e.g., 'PROJ-123')
            user: The username or account ID to remove as a watcher

        Returns:
            Dictionary with the result of the operation

        Raises:
            ValueError: If required fields are missing
            MCPAtlassianAuthenticationError: If authentication fails with the Jira API (401/403)
            Exception: If there is an error removing the watcher
        """
        # Validate required fields
        if not issue_key:
            raise ValueError("Issue key is required")
        if not user:
            raise ValueError("User is required")

        try:
            # Remove the watcher using the Jira API
            endpoint = f"rest/api/3/issue/{issue_key}/watchers"
            params = {"username": user} if not self.config.is_cloud else {"accountId": user}
            self.jira.delete(endpoint, params=params)

            # Return a response indicating success
            response = {
                "success": True,
                "message": f"Watcher '{user}' removed from issue {issue_key}",
                "issue_key": issue_key,
                "user": user,
            }

            return response

        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code in [
                401,
                403,
            ]:
                error_msg = (
                    f"Authentication failed for Jira API "
                    f"({http_err.response.status_code}). "
                    "Token may be expired or invalid. Please verify credentials."
                )
                logger.error(error_msg)
                raise MCPAtlassianAuthenticationError(error_msg) from http_err
            else:
                logger.error(f"HTTP error during API call: {http_err}", exc_info=True)
                raise Exception(f"Error removing watcher: {http_err}") from http_err
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error removing watcher: {error_msg}", exc_info=True)
            raise Exception(f"Error removing watcher: {error_msg}") from e 