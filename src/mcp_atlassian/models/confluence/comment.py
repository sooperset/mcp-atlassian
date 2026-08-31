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
    parent_comment_id: str | None = None
    location: str | None = None  # "inline", "footer", or None
    marker_ref: str | None = None
    original_selection: str | None = None
    resolution_status: str | None = None

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
        if not isinstance(container, dict):
            container = {}
        if not title and container:
            title = container.get("title")

        # Extract parent comment ID from v2 or v1 format
        parent_comment_id: str | None = None
        if v2_parent := data.get("parentCommentId"):
            parent_comment_id = str(v2_parent)
        elif container and container.get("type") == "comment":
            parent_comment_id = str(container.get("id", ""))
        elif isinstance(data.get("ancestors"), list):
            for ancestor in reversed(data["ancestors"]):
                if (
                    isinstance(ancestor, dict)
                    and ancestor.get("type") == "comment"
                    and ancestor.get("id") is not None
                ):
                    parent_comment_id = str(ancestor["id"])
                    break

        extensions = data.get("extensions")
        if not isinstance(extensions, dict):
            extensions = {}

        # Extract inline anchor metadata from Server/DC v1 and Cloud v2 shapes.
        inline_properties = extensions.get("inlineProperties")
        if not isinstance(inline_properties, dict):
            inline_properties = {}
        v2_inline_properties = data.get("inlineCommentProperties")
        if not isinstance(v2_inline_properties, dict):
            v2_inline_properties = {}
        properties = data.get("properties")
        if not isinstance(properties, dict):
            properties = {}

        marker_ref_value = (
            inline_properties.get("markerRef")
            or properties.get("inlineMarkerRef")
            or properties.get("inline-marker-ref")
        )
        original_selection_value = (
            inline_properties.get("originalSelection")
            or properties.get("inlineOriginalSelection")
            or properties.get("inline-original-selection")
            or v2_inline_properties.get("textSelection")
        )

        resolution_status_value = data.get("resolutionStatus")
        resolution = extensions.get("resolution")
        if resolution_status_value is None and isinstance(resolution, dict):
            resolution_status_value = resolution.get("status")
        elif resolution_status_value is None and isinstance(resolution, str):
            resolution_status_value = resolution
        if resolution_status_value is None and isinstance(
            v2_inline_properties.get("resolved"), bool
        ):
            resolution_status_value = (
                "resolved" if v2_inline_properties["resolved"] else "open"
            )

        version = data.get("version")
        if not isinstance(version, dict):
            version = {}
        created = (
            data.get("created")
            or version.get("createdAt")
            or version.get("when")
            or EMPTY_STRING
        )
        updated = (
            data.get("updated")
            or version.get("createdAt")
            or version.get("when")
            or EMPTY_STRING
        )

        return cls(
            id=str(data.get("id", CONFLUENCE_DEFAULT_ID)),
            title=title,
            body=data.get("body", {}).get("view", {}).get("value", EMPTY_STRING),
            created=str(created),
            updated=str(updated),
            author=author,
            type=data.get("type", "comment"),
            parent_comment_id=parent_comment_id,
            location=extensions.get("location"),
            marker_ref=(str(marker_ref_value) if marker_ref_value else None),
            original_selection=(
                str(original_selection_value) if original_selection_value else None
            ),
            resolution_status=(
                str(resolution_status_value) if resolution_status_value else None
            ),
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

        if self.parent_comment_id:
            result["parent_comment_id"] = self.parent_comment_id

        if self.location:
            result["location"] = self.location

        if self.marker_ref:
            result["marker_ref"] = self.marker_ref

        if self.original_selection:
            result["original_selection"] = self.original_selection

        if self.resolution_status:
            result["resolution_status"] = self.resolution_status

        return result
