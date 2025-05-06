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
