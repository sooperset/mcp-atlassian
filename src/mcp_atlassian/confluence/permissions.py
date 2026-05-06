"""Module for Confluence permission operations."""

import logging
from typing import Any, cast

from requests.exceptions import HTTPError

from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class PermissionsMixin(ConfluenceClient):
    """Mixin for Confluence permission operations."""

    def check_content_permissions(
        self,
        content_id: str,
        user_identifier: str,
        operation: str,
        target_type: str = "page",
        subject_type: str = "user",
    ) -> dict[str, Any]:
        """Check whether a user or group has a specific permission on content.

        Wraps POST /wiki/rest/api/content/{id}/permission/check.

        Args:
            content_id: The ID of the page, blog post, or other content.
            user_identifier: Account ID (for users) or group name (for groups).
            operation: The operation to check, e.g. "read", "update", "delete".
            target_type: The content type being checked, e.g. "page", "blogpost",
                "comment", "attachment". Defaults to "page".
            subject_type: Whether the subject is a "user" or "group".
                Defaults to "user".

        Returns:
            Dictionary with a "hasPermission" boolean key.

        Raises:
            ValueError: If the API call fails or returns an unexpected response.
            HTTPError: If authentication fails (401/403 are propagated).
        """
        url = (
            f"{self.confluence.url}/rest/api/content/{content_id}/permission/check"
        )
        body = {
            "operation": {
                "operation": operation,
                "targetType": target_type,
            },
            "subject": {
                "type": subject_type,
                "identifier": user_identifier,
            },
        }
        try:
            response = self.confluence._session.post(url, json=body)
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403):
                raise
            logger.error(
                f"HTTP error checking content permissions for '{content_id}': {e}"
            )
            msg = f"Failed to check permissions for content '{content_id}': {e}"
            raise ValueError(msg) from e
        except Exception as e:
            logger.error(
                f"Error checking content permissions for '{content_id}': {e}"
            )
            msg = f"Failed to check permissions for content '{content_id}': {e}"
            raise ValueError(msg) from e

    def get_space_permissions(
        self,
        space_id: str,
        limit: int = 25,
    ) -> dict[str, Any]:
        """List all permission assignments for a Confluence space.

        Wraps GET /wiki/api/v2/spaces/{id}/permissions.

        Args:
            space_id: The numeric ID of the space.
            limit: Maximum number of permission entries to return. Defaults to 25.

        Returns:
            Dictionary with a "results" list of permission assignment objects,
            each containing "id", "principal", and "operation" fields.

        Raises:
            ValueError: If the API call fails or returns an unexpected response.
            HTTPError: If authentication fails (401/403 are propagated).
        """
        url = f"{self.confluence.url}/api/v2/spaces/{space_id}/permissions"
        params: dict[str, Any] = {"limit": limit}
        try:
            response = self.confluence._session.get(url, params=params)
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403):
                raise
            logger.error(
                f"HTTP error fetching space permissions for space '{space_id}': {e}"
            )
            msg = f"Failed to get permissions for space '{space_id}': {e}"
            raise ValueError(msg) from e
        except Exception as e:
            logger.error(
                f"Error fetching space permissions for space '{space_id}': {e}"
            )
            msg = f"Failed to get permissions for space '{space_id}': {e}"
            raise ValueError(msg) from e
