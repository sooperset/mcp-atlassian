"""Models for Confluence Analytics (page views)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PageViews(BaseModel):
    """Page view statistics for a Confluence page."""

    page_id: str
    page_title: str | None = None
    total_views: int = 0
    unique_viewers: int | None = None
    last_viewed: datetime | None = None

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        result: dict[str, Any] = {
            "page_id": self.page_id,
            "total_views": self.total_views,
        }
        if self.page_title:
            result["page_title"] = self.page_title
        if self.unique_viewers is not None:
            result["unique_viewers"] = self.unique_viewers
        if self.last_viewed:
            result["last_viewed"] = self.last_viewed.isoformat()
        return result


class PageViewsBatchResponse(BaseModel):
    """Response containing page views for multiple pages."""

    pages: list[PageViews]
    total_count: int
    success_count: int
    error_count: int
    errors: list[dict[str, str]]

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary."""
        result: dict[str, Any] = {
            "pages": [p.to_simplified_dict() for p in self.pages],
            "total_count": self.total_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
        }
        if self.errors:
            result["errors"] = self.errors
        return result
