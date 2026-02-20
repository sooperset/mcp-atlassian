"""
Common Confluence entity models.
This module provides Pydantic models for common Confluence entities like users
and attachments.
"""

import logging
import warnings
from typing import Any

from ..base import ApiModel
from ..constants import (
    UNASSIGNED,
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

    Contains information about files attached to Confluence content (pages, blog posts),
    including filename, size, media type, download URL, and version information.
    """

    id: str | None = None
    type: str | None = None
    status: str | None = None
    title: str | None = None
    media_type: str | None = None
    file_size: int | None = None
    download_url: str | None = None
    version_number: int | None = None
    version_when: str | None = None
    created: str | None = None
    author_display_name: str | None = None
    author_account_id: str | None = None

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

        # Extract version information if available
        version_data = data.get("version", {})
        version_number = version_data.get("number") if version_data else None
        version_when = version_data.get("when") if version_data else None

        # Extract author information
        author_data = (
            version_data.get("by", {})
            if version_data
            else data.get("metadata", {}).get("author", {})
        )
        author_display_name = author_data.get("displayName") if author_data else None
        author_account_id = author_data.get("accountId") if author_data else None

        # Extract download URL from _links
        links = data.get("_links", {})
        download_url = links.get("download") if links else None

        return cls(
            id=data.get("id"),
            type=data.get("type"),
            status=data.get("status"),
            title=data.get("title"),
            media_type=data.get("extensions", {}).get("mediaType"),
            file_size=data.get("extensions", {}).get("fileSize"),
            download_url=download_url,
            version_number=version_number,
            version_when=version_when,
            created=data.get("created"),
            author_display_name=author_display_name,
            author_account_id=author_account_id,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "title": self.title,
            "media_type": self.media_type,
            "file_size": self.file_size,
        }

        # Add optional fields only if they exist
        if self.download_url:
            result["download_url"] = self.download_url
        if self.version_number is not None:
            result["version_number"] = self.version_number
        if self.version_when:
            result["version_when"] = self.version_when
        if self.created:
            result["created"] = self.created
        if self.author_display_name:
            result["author_display_name"] = self.author_display_name

        return result
