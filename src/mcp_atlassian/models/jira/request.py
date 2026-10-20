"""
Jira Service Management customer request models.

This module provides Pydantic models for Jira Service Management
request types, request fields, and created customer requests.
"""

from typing import Any

from pydantic import Field

from ..base import ApiModel
from ..constants import EMPTY_STRING


class JiraRequestType(ApiModel):
    """Model representing a Jira Service Management request type."""

    id: str = EMPTY_STRING
    name: str = EMPTY_STRING
    description: str | None = None
    help_text: str | None = None
    issue_type_id: str | None = None
    group_ids: list[str] = Field(default_factory=list)
    icon: dict[str, Any] | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestType":
        """Create a JiraRequestType model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()

        raw_group_ids = data.get("groupIds")
        group_ids: list[str] = []
        if isinstance(raw_group_ids, list):
            group_ids = [str(value) for value in raw_group_ids if value is not None]

        issue_type_id = data.get("issueTypeId")
        request_type_id = data.get("id")

        return cls(
            id=str(request_type_id) if request_type_id is not None else EMPTY_STRING,
            name=str(data.get("name", EMPTY_STRING)),
            description=(
                str(data.get("description")) if data.get("description") else None
            ),
            help_text=(str(data.get("helpText")) if data.get("helpText") else None),
            issue_type_id=(str(issue_type_id) if issue_type_id is not None else None),
            group_ids=group_ids,
            icon=data.get("icon") if isinstance(data.get("icon"), dict) else None,
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
        if self.group_ids:
            result["group_ids"] = self.group_ids
        if self.icon:
            result["icon"] = self.icon
        return result


class JiraRequestTypesResult(ApiModel):
    """Model representing request type listing results for a service desk."""

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

        raw_request_types = data.get("values", [])
        request_types: list[JiraRequestType] = []
        if isinstance(raw_request_types, list):
            request_types = [
                JiraRequestType.from_api_response(request_type_data)
                for request_type_data in raw_request_types
                if isinstance(request_type_data, dict)
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
            "request_types": [
                request_type.to_simplified_dict() for request_type in self.request_types
            ],
        }
        if self.links:
            result["links"] = self.links
        return result


class JiraRequestTypeField(ApiModel):
    """Model representing a field in a Jira Service Management request type."""

    field_id: str = EMPTY_STRING
    name: str = EMPTY_STRING
    description: str | None = None
    required: bool = False
    visible: bool | None = None
    jira_schema: dict[str, Any] | None = None
    valid_values: list[Any] = Field(default_factory=list)
    default_values: list[Any] = Field(default_factory=list)
    supports_multiple: bool = False

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestTypeField":
        """Create a JiraRequestTypeField model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()

        jira_schema = data.get("jiraSchema")
        if not isinstance(jira_schema, dict):
            jira_schema = None

        valid_values = data.get("validValues")
        if not isinstance(valid_values, list):
            valid_values = []

        default_values = data.get("defaultValues")
        if not isinstance(default_values, list):
            default_values = []

        field_id = data.get("fieldId")
        supports_multiple = bool(jira_schema and jira_schema.get("type") == "array")

        return cls(
            field_id=str(field_id) if field_id is not None else EMPTY_STRING,
            name=str(data.get("name", EMPTY_STRING)),
            description=(
                str(data.get("description")) if data.get("description") else None
            ),
            required=bool(data.get("required", False)),
            visible=(bool(data.get("visible")) if "visible" in data else None),
            jira_schema=jira_schema,
            valid_values=valid_values,
            default_values=default_values,
            supports_multiple=supports_multiple,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "field_id": self.field_id,
            "name": self.name,
            "required": self.required,
            "supports_multiple": self.supports_multiple,
        }
        if self.description:
            result["description"] = self.description
        if self.visible is not None:
            result["visible"] = self.visible
        if self.jira_schema:
            result["jira_schema"] = self.jira_schema
        if self.valid_values:
            result["valid_values"] = self.valid_values
        if self.default_values:
            result["default_values"] = self.default_values
        return result


class JiraRequestTypeFieldsResult(ApiModel):
    """Model representing request type field discovery results."""

    service_desk_id: str = EMPTY_STRING
    request_type_id: str = EMPTY_STRING
    can_raise_on_behalf_of: bool | None = None
    can_add_request_participants: bool | None = None
    fields: list[JiraRequestTypeField] = Field(default_factory=list)

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestTypeFieldsResult":
        """Create a JiraRequestTypeFieldsResult model from API response data."""
        if not data or not isinstance(data, dict):
            return cls(
                service_desk_id=str(kwargs.get("service_desk_id", EMPTY_STRING)),
                request_type_id=str(kwargs.get("request_type_id", EMPTY_STRING)),
            )

        raw_fields = data.get("requestTypeFields", [])
        fields: list[JiraRequestTypeField] = []
        if isinstance(raw_fields, list):
            fields = [
                JiraRequestTypeField.from_api_response(field_data)
                for field_data in raw_fields
                if isinstance(field_data, dict)
            ]

        return cls(
            service_desk_id=str(kwargs.get("service_desk_id", EMPTY_STRING)),
            request_type_id=str(kwargs.get("request_type_id", EMPTY_STRING)),
            can_raise_on_behalf_of=(
                bool(data.get("canRaiseOnBehalfOf"))
                if "canRaiseOnBehalfOf" in data
                else None
            ),
            can_add_request_participants=(
                bool(data.get("canAddRequestParticipants"))
                if "canAddRequestParticipants" in data
                else None
            ),
            fields=fields,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "service_desk_id": self.service_desk_id,
            "request_type_id": self.request_type_id,
            "fields": [field.to_simplified_dict() for field in self.fields],
        }
        if self.can_raise_on_behalf_of is not None:
            result["can_raise_on_behalf_of"] = self.can_raise_on_behalf_of
        if self.can_add_request_participants is not None:
            result["can_add_request_participants"] = self.can_add_request_participants
        return result


class JiraCustomerRequest(ApiModel):
    """Model representing a created Jira Service Management customer request."""

    request_id: str = EMPTY_STRING
    request_key: str = EMPTY_STRING
    portal_url: str = EMPTY_STRING
    created_mode: str = EMPTY_STRING
    on_behalf_user: str | None = None
    request_participants: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    links: dict[str, Any] | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraCustomerRequest":
        """Create a JiraCustomerRequest model from API response data."""
        if not data or not isinstance(data, dict):
            return cls(
                created_mode=str(kwargs.get("created_mode", EMPTY_STRING)),
                on_behalf_user=kwargs.get("on_behalf_user"),
                request_participants=kwargs.get("request_participants", []),
                warnings=list(kwargs.get("warnings", [])),
            )

        issue_id = data.get("issueId")
        request_id = data.get("id", issue_id)
        request_key = data.get("issueKey") or data.get("key")
        links = data.get("_links") if isinstance(data.get("_links"), dict) else None

        portal_url = kwargs.get("portal_url", EMPTY_STRING)
        if not portal_url and links:
            web_link = links.get("web") or links.get("self")
            if isinstance(web_link, str):
                portal_url = web_link

        return cls(
            request_id=str(request_id) if request_id is not None else EMPTY_STRING,
            request_key=str(request_key) if request_key is not None else EMPTY_STRING,
            portal_url=str(portal_url or EMPTY_STRING),
            created_mode=str(kwargs.get("created_mode", EMPTY_STRING)),
            on_behalf_user=kwargs.get("on_behalf_user"),
            request_participants=list(kwargs.get("request_participants", [])),
            warnings=list(kwargs.get("warnings", [])),
            links=links,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "request_id": self.request_id,
            "request_key": self.request_key,
            "portal_url": self.portal_url,
            "created_mode": self.created_mode,
        }
        if self.on_behalf_user:
            result["on_behalf_user"] = self.on_behalf_user
        if self.request_participants:
            result["request_participants"] = self.request_participants
        if self.warnings:
            result["warnings"] = self.warnings
        if self.links:
            result["links"] = self.links
        return result


def _to_int(value: Any, default: int) -> int:
    """Convert a pagination value to int, falling back to a default."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _date_iso(value: Any) -> str | None:
    """Extract an ISO 8601 timestamp from a Service Management date object."""
    if isinstance(value, dict):
        iso = value.get("iso8601")
        return str(iso) if iso else None
    if isinstance(value, str) and value:
        return value
    return None


def _simplify_servicedesk_user(data: Any) -> dict[str, Any] | None:
    """Reduce a Service Management user payload to identifying fields."""
    if not isinstance(data, dict):
        return None
    result: dict[str, Any] = {
        "display_name": str(data.get("displayName", EMPTY_STRING)),
    }
    if data.get("accountId"):
        result["account_id"] = str(data["accountId"])
    if data.get("name"):
        result["name"] = str(data["name"])
    if data.get("emailAddress"):
        result["email"] = str(data["emailAddress"])
    return result


def _simplify_field_value(value: Any) -> Any:
    """Reduce a request field value to a compact, readable representation."""
    if isinstance(value, list):
        return [_simplify_field_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    if "filename" in value:
        attachment: dict[str, Any] = {"filename": value.get("filename")}
        for source_key, target_key in (
            ("id", "id"),
            ("mimeType", "mime_type"),
            ("size", "size"),
        ):
            if value.get(source_key) is not None:
                attachment[target_key] = value[source_key]
        return attachment
    if "displayName" in value:
        return value.get("displayName")
    for key in ("value", "name", "label"):
        if key in value:
            return value[key]
    return {
        key: item
        for key, item in value.items()
        if key not in {"self", "_links", "avatarUrls", "iconUrl"}
    }


class JiraRequestApprover(ApiModel):
    """Model representing one approver of a customer request approval."""

    approver: dict[str, Any] | None = None
    decision: str | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestApprover":
        """Create a JiraRequestApprover model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()
        decision = data.get("approverDecision")
        return cls(
            approver=_simplify_servicedesk_user(data.get("approver")),
            decision=str(decision) if decision else None,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {"approver": self.approver}
        if self.decision:
            result["decision"] = self.decision
        return result


class JiraRequestApproval(ApiModel):
    """Model representing an approval on a Jira Service Management request."""

    id: str = EMPTY_STRING
    name: str = EMPTY_STRING
    final_decision: str = EMPTY_STRING
    can_answer_approval: bool = False
    approvers: list[JiraRequestApprover] = Field(default_factory=list)
    created_date: str | None = None
    completed_date: str | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestApproval":
        """Create a JiraRequestApproval model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()

        raw_approvers = data.get("approvers")
        approvers: list[JiraRequestApprover] = []
        if isinstance(raw_approvers, list):
            approvers = [
                JiraRequestApprover.from_api_response(approver_data)
                for approver_data in raw_approvers
                if isinstance(approver_data, dict)
            ]

        approval_id = data.get("id")
        return cls(
            id=str(approval_id) if approval_id is not None else EMPTY_STRING,
            name=str(data.get("name", EMPTY_STRING)),
            final_decision=str(data.get("finalDecision", EMPTY_STRING)),
            can_answer_approval=bool(data.get("canAnswerApproval", False)),
            approvers=approvers,
            created_date=_date_iso(data.get("createdDate")),
            completed_date=_date_iso(data.get("completedDate")),
        )

    @property
    def is_pending(self) -> bool:
        """Whether the approval is still waiting for a decision."""
        return self.final_decision.lower() == "pending"

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "final_decision": self.final_decision,
            "can_answer_approval": self.can_answer_approval,
            "approvers": [approver.to_simplified_dict() for approver in self.approvers],
        }
        if self.created_date:
            result["created_date"] = self.created_date
        if self.completed_date:
            result["completed_date"] = self.completed_date
        return result


class JiraRequestApprovalsResult(ApiModel):
    """Model representing the approvals of a customer request."""

    issue_key: str = EMPTY_STRING
    start: int = 0
    limit: int = 50
    size: int = 0
    is_last_page: bool = True
    approvals: list[JiraRequestApproval] = Field(default_factory=list)

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraRequestApprovalsResult":
        """Create a JiraRequestApprovalsResult model from API response data."""
        issue_key = str(kwargs.get("issue_key", EMPTY_STRING))
        if not data or not isinstance(data, dict):
            return cls(issue_key=issue_key)

        raw_approvals = data.get("values", [])
        approvals: list[JiraRequestApproval] = []
        if isinstance(raw_approvals, list):
            approvals = [
                JiraRequestApproval.from_api_response(approval_data)
                for approval_data in raw_approvals
                if isinstance(approval_data, dict)
            ]

        return cls(
            issue_key=issue_key,
            start=_to_int(data.get("start"), 0),
            limit=_to_int(data.get("limit"), 50),
            size=_to_int(data.get("size"), len(approvals)),
            is_last_page=bool(data.get("isLastPage", True)),
            approvals=approvals,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "issue_key": self.issue_key,
            "start": self.start,
            "limit": self.limit,
            "size": self.size,
            "is_last_page": self.is_last_page,
            "approvals": [approval.to_simplified_dict() for approval in self.approvals],
        }


class JiraCustomerRequestDetails(ApiModel):
    """Model representing a customer request read through the portal API."""

    issue_id: str = EMPTY_STRING
    issue_key: str = EMPTY_STRING
    service_desk_id: str | None = None
    request_type: dict[str, Any] | None = None
    status: str | None = None
    status_date: str | None = None
    created_date: str | None = None
    reporter: dict[str, Any] | None = None
    participants: list[dict[str, Any]] = Field(default_factory=list)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    portal_url: str | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraCustomerRequestDetails":
        """Create a JiraCustomerRequestDetails model from API response data."""
        if not data or not isinstance(data, dict):
            return cls()

        request_type: dict[str, Any] | None = None
        raw_request_type = data.get("requestType")
        if isinstance(raw_request_type, dict):
            request_type = {
                "id": str(raw_request_type.get("id", EMPTY_STRING)),
                "name": str(raw_request_type.get("name", EMPTY_STRING)),
            }
        elif data.get("requestTypeId") is not None:
            request_type = {"id": str(data["requestTypeId"])}

        current_status = data.get("currentStatus")
        status = None
        status_date = None
        if isinstance(current_status, dict):
            status = current_status.get("status")
            status_date = _date_iso(current_status.get("statusDate"))

        participants: list[dict[str, Any]] = []
        raw_participants = data.get("participants")
        if isinstance(raw_participants, dict):
            raw_participants = raw_participants.get("values")
        if isinstance(raw_participants, list):
            participants = [
                user
                for user in map(_simplify_servicedesk_user, raw_participants)
                if user is not None
            ]

        fields: list[dict[str, Any]] = []
        raw_fields = data.get("requestFieldValues")
        if isinstance(raw_fields, list):
            for field_data in raw_fields:
                if not isinstance(field_data, dict):
                    continue
                fields.append(
                    {
                        "field_id": str(field_data.get("fieldId", EMPTY_STRING)),
                        "label": str(field_data.get("label", EMPTY_STRING)),
                        "value": _simplify_field_value(field_data.get("value")),
                    }
                )

        portal_url = None
        links = data.get("_links")
        if isinstance(links, dict) and isinstance(links.get("web"), str):
            portal_url = links["web"]

        service_desk_id = data.get("serviceDeskId")
        return cls(
            issue_id=str(data.get("issueId", EMPTY_STRING)),
            issue_key=str(data.get("issueKey", EMPTY_STRING)),
            service_desk_id=(
                str(service_desk_id) if service_desk_id is not None else None
            ),
            request_type=request_type,
            status=str(status) if status else None,
            status_date=status_date,
            created_date=_date_iso(data.get("createdDate")),
            reporter=_simplify_servicedesk_user(data.get("reporter")),
            participants=participants,
            fields=fields,
            portal_url=portal_url,
        )

    @property
    def summary(self) -> str | None:
        """Return the request summary field value, if present."""
        for field in self.fields:
            if field.get("field_id") == "summary" and field.get("value"):
                return str(field["value"])
        return None

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "issue_id": self.issue_id,
            "issue_key": self.issue_key,
        }
        for key, value in (
            ("service_desk_id", self.service_desk_id),
            ("request_type", self.request_type),
            ("status", self.status),
            ("status_date", self.status_date),
            ("created_date", self.created_date),
            ("reporter", self.reporter),
            ("portal_url", self.portal_url),
        ):
            if value:
                result[key] = value
        if self.participants:
            result["participants"] = self.participants
        result["fields"] = self.fields
        return result


class JiraPendingApproval(ApiModel):
    """Model representing a customer request awaiting the user's decision."""

    request: JiraCustomerRequestDetails = Field(
        default_factory=JiraCustomerRequestDetails
    )
    approvals: list[JiraRequestApproval] = Field(default_factory=list)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        request = self.request
        result: dict[str, Any] = {"issue_key": request.issue_key}
        for key, value in (
            ("summary", request.summary),
            ("request_type", request.request_type),
            ("status", request.status),
            ("created_date", request.created_date),
            ("reporter", request.reporter),
            ("portal_url", request.portal_url),
        ):
            if value:
                result[key] = value
        result["approvals"] = [
            {"id": approval.id, "name": approval.name} for approval in self.approvals
        ]
        return result


class JiraPendingApprovalsResult(ApiModel):
    """Model representing customer requests awaiting the user's approval."""

    start: int = 0
    limit: int = 50
    next_start: int | None = None
    is_last_page: bool = True
    requests: list[JiraPendingApproval] = Field(default_factory=list)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "start": self.start,
            "limit": self.limit,
            "size": len(self.requests),
            "is_last_page": self.is_last_page,
            "requests": [request.to_simplified_dict() for request in self.requests],
        }
        if self.next_start is not None:
            result["next_start"] = self.next_start
        return result
