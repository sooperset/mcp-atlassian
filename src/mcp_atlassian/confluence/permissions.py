"""Module for Confluence permission operations."""

import logging
from typing import Any, cast

from requests.exceptions import HTTPError

from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class PermissionsMixin(ConfluenceClient):
    """Mixin for Confluence permission operations."""

    def _require_cloud_permissions_api(self) -> None:
        """Ensure the Cloud permissions APIs are available."""
        if not self.config.is_cloud:
            msg = (
                "Confluence permission inspection is only available for "
                "Confluence Cloud. Server/Data Center instances use different "
                "permission APIs."
            )
            raise ValueError(msg)

    def _permissions_rest_base_url(self) -> str:
        """Return the REST base URL for Cloud permission endpoints."""
        if self.config.auth_type == "oauth" and self.config.is_cloud:
            return str(self.confluence.url).rstrip("/")

        base_url = self.config.url.rstrip("/")
        if self.config.is_cloud and not base_url.endswith("/wiki"):
            base_url = f"{base_url}/wiki"
        return base_url

    def check_content_permissions(
        self,
        content_id: str,
        user_identifier: str,
        operation: str,
        subject_type: str = "user",
    ) -> dict[str, Any]:
        """Check whether a user or group has a specific permission on content.

        Wraps POST /wiki/rest/api/content/{id}/permission/check.

        Args:
            content_id: The ID of the page, blog post, or other content.
            user_identifier: Account ID (for users) or group ID (for groups).
            operation: The operation to check, e.g. "read", "update", "delete".
            subject_type: Whether the subject is a "user" or "group".
                Defaults to "user".

        Returns:
            Dictionary with a "hasPermission" boolean key.

        Raises:
            ValueError: If the API call fails or returns an unexpected response.
            HTTPError: If authentication fails (401/403 are propagated).
        """
        self._require_cloud_permissions_api()
        url = (
            f"{self._permissions_rest_base_url()}"
            f"/rest/api/content/{content_id}/permission/check"
        )
        body = {
            "operation": operation,
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
            logger.error(f"Error checking content permissions for '{content_id}': {e}")
            msg = f"Failed to check permissions for content '{content_id}': {e}"
            raise ValueError(msg) from e

    def get_space_permissions(
        self,
        space_id: str,
        limit: int = 25,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List all permission assignments for a Confluence space.

        Wraps GET /wiki/api/v2/spaces/{id}/permissions.

        Args:
            space_id: The numeric ID of the space.
            limit: Maximum number of permission entries to return. Defaults to 25.
            cursor: Optional pagination cursor from a previous response.

        Returns:
            Dictionary with a "results" list of permission assignment objects,
            each containing "id", "principal", and "operation" fields.

        Raises:
            ValueError: If the API call fails or returns an unexpected response.
            HTTPError: If authentication fails (401/403 are propagated).
        """
        self._require_cloud_permissions_api()
        url = (
            f"{self._permissions_rest_base_url()}/api/v2/spaces/{space_id}/permissions"
        )
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
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
