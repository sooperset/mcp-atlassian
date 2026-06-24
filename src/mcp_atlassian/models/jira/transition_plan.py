"""Jira transition planning models."""

from enum import Enum
from typing import Any

from pydantic import ConfigDict, Field

from ..base import ApiModel


class TransitionPlanStatus(str, Enum):
    """Lifecycle status for a transition plan."""

    CREATED = "created"
    NEEDS_USER_INPUT = "needs_user_input"
    READY = "ready"
    PREVIEWED = "previewed"
    APPLIED = "applied"
    STALE = "stale"
    FAILED = "failed"


class TransitionFieldSource(str, Enum):
    """Source of a field value in a transition plan."""

    CURRENT_ISSUE = "current_issue"
    AUTO_DRAFT = "auto_draft"
    USER_SELECTION = "user_selection"
    EMPTY = "empty"


class TransitionFieldValue(ApiModel):
    """A candidate or final value for a transition field."""

    value: Any = None
    source: TransitionFieldSource
    changed: bool = False
    destructive: bool = False
    confidence: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class TransitionFieldPlan(ApiModel):
    """Planning metadata for one transition screen field."""

    model_config = ConfigDict(populate_by_name=True)

    field_key: str
    name: str
    field_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
    required: bool = False
    required_level: str = "optional"
    operations: list[str] = Field(default_factory=list)
    interaction_type: str = "text_input"
    value_format: str = "raw"
    lookup_tool: str | None = None
    needs_user_input: bool = False
    current_value: Any = None
    auto_draft: TransitionFieldValue | None = None
    user_value: TransitionFieldValue | None = None
    final_value: TransitionFieldValue | None = None


class TransitionStaleChecks(ApiModel):
    """Jira state captured when a transition plan was prepared."""

    issue_updated: str
    status_id: str | None = None
    transition_id: str
    schema_hash: str
    latest_comment_id: str | None = None
    latest_comment_updated: str | None = None
    comment_fingerprints: dict[str, str] = Field(default_factory=dict)


class TransitionPlan(ApiModel):
    """A prepared Jira transition plan."""

    plan_id: str
    issue_key: str
    transition_id: str
    transition_name: str
    to_status: str | None = None
    schema_hash: str
    issue_updated: str
    status: TransitionPlanStatus = TransitionPlanStatus.CREATED
    profile: str | None = None
    fields: list[TransitionFieldPlan] = Field(default_factory=list)
    comment_context: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    stale_checks: TransitionStaleChecks | None = None
    last_preview_id: str | None = None
    last_payload_hash: str | None = None

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary using API-facing aliases."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)
