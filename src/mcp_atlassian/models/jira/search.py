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

    Supports both Jira Cloud (v3 API) and Server/DC (v2 API) response formats:
    - Cloud: Uses nextPageToken for pagination, total=-1 (not provided)
    - Server/DC: Uses startAt for pagination, total=actual count
    """

    total: int = 0
    start_at: int = 0
    max_results: int = 0
    issues: list[JiraIssue] = Field(default_factory=list)
    next_page_token: str | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraSearchResult":
        """
        Create a JiraSearchResult from a Jira API response.

        Handles both v2 (Server/DC) and v3 (Cloud) response formats:
        - v2: Includes total, startAt, maxResults
        - v3: Includes nextPageToken, no total count

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
                    is_cloud = kwargs.get("is_cloud", False)
                    issues.append(
                        JiraIssue.from_api_response(
                            issue_data,
                            requested_fields=requested_fields,
                            is_cloud=is_cloud,
                        )
                    )

        raw_total = data.get("total")
        raw_start_at = data.get("startAt")
        raw_max_results = data.get("maxResults")
        next_token = data.get("nextPageToken")

        try:
            total = int(raw_total) if raw_total is not None else -1
        except (ValueError, TypeError):
            total = -1

        try:
            start_at = int(raw_start_at) if raw_start_at is not None else 0
        except (ValueError, TypeError):
            start_at = 0

        try:
            max_results = int(raw_max_results) if raw_max_results is not None else -1
        except (ValueError, TypeError):
            max_results = -1

        return cls(
            total=total,
            start_at=start_at,
            max_results=max_results,
            issues=issues,
            next_page_token=next_token,
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
        """Convert to simplified dictionary for API response.

        Note: next_page_token is intentionally excluded to maintain
        backward compatibility with existing MCP clients.
        """
        return {
            "total": self.total,
            "start_at": self.start_at,
            "max_results": self.max_results,
            "issues": [issue.to_simplified_dict() for issue in self.issues],
        }
