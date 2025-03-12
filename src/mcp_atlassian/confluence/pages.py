"""Module for Confluence page operations."""

import logging

import requests

from ..models.confluence import ConfluencePage
from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class PagesMixin(ConfluenceClient):
    """Mixin for Confluence page operations."""

    def get_page_content(
        self, page_id: str, *, convert_to_markdown: bool = True
    ) -> ConfluencePage:
        """
        Get content of a specific page.

        Args:
            page_id: The ID of the page to retrieve
            convert_to_markdown: When True, returns content in markdown format,
                               otherwise returns raw HTML (keyword-only)

        Returns:
            ConfluencePage model containing the page content and metadata
        """
        page = self.confluence.get_page_by_id(
            page_id=page_id, expand="body.storage,version,space"
        )
        space_key = page.get("space", {}).get("key", "")
        content = page["body"]["storage"]["value"]
        processed_html, processed_markdown = self.preprocessor.process_html_content(
            content, space_key=space_key
        )

        # Use the appropriate content format based on the convert_to_markdown flag
        page_content = processed_markdown if convert_to_markdown else processed_html

        # Create and return the ConfluencePage model
        return ConfluencePage.from_api_response(
            page,
            base_url=self.config.url,
            include_body=True,
            # Override content with our processed version
            content_override=page_content,
            content_format="storage" if not convert_to_markdown else "markdown",
        )

    def get_page_by_title(
        self, space_key: str, title: str, *, convert_to_markdown: bool = True
    ) -> ConfluencePage | None:
        """
        Get a specific page by its title from a Confluence space.

        Args:
            space_key: The key of the space containing the page
            title: The title of the page to retrieve
            convert_to_markdown: When True, returns content in markdown format,
                               otherwise returns raw HTML (keyword-only)

        Returns:
            ConfluencePage model containing the page content and metadata, or None if not found
        """
        try:
            # First check if the space exists
            spaces = self.confluence.get_all_spaces(start=0, limit=500)

            # Handle case where spaces can be a dictionary with a "results" key
            if isinstance(spaces, dict) and "results" in spaces:
                space_keys = [s["key"] for s in spaces["results"]]
            else:
                space_keys = [s["key"] for s in spaces]

            if space_key not in space_keys:
                logger.warning(f"Space {space_key} not found")
                return None

            # Then try to find the page by title
            page = self.confluence.get_page_by_title(
                space=space_key, title=title, expand="body.storage,version"
            )

            if not page:
                logger.warning(f"Page '{title}' not found in space {space_key}")
                return None

            content = page["body"]["storage"]["value"]
            processed_html, processed_markdown = self.preprocessor.process_html_content(
                content, space_key=space_key
            )

            # Use the appropriate content format based on the convert_to_markdown flag
            page_content = processed_markdown if convert_to_markdown else processed_html

            # Create and return the ConfluencePage model
            return ConfluencePage.from_api_response(
                page,
                base_url=self.config.url,
                include_body=True,
                # Override content with our processed version
                content_override=page_content,
                content_format="storage" if not convert_to_markdown else "markdown",
            )

        except KeyError as e:
            logger.error(f"Missing key in page data: {str(e)}")
            return None
        except requests.RequestException as e:
            logger.error(f"Network error when fetching page: {str(e)}")
            return None
        except (ValueError, TypeError) as e:
            logger.error(f"Error processing page data: {str(e)}")
            return None
        except Exception as e:  # noqa: BLE001 - Intentional fallback with full logging
            logger.error(f"Unexpected error fetching page: {str(e)}")
            # Log the full traceback at debug level for troubleshooting
            logger.debug("Full exception details:", exc_info=True)
            return None

    def get_space_pages(
        self,
        space_key: str,
        start: int = 0,
        limit: int = 10,
        *,
        convert_to_markdown: bool = True,
    ) -> list[ConfluencePage]:
        """
        Get all pages from a specific space.

        Args:
            space_key: The key of the space to get pages from
            start: The starting index for pagination
            limit: Maximum number of pages to return
            convert_to_markdown: When True, returns content in markdown format,
                               otherwise returns raw HTML (keyword-only)

        Returns:
            List of ConfluencePage models containing page content and metadata
        """
        pages = self.confluence.get_all_pages_from_space(
            space=space_key, start=start, limit=limit, expand="body.storage"
        )

        page_models = []
        for page in pages:
            content = page["body"]["storage"]["value"]
            processed_html, processed_markdown = self.preprocessor.process_html_content(
                content, space_key=space_key
            )

            # Use the appropriate content format based on the convert_to_markdown flag
            page_content = processed_markdown if convert_to_markdown else processed_html

            # Ensure space information is included
            if "space" not in page:
                page["space"] = {
                    "key": space_key,
                    "name": space_key,  # Use space_key as name if not available
                }

            # Create the ConfluencePage model
            page_model = ConfluencePage.from_api_response(
                page,
                base_url=self.config.url,
                include_body=True,
                # Override content with our processed version
                content_override=page_content,
                content_format="storage" if not convert_to_markdown else "markdown",
            )

            page_models.append(page_model)

        return page_models

    def create_page(
        self, space_key: str, title: str, body: str, parent_id: str | None = None
    ) -> ConfluencePage:
        """
        Create a new page in a Confluence space.

        Args:
            space_key: The key of the space to create the page in
            title: The title of the new page
            body: The HTML content of the page in storage format
            parent_id: Optional ID of a parent page

        Returns:
            ConfluencePage model containing the new page's data

        Raises:
            Exception: If there is an error creating the page
        """
        try:
            # Create the page
            result = self.confluence.create_page(
                space=space_key,
                title=title,
                body=body,
                parent_id=parent_id,
                representation="storage",
            )

            # Get the new page content
            page_id = result.get("id")
            if not page_id:
                raise ValueError("Create page response did not contain an ID")

            return self.get_page_content(page_id)
        except Exception as e:
            logger.error(
                f"Error creating page '{title}' in space {space_key}: {str(e)}"
            )
            raise Exception(
                f"Failed to create page '{title}' in space {space_key}: {str(e)}"
            ) from e

    def update_page(
        self,
        page_id: str,
        title: str,
        body: str,
        *,
        is_minor_edit: bool = False,
        version_comment: str = "",
    ) -> ConfluencePage:
        """
        Update an existing page in Confluence.

        Args:
            page_id: The ID of the page to update
            title: The new title of the page
            body: The new HTML content of the page in storage format
            is_minor_edit: Whether this is a minor edit (keyword-only)
            version_comment: Optional comment for this version (keyword-only)

        Returns:
            ConfluencePage model containing the updated page's data

        Raises:
            Exception: If there is an error updating the page
        """
        try:
            # We'll let the underlying Confluence API handle this operation completely
            # as it has internal logic for versioning and updating
            logger.debug(f"Updating page {page_id} with title '{title}'")

            # Simply pass through all parameters, making sure to match parameter names
            response = self.confluence.update_page(
                page_id=page_id,
                title=title,
                body=body,
                type="page",
                representation="storage",
                minor_edit=is_minor_edit,  # This matches the parameter name in the API
                version_comment=version_comment,
                always_update=True,  # Force update to avoid content comparison issues
            )

            # After update, refresh the page data
            return self.get_page_content(page_id)
        except Exception as e:
            logger.error(f"Error updating page {page_id}: {str(e)}")
            raise Exception(f"Failed to update page {page_id}: {str(e)}") from e

    def delete_page(self, page_id: str) -> bool:
        """
        Delete a Confluence page by its ID.

        Args:
            page_id: The ID of the page to delete

        Returns:
            Boolean indicating success (True) or failure (False)

        Raises:
            Exception: If there is an error deleting the page
        """
        try:
            logger.debug(f"Deleting page {page_id}")
            response = self.confluence.remove_page(page_id=page_id)

            # The Atlassian library's remove_page returns the raw response from
            # the REST API call. For a successful deletion, we should get a
            # response object, but it might be empty (HTTP 204 No Content).
            # For REST DELETE operations, a success typically returns 204 or 200

            # Check if we got a response object
            if isinstance(response, requests.Response):
                # Check if status code indicates success (2xx)
                success = 200 <= response.status_code < 300
                logger.debug(
                    f"Delete page {page_id} returned status code {response.status_code}"
                )
                return success
            # If it's not a response object but truthy (like True), consider it a success
            elif response:
                return True
            # Default to true since no exception was raised
            # This is safer than returning false when we don't know what happened
            return True

        except Exception as e:
            logger.error(f"Error deleting page {page_id}: {str(e)}")
            raise Exception(f"Failed to delete page {page_id}: {str(e)}") from e
