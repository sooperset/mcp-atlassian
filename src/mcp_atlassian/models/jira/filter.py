"""
Jira filter models.

This module provides Pydantic models for Jira saved filters.
"""

import logging
from typing import Any

from ..base import ApiModel
from ..constants import EMPTY_STRING
from .common import JiraUser

logger = logging.getLogger(__name__)


class JiraFilter(ApiModel):
    """
    Model representing a Jira saved filter.
    """

    id: str = EMPTY_STRING
    name: str = EMPTY_STRING
    description: str | None = None
    jql: str = EMPTY_STRING
    owner: JiraUser | None = None
    url: str | None = None
    favourite: bool = False

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraFilter":
        """
        Create a JiraFilter from a Jira API response.

        Args:
            data: The filter data from the Jira API

        Returns:
            A JiraFilter instance
        """
        if not data:
            return cls()

        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        owner = None
        owner_data = data.get("owner")
        if owner_data:
            owner = JiraUser.from_api_response(owner_data)

        filter_id = data.get("id", EMPTY_STRING)
        if filter_id is not None:
            filter_id = str(filter_id)

        return cls(
            id=filter_id,
            name=str(data.get("name", EMPTY_STRING)),
            description=data.get("description"),
            jql=str(data.get("jql", EMPTY_STRING)),
            owner=owner,
            url=data.get("self"),
            favourite=bool(data.get("favourite", False)),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "jql": self.jql,
            "favourite": self.favourite,
        }

        if self.description:
            result["description"] = self.description

        if self.owner:
            result["owner"] = self.owner.to_simplified_dict()

        return result
