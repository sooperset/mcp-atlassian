import logging
import os

import requests
from atlassian import Confluence

from .config import ConfluenceConfig
from .document_types import Document
from .preprocessing import TextPreprocessor

# Configure logging
logger = logging.getLogger("mcp-atlassian")


class ConfluenceFetcher:
    """Handles fetching and parsing content from Confluence."""

    def __init__(self) -> None:
        """Initialize the Confluence client with configuration from environment variables."""
        url = os.getenv("CONFLUENCE_URL")
        username = os.getenv("CONFLUENCE_USERNAME")
        token = os.getenv("CONFLUENCE_API_TOKEN")

        if not all([url, username, token]):
            error_msg = "Missing required Confluence environment variables"
            raise ValueError(error_msg)

        # Type assertions after null check
        assert url is not None
        assert username is not None
        assert token is not None

        self.config = ConfluenceConfig(url=url, username=username, api_token=token)
        self.confluence = Confluence(
            url=self.config.url,
            username=self.config.username,
            password=self.config.api_token,  # API token is used as password
            cloud=True,
        )
        self.preprocessor = TextPreprocessor(
            base_url=self.config.url, confluence_client=self.confluence
        )

    def _process_html_content(
        self, html_content: str, space_key: str
    ) -> tuple[str, str]:
        return self.preprocessor.process_html_content(html_content, space_key)

    def get_spaces(self, start: int = 0, limit: int = 10) -> list[dict]:
        """
        Get all available spaces.

        Args:
            start: The starting index for pagination
            limit: Maximum number of spaces to return

        Returns:
            List of dictionaries with space information
        """
        spaces = self.confluence.get_all_spaces(start=start, limit=limit)
        return spaces if isinstance(spaces, list) else []

    def get_page_content(
        self, page_id: str, *, convert_to_markdown: bool = True
    ) -> Document:
        """
        Get content of a specific page.

        Args:
            page_id: The ID of the page to retrieve
            convert_to_markdown: When True, returns content in markdown format,
                                 otherwise returns raw HTML

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
                                 otherwise returns raw HTML

        Returns:
            Document containing the page content and metadata, or None if not found
        """
        try:
            # First check if the space exists
            spaces = self.confluence.get_all_spaces(start=0, limit=500)
            space_keys = [s["key"] for s in spaces]
            if space_key not in space_keys:
                logger.warning(f"Space {space_key} not found")
                return None

            # Then try to find the page by title
            page = self.confluence.get_page_by_title(
                space=space_key, title=title, expand="body.storage"
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
        except Exception as e:
            logger.error(f"Unexpected error fetching page: {str(e)}")
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
                                 otherwise returns raw HTML

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
                "version": page.get("version", {}).get("number"),
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

    def get_page_comments(
        self, page_id: str, clean_html: bool = True
    ) -> list[Document]:
        """Get all comments for a specific page."""
        page = self.confluence.get_page_by_id(page_id=page_id, expand="space")
        space_key = page.get("space", {}).get("key", "")
        space_name = page.get("space", {}).get("name", "")

        comments = self.confluence.get_page_comments(
            content_id=page_id, expand="body.view.value,version", depth="all"
        )["results"]

        comment_documents = []
        for comment in comments:
            body = comment["body"]["view"]["value"]
            processed_html, processed_markdown = self._process_html_content(
                body, space_key
            )

            # Get author information from version.by instead of author
            author = comment.get("version", {}).get("by", {})

            metadata = {
                "page_id": page_id,
                "comment_id": comment["id"],
                "last_modified": comment.get("version", {}).get("when"),
                "type": "comment",
                "author_name": author.get("displayName"),
                "space_key": space_key,
                "space_name": space_name,
            }

            comment_documents.append(
                Document(
                    page_content=processed_markdown if clean_html else processed_html,
                    metadata=metadata,
                )
            )

        return comment_documents

    def search(self, cql: str, limit: int = 10) -> list[Document]:
        """Search content using Confluence Query Language (CQL)."""
        try:
            results = self.confluence.cql(cql=cql, limit=limit)
            documents = []

            for result in results.get("results", []):
                content = result.get("content", {})
                if content.get("type") == "page":
                    metadata = {
                        "page_id": content["id"],
                        "title": result["title"],
                        "space": result.get("resultGlobalContainer", {}).get("title"),
                        "url": f"{self.config.url}{result['url']}",
                        "last_modified": result.get("lastModified"),
                        "type": content["type"],
                    }

                    # Use the excerpt as page_content since it's already a good summary
                    documents.append(
                        Document(
                            page_content=result.get("excerpt", ""), metadata=metadata
                        )
                    )

            return documents
        except Exception as e:
            logger.error(f"Search failed with error: {str(e)}")
            return []

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
        minor_edit: bool = False,
        version_comment: str = "",
    ) -> Document:
        """
        Update an existing Confluence page.

        Args:
            page_id: ID of the page to update
            title: New page title
            body: New page content in Confluence storage format
            minor_edit: Whether this update is a minor edit
            version_comment: Optional comment for the version history

        Returns:
            Document representing the updated page
        """
        try:
            # Get the current page to get its version number
            current_page = self.confluence.get_page_by_id(page_id=page_id)
            version = current_page.get("version", {}).get("number", 0) + 1

            # Update the page
            self.confluence.update_page(
                page_id=page_id,
                title=title,
                body=body,
                minor_edit=minor_edit,
                version_comment=version_comment,
                version_number=version,
            )

            # Return the updated page as a Document
            return self.get_page_content(page_id)
        except Exception as e:
            logger.error(f"Error updating page {page_id}: {str(e)}")
            raise

    def get_user_contributed_spaces(self, limit: int = 250) -> dict:
        """
        Get spaces the current user has contributed to.

        Args:
            limit: Maximum number of results to return

        Returns:
            Dictionary of space keys to space information
        """
        try:
            # Use CQL to find content the user has contributed to
            cql = "contributor = currentUser() order by lastmodified DESC"
            results = self.confluence.cql(cql=cql, limit=limit)

            # Extract and deduplicate spaces
            spaces = {}
            for result in results.get("results", []):
                space_key = None
                space_name = None

                # Try to extract space from container
                if "resultGlobalContainer" in result:
                    container = result.get("resultGlobalContainer", {})
                    space_name = container.get("title")
                    display_url = container.get("displayUrl", "")
                    if display_url and "/spaces/" in display_url:
                        space_key = display_url.split("/spaces/")[1].split("/")[0]

                # Try to extract from content expandable
                if (
                    not space_key
                    and "content" in result
                    and "_expandable" in result["content"]
                ):
                    expandable = result["content"].get("_expandable", {})
                    space_path = expandable.get("space", "")
                    if space_path and space_path.startswith("/rest/api/space/"):
                        space_key = space_path.split("/rest/api/space/")[1]

                # Try to extract from URL
                if not space_key and "url" in result:
                    url = result.get("url", "")
                    if url and url.startswith("/spaces/"):
                        space_key = url.split("/spaces/")[1].split("/")[0]

                # If we found a space key, add it to our dictionary
                if space_key and space_key not in spaces:
                    spaces[space_key] = {
                        "key": space_key,
                        "name": space_name or space_key,
                        "description": "",
                    }

            return spaces
        except Exception as e:
            logger.error(f"Error getting user contributed spaces: {str(e)}")
            return {}
