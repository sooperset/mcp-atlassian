"""Module for Jira status operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from ..utils.decorators import handle_auth_errors
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class StatusesMixin(JiraClient):
    """Mixin for Jira status operations."""

    @handle_auth_errors("Jira API")
    def get_statuses(self, name_filter: str | None = None) -> list[dict[str, Any]]:
        """Get all statuses available in Jira.

        Args:
            name_filter: Optional case-insensitive substring to filter status names.

        Returns:
            A list of statuses with their id, name, description, and category.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails
                with the Jira API (401/403).
            Exception: If retrieving statuses fails.
        """
        try:
            response: object = self.jira.get(
                self.jira.resource_url("status", api_version="2")
            )
            if not isinstance(response, list):
                return []

            statuses: list[dict[str, Any]] = []
            for status in response:
                if not isinstance(status, dict):
                    continue

                status_name = status.get("name", "")
                if (
                    name_filter
                    and name_filter.casefold() not in str(status_name).casefold()
                ):
                    continue

                category = status.get("statusCategory")
                if not isinstance(category, dict):
                    category = {}

                statuses.append(
                    {
                        "id": status.get("id", ""),
                        "name": status_name,
                        "description": status.get("description"),
                        "statusCategory": {
                            "id": category.get("id", ""),
                            "name": category.get("name", ""),
                        },
                    }
                )
            return statuses
        except HTTPError:
            raise
        except Exception as e:
            error_msg = f"Error getting statuses: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
