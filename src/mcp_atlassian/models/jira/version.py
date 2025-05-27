from typing import Any

from ..base import ApiModel


class JiraVersion(ApiModel):
    """
    Model representing a Jira project version (fix version).
    """

    id: str
    name: str
    description: str | None = None
    startDate: str | None = None  # noqa: N815
    releaseDate: str | None = None  # noqa: N815
    released: bool = False
    archived: bool = False

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraVersion":
        """Create JiraVersion from API response."""
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            description=data.get("description"),
            startDate=data.get("startDate"),
            releaseDate=data.get("releaseDate"),
            released=bool(data.get("released", False)),
            archived=bool(data.get("archived", False)),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simple dict for API output."""
        result = {
            "id": self.id,
            "name": self.name,
            "released": self.released,
            "archived": self.archived,
        }
        if self.description is not None:
            result["description"] = self.description
        if self.startDate is not None:
            result["startDate"] = self.startDate
        if self.releaseDate is not None:
            result["releaseDate"] = self.releaseDate
        return result
