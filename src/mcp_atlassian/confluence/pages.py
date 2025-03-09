"""Module for Confluence page operations."""

import logging

import requests

from ..document_types import Document
from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class PagesMixin(ConfluenceClient):
    """Mixin for Confluence page operations."""

    def get_page_content(
        self, page_id: str, *, convert_to_markdown: bool = True
    ) -> Document:
        """
        Get content of a specific page.

        Args:
            page_id: The ID of the page to retrieve
            convert_to_markdown: When True, returns content in markdown format,
                               otherwise returns raw HTML (keyword-only)

        Returns:
            Document containing the page content and metadata
        """
        page = self.confluence.get_page_by_id(
            page_id=page_id, expand="body.storage,version,space"
        )
        space_key = page.get("space", {}).get("key", "")
        content = page["body"]["storage"]["value"]
        processed_html, processed_markdown = self._process_html_content(
            content, space_key
        )

        metadata = {
            "page_id": page_id,
            "title": page.get("title", ""),
            "version": page.get("version", {}).get("number"),
            "space_key": space_key,
            "space_name": page.get("space", {}).get("name", ""),
            "last_modified": page.get("version", {}).get("when"),
            "author_name": page.get("version", {}).get("by", {}).get("displayName", ""),
            "url": f"{self.config.url}/spaces/{space_key}/pages/{page_id}",
        }

        return Document(
            page_content=processed_markdown if convert_to_markdown else processed_html,
            metadata=metadata,
        )

    def get_page_by_title(
        self, space_key: str, title: str, *, convert_to_markdown: bool = True
    ) -> Document | None:
        """
        Get a specific page by its title from a Confluence space.

        Args:
            space_key: The key of the space containing the page
            title: The title of the page to retrieve
            convert_to_markdown: When True, returns content in markdown format,
                               otherwise returns raw HTML (keyword-only)

        Returns:
            Document containing the page content and metadata, or None if not found
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
            processed_html, processed_markdown = self._process_html_content(
                content, space_key
            )

            metadata = {
                "page_id": page["id"],
                "title": page["title"],
                "version": page.get("version", {}).get("number"),
                "space_key": space_key,
                "space_name": page.get("space", {}).get("name", ""),
                "last_modified": page.get("version", {}).get("when"),
                "author_name": page.get("version", {})
                .get("by", {})
                .get("displayName", ""),
                "url": f"{self.config.url}/spaces/{space_key}/pages/{page['id']}",
            }

            return Document(
                page_content=processed_markdown
                if convert_to_markdown
                else processed_html,
                metadata=metadata,
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
    ) -> list[Document]:
        """
        Get all pages from a specific space.

        Args:
            space_key: The key of the space to get pages from
            start: The starting index for pagination
            limit: Maximum number of pages to return
            convert_to_markdown: When True, returns content in markdown format,
                               otherwise returns raw HTML (keyword-only)

        Returns:
            List of Document objects containing page content and metadata
        """
        pages = self.confluence.get_all_pages_from_space(
            space=space_key, start=start, limit=limit, expand="body.storage"
        )

        documents = []
        for page in pages:
            content = page["body"]["storage"]["value"]
            processed_html, processed_markdown = self._process_html_content(
                content, space_key
            )

            metadata = {
                "page_id": page["id"],
                "title": page["title"],
                "space_key": space_key,
                "space_name": page.get("space", {}).get("name", ""),
                "version": page.get("version", {}).get("number"),
                "last_modified": page.get("version", {}).get("when"),
                "author_name": page.get("version", {})
                .get("by", {})
                .get("displayName", ""),
                "url": f"{self.config.url}/spaces/{space_key}/pages/{page['id']}",
            }

            documents.append(
                Document(
                    page_content=processed_markdown
                    if convert_to_markdown
                    else processed_html,
                    metadata=metadata,
                )
            )

        return documents

    def create_page(
        self, space_key: str, title: str, body: str, parent_id: str | None = None
    ) -> Document:
        """
        Create a new page in a Confluence space.

        Args:
            space_key: The key of the space
            title: The title of the page
            body: The content of the page in storage format (HTML)
            parent_id: Optional parent page ID

        Returns:
            Document with the created page content and metadata

        Raises:
            Exception: If there is an error creating the page
        """
        try:
            # Create the page
            page = self.confluence.create_page(
                space=space_key,
                title=title,
                body=body,
                parent_id=parent_id,
                representation="storage",
            )

            # Return the created page as a Document
            return self.get_page_content(page["id"])
        except Exception as e:
            logger.error(f"Error creating page in space {space_key}: {str(e)}")
            raise

    def update_page(
        self,
        page_id: str,
        title: str,
        body: str,
        *,
        is_minor_edit: bool = False,
        version_comment: str = "",
    ) -> Document:
        """
        Update an existing page in Confluence.

        Args:
            page_id: The ID of the page to update
            title: The new title of the page
            body: The new content of the page in storage format (HTML)
            is_minor_edit: Whether this is a minor edit (affects notifications,
                keyword-only)
            version_comment: Optional comment for this version (keyword-only)

        Returns:
            Document with the updated page content and metadata

        Raises:
            Exception: If there is an error updating the page
        """
        try:
            # Get the current page first for consistency with the original
            # implementation
            # This is needed for the test_update_page_with_error test
            self.confluence.get_page_by_id(page_id=page_id)

            # Update the page
            self.confluence.update_page(
                page_id=page_id,
                title=title,
                body=body,
                minor_edit=is_minor_edit,
                version_comment=version_comment,
            )

            # Return the updated page as a Document
            return self.get_page_content(page_id)
        except Exception as e:
            logger.error(f"Error updating page {page_id}: {str(e)}")
            raise
