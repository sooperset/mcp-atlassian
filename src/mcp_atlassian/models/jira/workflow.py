"""
Jira workflow models.

This module provides Pydantic models for Jira workflow entities,
such as transitions between statuses.
"""

import logging
from typing import Any

from ..base import ApiModel
from ..constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
)
from .common import JiraStatus

logger = logging.getLogger(__name__)


class JiraTransition(ApiModel):
    """
    Model representing a Jira issue transition.

    This model contains information about possible status transitions
    for Jira issues, including the target status and related metadata.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = EMPTY_STRING
    to_status: JiraStatus | None = None
    has_screen: bool = False
    is_global: bool = False
    is_initial: bool = False
    is_conditional: bool = False

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraTransition":
        """
        Create a JiraTransition from a Jira API response.

        Args:
            data: The transition data from the Jira API

        Returns:
            A JiraTransition instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Extract to_status data if available
        to_status = None
        if to := data.get("to"):
            if isinstance(to, dict):
                to_status = JiraStatus.from_api_response(to)

        # Ensure ID is a string
        transition_id = data.get("id", JIRA_DEFAULT_ID)
        if transition_id is not None:
            transition_id = str(transition_id)

        # Extract boolean flags with type safety
        has_screen = bool(data.get("hasScreen", False))
        is_global = bool(data.get("isGlobal", False))
        is_initial = bool(data.get("isInitial", False))
        is_conditional = bool(data.get("isConditional", False))

        return cls(
            id=transition_id,
            name=str(data.get("name", EMPTY_STRING)),
            to_status=to_status,
            has_screen=has_screen,
            is_global=is_global,
            is_initial=is_initial,
            is_conditional=is_conditional,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "name": self.name,
        }

        if self.to_status:
            result["to_status"] = self.to_status.to_simplified_dict()

        return result
