"""
Jira sprint models.
"""

from typing import Any

from ..base import ApiModel


class JiraSprintInfo(ApiModel):
    """
    Model representing Jira sprint information.
    """

    id: int | None = None
    name: str | None = None
    state: str | None = None
    board_id: int | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraSprintInfo":
        """
        Create a JiraSprintInfo from a Jira API response.
        """
        if not data:
            return cls()

        return cls(
            id=data.get("id"),
            name=data.get("name"),
            state=data.get("state"),
            board_id=data.get("boardId"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "boardId": self.board_id,
        }
