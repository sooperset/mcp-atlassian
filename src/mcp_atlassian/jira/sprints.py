"""Module for Jira sprints operations."""

import datetime
import logging
from typing import Any

import requests

from ..models.jira import JiraSprint
from ..utils import parse_date
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class SprintsMixin(JiraClient):
    """Mixin for Jira sprints operations."""

    def get_all_sprints_from_board(
        self, board_id: str, state: str | None = None, start: int = 0, limit: int = 50
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
        self, board_id: str, state: str | None = None, start: int = 0, limit: int = 50
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

    def update_sprint(
        self,
        sprint_id: str,
        sprint_name: str | None,
        state: str | None,
        start_date: str | None,
        end_date: str | None,
        goal: str | None,
    ) -> JiraSprint | None:
        """
        Update a sprint.

        Args:
            sprint_id: Sprint ID
            sprint_name: New name for the sprint (optional)
            state: New state for the sprint (future|active|closed - optional)
            start_date: New start date for the sprint (optional)
            end_date: New end date for the sprint (optional)
            goal: New goal for the sprint (optional)

        Returns:
            Updated sprint
        """
        data = {}
        if sprint_name:
            data["name"] = sprint_name
        if state and state not in ["future", "active", "closed"]:
            logger.warning("Invalid state. Valid states are: future, active, closed.")
            return None
        elif state:
            data["state"] = state
        if start_date:
            data["startDate"] = start_date
        if end_date:
            data["endDate"] = end_date
        if goal:
            data["goal"] = goal
        if not sprint_id:
            logger.warning("Sprint ID is required.")
            return None
        try:
            updated_sprint = self.jira.update_partially_sprint(
                sprint_id=sprint_id,
                data=data,
            )

            if not isinstance(updated_sprint, dict):
                msg = f"Unexpected return value type from `SprintMixin.update_sprint`: {type(updated_sprint)}"
                logger.error(msg)
                raise TypeError(msg)

            return JiraSprint.from_api_response(updated_sprint)
        except requests.HTTPError as e:
            logger.error(f"Error updating sprint: {str(e.response.content)}")
            return None
        except Exception as e:
            logger.error(f"Error updating sprint: {str(e)}")
            return None

    def create_sprint(
        self,
        board_id: str,
        sprint_name: str,
        start_date: str,
        end_date: str,
        goal: str | None = None,
    ) -> JiraSprint:
        """
        Create a new sprint.

        Args:
            board_id: Board ID
            sprint_name: Sprint name
            start_date: Start date in ISO format
            end_date: End date in ISO format
            goal: Sprint goal

        Returns:
            Created sprint details
        """

        if not start_date:
            raise ValueError("Start date is required.")

        # validate start date format
        parsed_start_date = parse_date(start_date)

        if parsed_start_date is None:
            raise ValueError("Start date is required.")

        # validate start date is not in the past
        if parsed_start_date < datetime.datetime.now(datetime.timezone.utc):
            raise ValueError("Start date cannot be in the past.")

        # validate end date format
        if end_date:
            parsed_end_date = parse_date(end_date)
            if parsed_end_date is not None and parsed_start_date >= parsed_end_date:
                raise ValueError("Start date must be before end date.")

        try:
            sprint = self.jira.create_sprint(
                name=sprint_name,
                board_id=board_id,
                start_date=start_date,
                end_date=end_date,
                goal=goal,
            )

            logger.info(f"Sprint created: {sprint}")

            if not isinstance(sprint, dict):
                msg = f"Unexpected return value type from `SprintMixin.create_sprint`: {type(sprint)}"
                logger.error(msg)
                raise TypeError(msg)

            return JiraSprint.from_api_response(sprint)

        except requests.HTTPError as e:
            logger.error(f"Error creating sprint: {str(e.response.content)}")
            raise
        except Exception as e:
            logger.error(f"Error creating sprint: {str(e)}")
            raise
