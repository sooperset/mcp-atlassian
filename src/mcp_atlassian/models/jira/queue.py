"""
Jira Service Management queue models.

This module provides Pydantic models for Jira Service Management
service desks, queues, and queue issue responses.
"""

from typing import Any

from pydantic import Field

from ..base import ApiModel
from ..constants import EMPTY_STRING


class JiraServiceDesk(ApiModel):
    """Model representing a Jira Service Management service desk."""

    id: str = EMPTY_STRING
    project_id: str | None = None
    project_key: str = EMPTY_STRING
    project_name: str = EMPTY_STRING
    name: str | None = None
    links: dict[str, Any] | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraServiceDesk":
        """Create a JiraServiceDesk model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()

        service_desk_id = data.get("id")
        project_id = data.get("projectId")

        return cls(
            id=str(service_desk_id) if service_desk_id is not None else EMPTY_STRING,
            project_id=str(project_id) if project_id is not None else None,
            project_key=str(data.get("projectKey", EMPTY_STRING)),
            project_name=str(data.get("projectName", EMPTY_STRING)),
            name=data.get("name"),
            links=data.get("_links") if isinstance(data.get("_links"), dict) else None,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "id": self.id,
            "project_key": self.project_key,
            "project_name": self.project_name,
        }

        if self.project_id:
            result["project_id"] = self.project_id
        if self.name:
            result["name"] = self.name
        if self.links:
            result["links"] = self.links

        return result


class JiraQueue(ApiModel):
    """Model representing a Jira Service Management queue."""

    id: str = EMPTY_STRING
    name: str = EMPTY_STRING
    issue_count: int | None = None
    jql: str | None = None
    fields: list[str] = Field(default_factory=list)
    links: dict[str, Any] | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraQueue":
        """Create a JiraQueue model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()

        queue_id = data.get("id")
        raw_issue_count = data.get("issueCount")
        issue_count = None
        if raw_issue_count is not None:
            try:
                issue_count = int(raw_issue_count)
            except (TypeError, ValueError):
                issue_count = None

        raw_fields = data.get("fields")
        fields: list[str] = []
        if isinstance(raw_fields, list):
            fields = [str(field) for field in raw_fields if field is not None]

        return cls(
            id=str(queue_id) if queue_id is not None else EMPTY_STRING,
            name=str(data.get("name", EMPTY_STRING)),
            issue_count=issue_count,
            jql=data.get("jql"),
            fields=fields,
            links=data.get("_links") if isinstance(data.get("_links"), dict) else None,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
        }

        if self.issue_count is not None:
            result["issue_count"] = self.issue_count
        if self.jql:
            result["jql"] = self.jql
        if self.fields:
            result["fields"] = self.fields
        if self.links:
            result["links"] = self.links

        return result


class JiraServiceDeskQueuesResult(ApiModel):
    """Model representing queue listing results for a service desk."""

    service_desk_id: str = EMPTY_STRING
    start: int = 0
    limit: int = 50
    size: int = 0
    is_last_page: bool = True
    queues: list[JiraQueue] = Field(default_factory=list)
    links: dict[str, Any] | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraServiceDeskQueuesResult":
        """Create a JiraServiceDeskQueuesResult model from API response data."""
        if not data or not isinstance(data, dict):
            return cls(service_desk_id=str(kwargs.get("service_desk_id", EMPTY_STRING)))

        raw_queues = data.get("values", [])
        queues: list[JiraQueue] = []
        if isinstance(raw_queues, list):
            queues = [
                JiraQueue.from_api_response(queue_data)
                for queue_data in raw_queues
                if isinstance(queue_data, dict)
            ]

        def _to_int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        service_desk_id = kwargs.get("service_desk_id", EMPTY_STRING)

        return cls(
            service_desk_id=str(service_desk_id),
            start=_to_int(data.get("start"), 0),
            limit=_to_int(data.get("limit"), 50),
            size=_to_int(data.get("size"), len(queues)),
            is_last_page=bool(data.get("isLastPage", True)),
            queues=queues,
            links=data.get("_links") if isinstance(data.get("_links"), dict) else None,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "service_desk_id": self.service_desk_id,
            "start": self.start,
            "limit": self.limit,
            "size": self.size,
            "is_last_page": self.is_last_page,
            "queues": [queue.to_simplified_dict() for queue in self.queues],
        }
        if self.links:
            result["links"] = self.links
        return result


class JiraQueueIssuesResult(ApiModel):
    """Model representing queue issues results."""

    service_desk_id: str = EMPTY_STRING
    queue_id: str = EMPTY_STRING
    queue: JiraQueue | None = None
    start: int = 0
    limit: int = 50
    size: int = 0
    is_last_page: bool = True
    issues: list[dict[str, Any]] = Field(default_factory=list)
    links: dict[str, Any] | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraQueueIssuesResult":
        """Create a JiraQueueIssuesResult model from API response data."""
        if not data or not isinstance(data, dict):
            return cls(
                service_desk_id=str(kwargs.get("service_desk_id", EMPTY_STRING)),
                queue_id=str(kwargs.get("queue_id", EMPTY_STRING)),
                queue=kwargs.get("queue"),
            )

        raw_issues = data.get("values", [])
        issues: list[dict[str, Any]] = []
        if isinstance(raw_issues, list):
            issues = [issue for issue in raw_issues if isinstance(issue, dict)]

        def _to_int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return cls(
            service_desk_id=str(kwargs.get("service_desk_id", EMPTY_STRING)),
            queue_id=str(kwargs.get("queue_id", EMPTY_STRING)),
            queue=kwargs.get("queue"),
            start=_to_int(data.get("start"), 0),
            limit=_to_int(data.get("limit"), 50),
            size=_to_int(data.get("size"), len(issues)),
            is_last_page=bool(data.get("isLastPage", True)),
            issues=issues,
            links=data.get("_links") if isinstance(data.get("_links"), dict) else None,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "service_desk_id": self.service_desk_id,
            "queue_id": self.queue_id,
            "start": self.start,
            "limit": self.limit,
            "size": self.size,
            "is_last_page": self.is_last_page,
            "issues": self.issues,
        }
        if self.queue:
            result["queue"] = self.queue.to_simplified_dict()
        if self.links:
            result["links"] = self.links
        return result
