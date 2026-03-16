"""Module for Confluence content property operations."""

import logging
from typing import Any

from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class PropertiesMixin(ConfluenceClient):
    """Mixin for Confluence content property operations."""

    def get_content_properties(
        self, page_id: str, key: str | None = None
    ) -> dict[str, Any]:
        """Get content properties for a Confluence page.

        Args:
            page_id: The ID of the page.
            key: Optional property key. If provided, returns only that property.
                If omitted, returns all properties as a ``{key: value}`` dict.

        Returns:
            Dict mapping property key(s) to their values.

        Raises:
            Exception: If the API request fails.
        """
        try:
            base_url = self.confluence.url.rstrip("/")
            if key:
                url = f"{base_url}/rest/api/content/{page_id}/property/{key}"
                response = self.confluence._session.get(url)
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return {data["key"]: data["value"]}
            else:
                url = f"{base_url}/rest/api/content/{page_id}/property"
                response = self.confluence._session.get(
                    url, params={"expand": "version"}
                )
                response.raise_for_status()
                data = response.json()
                return {item["key"]: item["value"] for item in data.get("results", [])}
        except Exception as e:
            logger.error(f"Failed to get content properties for page {page_id}: {e}")
            raise Exception(
                f"Failed to get content properties for page {page_id}: {e}"
            ) from e

    def set_content_property(
        self, page_id: str, key: str, value: Any
    ) -> dict[str, Any]:
        """Create or update a content property on a Confluence page.

        Handles version increment automatically. Reads the current version before
        writing, so callers do not need to manage version numbers.

        If the property does not exist it is created (POST). If it already exists
        it is updated (PUT) with ``version.number`` incremented by one.

        Args:
            page_id: The ID of the page.
            key: Property key (e.g. ``content-appearance-published``).
            value: Property value. Strings are passed as-is; dicts/lists are
                serialised as JSON objects by the REST API.

        Returns:
            Dict with ``{key: value}`` of the created or updated property.

        Raises:
            Exception: If the API request fails.
        """
        try:
            base_url = self.confluence.url.rstrip("/")
            get_url = f"{base_url}/rest/api/content/{page_id}/property/{key}"
            get_response = self.confluence._session.get(get_url)

            if get_response.status_code == 404:
                # Property does not exist — create it
                post_url = f"{base_url}/rest/api/content/{page_id}/property"
                body: dict[str, Any] = {"key": key, "value": value}
                result_response = self.confluence._session.post(post_url, json=body)
                result_response.raise_for_status()
            else:
                get_response.raise_for_status()
                current: dict[str, Any] = get_response.json()
                version_number = current.get("version", {}).get("number", 0) + 1
                body = {
                    "key": key,
                    "value": value,
                    "version": {"number": version_number},
                }
                put_url = f"{base_url}/rest/api/content/{page_id}/property/{key}"
                result_response = self.confluence._session.put(put_url, json=body)
                result_response.raise_for_status()

            result: dict[str, Any] = result_response.json()
            return {result["key"]: result["value"]}

        except Exception as e:
            logger.error(
                f"Failed to set content property '{key}' on page {page_id}: {e}"
            )
            raise Exception(
                f"Failed to set content property '{key}' on page {page_id}: {e}"
            ) from e
