"""
Confluence user search result models.
This module provides Pydantic models for Confluence user search results.
"""

import logging
from typing import Any

from pydantic import Field

from ..base import ApiModel, TimestampMixin
from .common import ConfluenceUser

logger = logging.getLogger(__name__)


class ConfluenceUserSearchResult(ApiModel):
    """
    Model representing a single user search result.
    """

    user: ConfluenceUser | None = None
    title: str | None = None
    excerpt: str | None = None
    url: str | None = None
    entity_type: str = "user"
    last_modified: str | None = None
    score: float = 0.0

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ConfluenceUserSearchResult":
        """
        Create a ConfluenceUserSearchResult from a Confluence API response.

        Args:
            data: The user search result data from the Confluence API
            **kwargs: Additional context parameters

        Returns:
            A ConfluenceUserSearchResult instance
        """
        if not data:
            return cls()

        # Extract user data from the result
        user_data = data.get("user", {})
        user = ConfluenceUser.from_api_response(user_data) if user_data else None

        return cls(
            user=user,
            title=data.get("title"),
            excerpt=data.get("excerpt"),
            url=data.get("url"),
            entity_type=data.get("entityType", "user"),
            last_modified=data.get("lastModified"),
            score=data.get("score", 0.0),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "entity_type": self.entity_type,
            "title": self.title,
            "score": self.score,
        }

        if self.user:
            result["user"] = {
                "account_id": self.user.account_id,
                "display_name": self.user.display_name,
                "email": self.user.email,
                "profile_picture": self.user.profile_picture,
                "is_active": self.user.is_active,
            }

        if self.url:
            result["url"] = self.url

        if self.last_modified:
            result["last_modified"] = self.last_modified

        if self.excerpt:
            result["excerpt"] = self.excerpt

        return result


class ConfluenceUserSearchResults(ApiModel, TimestampMixin):
    """
    Model representing a collection of user search results.
    """

    total_size: int = 0
    start: int = 0
    limit: int = 0
    results: list[ConfluenceUserSearchResult] = Field(default_factory=list)
    cql_query: str | None = None
    search_duration: int | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ConfluenceUserSearchResults":
        """
        Create a ConfluenceUserSearchResults from a Confluence API response.

        Args:
            data: The search result data from the Confluence API
            **kwargs: Additional context parameters

        Returns:
            A ConfluenceUserSearchResults instance
        """
        if not data:
            return cls()

        # Convert search results to ConfluenceUserSearchResult models
        results = []
        for result_data in data.get("results", []):
            user_result = ConfluenceUserSearchResult.from_api_response(
                result_data, **kwargs
            )
            results.append(user_result)

        return cls(
            total_size=data.get("totalSize", 0),
            start=data.get("start", 0),
            limit=data.get("limit", 0),
            results=results,
            cql_query=data.get("cqlQuery"),
            search_duration=data.get("searchDuration"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "total_size": self.total_size,
            "start": self.start,
            "limit": self.limit,
            "cql_query": self.cql_query,
            "search_duration": self.search_duration,
            "results": [result.to_simplified_dict() for result in self.results],
        }
