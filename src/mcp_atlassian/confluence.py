import logging
import os

from atlassian import Confluence

from .config import ConfluenceConfig
from .document_types import Document
from .preprocessing import TextPreprocessor

# Configure logging
logger = logging.getLogger("mcp-atlassian")


class ConfluenceFetcher:
    """Handles fetching and parsing content from Confluence."""

    def __init__(self):
        url = os.getenv("CONFLUENCE_URL")
        username = os.getenv("CONFLUENCE_USERNAME")
        token = os.getenv("CONFLUENCE_API_TOKEN")

        if not all([url, username, token]):
            raise ValueError("Missing required Confluence environment variables")

        self.config = ConfluenceConfig(url=url, username=username, api_token=token)
        self.confluence = Confluence(
            url=self.config.url,
            username=self.config.username,
            password=self.config.api_token,  # API token is used as password
            cloud=True,
        )
        self.preprocessor = TextPreprocessor(self.config.url, self.confluence)

    def _process_html_content(self, html_content: str, space_key: str) -> tuple[str, str]:
        return self.preprocessor.process_html_content(html_content, space_key)

    def get_spaces(self, start: int = 0, limit: int = 10):
        """Get all available spaces."""
        return self.confluence.get_all_spaces(start=start, limit=limit)

    def get_page_content(self, page_id: str, clean_html: bool = True) -> Document:
        """Get content of a specific page."""
        page = self.confluence.get_page_by_id(page_id=page_id, expand="body.storage,version,space")
        space_key = page.get("space", {}).get("key", "")

        content = page["body"]["storage"]["value"]
        processed_html, processed_markdown = self._process_html_content(content, space_key)

        # Get author information from version
        version = page.get("version", {})
        author = version.get("by", {})

        metadata = {
            "page_id": page_id,
            "title": page["title"],
            "version": version.get("number"),
            "url": f"{self.config.url}/spaces/{space_key}/pages/{page_id}",
            "space_key": space_key,
            "author_name": author.get("displayName"),
            "space_name": page.get("space", {}).get("name", ""),
            "last_modified": version.get("when"),
        }

        return Document(
            page_content=processed_markdown if clean_html else processed_html,
            metadata=metadata,
        )

    def get_page_by_title(self, space_key: str, title: str, clean_html: bool = True) -> Document | None:
        """Get page content by space key and title."""
        try:
            page = self.confluence.get_page_by_title(space=space_key, title=title, expand="body.storage,version")

            if not page:
                return None

            content = page["body"]["storage"]["value"]
            processed_html, processed_markdown = self._process_html_content(content, space_key)

            metadata = {
                "page_id": page["id"],
                "title": page["title"],
                "version": page.get("version", {}).get("number"),
                "space_key": space_key,
                "url": f"{self.config.url}/spaces/{space_key}/pages/{page['id']}",
            }

            return Document(
                page_content=processed_markdown if clean_html else processed_html,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Error fetching page: {str(e)}")
            return None

    def get_space_pages(
        self, space_key: str, start: int = 0, limit: int = 10, clean_html: bool = True
    ) -> list[Document]:
        """Get all pages from a specific space."""
        pages = self.confluence.get_all_pages_from_space(
            space=space_key, start=start, limit=limit, expand="body.storage"
        )

        documents = []
        for page in pages:
            content = page["body"]["storage"]["value"]
            processed_html, processed_markdown = self._process_html_content(content, space_key)

            metadata = {
                "page_id": page["id"],
                "title": page["title"],
                "space_key": space_key,
                "version": page.get("version", {}).get("number"),
                "url": f"{self.config.url}/spaces/{space_key}/pages/{page['id']}",
            }

            documents.append(
                Document(
                    page_content=processed_markdown if clean_html else processed_html,
                    metadata=metadata,
                )
            )

        return documents

    def get_page_comments(self, page_id: str, clean_html: bool = True) -> list[Document]:
        """Get all comments for a specific page."""
        page = self.confluence.get_page_by_id(page_id=page_id, expand="space")
        space_key = page.get("space", {}).get("key", "")
        space_name = page.get("space", {}).get("name", "")

        comments = self.confluence.get_page_comments(content_id=page_id, expand="body.view.value,version", depth="all")[
            "results"
        ]

        comment_documents = []
        for comment in comments:
            body = comment["body"]["view"]["value"]
            processed_html, processed_markdown = self._process_html_content(body, space_key)

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
                    documents.append(Document(page_content=result.get("excerpt", ""), metadata=metadata))

            return documents
        except Exception as e:
            logger.error(f"Search failed with error: {str(e)}")
            return []

    def create_page(self, space_key: str, title: str, body: str, parent_id: str = None) -> Document:
        """
        Create a new page in a Confluence space.

        Args:
            space_key: The key of the space
            title: The title of the page
            body: The content of the page in storage format (HTML)
            parent_id: Optional parent page ID

        Returns:
            Document representing the newly created page
        """
        try:
            # Create the page
            page = self.confluence.create_page(
                space=space_key, title=title, body=body, parent_id=parent_id, representation="storage"
            )

            # Return the created page as a Document
            return self.get_page_content(page["id"])
        except Exception as e:
            logger.error(f"Error creating page in space {space_key}: {str(e)}")
            raise

    def update_page(
        self, page_id: str, title: str, body: str, minor_edit: bool = False, version_comment: str = ""
    ) -> Document:
        """
        Update an existing Confluence page.

        Args:
            page_id: The ID of the page to update
            title: The new title of the page
            body: The new content of the page in storage format (HTML)
            minor_edit: Whether this is a minor edit
            version_comment: Optional comment for this version

        Returns:
            Document representing the updated page
        """
        try:
            # Get the current page to get its version number
            current_page = self.confluence.get_page_by_id(page_id=page_id)

            # Update the page
            self.confluence.update_page(
                page_id=page_id, title=title, body=body, minor_edit=minor_edit, version_comment=version_comment
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
                if not space_key and "content" in result and "_expandable" in result["content"]:
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
                    spaces[space_key] = {"key": space_key, "name": space_name or space_key, "description": ""}

            return spaces
        except Exception as e:
            logger.error(f"Error getting user contributed spaces: {str(e)}")
            return {}
