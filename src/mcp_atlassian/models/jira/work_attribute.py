"""
Jira work attribute models.

This module provides Pydantic models for Tempo Core Work Attributes
used in Jira Time Tracking. Work attributes allow teams to categorize
and tag worklog entries with custom attributes like "Work Mode",
"Cost Category", etc.

See https://apidocs.tempo.io for Tempo Core API documentation.
"""

from typing import Any

from ..base import ApiModel, TimestampMixin
from ..constants import EMPTY_STRING


class JiraWorkAttribute(ApiModel, TimestampMixin):
    """
    Model representing a Tempo Core Work Attribute type.

    Work attributes define the available categories/fields that can be
    assigned to worklog entries. Examples include "Work Mode" (Office/Remote),
    "Cost Category" (Billable/Non-Billable), etc.

    Attributes:
        id: Unique identifier for the work attribute
        name: Human-readable name of the attribute
        type: The attribute type (e.g., 'singleselect', 'multiselect', 'text')
        description: Optional description of the attribute
        is_required: Whether this attribute must be provided when adding a worklog
    """

    id: int = 0
    name: str = EMPTY_STRING
    type: str = EMPTY_STRING
    description: str = EMPTY_STRING
    is_required: bool = False

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraWorkAttribute":
        """
        Create a JiraWorkAttribute from a Tempo Core API response.

        Args:
            data: The work attribute data from the Tempo Core API
            **kwargs: Additional context parameters (unused)

        Returns:
            A JiraWorkAttribute instance
        """
        if not data:
            return cls()

        if not isinstance(data, dict):
            return cls()

        attribute_id = data.get("id", 0)
        if attribute_id is not None:
            attribute_id = int(attribute_id)

        is_required = data.get("isRequired", False)
        if isinstance(is_required, str):
            is_required = is_required.lower() in ("true", "1", "yes")

        return cls(
            id=attribute_id,
            name=data.get("name", EMPTY_STRING),
            type=data.get("type", EMPTY_STRING),
            description=data.get("description", EMPTY_STRING),
            is_required=is_required,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "is_required": self.is_required,
        }


class JiraWorkAttributeValue(ApiModel):
    """
    Model representing a value for a Tempo Core Work Attribute.

    Each work attribute type has associated values. For example, a
    "singleselect" attribute might have values like "Office", "Remote",
    "On-site", etc.

    Attributes:
        id: Unique identifier for the value
        name: Human-readable name of the value
        color: Optional color code for UI display
        work_attribute_id: ID of the parent work attribute this value belongs to
    """

    id: int = 0
    name: str = EMPTY_STRING
    color: str = EMPTY_STRING
    work_attribute_id: int = 0

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraWorkAttributeValue":
        """
        Create a JiraWorkAttributeValue from a Tempo Core API response.

        Args:
            data: The work attribute value data from the Tempo Core API
            **kwargs: Additional context parameters (unused)

        Returns:
            A JiraWorkAttributeValue instance
        """
        if not data:
            return cls()

        if not isinstance(data, dict):
            return cls()

        value_id = data.get("id", 0)
        if value_id is not None:
            value_id = int(value_id)

        work_attribute_id = data.get("workAttributeId", 0)
        if work_attribute_id is not None:
            work_attribute_id = int(work_attribute_id)

        return cls(
            id=value_id,
            name=data.get("name", EMPTY_STRING),
            color=data.get("color", EMPTY_STRING),
            work_attribute_id=work_attribute_id,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "work_attribute_id": self.work_attribute_id,
        }
