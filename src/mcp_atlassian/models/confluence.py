"""
Pydantic models for Confluence API responses.

This module provides type-safe models for working with Confluence API data,
including user information, spaces, pages, and search results.

Key models:
- ConfluencePage: Complete model for Confluence page content and metadata
- ConfluenceSpace: Space information and settings
- ConfluenceUser: User account details
- ConfluenceSearchResult: Container for Confluence search (CQL) results
- ConfluenceComment: Page and inline comments
- ConfluenceVersion: Content versioning information

Usage examples:

    # Get a typed page model
    from mcp_atlassian.confluence import ConfluenceClient

    client = ConfluenceClient.from_env()
    page = client.get_page_content("123456789")

    # Access typed properties with auto-completion
    print(f"Page: {page.title}")
    print(f"Space: {page.space.name} ({page.space.key})")
    print(f"Last updated: {page.format_timestamp(page.updated)}")

    # Get all pages in a space
    pages = client.get_space_pages("SPACEKEY", limit=10)
    for page in pages:
        print(f"- {page.title}")

    # All models support conversion from/to API responses
    custom_page = ConfluencePage.from_api_response(api_data)
    simplified = custom_page.to_simplified_dict()
"""

import logging
import warnings
from typing import Any

from pydantic import Field, model_validator

from .base import ApiModel, TimestampMixin
from .constants import (
    CONFLUENCE_DEFAULT_ID,
    EMPTY_STRING,
    UNASSIGNED,
    UNKNOWN,
)

logger = logging.getLogger(__name__)


class ConfluenceUser(ApiModel):
    """
    Model representing a Confluence user.
    """

    account_id: str | None = None
    display_name: str = UNASSIGNED
    email: str | None = None
    profile_picture: str | None = None
    is_active: bool = True
    locale: str | None = None

    @property
    def name(self) -> str:
        """
        Alias for display_name to maintain compatibility with tests.

        Deprecated: Use display_name instead.
        """
        warnings.warn(
            "The 'name' property is deprecated. Use 'display_name' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.display_name

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "ConfluenceUser":
        """
        Create a ConfluenceUser from a Confluence API response.

        Args:
            data: The user data from the Confluence API

        Returns:
            A ConfluenceUser instance
        """
        if not data:
            return cls()

        profile_pic = None
        if pic_data := data.get("profilePicture"):
            # Use the full path to the profile picture
            profile_pic = pic_data.get("path")

        return cls(
            account_id=data.get("accountId"),
            display_name=data.get("displayName", UNASSIGNED),
            email=data.get("email"),
            profile_picture=profile_pic,
            is_active=data.get("accountStatus") == "active",
            locale=data.get("locale"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "display_name": self.display_name,
            "email": self.email,
            "profile_picture": self.profile_picture,
        }


class ConfluenceAttachment(ApiModel):
    """
    Model representing a Confluence attachment.
    """

    id: str | None = None
    type: str | None = None
    status: str | None = None
    title: str | None = None
    media_type: str | None = None
    file_size: int | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ConfluenceAttachment":
        """
        Create a ConfluenceAttachment from a Confluence API response.

        Args:
            data: The attachment data from the Confluence API

        Returns:
            A ConfluenceAttachment instance
        """
        if not data:
            return cls()

        return cls(
            id=data.get("id"),
            type=data.get("type"),
            status=data.get("status"),
            title=data.get("title"),
            media_type=data.get("extensions", {}).get("mediaType"),
            file_size=data.get("extensions", {}).get("fileSize"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "title": self.title,
            "media_type": self.media_type,
            "file_size": self.file_size,
        }


class ConfluenceSpace(ApiModel):
    """
    Model representing a Confluence space.
    """

    id: str = CONFLUENCE_DEFAULT_ID
    key: str = EMPTY_STRING
    name: str = UNKNOWN
    type: str = "global"  # "global", "personal", etc.
    status: str = "current"  # "current", "archived", etc.

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ConfluenceSpace":
        """
        Create a ConfluenceSpace from a Confluence API response.

        Args:
            data: The space data from the Confluence API

        Returns:
            A ConfluenceSpace instance
        """
        if not data:
            return cls()

        return cls(
            id=str(data.get("id", CONFLUENCE_DEFAULT_ID)),
            key=data.get("key", EMPTY_STRING),
            name=data.get("name", UNKNOWN),
            type=data.get("type", "global"),
            status=data.get("status", "current"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "key": self.key,
            "name": self.name,
            "type": self.type,
            "status": self.status,
        }


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


class ConfluenceSearchResult(ApiModel, TimestampMixin):
    """
    Model representing a Confluence search (CQL) result.
    """

    total_size: int = 0
    start: int = 0
    limit: int = 0
    results: list[ConfluencePage] = Field(default_factory=list)
    cql_query: str | None = None
    search_duration: int | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ConfluenceSearchResult":
        """
        Create a ConfluenceSearchResult from a Confluence API response.

        Args:
            data: The search result data from the Confluence API
            **kwargs: Additional context parameters, including:
                - base_url: Base URL for constructing page URLs

        Returns:
            A ConfluenceSearchResult instance
        """
        if not data:
            return cls()

        # Convert search results to ConfluencePage models
        results = []
        for item in data.get("results", []):
            # In Confluence search, the content is nested inside the result item
            if content := item.get("content"):
                results.append(ConfluencePage.from_api_response(content, **kwargs))

        return cls(
            total_size=data.get("totalSize", 0),
            start=data.get("start", 0),
            limit=data.get("limit", 0),
            results=results,
            cql_query=data.get("cqlQuery"),
            search_duration=data.get("searchDuration"),
        )

    @model_validator(mode="after")
    def validate_search_result(self) -> "ConfluenceSearchResult":
        """Validate the search result and log warnings if needed."""
        if self.total_size > 0 and not self.results:
            logger.warning(
                "Search found %d pages but no content data was returned",
                self.total_size,
            )
        return self
