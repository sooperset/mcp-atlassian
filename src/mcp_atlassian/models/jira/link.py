"""
Jira issue link type models.

This module provides Pydantic models for Jira issue link types.
"""

import logging
from typing import Any

from ..base import ApiModel
from ..constants import EMPTY_STRING, JIRA_DEFAULT_ID, UNKNOWN

logger = logging.getLogger(__name__)


class JiraIssueLinkType(ApiModel):
    """
    Model representing a Jira issue link type.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = UNKNOWN
    inward: str = EMPTY_STRING
    outward: str = EMPTY_STRING
    self_url: str | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraIssueLinkType":
        """
        Create a JiraIssueLinkType from a Jira API response.

        Args:
            data: The issue link type data from the Jira API

        Returns:
            A JiraIssueLinkType instance
        """
        if not data:
            return cls()

        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        link_type_id = data.get("id", JIRA_DEFAULT_ID)
        if link_type_id is not None:
            link_type_id = str(link_type_id)

        return cls(
            id=link_type_id,
            name=str(data.get("name", UNKNOWN)),
            inward=str(data.get("inward", EMPTY_STRING)),
            outward=str(data.get("outward", EMPTY_STRING)),
            self_url=data.get("self"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "name": self.name,
            "inward": self.inward,
            "outward": self.outward,
        }

        if self.self_url:
            result["self"] = self.self_url

        return result
