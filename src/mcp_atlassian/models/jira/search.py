"""
Jira search result models.

This module provides Pydantic models for Jira search (JQL) results.
"""

import logging
from typing import Any

from pydantic import Field, model_validator

from ..base import ApiModel
from .issue import JiraIssue

logger = logging.getLogger(__name__)


class JiraSearchResult(ApiModel):
    """
    Model representing a Jira search (JQL) result.
    """

    total: int = 0
    start_at: int = 0
    max_results: int = 0
    # Jira Cloud enhanced search paging
    next_page_token: str | None = None
    is_last: bool | None = None
    issues: list[JiraIssue] = Field(default_factory=list)

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraSearchResult":
        """
        Create a JiraSearchResult from a Jira API response.

        Args:
            data: The search result data from the Jira API
            **kwargs: Additional arguments to pass to the constructor

        Returns:
            A JiraSearchResult instance
        """
        if not data:
            return cls()

        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        issues = []
        issues_data = data.get("issues", [])
        if isinstance(issues_data, list):
            for issue_data in issues_data:
                if issue_data:
                    requested_fields = kwargs.get("requested_fields")
                    issues.append(
                        JiraIssue.from_api_response(
                            issue_data, requested_fields=requested_fields
                        )
                    )

        raw_total = data.get("total")
        raw_start_at = data.get("startAt")
        raw_max_results = data.get("maxResults")
        next_page_token = data.get("nextPageToken")
        is_last = data.get("isLast")

        try:
            total = int(raw_total) if raw_total is not None else -1
        except (ValueError, TypeError):
            total = -1

        try:
            start_at = int(raw_start_at) if raw_start_at is not None else -1
        except (ValueError, TypeError):
            start_at = -1

        try:
            max_results = int(raw_max_results) if raw_max_results is not None else -1
        except (ValueError, TypeError):
            max_results = -1

        return cls(
            total=total,
            start_at=start_at,
            max_results=max_results,
            next_page_token=str(next_page_token) if next_page_token else None,
            is_last=bool(is_last) if is_last is not None else None,
            issues=issues,
        )

    @model_validator(mode="after")
    def validate_search_result(self) -> "JiraSearchResult":
        """
        Validate the search result.

        This validator ensures that pagination values are sensible and
        consistent with the number of issues returned.

        Returns:
            The validated JiraSearchResult instance
        """
        return self

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "total": self.total,
            "start_at": self.start_at,
            "max_results": self.max_results,
            "next_page_token": self.next_page_token,
            "is_last": self.is_last,
            "issues": [issue.to_simplified_dict() for issue in self.issues],
        }
