"""
Jira custom field option models.

This module provides Pydantic models for Jira custom field contexts
and options, used for discovering allowed values for select, radio,
checkbox, and cascading select fields.
"""

from typing import Any

from pydantic import Field

from ..base import ApiModel


class FieldContext(ApiModel):
    """Model representing a custom field context in Jira Cloud."""

    id: str
    name: str
    description: str = ""
    is_global_context: bool = False
    is_any_issue_type: bool = False

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "FieldContext":
        """Create a FieldContext from a Jira API response.

        Args:
            data: The context data from the Jira API

        Returns:
            A FieldContext instance
        """
        if not data or not isinstance(data, dict):
            return cls(id="", name="")

        return cls(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            description=data.get("description", ""),
            is_global_context=data.get("isGlobalContext", False),
            is_any_issue_type=data.get("isAnyIssueType", False),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
        }
        if self.description:
            result["description"] = self.description
        if self.is_global_context:
            result["is_global_context"] = True
        return result


class FieldOption(ApiModel):
    """Model representing a custom field option value."""

    id: str
    value: str
    disabled: bool = False
    child_options: list["FieldOption"] = Field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "FieldOption":
        """Create a FieldOption from a Jira API response.

        Args:
            data: The option data from the Jira API

        Returns:
            A FieldOption instance
        """
        if not data or not isinstance(data, dict):
            return cls(id="", value="")

        children = [
            cls.from_api_response(c)
            for c in data.get("cascadingOptions", [])
            if isinstance(c, dict)
        ]

        return cls(
            id=str(data.get("id", data.get("optionId", ""))),
            value=data.get("value", ""),
            disabled=data.get("disabled", False),
            child_options=children,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result: dict[str, Any] = {
            "id": self.id,
            "value": self.value,
        }
        if self.disabled:
            result["disabled"] = True
        if self.child_options:
            result["child_options"] = [
                child.to_simplified_dict() for child in self.child_options
            ]
        return result
