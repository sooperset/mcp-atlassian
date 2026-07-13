"""
Confluence search result models.
This module provides Pydantic models for Confluence search (CQL) results.
"""

import logging
from typing import Any
from urllib.parse import quote

from pydantic import Field, model_validator

from ..base import ApiModel, TimestampMixin

# Import other necessary models using relative imports
from .page import ConfluencePage

logger = logging.getLogger(__name__)


def get_search_result_identifier(item: dict[str, Any]) -> str | None:
    """Return the stable identifier for a Confluence search result item."""
    if content := item.get("content"):
        identifier = content.get("id")
    elif space_data := item.get("space"):
        identifier = space_data.get("id") or space_data.get("key")
    else:
        return None

    if identifier is None or identifier == "":
        return None
    return str(identifier)


def _get_space_result_url(
    item: dict[str, Any], space_data: dict[str, Any], **kwargs: Any
) -> str | None:
    """Return an absolute UI URL for a space search result when possible."""
    url_candidates = (
        item.get("url"),
        item.get("resultGlobalContainer", {}).get("displayUrl"),
        space_data.get("_links", {}).get("webui"),
    )
    url = next(
        (
            candidate
            for candidate in url_candidates
            if isinstance(candidate, str) and candidate
        ),
        None,
    )

    base_url = kwargs.get("base_url")
    space_key = space_data.get("key")
    if (
        not url
        and isinstance(base_url, str)
        and isinstance(space_key, str)
        and space_key
    ):
        encoded_key = quote(space_key, safe="")
        path = (
            f"/spaces/{encoded_key}/overview"
            if kwargs.get("is_cloud")
            else f"/display/{encoded_key}"
        )
        url = path

    if (
        url
        and isinstance(base_url, str)
        and not url.startswith(("http://", "https://"))
    ):
        return f"{base_url.rstrip('/')}/{url.lstrip('/')}"
    return url


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
            elif space_data := item.get("space"):
                # Space-type results: map to ConfluencePage for uniform return type
                space_as_page = {
                    "id": get_search_result_identifier(item) or "",
                    "title": space_data.get("name", item.get("title", "")),
                    "space": space_data,
                    "type": "space",
                }
                page = ConfluencePage.from_api_response(space_as_page, **kwargs)
                if space_url := _get_space_result_url(item, space_data, **kwargs):
                    page.url = space_url
                results.append(page)

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
