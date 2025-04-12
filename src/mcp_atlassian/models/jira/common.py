"""
Common Jira entity models.

This module provides Pydantic models for common Jira entities like users, statuses,
issue types, priorities, attachments, and time tracking.
"""

import logging
from typing import Any

from pydantic import Field

from ..base import ApiModel
from ..constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
    NONE_VALUE,
    UNASSIGNED,
    UNKNOWN,
)

logger = logging.getLogger(__name__)


class JiraUser(ApiModel):
    """
    Model representing a Jira user.
    """

    account_id: str | None = None
    display_name: str = UNASSIGNED
    email: str | None = None
    active: bool = True
    avatar_url: str | None = None
    time_zone: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraUser":
        """
        Create a JiraUser from a Jira API response.

        Args:
            data: The user data from the Jira API

        Returns:
            A JiraUser instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        avatar_url = None
        if avatars := data.get("avatarUrls"):
            if isinstance(avatars, dict):
                # Get the largest available avatar (48x48)
                avatar_url = avatars.get("48x48")
            else:
                logger.debug(f"Unexpected avatar data format: {type(avatars)}")

        return cls(
            account_id=data.get("accountId"),
            display_name=str(data.get("displayName", UNASSIGNED)),
            email=data.get("emailAddress"),
            active=bool(data.get("active", True)),
            avatar_url=avatar_url,
            time_zone=data.get("timeZone"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "display_name": self.display_name,
            "name": self.display_name,  # Add name for backward compatibility
            "email": self.email,
            "avatar_url": self.avatar_url,
        }


class JiraStatusCategory(ApiModel):
    """
    Model representing a Jira status category.
    """

    id: int = 0
    key: str = EMPTY_STRING
    name: str = UNKNOWN
    color_name: str = EMPTY_STRING

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraStatusCategory":
        """
        Create a JiraStatusCategory from a Jira API response.

        Args:
            data: The status category data from the Jira API

        Returns:
            A JiraStatusCategory instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Safely get and convert fields, handling potential type mismatches
        id_value = data.get("id", 0)
        try:
            # Ensure id is an integer
            id_value = int(id_value) if id_value is not None else 0
        except (ValueError, TypeError):
            id_value = 0

        return cls(
            id=id_value,
            key=str(data.get("key", EMPTY_STRING)),
            name=str(data.get("name", UNKNOWN)),
            color_name=str(data.get("colorName", EMPTY_STRING)),
        )


class JiraStatus(ApiModel):
    """
    Model representing a Jira issue status.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = UNKNOWN
    description: str | None = None
    icon_url: str | None = None
    category: JiraStatusCategory | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraStatus":
        """
        Create a JiraStatus from a Jira API response.

        Args:
            data: The status data from the Jira API

        Returns:
            A JiraStatus instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        category = None
        category_data = data.get("statusCategory")
        if category_data:
            category = JiraStatusCategory.from_api_response(category_data)

        # Ensure ID is a string (API sometimes returns integers)
        status_id = data.get("id", JIRA_DEFAULT_ID)
        if status_id is not None:
            status_id = str(status_id)

        return cls(
            id=status_id,
            name=str(data.get("name", UNKNOWN)),
            description=data.get("description"),
            icon_url=data.get("iconUrl"),
            category=category,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "name": self.name,
        }

        if self.category:
            result["category"] = self.category.name
            result["color"] = self.category.color_name

        return result


class JiraIssueType(ApiModel):
    """
    Model representing a Jira issue type.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = UNKNOWN
    description: str | None = None
    icon_url: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraIssueType":
        """
        Create a JiraIssueType from a Jira API response.

        Args:
            data: The issue type data from the Jira API

        Returns:
            A JiraIssueType instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Ensure ID is a string
        issue_type_id = data.get("id", JIRA_DEFAULT_ID)
        if issue_type_id is not None:
            issue_type_id = str(issue_type_id)

        return cls(
            id=issue_type_id,
            name=str(data.get("name", UNKNOWN)),
            description=data.get("description"),
            icon_url=data.get("iconUrl"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {"name": self.name}


class JiraPriority(ApiModel):
    """
    Model representing a Jira priority.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = NONE_VALUE
    description: str | None = None
    icon_url: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraPriority":
        """
        Create a JiraPriority from a Jira API response.

        Args:
            data: The priority data from the Jira API

        Returns:
            A JiraPriority instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Ensure ID is a string
        priority_id = data.get("id", JIRA_DEFAULT_ID)
        if priority_id is not None:
            priority_id = str(priority_id)

        return cls(
            id=priority_id,
            name=str(data.get("name", NONE_VALUE)),
            description=data.get("description"),
            icon_url=data.get("iconUrl"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {"name": self.name}


class JiraAttachment(ApiModel):
    """
    Model representing a Jira issue attachment.

    This model contains information about files attached to Jira issues,
    including the filename, size, content type, and download URL.
    """

    id: str = JIRA_DEFAULT_ID
    filename: str = EMPTY_STRING
    size: int = 0
    content_type: str | None = None
    created: str = EMPTY_STRING
    author: JiraUser | None = None
    url: str | None = None
    thumbnail_url: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraAttachment":
        """
        Create a JiraAttachment from a Jira API response.

        Args:
            data: The attachment data from the Jira API

        Returns:
            A JiraAttachment instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Extract author data
        author = None
        author_data = data.get("author")
        if author_data:
            author = JiraUser.from_api_response(author_data)

        # Ensure ID is a string
        attachment_id = data.get("id", JIRA_DEFAULT_ID)
        if attachment_id is not None:
            attachment_id = str(attachment_id)

        # Extract size with type safety
        size = data.get("size", 0)
        try:
            size = int(size) if size is not None else 0
        except (ValueError, TypeError):
            size = 0

        return cls(
            id=attachment_id,
            filename=str(data.get("filename", EMPTY_STRING)),
            size=size,
            content_type=data.get("mimeType"),
            created=str(data.get("created", EMPTY_STRING)),
            author=author,
            url=data.get("content"),  # This is actually the download URL
            thumbnail_url=data.get("thumbnail"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "filename": self.filename,
            "size": self.size,
            "url": self.url,
        }

        if self.content_type:
            result["content_type"] = self.content_type

        if self.author:
            result["author"] = self.author.to_simplified_dict()

        if self.thumbnail_url:
            result["thumbnail_url"] = self.thumbnail_url

        if self.created:
            result["created"] = self.created

        return result


class JiraTimetracking(ApiModel):
    """
    Model representing the time tracking information for a Jira issue.
    """

    original_estimate: str | None = Field(None, alias="originalEstimate")
    remaining_estimate: str | None = Field(None, alias="remainingEstimate")
    time_spent: str | None = Field(None, alias="timeSpent")
    original_estimate_seconds: int | None = Field(None, alias="originalEstimateSeconds")
    remaining_estimate_seconds: int | None = Field(
        None, alias="remainingEstimateSeconds"
    )
    time_spent_seconds: int | None = Field(None, alias="timeSpentSeconds")

    model_config = {
        "populate_by_name": True,
    }

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraTimetracking | None":
        """
        Create a JiraTimetracking from a Jira API response.

        Args:
            data: The timetracking data from the Jira API

        Returns:
            A JiraTimetracking instance or None if no data
        """
        if not data:
            return None

        # Handle non-dictionary data
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data for timetracking")
            return None

        return cls(**data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "original_estimate": self.original_estimate,
            "time_spent": self.time_spent,
            "remaining_estimate": self.remaining_estimate,
        }
