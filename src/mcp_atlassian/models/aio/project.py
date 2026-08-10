"""Models for AIO Tests project information and test case schema."""

from typing import Any

from ..base import ApiModel
from .common import AIOEntity


class AIOProject(ApiModel):
    """Basic AIO Tests information about a Jira project."""

    key: str | None = None
    id: int | None = None
    aio_enabled: bool = False
    error: str | None = None
    adhoc_cycle_key: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "AIOProject":
        """Create project info from an AIO Tests project configuration response.

        The AIO Tests API has no dedicated project resource; a successful
        configuration call is itself the proof that AIO Tests is enabled, and the
        Jira project ID is carried on the project's ad-hoc cycle.

        Args:
            data: Raw ``ProjectConfiguration`` payload.
            **kwargs: Optional ``project_key`` used as requested by the caller.

        Returns:
            The parsed project information.
        """
        adhoc = data.get("adhocTestCycle") if isinstance(data, dict) else None
        adhoc = adhoc if isinstance(adhoc, dict) else {}
        return cls(
            key=kwargs.get("project_key"),
            id=adhoc.get("jiraProjectID"),
            aio_enabled=True,
            adhoc_cycle_key=adhoc.get("key"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary.

        Returns:
            Dictionary describing the project and its AIO Tests availability.
        """
        result: dict[str, Any] = {"aio_enabled": self.aio_enabled}
        if self.key:
            result["project_key"] = self.key
        if self.id is not None:
            result["project_id"] = self.id
        if self.adhoc_cycle_key:
            result["adhoc_cycle_key"] = self.adhoc_cycle_key
        if self.error:
            result["error"] = self.error
        return result


class AIOCustomField(ApiModel):
    """A custom field configured for AIO Tests test cases."""

    id: int | None = None
    name: str | None = None
    description: str | None = None
    type: str | None = None
    required: bool = False
    jira_field: str | None = None
    allowed_values: list[dict[str, Any]] = []

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "AIOCustomField":
        """Create a custom field from an AIO Tests API response.

        Args:
            data: Raw ``CustomField`` payload.
            **kwargs: Unused, accepted for interface compatibility.

        Returns:
            The parsed custom field.
        """
        if not isinstance(data, dict):
            return cls()
        association = data.get("caseAssociation")
        association = association if isinstance(association, dict) else {}
        allowed: list[dict[str, Any]] = []
        for value in data.get("allowedListValues") or []:
            if isinstance(value, dict):
                allowed.append({"id": value.get("ID"), "value": value.get("value")})
        for value in data.get("colorAllowedListValues") or []:
            if isinstance(value, dict):
                allowed.append(
                    {
                        "id": value.get("ID"),
                        "value": value.get("description"),
                        "hex_code": value.get("hexCode"),
                    }
                )
        return cls(
            id=data.get("ID"),
            name=data.get("name"),
            description=data.get("description"),
            type=data.get("type"),
            required=bool(association.get("isRequired")),
            jira_field=data.get("jiraField"),
            allowed_values=allowed,
        )

    @property
    def is_associated_with_cases(self) -> bool:
        """Whether the field applies to test cases.

        Returns:
            True when the field is associated with the case entity.
        """
        return True

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary.

        Returns:
            Dictionary describing the custom field and its allowed values.
        """
        result: dict[str, Any] = {"required": self.required}
        if self.id is not None:
            result["id"] = self.id
        if self.name:
            result["name"] = self.name
        if self.description:
            result["description"] = self.description
        if self.type:
            result["type"] = self.type
        if self.jira_field:
            result["jira_field"] = self.jira_field
        if self.allowed_values:
            result["allowed_values"] = self.allowed_values
        return result


class AIOSchemaField(ApiModel):
    """A built-in test case field exposed by the create/update APIs."""

    name: str
    type: str
    description: str
    required: bool = False
    read_only: bool = False
    allowed_values_from: str | None = None

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary.

        Returns:
            Dictionary describing the field.
        """
        result: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required,
        }
        if self.read_only:
            result["read_only"] = True
        if self.allowed_values_from:
            result["allowed_values_from"] = self.allowed_values_from
        return result


class AIOTestCaseSchema(ApiModel):
    """The complete test case schema configuration for a project."""

    project_key: str | None = None
    project_id: int | None = None
    fields: list[AIOSchemaField] = []
    custom_fields: list[AIOCustomField] = []
    priorities: list[AIOEntity] = []
    statuses: list[AIOEntity] = []
    types: list[AIOEntity] = []
    script_types: list[AIOEntity] = []
    automation_statuses: list[AIOEntity] = []

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "AIOTestCaseSchema":
        """Create a schema from an AIO Tests project configuration response.

        Args:
            data: Raw ``ProjectConfiguration`` payload.
            **kwargs: ``project_key`` of the request and ``fields`` catalog of
                built-in case fields.

        Returns:
            The parsed schema.
        """
        if not isinstance(data, dict):
            data = {}

        def entities(key: str) -> list[AIOEntity]:
            return [
                AIOEntity.from_api_response(value)
                for value in (data.get(key) or [])
                if isinstance(value, dict)
            ]

        adhoc = data.get("adhocTestCycle")
        adhoc = adhoc if isinstance(adhoc, dict) else {}
        custom_fields = [
            AIOCustomField.from_api_response(value)
            for value in (data.get("customFields") or [])
            if isinstance(value, dict)
            and isinstance(value.get("caseAssociation"), dict)
            and value["caseAssociation"].get("isAssociated")
        ]
        return cls(
            project_key=kwargs.get("project_key"),
            project_id=adhoc.get("jiraProjectID"),
            fields=list(kwargs.get("fields") or []),
            custom_fields=custom_fields,
            priorities=entities("casePriorities"),
            statuses=entities("caseStatuses"),
            types=entities("caseTypes"),
            script_types=entities("caseScriptTypes"),
            automation_statuses=entities("caseAutomationStatuses"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary.

        Returns:
            Dictionary describing fields, custom fields and allowed values.
        """
        result: dict[str, Any] = {}
        if self.project_key:
            result["project_key"] = self.project_key
        if self.project_id is not None:
            result["project_id"] = self.project_id
        result["fields"] = [field.to_simplified_dict() for field in self.fields]
        result["required_fields"] = [
            field.name for field in self.fields if field.required
        ] + [
            field.name for field in self.custom_fields if field.required and field.name
        ]
        result["custom_fields"] = [
            field.to_simplified_dict() for field in self.custom_fields
        ]
        result["allowed_values"] = {
            "priorities": [entity.to_simplified_dict() for entity in self.priorities],
            "statuses": [entity.to_simplified_dict() for entity in self.statuses],
            "types": [entity.to_simplified_dict() for entity in self.types],
            "script_types": [
                entity.to_simplified_dict() for entity in self.script_types
            ],
            "automation_statuses": [
                entity.to_simplified_dict() for entity in self.automation_statuses
            ],
        }
        return result
