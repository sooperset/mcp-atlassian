"""Module for Confluence comment operations."""

import logging
from typing import Any

import requests

from ..models.confluence import ConfluenceComment
from .client import ConfluenceClient
from .v2_adapter import ConfluenceV2Adapter

logger = logging.getLogger("mcp-atlassian")


class CommentsMixin(ConfluenceClient):
    """Mixin for Confluence comment operations."""

    @property
    def _v2_adapter(self) -> ConfluenceV2Adapter | None:
        """Get v2 API adapter for OAuth authentication.

        Returns:
            ConfluenceV2Adapter instance if OAuth is configured, None otherwise
        """
        if self.config.auth_type == "oauth" and self.config.is_cloud:
            return ConfluenceV2Adapter(
                session=self.confluence._session, base_url=self.confluence.url
            )
        return None

    def get_page_comments(
        self, page_id: str, *, return_markdown: bool = True
    ) -> list[ConfluenceComment]:
        """
        Get all comments for a specific page.

        Args:
            page_id: The ID of the page to get comments from
            return_markdown: When True, returns content in markdown format,
                           otherwise returns raw HTML (keyword-only)

        Returns:
            List of ConfluenceComment models containing comment content and metadata
        """
        try:
            # Get page info to extract space details
            page = self.confluence.get_page_by_id(page_id=page_id, expand="space")
            space_key = page.get("space", {}).get("key", "")

            # Get comments with expanded content
            comments_response = self.confluence.get_page_comments(
                content_id=page_id, expand="body.view.value,version", depth="all"
            )

            # Process each comment
            comment_models = []
            for comment_data in comments_response.get("results", []):
                # Get the content based on format
                body = comment_data["body"]["view"]["value"]
                processed_html, processed_markdown = (
                    self.preprocessor.process_html_content(
                        body, space_key=space_key, confluence_client=self.confluence
                    )
                )

                # Create a copy of the comment data to modify
                modified_comment_data = comment_data.copy()

                # Modify the body value based on the return format
                if "body" not in modified_comment_data:
                    modified_comment_data["body"] = {}
                if "view" not in modified_comment_data["body"]:
                    modified_comment_data["body"]["view"] = {}

                # Set the appropriate content based on return format
                modified_comment_data["body"]["view"]["value"] = (
                    processed_markdown if return_markdown else processed_html
                )

                # Create the model with the processed content
                comment_model = ConfluenceComment.from_api_response(
                    modified_comment_data,
                    base_url=self.config.url,
                )

                comment_models.append(comment_model)

            return comment_models

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

    def add_comment(self, page_id: str, content: str) -> ConfluenceComment | None:
        """
        Add a comment to a Confluence page.

        Args:
            page_id: The ID of the page to add the comment to
            content: The content of the comment (in Confluence storage format)

        Returns:
            ConfluenceComment object if comment was added successfully, None otherwise
        """
        try:
            # Convert markdown to Confluence storage format if needed
            if not content.strip().startswith("<"):
                content = self.preprocessor.markdown_to_confluence_storage(content)

            # Route through v2 API for OAuth Cloud
            v2_adapter = self._v2_adapter
            if v2_adapter:
                response = v2_adapter.create_footer_comment(
                    page_id=page_id, body=content
                )
                space_key = ""
            else:
                # Get page info to extract space details (v1 path)
                page = self.confluence.get_page_by_id(page_id=page_id, expand="space")
                space_key = page.get("space", {}).get("key", "")
                response = self.confluence.add_comment(page_id, content)

            if not response:
                logger.error("Failed to add comment: empty response")
                return None

            return self._process_comment_response(response, space_key)

        except requests.RequestException as e:
            logger.error(f"Network error when adding comment: {str(e)}")
            return None
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Error processing comment data: {str(e)}")
            return None
        except Exception as e:  # noqa: BLE001 - Intentional fallback with full logging
            logger.error(f"Unexpected error adding comment: {str(e)}")
            logger.debug("Full exception details for adding comment:", exc_info=True)
            return None

    def reply_to_comment(
        self, comment_id: str, content: str
    ) -> ConfluenceComment | None:
        """
        Reply to an existing comment thread.

        Args:
            comment_id: The ID of the parent comment to reply to
            content: The reply content (markdown or HTML/storage format)

        Returns:
            ConfluenceComment object if reply was added successfully, None otherwise
        """
        try:
            # Convert markdown to Confluence storage format if needed
            if not content.strip().startswith("<"):
                content = self.preprocessor.markdown_to_confluence_storage(content)

            v2_adapter = self._v2_adapter
            if v2_adapter:
                response = v2_adapter.create_footer_comment(
                    parent_comment_id=comment_id, body=content
                )
                space_key = ""
            else:
                # v1 API: POST /rest/api/content/ with container type "comment"
                data: dict[str, Any] = {
                    "type": "comment",
                    "container": {
                        "id": comment_id,
                        "type": "comment",
                    },
                    "body": {
                        "storage": {
                            "value": content,
                            "representation": "storage",
                        },
                    },
                }
                response = self.confluence.post("rest/api/content/", data=data)
                space_key = ""

            if not response:
                logger.error("Failed to reply to comment: empty response")
                return None

            return self._process_comment_response(response, space_key)

        except requests.RequestException as e:
            logger.error(f"Network error when replying to comment: {str(e)}")
            return None
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Error processing reply data: {str(e)}")
            return None
        except Exception as e:  # noqa: BLE001 - Intentional fallback with full logging
            logger.error(f"Unexpected error replying to comment: {str(e)}")
            logger.debug("Full exception details for comment reply:", exc_info=True)
            return None

    def _process_comment_response(
        self, response: dict[str, Any], space_key: str
    ) -> ConfluenceComment:
        """Process a comment API response into a ConfluenceComment model.

        Args:
            response: Raw API response dict
            space_key: The space key for content processing

        Returns:
            Processed ConfluenceComment instance
        """
        processed_html, processed_markdown = self.preprocessor.process_html_content(
            response.get("body", {}).get("view", {}).get("value", ""),
            space_key=space_key,
            confluence_client=self.confluence,
        )

        modified_response = response.copy()
        if "body" not in modified_response:
            modified_response["body"] = {}
        if "view" not in modified_response["body"]:
            modified_response["body"]["view"] = {}

        modified_response["body"]["view"]["value"] = processed_markdown

        return ConfluenceComment.from_api_response(
            modified_response,
            base_url=self.config.url,
        )
