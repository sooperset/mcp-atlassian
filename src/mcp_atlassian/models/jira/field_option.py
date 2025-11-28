"""Data models for Jira custom field options."""

from typing import Any

from pydantic import BaseModel, Field

from ..base import ApiModel


class JiraFieldOption(BaseModel):
    """Model representing a custom field option in Jira."""

    id: str = Field(description="Unique identifier for the option")
    value: str = Field(description="Display value of the option")
    disabled: bool = Field(default=False, description="Whether the option is disabled")
    config: dict[str, Any] | None = Field(
        default=None, description="Configuration details for the option"
    )


class JiraFieldContext(BaseModel):
    """Model representing a field context in Jira."""

    id: str = Field(description="Unique identifier for the context")
    name: str = Field(description="Name of the context")
    description: str | None = Field(
        default=None, description="Description of the context"
    )
    is_global_context: bool = Field(
        default=False,
        description="Whether this is a global context",
        alias="isGlobalContext",
    )
    is_any_issue_type: bool = Field(
        default=False,
        description="Whether the context applies to any issue type",
        alias="isAnyIssueType",
    )


class JiraFieldOptionsResponse(ApiModel):
    """Model representing the response when fetching field options."""

    max_results: int = Field(
        description="Maximum results per page", alias="maxResults", default=0
    )
    start_at: int = Field(
        description="Starting index of results", alias="startAt", default=0
    )
    total: int = Field(description="Total number of options available", default=0)
    is_last: bool = Field(
        description="Whether this is the last page", alias="isLast", default=True
    )
    values: list[JiraFieldOption] = Field(
        description="List of field options", default_factory=list
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraFieldOptionsResponse":
        """Create a JiraFieldOptionsResponse from a Jira API response."""
        if not data or not isinstance(data, dict):
            return cls()

        values = []
        # Handle both Cloud ("values") and DC/Server ("options") response formats
        values_data = data.get("values", data.get("options", []))
        if isinstance(values_data, list):
            for value_data in values_data:
                if value_data and isinstance(value_data, dict):
                    values.append(
                        JiraFieldOption(
                            id=str(value_data.get("id", "")),
                            value=str(value_data.get("value", "")),
                            disabled=bool(value_data.get("disabled", False)),
                            config=value_data.get("config"),
                        )
                    )

        # Extract pagination info - Cloud includes it, DC/Server might not
        total = int(data.get("total", len(values)))
        max_results = int(data.get("maxResults", data.get("max_results", len(values))))
        start_at = int(data.get("startAt", data.get("start_at", 0)))
        is_last = bool(data.get("isLast", data.get("is_last", True)))

        # For DC/Server responses that don't include pagination info,
        # calculate is_last based on results returned vs requested
        if "isLast" not in data and "is_last" not in data:
            # If we have fewer results than max_results, we're on the last page
            requested_max = kwargs.get("max_results", max_results)
            if len(values) < requested_max:
                is_last = True

        return cls(
            max_results=max_results,
            start_at=start_at,
            total=total,
            is_last=is_last,
            values=values,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary format."""
        return {
            "pagination": {
                "start_at": self.start_at,
                "max_results": self.max_results,
                "total": self.total,
                "is_last": self.is_last,
            },
            "options": [
                {
                    "id": option.id,
                    "value": option.value,
                    "disabled": option.disabled,
                    "config": option.config,
                }
                for option in self.values
            ],
        }


class JiraFieldContextOptionsResponse(ApiModel):
    """Model representing the response when fetching field context options."""

    max_results: int = Field(description="Maximum results per page", alias="maxResults")
    start_at: int = Field(description="Starting index of results", alias="startAt")
    total: int = Field(description="Total number of options available")
    is_last: bool = Field(description="Whether this is the last page", alias="isLast")
    values: list[JiraFieldOption] = Field(
        description="List of field options for the context"
    )
    context: JiraFieldContext | None = Field(
        default=None, description="Context information"
    )

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraFieldContextOptionsResponse":
        """Create a JiraFieldContextOptionsResponse from a Jira API response."""
        if not data or not isinstance(data, dict):
            return cls()

        values = []
        # Handle both Cloud ("values") and DC/Server ("options") response formats
        values_data = data.get("values", data.get("options", []))
        if isinstance(values_data, list):
            for value_data in values_data:
                if value_data and isinstance(value_data, dict):
                    values.append(
                        JiraFieldOption(
                            id=str(value_data.get("id", "")),
                            value=str(value_data.get("value", "")),
                            disabled=bool(value_data.get("disabled", False)),
                            config=value_data.get("config"),
                        )
                    )

        context = None
        context_data = data.get("context")
        if context_data and isinstance(context_data, dict):
            context = JiraFieldContext(
                id=str(context_data.get("id", "")),
                name=str(context_data.get("name", "")),
                description=context_data.get("description"),
                is_global_context=bool(context_data.get("isGlobalContext", False)),
                is_any_issue_type=bool(context_data.get("isAnyIssueType", False)),
            )

        # Extract pagination info - handle both Cloud and DC/Server formats
        total = int(data.get("total", len(values)))
        max_results = int(data.get("maxResults", data.get("max_results", len(values))))
        start_at = int(data.get("startAt", data.get("start_at", 0)))
        is_last = bool(data.get("isLast", data.get("is_last", True)))

        # For DC/Server responses that don't include pagination info,
        # calculate is_last based on results returned vs requested
        if "isLast" not in data and "is_last" not in data:
            # If we have fewer results than max_results, we're on the last page
            requested_max = kwargs.get("max_results", max_results)
            if len(values) < requested_max:
                is_last = True

        return cls(
            max_results=max_results,
            start_at=start_at,
            total=total,
            is_last=is_last,
            values=values,
            context=context,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary format."""
        result = {
            "pagination": {
                "start_at": self.start_at,
                "max_results": self.max_results,
                "total": self.total,
                "is_last": self.is_last,
            },
            "options": [
                {
                    "id": option.id,
                    "value": option.value,
                    "disabled": option.disabled,
                    "config": option.config,
                }
                for option in self.values
            ],
        }

        if self.context:
            result["context"] = {
                "id": self.context.id,
                "name": self.context.name,
                "description": self.context.description,
                "is_global_context": self.context.is_global_context,
                "is_any_issue_type": self.context.is_any_issue_type,
            }

        return result


class JiraFieldContextsResponse(ApiModel):
    """Model representing the response when fetching field contexts."""

    max_results: int = Field(description="Maximum results per page", alias="maxResults")
    start_at: int = Field(description="Starting index of results", alias="startAt")
    total: int = Field(description="Total number of contexts available")
    is_last: bool = Field(description="Whether this is the last page", alias="isLast")
    values: list[JiraFieldContext] = Field(description="List of field contexts")

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraFieldContextsResponse":
        """Create a JiraFieldContextsResponse from a Jira API response."""
        if not data or not isinstance(data, dict):
            return cls()

        values = []
        values_data = data.get("values", [])
        if isinstance(values_data, list):
            for value_data in values_data:
                if value_data and isinstance(value_data, dict):
                    values.append(
                        JiraFieldContext(
                            id=str(value_data.get("id", "")),
                            name=str(value_data.get("name", "")),
                            description=value_data.get("description"),
                            is_global_context=bool(
                                value_data.get("isGlobalContext", False)
                            ),
                            is_any_issue_type=bool(
                                value_data.get("isAnyIssueType", False)
                            ),
                        )
                    )

        # Extract pagination info - handle both Cloud and DC/Server formats
        total = int(data.get("total", len(values)))
        max_results = int(data.get("maxResults", data.get("max_results", len(values))))
        start_at = int(data.get("startAt", data.get("start_at", 0)))
        is_last = bool(data.get("isLast", data.get("is_last", True)))

        # For DC/Server responses that don't include pagination info,
        # calculate is_last based on results returned vs requested
        if "isLast" not in data and "is_last" not in data:
            # If we have fewer results than max_results, we're on the last page
            requested_max = kwargs.get("max_results", max_results)
            if len(values) < requested_max:
                is_last = True

        return cls(
            max_results=max_results,
            start_at=start_at,
            total=total,
            is_last=is_last,
            values=values,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary format."""
        return {
            "pagination": {
                "start_at": self.start_at,
                "max_results": self.max_results,
                "total": self.total,
                "is_last": self.is_last,
            },
            "contexts": [
                {
                    "id": context.id,
                    "name": context.name,
                    "description": context.description,
                    "is_global_context": context.is_global_context,
                    "is_any_issue_type": context.is_any_issue_type,
                }
                for context in self.values
            ],
        }
