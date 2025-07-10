"""Confluence REST API v2 adapter for OAuth authentication.

This module provides direct v2 API calls to handle the deprecated v1 endpoints
when using OAuth authentication. The v1 endpoints have been removed for OAuth
but still work for API token authentication.
"""

import logging
from typing import Any

import requests
from requests.exceptions import HTTPError

logger = logging.getLogger("mcp-atlassian")


class ConfluenceV2Adapter:
    """Adapter for Confluence REST API v2 operations when using OAuth."""

    def __init__(self, session: requests.Session, base_url: str) -> None:
        """Initialize the v2 adapter.

        Args:
            session: Authenticated requests session (OAuth configured)
            base_url: Base URL for the Confluence instance
        """
        self.session = session
        self.base_url = base_url

    def _get_space_id(self, space_key: str) -> str:
        """Get space ID from space key using v2 API.

        Args:
            space_key: The space key to look up

        Returns:
            The space ID

        Raises:
            ValueError: If space not found or API error
        """
        try:
            # Use v2 spaces endpoint to get space ID
            url = f"{self.base_url}/api/v2/spaces"
            params = {"keys": space_key}

            response = self.session.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if not results:
                raise ValueError(f"Space with key '{space_key}' not found")

            space_id = results[0].get("id")
            if not space_id:
                raise ValueError(f"No ID found for space '{space_key}'")

            return space_id

        except HTTPError as e:
            logger.error(f"HTTP error getting space ID for '{space_key}': {e}")
            raise ValueError(f"Failed to get space ID for '{space_key}': {e}") from e
        except Exception as e:
            logger.error(f"Error getting space ID for '{space_key}': {e}")
            raise ValueError(f"Failed to get space ID for '{space_key}': {e}") from e

    def create_page(
        self,
        space_key: str,
        title: str,
        body: str,
        parent_id: str | None = None,
        representation: str = "storage",
        status: str = "current",
    ) -> dict[str, Any]:
        """Create a page using the v2 API.

        Args:
            space_key: The key of the space to create the page in
            title: The title of the page
            body: The content body in the specified representation
            parent_id: Optional parent page ID
            representation: Content representation format (default: "storage")
            status: Page status (default: "current")

        Returns:
            The created page data from the API response

        Raises:
            ValueError: If page creation fails
        """
        try:
            # Get space ID from space key
            space_id = self._get_space_id(space_key)

            # Prepare request data for v2 API
            data = {
                "spaceId": space_id,
                "status": status,
                "title": title,
                "body": {
                    "representation": representation,
                    "value": body,
                },
            }

            # Add parent if specified
            if parent_id:
                data["parentId"] = parent_id

            # Make the v2 API call
            url = f"{self.base_url}/api/v2/pages"
            response = self.session.post(url, json=data)
            response.raise_for_status()

            result = response.json()
            logger.debug(f"Successfully created page '{title}' with v2 API")

            # Convert v2 response to v1-compatible format for consistency
            return self._convert_v2_to_v1_format(result, space_key)

        except HTTPError as e:
            logger.error(f"HTTP error creating page '{title}': {e}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise ValueError(f"Failed to create page '{title}': {e}") from e
        except Exception as e:
            logger.error(f"Error creating page '{title}': {e}")
            raise ValueError(f"Failed to create page '{title}': {e}") from e

    def _get_page_version(self, page_id: str) -> int:
        """Get the current version number of a page.

        Args:
            page_id: The ID of the page

        Returns:
            The current version number

        Raises:
            ValueError: If page not found or API error
        """
        try:
            url = f"{self.base_url}/api/v2/pages/{page_id}"
            params = {"body-format": "storage"}

            response = self.session.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            version_number = data.get("version", {}).get("number")

            if version_number is None:
                raise ValueError(f"No version number found for page '{page_id}'")

            return version_number

        except HTTPError as e:
            logger.error(f"HTTP error getting page version for '{page_id}': {e}")
            raise ValueError(f"Failed to get page version for '{page_id}': {e}") from e
        except Exception as e:
            logger.error(f"Error getting page version for '{page_id}': {e}")
            raise ValueError(f"Failed to get page version for '{page_id}': {e}") from e

    def update_page(
        self,
        page_id: str,
        title: str,
        body: str,
        representation: str = "storage",
        version_comment: str = "",
        status: str = "current",
    ) -> dict[str, Any]:
        """Update a page using the v2 API.

        Args:
            page_id: The ID of the page to update
            title: The new title of the page
            body: The new content body in the specified representation
            representation: Content representation format (default: "storage")
            version_comment: Optional comment for this version
            status: Page status (default: "current")

        Returns:
            The updated page data from the API response

        Raises:
            ValueError: If page update fails
        """
        try:
            # Get current version and increment it
            current_version = self._get_page_version(page_id)
            new_version = current_version + 1

            # Prepare request data for v2 API
            data = {
                "id": page_id,
                "status": status,
                "title": title,
                "body": {
                    "representation": representation,
                    "value": body,
                },
                "version": {
                    "number": new_version,
                },
            }

            # Add version comment if provided
            if version_comment:
                data["version"]["message"] = version_comment

            # Make the v2 API call
            url = f"{self.base_url}/api/v2/pages/{page_id}"
            response = self.session.put(url, json=data)
            response.raise_for_status()

            result = response.json()
            logger.debug(f"Successfully updated page '{title}' with v2 API")

            # Convert v2 response to v1-compatible format for consistency
            # For update, we need to extract space key from the result
            space_id = result.get("spaceId")
            space_key = self._get_space_key_from_id(space_id) if space_id else "unknown"

            return self._convert_v2_to_v1_format(result, space_key)

        except HTTPError as e:
            logger.error(f"HTTP error updating page '{page_id}': {e}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise ValueError(f"Failed to update page '{page_id}': {e}") from e
        except Exception as e:
            logger.error(f"Error updating page '{page_id}': {e}")
            raise ValueError(f"Failed to update page '{page_id}': {e}") from e

    def _get_space_key_from_id(self, space_id: str) -> str:
        """Get space key from space ID using v2 API.

        Args:
            space_id: The space ID to look up

        Returns:
            The space key

        Raises:
            ValueError: If space not found or API error
        """
        try:
            # Use v2 spaces endpoint to get space key
            url = f"{self.base_url}/api/v2/spaces/{space_id}"

            response = self.session.get(url)
            response.raise_for_status()

            data = response.json()
            space_key = data.get("key")

            if not space_key:
                raise ValueError(f"No key found for space ID '{space_id}'")

            return space_key

        except HTTPError as e:
            logger.error(f"HTTP error getting space key for ID '{space_id}': {e}")
            # Return the space_id as fallback
            return space_id
        except Exception as e:
            logger.error(f"Error getting space key for ID '{space_id}': {e}")
            # Return the space_id as fallback
            return space_id

    def get_page(
        self,
        page_id: str,
        expand: str | None = None,
    ) -> dict[str, Any]:
        """Get a page using the v2 API.

        Args:
            page_id: The ID of the page to retrieve
            expand: Fields to expand in the response (not used in v2 API, for compatibility only)

        Returns:
            The page data from the API response in v1-compatible format

        Raises:
            ValueError: If page retrieval fails
        """
        try:
            # Make the v2 API call to get the page
            url = f"{self.base_url}/api/v2/pages/{page_id}"

            # Convert v1 expand parameters to v2 format
            params = {"body-format": "storage"}

            response = self.session.get(url, params=params)
            response.raise_for_status()

            v2_response = response.json()
            logger.debug(f"Successfully retrieved page '{page_id}' with v2 API")

            # Get space key from space ID
            space_id = v2_response.get("spaceId")
            space_key = self._get_space_key_from_id(space_id) if space_id else "unknown"

            # Convert v2 response to v1-compatible format
            v1_compatible = self._convert_v2_to_v1_format(v2_response, space_key)

            # Add body.storage structure if body content exists
            if "body" in v2_response and v2_response["body"].get("storage"):
                storage_value = v2_response["body"]["storage"].get("value", "")
                v1_compatible["body"] = {
                    "storage": {"value": storage_value, "representation": "storage"}
                }

            # Add space information with more details
            if space_id:
                v1_compatible["space"] = {
                    "key": space_key,
                    "id": space_id,
                }

            # Add version information
            if "version" in v2_response:
                v1_compatible["version"] = {
                    "number": v2_response["version"].get("number", 1)
                }

            return v1_compatible

        except HTTPError as e:
            logger.error(f"HTTP error getting page '{page_id}': {e}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise ValueError(f"Failed to get page '{page_id}': {e}") from e
        except Exception as e:
            logger.error(f"Error getting page '{page_id}': {e}")
            raise ValueError(f"Failed to get page '{page_id}': {e}") from e

    def delete_page(self, page_id: str) -> bool:
        """Delete a page using the v2 API.

        Args:
            page_id: The ID of the page to delete

        Returns:
            True if the page was successfully deleted, False otherwise

        Raises:
            ValueError: If page deletion fails
        """
        try:
            # Make the v2 API call to delete the page
            url = f"{self.base_url}/api/v2/pages/{page_id}"
            response = self.session.delete(url)
            response.raise_for_status()

            logger.debug(f"Successfully deleted page '{page_id}' with v2 API")

            # Check if status code indicates success (204 No Content is typical for deletes)
            if response.status_code in [200, 204]:
                return True

            # If we get here, it's an unexpected success status
            logger.warning(
                f"Delete page returned unexpected status {response.status_code}"
            )
            return True

        except HTTPError as e:
            logger.error(f"HTTP error deleting page '{page_id}': {e}")
            if e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise ValueError(f"Failed to delete page '{page_id}': {e}") from e
        except Exception as e:
            logger.error(f"Error deleting page '{page_id}': {e}")
            raise ValueError(f"Failed to delete page '{page_id}': {e}") from e

    def _convert_v2_to_v1_format(
        self, v2_response: dict[str, Any], space_key: str
    ) -> dict[str, Any]:
        """Convert v2 API response to v1-compatible format.

        This ensures compatibility with existing code that expects v1 response format.

        Args:
            v2_response: The response from v2 API
            space_key: The space key (needed since v2 response uses space ID)

        Returns:
            Response formatted like v1 API for compatibility
        """
        # Map v2 response fields to v1 format
        v1_compatible = {
            "id": v2_response.get("id"),
            "type": "page",
            "status": v2_response.get("status"),
            "title": v2_response.get("title"),
            "space": {
                "key": space_key,
                "id": v2_response.get("spaceId"),
            },
            "version": {
                "number": v2_response.get("version", {}).get("number", 1),
            },
            "_links": v2_response.get("_links", {}),
        }

        # Add body if present in v2 response
        if "body" in v2_response:
            v1_compatible["body"] = {
                "storage": {
                    "value": v2_response["body"].get("storage", {}).get("value", ""),
                    "representation": "storage",
                }
            }

        return v1_compatible
