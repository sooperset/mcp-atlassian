"""
Jira project models.

This module provides Pydantic models for Jira projects.
"""

import logging
from typing import Any

from ..base import ApiModel
from ..constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_PROJECT,
    UNKNOWN,
)
from .common import JiraUser

logger = logging.getLogger(__name__)


class JiraProject(ApiModel):
    """
    Model representing a Jira project.

    This model contains the basic information about a Jira project,
    including its key, name, and category.
    """

    id: str = JIRA_DEFAULT_PROJECT
    key: str = EMPTY_STRING
    name: str = UNKNOWN
    description: str | None = None
    lead: JiraUser | None = None
    url: str | None = None
    category_name: str | None = None
    avatar_url: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraProject":
        """
        Create a JiraProject from a Jira API response.

        Args:
            data: The project data from the Jira API

        Returns:
            A JiraProject instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Extract lead data if available
        lead = None
        lead_data = data.get("lead")
        if lead_data:
            lead = JiraUser.from_api_response(lead_data)

        # Get avatar URL from avatarUrls if available
        avatar_url = None
        if avatars := data.get("avatarUrls"):
            if isinstance(avatars, dict):
                # Get the largest available avatar (48x48)
                avatar_url = avatars.get("48x48")

        # Get project category name if available
        category_name = None
        if project_category := data.get("projectCategory"):
            if isinstance(project_category, dict):
                category_name = project_category.get("name")

        # Ensure ID is a string
        project_id = data.get("id", JIRA_DEFAULT_PROJECT)
        if project_id is not None:
            project_id = str(project_id)

        return cls(
            id=project_id,
            key=str(data.get("key", EMPTY_STRING)),
            name=str(data.get("name", UNKNOWN)),
            description=data.get("description"),
            lead=lead,
            url=data.get("self"),  # API URL for the project
            category_name=category_name,
            avatar_url=avatar_url,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "key": self.key,
            "name": self.name,
        }

        if self.description:
            result["description"] = self.description

        if self.category_name:
            result["category"] = self.category_name

        if self.avatar_url:
            result["avatar_url"] = self.avatar_url

        if self.lead:
            result["lead"] = self.lead.to_simplified_dict()

        return result
