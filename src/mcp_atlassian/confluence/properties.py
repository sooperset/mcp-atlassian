"""Module for Confluence content property operations."""

from typing import Any
from urllib.parse import quote

from ..utils.decorators import handle_auth_errors
from .client import ConfluenceClient


class PropertiesMixin(ConfluenceClient):
    """Mixin for Confluence content property operations."""

    def _content_property_url(self, page_id: str, key: str | None = None) -> str:
        """Build a v1 content-property URL for all supported auth modes."""
        encoded_page_id = quote(page_id, safe="")
        url = f"{self._v1_rest_base_url()}/rest/api/content/{encoded_page_id}/property"
        if key is not None:
            url = f"{url}/{quote(key, safe='')}"
        return url

    @handle_auth_errors("Confluence API")
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
            HTTPError: If the API request fails.
            ValueError: If Confluence returns an unexpected response shape.
        """
        if key is not None:
            data = self.confluence.get(
                self._content_property_url(page_id, key),
                absolute=True,
            )
            if not isinstance(data, dict) or "key" not in data or "value" not in data:
                raise ValueError("Confluence returned an invalid content property")
            return {str(data["key"]): data["value"]}

        data = self.confluence.get(
            self._content_property_url(page_id),
            params={"expand": "version", "limit": 200},
            absolute=True,
        )
        if not isinstance(data, dict):
            raise ValueError("Confluence returned an invalid content property list")

        results = data.get("results", [])
        if not isinstance(results, list):
            raise ValueError("Confluence returned an invalid content property list")
        return {
            str(item["key"]): item["value"]
            for item in results
            if isinstance(item, dict) and "key" in item and "value" in item
        }

    @handle_auth_errors("Confluence API")
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
            HTTPError: If the API request fails.
            ValueError: If Confluence returns an unexpected response shape.
        """
        property_url = self._content_property_url(page_id, key)
        current_response = self.confluence.get(
            property_url,
            absolute=True,
            advanced_mode=True,
        )
        body: dict[str, Any] = {"key": key, "value": value}

        if current_response.status_code == 404:
            result = self.confluence.post(
                self._content_property_url(page_id),
                data=body,
                absolute=True,
            )
        else:
            current_response.raise_for_status()
            current = current_response.json()
            if not isinstance(current, dict):
                raise ValueError("Confluence returned an invalid content property")
            version = current.get("version", {})
            version_number = (
                version.get("number", 0) if isinstance(version, dict) else 0
            )
            body["version"] = {"number": version_number + 1}
            result = self.confluence.put(
                property_url,
                data=body,
                absolute=True,
            )

        if not isinstance(result, dict) or "key" not in result or "value" not in result:
            raise ValueError("Confluence returned an invalid content property")
        return {str(result["key"]): result["value"]}
