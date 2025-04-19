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
            **kwargs: Additional context parameters, including:
                - base_url: Base URL for constructing the page URL
                - include_body: Whether to include the page body (defaults to True)
                - content_format: Content format to use (defaults to "view")
                - content_override: Optional content to use instead of extracting from API response

        Returns:
            A ConfluencePage instance
        """
        if not data:
            return cls()

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

        # Process space
        space = None
        if space_data := data.get("space"):
            space = ConfluenceSpace.from_api_response(space_data)

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
            url = f"{base_url}/spaces/{data.get('space', {}).get('key')}/"
            url += f"pages/{data.get('id')}"

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
