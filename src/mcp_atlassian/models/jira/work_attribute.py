"""Jira work attribute models."""

from typing import Any

from ..base import ApiModel
from ..constants import EMPTY_STRING


def _as_int(value: Any) -> int:
    """Convert an API value to an integer, defaulting invalid values to zero."""
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _as_bool(value: Any) -> bool:
    """Convert the API's boolean representations to a Python boolean."""
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}
    return bool(value)


class JiraWorkAttributeType(ApiModel):
    """A Tempo work attribute type."""

    name: str = EMPTY_STRING
    value: str = EMPTY_STRING
    system_type: bool = False

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraWorkAttributeType":
        """Create a work attribute type from a Tempo API response."""
        if not isinstance(data, dict):
            return cls()

        return cls(
            name=str(data.get("name", EMPTY_STRING)),
            value=str(data.get("value", EMPTY_STRING)),
            system_type=_as_bool(data.get("systemType", False)),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert the type to a simplified response dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "system_type": self.system_type,
        }


class JiraWorkAttributeValue(ApiModel):
    """A static-list value for a Tempo work attribute."""

    id: int = 0
    name: str = EMPTY_STRING
    value: str = EMPTY_STRING
    removed: bool = False
    sequence: int = 0
    work_attribute_id: int = 0

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraWorkAttributeValue":
        """Create a static-list value from a Tempo API response."""
        if not isinstance(data, dict):
            return cls()

        value = data.get("value", EMPTY_STRING)
        return cls(
            id=_as_int(data.get("id")),
            name=str(data.get("name", value)),
            value=str(value),
            removed=_as_bool(data.get("removed", False)),
            sequence=_as_int(data.get("sequence")),
            work_attribute_id=_as_int(data.get("workAttributeId")),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert the value to a simplified response dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "value": self.value,
            "removed": self.removed,
            "sequence": self.sequence,
            "work_attribute_id": self.work_attribute_id,
        }


class JiraWorkAttribute(ApiModel):
    """A Tempo work attribute definition."""

    id: int = 0
    key: str = EMPTY_STRING
    name: str = EMPTY_STRING
    type: JiraWorkAttributeType | None = None
    external_url: str = EMPTY_STRING
    required: bool = False
    sequence: int = 0
    static_list_values: list[JiraWorkAttributeValue] = []

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraWorkAttribute":
        """Create a work attribute from a Tempo API response."""
        if not isinstance(data, dict):
            return cls()

        type_data = data.get("type")
        attribute_type: JiraWorkAttributeType | None = None
        if isinstance(type_data, dict):
            attribute_type = JiraWorkAttributeType.from_api_response(type_data)
        elif type_data is not None:
            attribute_type = JiraWorkAttributeType(value=str(type_data))

        values = data.get("staticListValues", [])
        static_list_values = (
            [
                JiraWorkAttributeValue.from_api_response(value)
                for value in values
                if isinstance(value, dict)
            ]
            if isinstance(values, list)
            else []
        )

        return cls(
            id=_as_int(data.get("id")),
            key=str(data.get("key", EMPTY_STRING)),
            name=str(data.get("name", EMPTY_STRING)),
            type=attribute_type,
            external_url=str(data.get("externalUrl", EMPTY_STRING)),
            required=_as_bool(data.get("required", data.get("isRequired", False))),
            sequence=_as_int(data.get("sequence")),
            static_list_values=static_list_values,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert the work attribute to a simplified response dictionary."""
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "type": self.type.to_simplified_dict() if self.type else None,
            "external_url": self.external_url,
            "required": self.required,
            "sequence": self.sequence,
            "static_list_values": [
                value.to_simplified_dict() for value in self.static_list_values
            ],
        }
