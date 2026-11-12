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
    next_page_token: str | None = None
    # Set when the caller opted into a total on Cloud (``include_total``):
    # the total then comes from the approximate-count API, which may lag
    # behind very recent updates, or ``total_error`` explains why it is -1.
    total_is_approximate: bool = False
    total_error: str | None = None

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
        # The 'names' map (field ID → display name) lives at the top level
        # of search responses.  Propagate it into each issue dict so that
        # JiraIssue.from_api_response can populate display names.
        top_level_names = data.get("names")
        base_url = kwargs.get("base_url")
        if isinstance(issues_data, list):
            base_url = kwargs.get("base_url")
            for issue_data in issues_data:
                if issue_data:
                    if top_level_names and isinstance(issue_data, dict):
                        issue_data = {**issue_data, "names": top_level_names}
                    requested_fields = kwargs.get("requested_fields")
                    issues.append(
                        JiraIssue.from_api_response(
                            issue_data,
                            base_url=base_url,
                            requested_fields=requested_fields,
                            allowed_projects=kwargs.get("allowed_projects"),
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

        next_page_token = data.get("nextPageToken")

        return cls(
            total=total,
            start_at=start_at,
            max_results=max_results,
            issues=issues,
            next_page_token=next_page_token,
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
        result: dict[str, Any] = {
            "total": self.total,
            "start_at": self.start_at,
            "max_results": self.max_results,
            "issues": [issue.to_simplified_dict() for issue in self.issues],
        }
        self._add_optional_metadata(result)
        return result

    def to_display_name_dict(self) -> dict[str, Any]:
        """Like ``to_simplified_dict`` but with display-name keys on each issue."""
        result: dict[str, Any] = {
            "total": self.total,
            "start_at": self.start_at,
            "max_results": self.max_results,
            "issues": [issue.to_display_name_dict() for issue in self.issues],
        }
        self._add_optional_metadata(result)
        return result

    def _add_optional_metadata(self, result: dict[str, Any]) -> None:
        """Add the pagination token and total-count notes when they are set."""
        if self.next_page_token is not None:
            result["next_page_token"] = self.next_page_token
        if self.total_is_approximate:
            result["total_is_approximate"] = True
        if self.total_error is not None:
            result["total_error"] = self.total_error
