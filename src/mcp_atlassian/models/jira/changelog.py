"""
Jira changelog models.

This module provides Pydantic models for Jira changelog entries.
"""

import logging
from typing import Any

from pydantic import Field

from ..base import ApiModel, TimestampMixin
from ..constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
)
from .common import JiraUser

logger = logging.getLogger(__name__)


class JiraChangeItem(ApiModel):
    """
    Model representing a single change item within a changelog entry.

    Each change item represents a field that was modified, including
    its previous and new values.
    """

    field: str = EMPTY_STRING
    fieldtype: str = EMPTY_STRING
    from_string: str | None = None
    to_string: str | None = None
    from_id: str | None = None
    to_id: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraChangeItem":
        """
        Create a JiraChangeItem from a Jira API response.

        Args:
            data: The change item data from the Jira API

        Returns:
            A JiraChangeItem instance
        """
        if not data or not isinstance(data, dict):
            return cls()

        return cls(
            field=str(data.get("field", EMPTY_STRING)),
            fieldtype=str(data.get("fieldtype", EMPTY_STRING)),
            from_string=data.get("fromString"),
            to_string=data.get("toString"),
            from_id=data.get("from"),
            to_id=data.get("to"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "field": self.field,
            "fieldtype": self.fieldtype,
        }

        if self.from_string is not None:
            result["from_string"] = self.from_string

        if self.to_string is not None:
            result["to_string"] = self.to_string

        if self.from_id is not None:
            result["from_id"] = self.from_id

        if self.to_id is not None:
            result["to_id"] = self.to_id

        return result


class JiraChangelog(ApiModel, TimestampMixin):
    """
    Model representing a Jira issue changelog entry.

    A changelog entry represents a set of changes made to an issue at a specific time,
    including who made the changes and what was changed.
    """

    id: str = JIRA_DEFAULT_ID
    author: JiraUser | None = None
    created: str = EMPTY_STRING
    items: list[JiraChangeItem] = Field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraChangelog":
        """
        Create a JiraChangelog from a Jira API response.

        Args:
            data: The changelog data from the Jira API

        Returns:
            A JiraChangelog instance
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
        changelog_id = data.get("id", JIRA_DEFAULT_ID)
        if changelog_id is not None:
            changelog_id = str(changelog_id)

        # Process change items
        items = []
        items_data = data.get("items", [])
        if isinstance(items_data, list):
            for item_data in items_data:
                item = JiraChangeItem.from_api_response(item_data)
                items.append(item)

        return cls(
            id=changelog_id,
            author=author,
            created=str(data.get("created", EMPTY_STRING)),
            items=items,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {}

        if self.items:
            result["items"] = [item.to_simplified_dict() for item in self.items]

        if self.author:
            result["author"] = self.author.to_simplified_dict()

        if self.created:
            result["created"] = self.created

        return result
