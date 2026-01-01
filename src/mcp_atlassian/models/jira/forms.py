"""
ProForma form models for Jira.

This module provides Pydantic models for ProForma forms in Jira,
including form state, fields, and submission data.
"""

import logging
from datetime import datetime
from typing import Any

from pydantic import Field

from ..base import ApiModel

logger = logging.getLogger(__name__)


class ProFormaFormState(ApiModel):
    """
    Model representing the state of a ProForma form.
    """

    status: str = Field(
        description="Status of the form (e.g., 'o' for open, 's' for submitted)"
    )
    version: str | None = Field(None, description="Version of the form")
    submitted_at: datetime | None = Field(
        None, description="Timestamp when the form was submitted"
    )
    submitted_by: str | None = Field(None, description="User who submitted the form")

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ProFormaFormState":
        """
        Create a ProFormaFormState from a Jira API response.

        Args:
            data: The form state data from the Jira API

        Returns:
            A ProFormaFormState instance
        """
        return cls(
            status=data.get("status", "o"),
            version=data.get("version"),
            submitted_at=data.get("submittedAt"),
            submitted_by=data.get("submittedBy"),
        )


class ProFormaFormField(ApiModel):
    """
    Model representing a field in a ProForma form.
    """

    id: str = Field(description="Unique identifier of the form field")
    name: str = Field(description="Display name of the field")
    type: str = Field(description="Type of the field (e.g., 'text', 'select', 'date')")
    value: Any = Field(None, description="Current value of the field")
    required: bool = Field(default=False, description="Whether the field is required")
    read_only: bool = Field(default=False, description="Whether the field is read-only")

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "ProFormaFormField":
        """
        Create a ProFormaFormField from a Jira API response.

        Args:
            data: The form field data from the Jira API

        Returns:
            A ProFormaFormField instance
        """
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            type=data.get("type", "text"),
            value=data.get("value"),
            required=data.get("required", False),
            read_only=data.get("readOnly", False),
        )


class ProFormaForm(ApiModel):
    """
    Model representing a complete ProForma form.

    Supports both the legacy entity properties API and the new Forms REST API.
    """

    id: str = Field(description="Unique identifier of the form (UUID in new API)")
    form_id: str = Field(
        description="Form ID used in API calls (UUID in new API, 'i' prefix in old API)"
    )
    name: str | None = Field(None, description="Display name of the form")
    description: str | None = Field(None, description="Description of the form")
    state: ProFormaFormState = Field(description="Current state of the form")
    fields: list[ProFormaFormField] = Field(
        default_factory=list, description="List of form fields"
    )
    issue_key: str | None = Field(None, description="Associated Jira issue key")
    updated: datetime | None = Field(
        None, description="Last updated timestamp"
    )
    internal: bool | None = Field(
        None, description="Whether form is internal only"
    )
    submitted: bool | None = Field(
        None, description="Whether form is submitted"
    )
    lock: bool | None = Field(None, description="Whether form is locked")
    design: dict[str, Any] | None = Field(
        None, description="ADF design data"
    )

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "ProFormaForm":
        """
        Create a ProFormaForm from a Jira Forms API response.

        Args:
            data: The form data from the Jira Forms API
            kwargs: Additional context like issue_key

        Returns:
            A ProFormaForm instance
        """
        # Forms API format
        # List response: {id, formTemplate, internal, submitted, lock, name, updated}
        # Detail response: {id, updated, design: {conditions, layout}}

        # Try to determine status from submitted flag
        status = "s" if data.get("submitted", False) else "o"
        state = ProFormaFormState(
            status=status, version=None, submitted_at=None, submitted_by=None
        )

        # Fields are not included in list responses
        fields: list[ProFormaFormField] = []

        # Store the design data
        design = data.get("design")

        return cls(
            id=data.get("id", ""),
            form_id=data.get("id", ""),  # form_id is the UUID
            name=data.get("name"),
            description=None,  # Not in simple list response
            state=state,
            fields=fields,
            issue_key=kwargs.get("issue_key"),
            updated=data.get("updated"),
            internal=data.get("internal"),
            submitted=data.get("submitted"),
            lock=data.get("lock"),
            design=design,
        )

    def is_open(self) -> bool:
        """Check if the form is in an open state."""
        return self.state.status == "o"

    def is_submitted(self) -> bool:
        """Check if the form has been submitted."""
        return self.state.status == "s"
