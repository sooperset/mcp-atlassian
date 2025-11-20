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
from .common import JiraUser

logger = logging.getLogger(__name__)


class JiraComment(ApiModel, TimestampMixin):
    """
    Model representing a Jira issue comment.
    """

    id: str = JIRA_DEFAULT_ID
    body: str = EMPTY_STRING
    created: str = EMPTY_STRING
    updated: str = EMPTY_STRING
    author: JiraUser | None = None

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

        # Get the body content
        body_content = EMPTY_STRING
        body = data.get("body")
        if body:
            # Check if this is Cloud (ADF format) or Server/DC (plain text)
            is_cloud = kwargs.get("is_cloud", False)
            if is_cloud and isinstance(body, dict):
                # Cloud uses ADF format
                from .adf_parser import parse_adf_to_text

                body_content = parse_adf_to_text(body)
            else:
                # Server/DC uses plain text
                body_content = str(body)

        return cls(
            id=comment_id,
            body=body_content,
            created=str(data.get("created", EMPTY_STRING)),
            updated=str(data.get("updated", EMPTY_STRING)),
            author=author,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "body": self.body,
        }

        if self.author:
            result["author"] = self.author.to_simplified_dict()

        if self.created:
            result["created"] = self.created

        if self.updated:
            result["updated"] = self.updated

        return result
