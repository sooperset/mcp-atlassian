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


class JiraRequestTypeField(ApiModel):
    """Model representing a field exposed by a Service Desk request type."""

    field_id: str = EMPTY_STRING
    name: str = EMPTY_STRING
    required: bool = False
    default_value: Any | None = None
    valid_values: list[dict[str, Any]] = Field(default_factory=list)
    jira_schema: dict[str, Any] | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestTypeField":
        """Create a JiraRequestTypeField model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()

        raw_valid = data.get("validValues")
        valid_values: list[dict[str, Any]] = []
        if isinstance(raw_valid, list):
            valid_values = [v for v in raw_valid if isinstance(v, dict)]

        jira_schema = data.get("jiraSchema")
        if not isinstance(jira_schema, dict):
            jira_schema = None

        default_value = data.get("defaultValues")
        if isinstance(default_value, list) and len(default_value) == 1:
            default_value = default_value[0]

        return cls(
            field_id=str(data.get("fieldId", EMPTY_STRING)),
            name=str(data.get("name", EMPTY_STRING)),
            required=bool(data.get("required", False)),
            default_value=default_value,
            valid_values=valid_values,
            jira_schema=jira_schema,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "field_id": self.field_id,
            "name": self.name,
            "required": self.required,
        }
        if self.default_value is not None:
            result["default_value"] = self.default_value
        if self.valid_values:
            result["valid_values"] = self.valid_values
        if self.jira_schema:
            result["jira_schema"] = self.jira_schema
        return result


class JiraRequestType(ApiModel):
    """Model representing a Service Desk request type."""

    id: str = EMPTY_STRING
    name: str = EMPTY_STRING
    description: str | None = None
    help_text: str | None = None
    issue_type_id: str | None = None
    service_desk_id: str | None = None
    portal_id: str | None = None
    group_ids: list[str] = Field(default_factory=list)
    icon: dict[str, Any] | None = None
    fields: list[JiraRequestTypeField] = Field(default_factory=list)

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestType":
        """Create a JiraRequestType model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()

        raw_groups = data.get("groupIds")
        group_ids: list[str] = []
        if isinstance(raw_groups, list):
            group_ids = [str(g) for g in raw_groups if g is not None]

        raw_fields = data.get("requestTypeFields") or data.get("fields") or []
        fields: list[JiraRequestTypeField] = []
        if isinstance(raw_fields, list):
            fields = [
                JiraRequestTypeField.from_api_response(field_data)
                for field_data in raw_fields
                if isinstance(field_data, dict)
            ]

        icon = data.get("icon")
        if not isinstance(icon, dict):
            icon = None

        return cls(
            id=str(data.get("id", EMPTY_STRING)),
            name=str(data.get("name", EMPTY_STRING)),
            description=data.get("description"),
            help_text=data.get("helpText"),
            issue_type_id=(
                str(data["issueTypeId"])
                if data.get("issueTypeId") is not None
                else None
            ),
            service_desk_id=(
                str(data["serviceDeskId"])
                if data.get("serviceDeskId") is not None
                else None
            ),
            portal_id=(
                str(data["portalId"]) if data.get("portalId") is not None else None
            ),
            group_ids=group_ids,
            icon=icon,
            fields=fields,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
        }
        if self.description:
            result["description"] = self.description
        if self.help_text:
            result["help_text"] = self.help_text
        if self.issue_type_id:
            result["issue_type_id"] = self.issue_type_id
        if self.service_desk_id:
            result["service_desk_id"] = self.service_desk_id
        if self.portal_id:
            result["portal_id"] = self.portal_id
        if self.group_ids:
            result["group_ids"] = self.group_ids
        if self.icon:
            result["icon"] = self.icon
        if self.fields:
            result["fields"] = [f.to_simplified_dict() for f in self.fields]
        return result


class JiraRequestTypesResult(ApiModel):
    """Model representing a paginated list of Service Desk request types."""

    service_desk_id: str = EMPTY_STRING
    start: int = 0
    limit: int = 50
    size: int = 0
    is_last_page: bool = True
    request_types: list[JiraRequestType] = Field(default_factory=list)
    links: dict[str, Any] | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestTypesResult":
        """Create a JiraRequestTypesResult model from API response data."""
        if not data or not isinstance(data, dict):
            return cls(service_desk_id=str(kwargs.get("service_desk_id", EMPTY_STRING)))

        raw_values = data.get("values", [])
        request_types: list[JiraRequestType] = []
        if isinstance(raw_values, list):
            request_types = [
                JiraRequestType.from_api_response(item)
                for item in raw_values
                if isinstance(item, dict)
            ]

        def _to_int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return cls(
            service_desk_id=str(kwargs.get("service_desk_id", EMPTY_STRING)),
            start=_to_int(data.get("start"), 0),
            limit=_to_int(data.get("limit"), 50),
            size=_to_int(data.get("size"), len(request_types)),
            is_last_page=bool(data.get("isLastPage", True)),
            request_types=request_types,
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
            "request_types": [rt.to_simplified_dict() for rt in self.request_types],
        }
        if self.links:
            result["links"] = self.links
        return result


class JiraServiceDeskRequest(ApiModel):
    """Model representing a Service Desk customer request."""

    issue_id: str = EMPTY_STRING
    issue_key: str = EMPTY_STRING
    service_desk_id: str | None = None
    request_type_id: str | None = None
    request_type_name: str | None = None
    reporter: dict[str, Any] | None = None
    created: str | None = None
    request_field_values: list[dict[str, Any]] = Field(default_factory=list)
    current_status: dict[str, Any] | None = None
    links: dict[str, Any] | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraServiceDeskRequest":
        """Create a JiraServiceDeskRequest model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()

        request_type = data.get("requestType")
        if not isinstance(request_type, dict):
            request_type = {}

        service_desk = data.get("serviceDesk")
        service_desk_id = None
        if isinstance(service_desk, dict) and service_desk.get("id") is not None:
            service_desk_id = str(service_desk["id"])

        created = data.get("createdDate")
        created_str: str | None = None
        if isinstance(created, dict):
            created_str = created.get("iso8601") or created.get("friendly")
        elif isinstance(created, str):
            created_str = created

        raw_field_values = data.get("requestFieldValues", [])
        field_values: list[dict[str, Any]] = []
        if isinstance(raw_field_values, list):
            field_values = [v for v in raw_field_values if isinstance(v, dict)]

        current_status = data.get("currentStatus")
        if not isinstance(current_status, dict):
            current_status = None

        reporter = data.get("reporter")
        if not isinstance(reporter, dict):
            reporter = None

        return cls(
            issue_id=str(data.get("issueId", EMPTY_STRING)),
            issue_key=str(data.get("issueKey", EMPTY_STRING)),
            service_desk_id=service_desk_id,
            request_type_id=(
                str(request_type["id"]) if request_type.get("id") is not None else None
            ),
            request_type_name=request_type.get("name"),
            reporter=reporter,
            created=created_str,
            request_field_values=field_values,
            current_status=current_status,
            links=data.get("_links") if isinstance(data.get("_links"), dict) else None,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "issue_id": self.issue_id,
            "issue_key": self.issue_key,
        }
        if self.service_desk_id:
            result["service_desk_id"] = self.service_desk_id
        if self.request_type_id:
            result["request_type_id"] = self.request_type_id
        if self.request_type_name:
            result["request_type_name"] = self.request_type_name
        if self.reporter:
            result["reporter"] = self.reporter
        if self.created:
            result["created"] = self.created
        if self.request_field_values:
            result["request_field_values"] = self.request_field_values
        if self.current_status:
            result["current_status"] = self.current_status
        if self.links:
            result["links"] = self.links
        return result


class JiraRequestStatusEntry(ApiModel):
    """Model representing one status entry in a request's status history."""

    status: str = EMPTY_STRING
    status_category: str | None = None
    status_date: str | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestStatusEntry":
        """Create a JiraRequestStatusEntry model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()

        status_date = data.get("statusDate")
        status_str: str | None = None
        if isinstance(status_date, dict):
            status_str = status_date.get("iso8601") or status_date.get("friendly")
        elif isinstance(status_date, str):
            status_str = status_date

        return cls(
            status=str(data.get("status", EMPTY_STRING)),
            status_category=data.get("statusCategory"),
            status_date=status_str,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {"status": self.status}
        if self.status_category:
            result["status_category"] = self.status_category
        if self.status_date:
            result["status_date"] = self.status_date
        return result


class JiraRequestStatusResult(ApiModel):
    """Model representing a paginated request status history result."""

    issue_key: str = EMPTY_STRING
    start: int = 0
    limit: int = 50
    size: int = 0
    is_last_page: bool = True
    statuses: list[JiraRequestStatusEntry] = Field(default_factory=list)

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestStatusResult":
        """Create a JiraRequestStatusResult model from API response data."""
        if not data or not isinstance(data, dict):
            return cls(issue_key=str(kwargs.get("issue_key", EMPTY_STRING)))

        raw_values = data.get("values", [])
        statuses: list[JiraRequestStatusEntry] = []
        if isinstance(raw_values, list):
            statuses = [
                JiraRequestStatusEntry.from_api_response(entry)
                for entry in raw_values
                if isinstance(entry, dict)
            ]

        def _to_int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return cls(
            issue_key=str(kwargs.get("issue_key", EMPTY_STRING)),
            start=_to_int(data.get("start"), 0),
            limit=_to_int(data.get("limit"), 50),
            size=_to_int(data.get("size"), len(statuses)),
            is_last_page=bool(data.get("isLastPage", True)),
            statuses=statuses,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "issue_key": self.issue_key,
            "start": self.start,
            "limit": self.limit,
            "size": self.size,
            "is_last_page": self.is_last_page,
            "statuses": [entry.to_simplified_dict() for entry in self.statuses],
        }


class JiraRequestTransition(ApiModel):
    """Model representing a transition available on a Service Desk request."""

    id: str = EMPTY_STRING
    name: str = EMPTY_STRING

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestTransition":
        """Create a JiraRequestTransition model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()
        return cls(
            id=str(data.get("id", EMPTY_STRING)),
            name=str(data.get("name", EMPTY_STRING)),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {"id": self.id, "name": self.name}


class JiraRequestTransitionsResult(ApiModel):
    """Model representing available transitions for a request."""

    issue_key: str = EMPTY_STRING
    start: int = 0
    limit: int = 50
    size: int = 0
    is_last_page: bool = True
    transitions: list[JiraRequestTransition] = Field(default_factory=list)

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestTransitionsResult":
        """Create a JiraRequestTransitionsResult model from API response data."""
        if not data or not isinstance(data, dict):
            return cls(issue_key=str(kwargs.get("issue_key", EMPTY_STRING)))

        raw_values = data.get("values", [])
        transitions: list[JiraRequestTransition] = []
        if isinstance(raw_values, list):
            transitions = [
                JiraRequestTransition.from_api_response(item)
                for item in raw_values
                if isinstance(item, dict)
            ]

        def _to_int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return cls(
            issue_key=str(kwargs.get("issue_key", EMPTY_STRING)),
            start=_to_int(data.get("start"), 0),
            limit=_to_int(data.get("limit"), 50),
            size=_to_int(data.get("size"), len(transitions)),
            is_last_page=bool(data.get("isLastPage", True)),
            transitions=transitions,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "issue_key": self.issue_key,
            "start": self.start,
            "limit": self.limit,
            "size": self.size,
            "is_last_page": self.is_last_page,
            "transitions": [t.to_simplified_dict() for t in self.transitions],
        }


class JiraTemporaryAttachment(ApiModel):
    """Model representing a Service Desk temporary attachment."""

    temporary_attachment_id: str = EMPTY_STRING
    file_name: str = EMPTY_STRING

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraTemporaryAttachment":
        """Create a JiraTemporaryAttachment model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()
        return cls(
            temporary_attachment_id=str(
                data.get("temporaryAttachmentId", EMPTY_STRING)
            ),
            file_name=str(data.get("fileName", EMPTY_STRING)),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "temporary_attachment_id": self.temporary_attachment_id,
            "file_name": self.file_name,
        }


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
