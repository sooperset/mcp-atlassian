"""
Confluence comment models.
This module provides Pydantic models for Confluence page comments.
"""

import logging
from typing import Any

from ..base import ApiModel, TimestampMixin
from ..constants import (
    CONFLUENCE_DEFAULT_ID,
    EMPTY_STRING,
)

# Import other necessary models using relative imports
from .common import ConfluenceUser

logger = logging.getLogger(__name__)


class ConfluenceComment(ApiModel, TimestampMixin):
    """
    Model representing a Confluence comment.
    """

    id: str = CONFLUENCE_DEFAULT_ID
    title: str | None = None
    body: str = EMPTY_STRING
    created: str = EMPTY_STRING
    updated: str = EMPTY_STRING
    author: ConfluenceUser | None = None
    type: str = "comment"  # "comment", "page", etc.

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ConfluenceComment":
        """
        Create a ConfluenceComment from a Confluence API response.

        Args:
            data: The comment data from the Confluence API

        Returns:
            A ConfluenceComment instance
        """
        if not data:
            return cls()

        author = None
        if author_data := data.get("author"):
            author = ConfluenceUser.from_api_response(author_data)
        # Try to get author from version.by if direct author is not available
        elif version_data := data.get("version"):
            if by_data := version_data.get("by"):
                author = ConfluenceUser.from_api_response(by_data)

        # For title, try to extract from different locations
        title = data.get("title")
        container = data.get("container")
        if not title and container:
            title = container.get("title")

        return cls(
            id=str(data.get("id", CONFLUENCE_DEFAULT_ID)),
            title=title,
            body=data.get("body", {}).get("view", {}).get("value", EMPTY_STRING),
            created=data.get("created", EMPTY_STRING),
            updated=data.get("updated", EMPTY_STRING),
            author=author,
            type=data.get("type", "comment"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "body": self.body,
            "created": self.format_timestamp(self.created),
            "updated": self.format_timestamp(self.updated),
        }

        if self.title:
            result["title"] = self.title

        if self.author:
            result["author"] = self.author.display_name

        return result
