"""
Jira comment models.

This module provides Pydantic models for Jira comments.
"""

import logging
from typing import Any

from ..base import ApiModel, TimestampMixin
from ..constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
)
from .adf import adf_to_text
from .common import JiraUser

logger = logging.getLogger(__name__)


def parse_comment_visibility(value: Any) -> dict[str, str] | None:
    """Extract the visibility fields returned by Jira.

    Args:
        value: The raw visibility value from a comment response.

    Returns:
        A new dictionary with available string fields, or None if absent.
    """
    if not isinstance(value, dict):
        return None
    visibility = {
        key: item
        for key in ("type", "value", "identifier")
        if isinstance(item := value.get(key), str)
    }
    return visibility or None


class JiraComment(ApiModel, TimestampMixin):
    """
    Model representing a Jira issue comment.
    """

    id: str = JIRA_DEFAULT_ID
    body: str = EMPTY_STRING
    created: str = EMPTY_STRING
    updated: str = EMPTY_STRING
    author: JiraUser | None = None
    visibility: dict[str, str] | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraComment":
        """
        Create a JiraComment from a Jira API response.

        Args:
            data: The comment data from the Jira API

        Returns:
            A JiraComment instance
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
        comment_id = data.get("id", JIRA_DEFAULT_ID)
        if comment_id is not None:
            comment_id = str(comment_id)

        # Get the body content - can be string (legacy) or ADF dict (Jira Cloud)
        body_content = EMPTY_STRING
        body = data.get("body")
        if isinstance(body, dict):
            # Handle Atlassian Document Format (ADF)
            converted = adf_to_text(body)
            body_content = converted if converted else EMPTY_STRING
        elif body:
            # Handle plain text or HTML content
            body_content = str(body)

        return cls(
            id=comment_id,
            body=body_content,
            created=str(data.get("created", EMPTY_STRING)),
            updated=str(data.get("updated", EMPTY_STRING)),
            author=author,
            visibility=parse_comment_visibility(data.get("visibility")),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "body": self.body,
        }

        if self.author:
            result["author"] = self.author.to_simplified_dict()

        if self.created:
            result["created"] = self.created

        if self.updated:
            result["updated"] = self.updated

        if self.visibility is not None:
            result["visibility"] = self.visibility.copy()

        return result
