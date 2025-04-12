"""
Jira agile models.

This module provides Pydantic models for Jira agile entities,
such as boards and sprints.
"""

import logging
from typing import Any

from ..base import ApiModel
from ..constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
    UNKNOWN,
)

logger = logging.getLogger(__name__)


class JiraBoard(ApiModel):
    """
    Model representing a Jira board.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = UNKNOWN
    type: str = UNKNOWN

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraBoard":
        """
        Create a JiraBoard from a Jira API response.

        Args:
            data: The board data from the Jira API

        Returns:
            A JiraBoard instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Ensure ID is a string
        board_id = data.get("id", JIRA_DEFAULT_ID)
        if board_id is not None:
            board_id = str(board_id)

        # We assume boards always have a name and type, but enforce strings
        board_name = str(data.get("name", UNKNOWN))
        board_type = str(data.get("type", UNKNOWN))

        return cls(
            id=board_id,
            name=board_name,
            type=board_type,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
        }


class JiraSprint(ApiModel):
    """
    Model representing a Jira sprint.
    """

    id: str = JIRA_DEFAULT_ID
    state: str = UNKNOWN
    name: str = UNKNOWN
    start_date: str = EMPTY_STRING
    end_date: str = EMPTY_STRING
    activated_date: str = EMPTY_STRING
    origin_board_id: str = JIRA_DEFAULT_ID
    goal: str = EMPTY_STRING
    synced: bool = False
    auto_start_stop: bool = False

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraSprint":
        """
        Create a JiraSprint from a Jira API response.

        Args:
            data: The sprint data from the Jira API

        Returns:
            A JiraSprint instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Ensure ID and origin board ID are strings
        sprint_id = data.get("id", JIRA_DEFAULT_ID)
        if sprint_id is not None:
            sprint_id = str(sprint_id)

        origin_board_id = data.get("originBoardId", JIRA_DEFAULT_ID)
        if origin_board_id is not None:
            origin_board_id = str(origin_board_id)

        # Boolean fields
        synced = bool(data.get("synced", False))
        auto_start_stop = bool(data.get("autoStartStop", False))

        return cls(
            id=sprint_id,
            state=str(data.get("state", UNKNOWN)),
            name=str(data.get("name", UNKNOWN)),
            start_date=str(data.get("startDate", EMPTY_STRING)),
            end_date=str(data.get("endDate", EMPTY_STRING)),
            activated_date=str(data.get("activatedDate", EMPTY_STRING)),
            origin_board_id=origin_board_id,
            goal=str(data.get("goal", EMPTY_STRING)),
            synced=synced,
            auto_start_stop=auto_start_stop,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "name": self.name,
            "state": self.state,
        }

        if self.goal and self.goal != EMPTY_STRING:
            result["goal"] = self.goal

        # Only include dates if they're not empty
        if self.start_date and self.start_date != EMPTY_STRING:
            result["start_date"] = self.start_date

        if self.end_date and self.end_date != EMPTY_STRING:
            result["end_date"] = self.end_date

        return result
