"""Module for Confluence comment operations."""

import logging

import requests

from ..document_types import Document
from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class CommentsMixin(ConfluenceClient):
    """Mixin for Confluence comment operations."""

    def get_page_comments(
        self, page_id: str, *, return_markdown: bool = True
    ) -> list[Document]:
        """
        Get all comments for a specific page.

        Args:
            page_id: The ID of the page to get comments from
            return_markdown: When True, returns content in markdown format,
                           otherwise returns raw HTML (keyword-only)

        Returns:
            List of Document objects containing comment content and metadata
        """
        try:
            # Get page info to extract space details
            page = self.confluence.get_page_by_id(page_id=page_id, expand="space")
            space_key = page.get("space", {}).get("key", "")
            space_name = page.get("space", {}).get("name", "")

            # Get comments with expanded content
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
                        page_content=processed_markdown
                        if return_markdown
                        else processed_html,
                        metadata=metadata,
                    )
                )

            return comment_documents

        except KeyError as e:
            logger.error(f"Missing key in comment data: {str(e)}")
            return []
        except requests.RequestException as e:
            logger.error(f"Network error when fetching comments: {str(e)}")
            return []
        except (ValueError, TypeError) as e:
            logger.error(f"Error processing comment data: {str(e)}")
            return []
        except Exception as e:  # noqa: BLE001 - Intentional fallback with full logging
            logger.error(f"Unexpected error fetching comments: {str(e)}")
            logger.debug("Full exception details for comments:", exc_info=True)
            return []
