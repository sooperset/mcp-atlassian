"""Module for Jira boards operations."""

import logging
from typing import Any

import requests

from ..models.jira import JiraBoard
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class BoardsMixin(JiraClient):
    """Mixin for Jira boards operations."""

    def get_all_agile_boards(
        self,
        board_name: str | None = None,
        project_key: str | None = None,
        board_type: str | None = None,
        start: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get boards from Jira by name, project key, or type.

        Args:
            board_name: The name of board, support fuzzy search
            project_key: Project key (e.g., PROJECT-123)
            board_type: Board type (e.g., scrum, kanban)
            start: Start index
            limit: Maximum number of boards to return

        Returns:
            List of board information

        Raises:
            Exception: If there is an error retrieving the boards
        """
        try:
            boards = self.jira.get_all_agile_boards(
                board_name=board_name,
                project_key=project_key,
                board_type=board_type,
                start=start,
                limit=limit,
            )
            return boards.get("values", []) if isinstance(boards, dict) else []
        except requests.HTTPError as e:
            logger.error(f"Error getting all agile boards: {str(e.response.content)}")
            return []
        except Exception as e:
            logger.error(f"Error getting all agile boards: {str(e)}")
            return []

    def get_all_agile_boards_model(
        self,
        board_name: str | None = None,
        project_key: str | None = None,
        board_type: str | None = None,
        start: int = 0,
        limit: int = 50,
    ) -> list[JiraBoard]:
        """
        Get boards as JiraBoards model from Jira by name, project key, or type.

        Args:
            board_name: The name of board, support fuzzy search
            project_key: Project key (e.g., PROJECT-123)
            board_type: Board type (e.g., scrum, kanban)
            start: Start index
            limit: Maximum number of boards to return

        Returns:
            List of JiraBoards model with board information

        Raises:
            Exception: If there is an error retrieving the boards
        """
        boards = self.get_all_agile_boards(
            board_name=board_name,
            project_key=project_key,
            board_type=board_type,
            start=start,
            limit=limit,
        )
        return [JiraBoard.from_api_response(board) for board in boards]
