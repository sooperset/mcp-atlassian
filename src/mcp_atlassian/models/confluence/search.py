"""
Confluence search result models.
This module provides Pydantic models for Confluence search (CQL) results.
"""

import logging
from typing import Any

from pydantic import Field, model_validator

from ..base import ApiModel, TimestampMixin

# Import other necessary models using relative imports
from .page import ConfluencePage

logger = logging.getLogger(__name__)


class ConfluenceSearchResult(ApiModel, TimestampMixin):
    """
    Model representing a Confluence search (CQL) result.
    """

    total_size: int = 0
    start: int = 0
    limit: int = 0
    results: list[ConfluencePage] = Field(default_factory=list)
    cql_query: str | None = None
    search_duration: int | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ConfluenceSearchResult":
        """
        Create a ConfluenceSearchResult from a Confluence API response.

        Args:
            data: The search result data from the Confluence API
            **kwargs: Additional context parameters, including:
                - base_url: Base URL for constructing page URLs
                - is_cloud: Whether this is a cloud instance (affects URL format)

        Returns:
            A ConfluenceSearchResult instance
        """
        if not data:
            return cls()

        # Convert search results to ConfluencePage models
        results = []
        for item in data.get("results", []):
            # In Confluence search, the content is nested inside the result item
            if content := item.get("content"):
                results.append(ConfluencePage.from_api_response(content, **kwargs))

        return cls(
            total_size=data.get("totalSize", 0),
            start=data.get("start", 0),
            limit=data.get("limit", 0),
            results=results,
            cql_query=data.get("cqlQuery"),
            search_duration=data.get("searchDuration"),
        )

    @model_validator(mode="after")
    def validate_search_result(self) -> "ConfluenceSearchResult":
        """Validate the search result and log warnings if needed."""
        if self.total_size > 0 and not self.results:
            logger.warning(
                "Search found %d pages but no content data was returned",
                self.total_size,
            )
        return self
