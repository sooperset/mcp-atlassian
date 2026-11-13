"""
Confluence folder models.
This module provides Pydantic models for Confluence Cloud folders.
"""

from typing import Any

from ..base import ApiModel
from ..constants import (
    CONFLUENCE_DEFAULT_ID,
    EMPTY_STRING,
)


class ConfluenceFolder(ApiModel):
    """
    Model representing a Confluence Cloud folder.

    Folders organize pages in the content tree but have no body.
    """

    id: str = CONFLUENCE_DEFAULT_ID
    title: str = EMPTY_STRING
    status: str = "current"
    space_id: str | None = None
    parent_id: str | None = None
    parent_type: str | None = None
    version: int | None = None
    url: str | None = None
    children: list[dict[str, Any]] | None = None
    children_has_more: bool = False

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ConfluenceFolder":
        """
        Create a ConfluenceFolder from a Confluence v2 API response.

        Args:
            data: The folder data from the Confluence v2 API
            **kwargs: Additional context parameters:
                base_url: Base URL used when the response has no `_links.base`

        Returns:
            A ConfluenceFolder instance
        """
        if not data:
            return cls()

        links = data.get("_links") or {}
        base_url = links.get("base") or kwargs.get("base_url")
        webui = links.get("webui")
        url = f"{base_url.rstrip('/')}{webui}" if base_url and webui else None

        version = data.get("version") or {}
        parent_id = data.get("parentId")
        space_id = data.get("spaceId")

        return cls(
            id=str(data.get("id", CONFLUENCE_DEFAULT_ID)),
            title=data.get("title", EMPTY_STRING),
            status=data.get("status", "current"),
            space_id=str(space_id) if space_id is not None else None,
            parent_id=str(parent_id) if parent_id is not None else None,
            parent_type=data.get("parentType"),
            version=version.get("number"),
            url=url,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "type": "folder",
            "status": self.status,
        }
        if self.space_id:
            result["space_id"] = self.space_id
        if self.parent_id:
            result["parent_id"] = self.parent_id
            result["parent_type"] = self.parent_type
        if self.version is not None:
            result["version"] = self.version
        if self.url:
            result["url"] = self.url
        if self.children is not None:
            result["children"] = [
                {
                    "id": str(child.get("id", "")),
                    "title": child.get("title", EMPTY_STRING),
                    "type": child.get("type"),
                    "status": child.get("status"),
                }
                for child in self.children
            ]
            result["children_has_more"] = self.children_has_more
        return result
