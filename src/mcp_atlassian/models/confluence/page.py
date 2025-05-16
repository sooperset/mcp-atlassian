"""
Confluence page models.
This module provides Pydantic models for Confluence pages and their versions.
"""

import logging
import warnings
from typing import Any

from pydantic import Field

from ..base import ApiModel, TimestampMixin
from ..constants import (
    CONFLUENCE_DEFAULT_ID,
    EMPTY_STRING,
)

# Import other necessary models using relative imports
from .common import ConfluenceAttachment, ConfluenceUser
from .space import ConfluenceSpace

logger = logging.getLogger(__name__)


class ConfluenceVersion(ApiModel, TimestampMixin):
    """
    Model representing a Confluence page version.
    """

    number: int = 0
    when: str = EMPTY_STRING
    message: str | None = None
    by: ConfluenceUser | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ConfluenceVersion":
        """
        Create a ConfluenceVersion from a Confluence API response.

        Args:
            data: The version data from the Confluence API

        Returns:
            A ConfluenceVersion instance
        """
        if not data:
            return cls()

        by_user = None
        if by_data := data.get("by"):
            by_user = ConfluenceUser.from_api_response(by_data)

        return cls(
            number=data.get("number", 0),
            when=data.get("when", EMPTY_STRING),
            message=data.get("message"),
            by=by_user,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {"number": self.number, "when": self.format_timestamp(self.when)}

        if self.message:
            result["message"] = self.message

        if self.by:
            result["by"] = self.by.display_name

        return result


class ConfluencePage(ApiModel, TimestampMixin):
    """
    Model representing a Confluence page.

    This model includes the content, metadata, and version information
    for a Confluence page.
    """

    id: str = CONFLUENCE_DEFAULT_ID
    title: str = EMPTY_STRING
    type: str = "page"  # "page", "blogpost", etc.
    status: str = "current"
    space: ConfluenceSpace | None = None
    content: str = EMPTY_STRING
    content_format: str = "view"  # "view", "storage", etc.
    created: str = EMPTY_STRING
    updated: str = EMPTY_STRING
    author: ConfluenceUser | None = None
    version: ConfluenceVersion | None = None
    ancestors: list[dict[str, Any]] = Field(default_factory=list)
    children: dict[str, Any] = Field(default_factory=dict)
    attachments: list[ConfluenceAttachment] = Field(default_factory=list)
    url: str | None = None

    @property
    def page_content(self) -> str:
        """
        Alias for content to maintain compatibility with tests.

        Deprecated: Use content instead.
        """
        warnings.warn(
            "The 'page_content' property is deprecated. Use 'content' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.content

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "ConfluencePage":
        """
        Create a ConfluencePage from a Confluence API response.

        Args:
            data: The page data from the Confluence API
            **kwargs: Additional keyword arguments
                base_url: Base URL for constructing page URLs
                include_body: Whether to include body content
                content_override: Override the content value
                content_format: Override the content format
                is_cloud: Whether this is a cloud instance (affects URL format)

        Returns:
            A ConfluencePage instance
        """
        if not data:
            return cls()

        # Extract space information first to ensure it's available for URL construction
        space_data = data.get("space", {})
        if not space_data:
            # Try to extract space info from _expandable if available
            if expandable := data.get("_expandable", {}):
                if space_path := expandable.get("space"):
                    # Extract space key from REST API path
                    if space_path.startswith("/rest/api/space/"):
                        space_key = space_path.split("/rest/api/space/")[1]
                        space_data = {"key": space_key, "name": f"Space {space_key}"}

        # Create space model
        space = ConfluenceSpace.from_api_response(space_data)

        # Extract content based on format or use override if provided
        content = EMPTY_STRING
        content_format = kwargs.get("content_format", "view")
        include_body = kwargs.get("include_body", True)

        # Allow content override to be provided directly
        if content_override := kwargs.get("content_override"):
            content = content_override
        elif include_body and "body" in data:
            body = data.get("body", {})
            if content_format in body:
                content = body.get(content_format, {}).get("value", EMPTY_STRING)

        # Adjust content_format if convert_to_markdown is False and content is processed HTML
        convert_to_markdown = kwargs.get("convert_to_markdown", True)
        if not convert_to_markdown:
            content_format = "html"

        # Process author/creator
        author = None
        if author_data := data.get("author"):
            author = ConfluenceUser.from_api_response(author_data)

        # Process version
        version = None
        if version_data := data.get("version"):
            version = ConfluenceVersion.from_api_response(version_data)

        # Process attachments
        attachments = []
        if (
            attachments_data := data.get("children", {})
            .get("attachment", {})
            .get("results", [])
        ):
            attachments = [
                ConfluenceAttachment.from_api_response(attachment)
                for attachment in attachments_data
            ]

        # Process metadata timestamps
        created = EMPTY_STRING
        updated = EMPTY_STRING

        if history := data.get("history"):
            created = history.get("createdDate", EMPTY_STRING)
            updated = history.get("lastUpdated", {}).get("when", EMPTY_STRING)

            # Fall back to version date if no history is available
            if not updated and version and version.when:
                updated = version.when

        # Construct URL if base_url is provided
        url = None
        if base_url := kwargs.get("base_url"):
            page_id = data.get("id")

            # Use different URL format based on whether it's cloud or server
            is_cloud = kwargs.get("is_cloud", False)
            if is_cloud:
                # Cloud format: {base_url}/spaces/{space_key}/pages/{page_id}
                space_key = space.key if space and space.key else "unknown"
                url = f"{base_url}/spaces/{space_key}/pages/{page_id}"
            else:
                # Server format: {base_url}/pages/viewpage.action?pageId={page_id}
                url = f"{base_url}/pages/viewpage.action?pageId={page_id}"

        return cls(
            id=str(data.get("id", CONFLUENCE_DEFAULT_ID)),
            title=data.get("title", EMPTY_STRING),
            type=data.get("type", "page"),
            status=data.get("status", "current"),
            space=space,
            content=content,
            content_format=content_format,
            created=created,
            updated=updated,
            author=author,
            version=version,
            ancestors=data.get("ancestors", []),
            children=data.get("children", {}),
            attachments=attachments,
            url=url,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "created": self.format_timestamp(self.created),
            "updated": self.format_timestamp(self.updated),
            "url": self.url,
        }

        # Add space information if available
        if self.space:
            result["space"] = {"key": self.space.key, "name": self.space.name}

        # Add author information if available
        if self.author:
            result["author"] = self.author.display_name

        # Add version information if available
        if self.version:
            result["version"] = self.version.number

        # Add attachments if available
        result["attachments"] = [
            attachment.to_simplified_dict() for attachment in self.attachments
        ]

        # Add content if it's not empty
        if self.content and self.content_format:
            result["content"] = {"value": self.content, "format": self.content_format}

        # Add ancestors if there are any
        if self.ancestors:
            result["ancestors"] = [
                {"id": a.get("id"), "title": a.get("title")}
                for a in self.ancestors
                if "id" in a
            ]

        return result
