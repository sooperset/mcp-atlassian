"""Module for Jira sprints operations."""

import logging
from typing import Any

import requests

from ..models.jira import JiraSprint
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class SprintsMixin(JiraClient):
    """Mixin for Jira sprints operations."""

    def get_all_sprints_from_board(
        self, board_id: str, state: str = None, start: int = 0, limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        Get all sprints from a board.

        Args:
            board_id: Board ID
            state: Sprint state (e.g., active, future, closed) if None, return all state sprints
            start: Start index
            limit: Maximum number of sprints to return

        Returns:
            List of sprints
        """
        try:
            sprints = self.jira.get_all_sprints_from_board(
                board_id=board_id,
                state=state,
                start=start,
                limit=limit,
            )
            return sprints.get("values", []) if isinstance(sprints, dict) else []
        except requests.HTTPError as e:
            logger.error(
                f"Error getting all sprints from board: {str(e.response.content)}"
            )
            return []
        except Exception as e:
            logger.error(f"Error getting all sprints from board: {str(e)}")
            return []

    def get_all_sprints_from_board_model(
        self, board_id: str, state: str = None, start: int = 0, limit: int = 50
    ) -> list[JiraSprint]:
        """
        Get all sprints as JiraSprint from a board.

        Args:
            board_id: Board ID
            state: Sprint state (e.g., active, future, closed) if None, return all state sprints
            start: Start index
            limit: Maximum number of sprints to return

        Returns:
            List of JiraSprint
        """
        sprints = self.get_all_sprints_from_board(
            board_id=board_id,
            state=state,
            start=start,
            limit=limit,
        )
        return [JiraSprint.from_api_response(sprint) for sprint in sprints]

    def create_sprint(
        self,
        board_id: str,
        sprint_name: str,
        start_date: str,
        end_date: str,
        goal: str = None,
    ) -> JiraSprint:
        """
        Create a new sprint.

        Args:
            sprint_name: Sprint name
            board_id: Board ID
            start_date: Start date in ISO format
            end_date: End date in ISO format
            goal: Sprint goal

        Returns:
            Created sprint details
        """

        try:
            sprint = self.jira.create_sprint(
                name=sprint_name,
                board_id=board_id,
                start_date=start_date,
                end_date=end_date,
                goal=goal,
            )

            logger.info(f"Sprint created: {sprint}")

            return JiraSprint.from_api_response(sprint)
        except requests.HTTPError as e:
            logger.error(f"Error creating sprint: {str(e.response.content)}")
            return {}
        except Exception as e:
            logger.error(f"Error creating sprint: {str(e)}")
            return {}
