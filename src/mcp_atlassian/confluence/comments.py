"""Module for Confluence comment operations."""

import json
import logging
import time
from typing import Any

import requests

from ..models.confluence import ConfluenceComment
from ..utils.truncation import mark_truncated, merge_truncation
from .client import ConfluenceClient
from .scope import allowed_space_keys
from .v2_adapter import (
    MAX_COMMENT_REQUESTS_PER_READ,
    MAX_COMMENTS_PER_READ,
    ConfluenceV2Adapter,
)

logger = logging.getLogger("mcp-atlassian")


def _comment_body_html(comment: dict[str, Any]) -> str:
    """Return a comment's view body, or its storage body when no view was read."""
    body = comment.get("body") or {}
    for representation in ("view", "storage"):
        value = (body.get(representation) or {}).get("value")
        if value:
            return str(value)
    return ""


class CommentsMixin(ConfluenceClient):
    """Mixin for Confluence comment operations."""

    def _v1_comment_body_expand(self) -> str:
        """Return the v1 body representation to read for comments.

        The view representation is rendered by Confluence, so include and
        listing macros in it carry content from other spaces. While a
        CONFLUENCE_SPACES_FILTER is set, the storage representation is read
        instead, as page reads do.
        """
        if allowed_space_keys(self.config):
            return "body.storage.value"
        return "body.view.value"

    def _get_all_v1_page_comments(
        self,
        page_id: str,
        *,
        expand: str,
        max_items: int = MAX_COMMENTS_PER_READ,
        max_pages: int = MAX_COMMENT_REQUESTS_PER_READ,
    ) -> list[dict[str, Any]]:
        """Fetch comment pages from the Confluence v1 API, up to the read limits."""
        response = self.confluence.get_page_comments(
            content_id=page_id,
            expand=expand,
            depth="all",
        )
        results = list(response.get("results", []))
        start = int(response.get("start", 0))
        pages = 1

        while response.get("_links", {}).get("next") and len(results) < max_items:
            if pages >= max_pages:
                logger.warning(
                    "Stopping comment pagination for page %s at the read limit",
                    page_id,
                )
                break
            page_size = int(response.get("size", len(response.get("results", []))))
            if page_size <= 0:
                break
            start += page_size
            limit = int(response.get("limit", 25))
            pages += 1
            response = self.confluence.get_page_comments(
                content_id=page_id,
                expand=expand,
                depth="all",
                start=start,
                limit=limit,
            )
            results.extend(response.get("results", []))

        more_upstream = bool(response.get("_links", {}).get("next"))
        if len(results) > max_items or more_upstream:
            logger.warning(
                "Returning the first %d comments of page %s",
                min(len(results), max_items),
                page_id,
            )
            # Comments beyond the limit were seen only if a page overshot it;
            # a next link alone may lead to an empty page.
            return mark_truncated(results[:max_items], certain=len(results) > max_items)
        return results

    @property
    def _v2_adapter(self) -> ConfluenceV2Adapter | None:
        """Get v2 API adapter for supported Confluence Cloud authentication.

        Returns:
            ConfluenceV2Adapter for Cloud OAuth/PAT, None otherwise
        """
        if self.config.is_cloud and self.config.auth_type in ("oauth", "pat"):
            return ConfluenceV2Adapter(
                session=self.confluence._session, base_url=self.confluence.url
            )
        return None

    @property
    def _inline_v2_adapter(self) -> ConfluenceV2Adapter | None:
        """Get v2 API adapter for inline comment operations.

        Inline comments require the v2 API on all Cloud instances because the
        v1 ``POST /rest/api/content/`` endpoint does not support inline comment
        creation on Confluence Cloud regardless of auth method.

        Returns:
            ConfluenceV2Adapter instance if this is a Cloud instance, None otherwise
        """
        if self.config.is_cloud:
            return ConfluenceV2Adapter(
                session=self.confluence._session, base_url=self.confluence.url
            )
        return None

    def get_page_comments(
        self, page_id: str, *, return_markdown: bool = True
    ) -> list[ConfluenceComment]:
        """
        Get the comments for a specific page.

        Each comment collection read (footer, inline, or the v1 listing)
        returns at most ``MAX_COMMENTS_PER_READ`` comments, roots and replies
        together, and sends a bounded number of requests.

        Args:
            page_id: The ID of the page to get comments from
            return_markdown: When True, returns content in markdown format,
                           otherwise returns raw HTML (keyword-only)

        Returns:
            List of ConfluenceComment models containing comment content and metadata
        """
        try:
            v2_adapter = self._v2_adapter
            if v2_adapter:
                # Cloud OAuth: the v1 page and comment reads are gone from the
                # gateway (410), so take both the space key and the comments
                # from v2. The v1 read returned footer and inline comments
                # together; keep that.
                page = v2_adapter.get_page(page_id)
                space_key = page.get("space", {}).get("key", "")
                # Each collection read is bounded (ReadBudget defaults).
                footer = v2_adapter.get_footer_comments(page_id)
                inline = v2_adapter.get_inline_comments(page_id)
                read_parts: tuple[Any, ...] = (footer, inline)
                raw_comments = [*footer, *inline]
            else:
                # Get page info to extract space details
                page = self.confluence.get_page_by_id(page_id=page_id, expand="space")
                space_key = page.get("space", {}).get("key", "")

                # Get comments with expanded content
                raw_comments = self._get_all_v1_page_comments(
                    page_id,
                    expand=(
                        f"{self._v1_comment_body_expand()},version,container,"
                        "ancestors,extensions.inlineProperties,"
                        "extensions.resolution"
                    ),
                )
                read_parts = (raw_comments,)

            # Process each comment
            comment_models = []
            for comment_data in raw_comments:
                # Get the content based on format
                body = _comment_body_html(comment_data)
                processed_html, processed_markdown = (
                    self.preprocessor.process_html_content(
                        body, space_key=space_key, confluence_client=self.confluence
                    )
                )

                # Create a copy of the comment data to modify
                modified_comment_data = comment_data.copy()
                if "body" in modified_comment_data:
                    modified_comment_data["body"] = modified_comment_data["body"].copy()
                    if "view" in modified_comment_data["body"]:
                        modified_comment_data["body"]["view"] = modified_comment_data[
                            "body"
                        ]["view"].copy()

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

            return merge_truncation(comment_models, *read_parts)

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

    def _comment_body_to_storage(self, content: str, content_format: str) -> str:
        """Return a comment body in storage format.

        The format is what the caller says it is, never inferred from the
        content: Markdown is always converted, even when it starts with ``<``.

        Args:
            content: The comment body.
            content_format: ``'markdown'`` or ``'storage'``.

        Returns:
            The body in Confluence storage format.

        Raises:
            ValueError: If ``content_format`` is not ``'markdown'`` or
                ``'storage'``.
        """
        if content_format == "storage":
            return content
        if content_format == "markdown":
            return self.preprocessor.markdown_to_confluence_storage(content)
        error_msg = (
            f"Invalid content_format '{content_format}'. Must be "
            "'markdown' or 'storage'."
        )
        raise ValueError(error_msg)

    def add_comment(
        self, page_id: str, content: str, content_format: str = "markdown"
    ) -> ConfluenceComment | None:
        """
        Add a comment to a Confluence page.

        Args:
            page_id: The ID of the page to add the comment to
            content: The content of the comment
            content_format: Format of content, ``'markdown'`` (default,
                converted to storage format) or ``'storage'`` (sent as is)

        Returns:
            ConfluenceComment object if comment was added successfully, None otherwise

        Raises:
            ValueError: If ``content_format`` is not ``'markdown'`` or
                ``'storage'``.
        """
        content = self._comment_body_to_storage(content, content_format)
        try:
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
        self, comment_id: str, content: str, content_format: str = "markdown"
    ) -> ConfluenceComment | None:
        """
        Reply to an existing comment thread.

        Args:
            comment_id: The ID of the parent comment to reply to
            content: The reply content
            content_format: Format of content, ``'markdown'`` (default,
                converted to storage format) or ``'storage'`` (sent as is)

        Returns:
            ConfluenceComment object if reply was added successfully, None otherwise

        Raises:
            ValueError: If ``content_format`` is not ``'markdown'`` or
                ``'storage'``.
        """
        content = self._comment_body_to_storage(content, content_format)
        try:
            v2_adapter = self._v2_adapter
            if v2_adapter:
                response = v2_adapter.create_footer_comment(
                    parent_comment_id=comment_id, body=content
                )
                space_key = ""
            else:
                # v1 API: thread replies under the parent page with ancestors,
                # not as a direct child of the parent comment.
                page_id = self._resolve_page_id_for_parent_comment(comment_id)
                page = self.confluence.get_page_by_id(page_id=page_id, expand="space")
                space_key = page.get("space", {}).get("key", "")
                data: dict[str, Any] = {
                    "type": "comment",
                    "container": {
                        "id": page_id,
                        "type": "page",
                    },
                    "ancestors": [{"id": comment_id}],
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

    @staticmethod
    def _page_id_from_reference(reference: Any) -> str | None:
        """Return a page ID from an expanded Confluence content reference."""
        if not isinstance(reference, dict) or reference.get("type") != "page":
            return None

        page_id = reference.get("id")
        return str(page_id) if page_id is not None else None

    def _resolve_page_id_for_parent_comment(self, comment_id: str) -> str:
        """Resolve the page containing a parent comment, including nested replies.

        Args:
            comment_id: The ID of the parent comment.

        Returns:
            The page ID that owns the comment thread.

        Raises:
            ValueError: If the parent response contains no page reference.
        """
        parent = self.confluence.get_page_by_id(
            page_id=comment_id, expand="container,ancestors"
        )

        page_id = self._page_id_from_reference(parent.get("container"))
        if page_id:
            return page_id

        ancestors = parent.get("ancestors")
        if isinstance(ancestors, list):
            for ancestor in reversed(ancestors):
                page_id = self._page_id_from_reference(ancestor)
                if page_id:
                    return page_id

        raise ValueError(f"Could not resolve page for parent comment {comment_id}")

    def get_inline_comments(
        self, page_id: str, *, return_markdown: bool = True
    ) -> list[ConfluenceComment]:
        """Get inline comments for a specific page.

        Args:
            page_id: The ID of the page to get inline comments from
            return_markdown: When True, returns content in markdown format,
                           otherwise returns raw HTML (keyword-only)

        Returns:
            List of ConfluenceComment models with location="inline"
        """
        try:
            v2_adapter = self._inline_v2_adapter
            if v2_adapter:
                raw_comments = v2_adapter.get_inline_comments(page_id)
                read_parts: tuple[Any, ...] = (raw_comments,)
                space_key = ""
            else:
                # v1: fetch all child comments then filter by location=inline
                page = self.confluence.get_page_by_id(page_id=page_id, expand="space")
                space_key = page.get("space", {}).get("key", "")
                all_comments = self._get_all_v1_page_comments(
                    page_id,
                    expand=(
                        f"{self._v1_comment_body_expand()},version,container,"
                        "ancestors,extensions.inlineProperties,"
                        "extensions.resolution"
                    ),
                )
                read_parts = (all_comments,)
                raw_comments = [
                    c
                    for c in all_comments
                    if c.get("extensions", {}).get("location") == "inline"
                ]

            comment_models = []
            for comment_data in raw_comments:
                body = _comment_body_html(comment_data)
                processed_html, processed_markdown = (
                    self.preprocessor.process_html_content(
                        body, space_key=space_key, confluence_client=self.confluence
                    )
                )

                modified_comment_data = comment_data.copy()
                if "body" in modified_comment_data:
                    modified_comment_data["body"] = modified_comment_data["body"].copy()
                    if "view" in modified_comment_data["body"]:
                        modified_comment_data["body"]["view"] = modified_comment_data[
                            "body"
                        ]["view"].copy()
                if "body" not in modified_comment_data:
                    modified_comment_data["body"] = {}
                if "view" not in modified_comment_data["body"]:
                    modified_comment_data["body"]["view"] = {}

                modified_comment_data["body"]["view"]["value"] = (
                    processed_markdown if return_markdown else processed_html
                )

                comment_models.append(
                    ConfluenceComment.from_api_response(
                        modified_comment_data, base_url=self.config.url
                    )
                )

            return merge_truncation(comment_models, *read_parts)

        except KeyError as e:
            logger.error(f"Missing key in inline comment data: {str(e)}")
            return []
        except requests.RequestException as e:
            logger.error(f"Network error when fetching inline comments: {str(e)}")
            return []
        except (ValueError, TypeError) as e:
            logger.error(f"Error processing inline comment data: {str(e)}")
            return []
        except Exception as e:  # noqa: BLE001 - Intentional fallback with full logging
            logger.error(f"Unexpected error fetching inline comments: {str(e)}")
            logger.debug("Full exception details for inline comments:", exc_info=True)
            return []

    def add_inline_comment(
        self,
        page_id: str,
        content: str,
        text_selection: str,
        text_selection_match_count: int = 1,
        text_selection_match_index: int = 0,
        content_format: str = "markdown",
    ) -> ConfluenceComment | None:
        """Add an inline comment anchored to a text selection on a page.

        For Cloud instances, uses the v2 API (POST /api/v2/inline-comments).
        For Server/DC, uses the v1 API (POST /rest/api/content/).

        Args:
            page_id: The ID of the page to add the inline comment to
            content: The comment content
            text_selection: The text on the page to anchor the comment to
            text_selection_match_count: How many times the text appears
                on the page
            text_selection_match_index: Zero-based index of which occurrence
                to anchor to
            content_format: Format of content, ``'markdown'`` (default,
                converted to storage format) or ``'storage'`` (sent as is)

        Returns:
            ConfluenceComment object if successful, None otherwise

        Raises:
            ValueError: If ``content_format`` is not ``'markdown'`` or
                ``'storage'``.
        """
        content = self._comment_body_to_storage(content, content_format)
        try:
            v2_adapter = self._inline_v2_adapter
            if v2_adapter:
                response = v2_adapter.create_inline_comment(
                    page_id=page_id,
                    body=content,
                    text_selection=text_selection,
                    text_selection_match_count=text_selection_match_count,
                    text_selection_match_index=text_selection_match_index,
                )
                space_key = ""
            else:
                # v1 API: POST /rest/api/content/ with inline location
                #
                # Confluence Server/DC requires four additional fields in
                # inlineProperties that the frontend editor normally supplies
                # when a user highlights text. Omitting any of them yields
                # HTTP 400 with validation keys matchIndex / lastFetchTime /
                # serializedHighlights. Field formats (discovered empirically
                # against Confluence DC 8.x):
                #
                # - numMatches:          int, total occurrences on the page
                # - matchIndex:          int, zero-based index of the match
                # - lastFetchTime:       str, Unix epoch in **milliseconds**
                # - serializedHighlights: str, JSON-encoded nested array of
                #                         the form [["<selected text>"]]
                last_fetch_time_ms = str(int(time.time() * 1000))
                serialized_highlights = json.dumps([[text_selection]])
                data: dict[str, Any] = {
                    "type": "comment",
                    "container": {
                        "id": page_id,
                        "type": "page",
                    },
                    "body": {
                        "storage": {
                            "value": content,
                            "representation": "storage",
                        },
                    },
                    "extensions": {
                        "location": "inline",
                        "inlineProperties": {
                            "originalSelection": text_selection,
                            "numMatches": text_selection_match_count,
                            "matchIndex": text_selection_match_index,
                            "lastFetchTime": last_fetch_time_ms,
                            "serializedHighlights": serialized_highlights,
                        },
                    },
                }
                page = self.confluence.get_page_by_id(page_id=page_id, expand="space")
                space_key = page.get("space", {}).get("key", "")
                response = self.confluence.post("rest/api/content/", data=data)

            if not response:
                logger.error("Failed to add inline comment: empty response")
                return None

            return self._process_comment_response(response, space_key)

        except requests.RequestException as e:
            logger.error(f"Network error when adding inline comment: {str(e)}")
            return None
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Error processing inline comment data: {str(e)}")
            return None
        except Exception as e:  # noqa: BLE001 - Intentional fallback with full logging
            logger.error(f"Unexpected error adding inline comment: {str(e)}")
            logger.debug(
                "Full exception details for adding inline comment:",
                exc_info=True,
            )
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
        body = response.get("body") or {}
        if not isinstance(body, dict):
            body = {}

        # Under a space allowlist only the storage body is used: the view is
        # rendered by Confluence and can carry content from other spaces.
        representations = (
            ("storage",) if allowed_space_keys(self.config) else ("view", "storage")
        )
        body_html = ""
        for representation in representations:
            part = body.get(representation) or {}
            if isinstance(part, dict) and part.get("value"):
                body_html = str(part["value"])
                break

        _, processed_markdown = self.preprocessor.process_html_content(
            body_html,
            space_key=space_key,
            confluence_client=self.confluence,
        )

        modified_response = response.copy()
        if "body" in modified_response:
            modified_response["body"] = modified_response["body"].copy()
            if "view" in modified_response["body"]:
                modified_response["body"]["view"] = modified_response["body"][
                    "view"
                ].copy()
        if "body" not in modified_response:
            modified_response["body"] = {}
        if "view" not in modified_response["body"]:
            modified_response["body"]["view"] = {}

        modified_response["body"]["view"]["value"] = processed_markdown

        return ConfluenceComment.from_api_response(
            modified_response,
            base_url=self.config.url,
        )
