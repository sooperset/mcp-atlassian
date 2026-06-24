"""Tests for Jira transition plan models."""

from mcp_atlassian.models.jira.transition_plan import (
    TransitionFieldPlan,
    TransitionFieldSource,
    TransitionFieldValue,
    TransitionPlan,
    TransitionPlanStatus,
    TransitionStaleChecks,
)


def test_transition_plan_defaults_to_created() -> None:
    """Transition plans start in the created state."""
    plan = TransitionPlan(
        plan_id="RY-8714:771:test",
        issue_key="RY-8714",
        transition_id="771",
        transition_name="完成分析",
        to_status="已分析",
        schema_hash="abc",
        issue_updated="2026-06-16T10:00:00.000+0800",
    )

    assert plan.status == TransitionPlanStatus.CREATED
    assert plan.fields == []
    assert plan.comment_context == {}
    assert plan.last_preview_id is None
    assert plan.last_payload_hash is None


def test_transition_field_plan_records_interaction_metadata() -> None:
    """Field plans describe how callers should collect and submit values."""
    field = TransitionFieldPlan(
        field_key="customfield_11405",
        name="引入版本",
        schema={"type": "array", "items": "version"},
        required=False,
        required_level="soft",
        operations=["set", "add", "remove"],
        interaction_type="version_picker",
        value_format="array_of_id_objects",
        lookup_tool="jira_search_transition_field_options",
        needs_user_input=True,
    )

    assert field.field_key == "customfield_11405"
    assert field.interaction_type == "version_picker"
    assert field.value_format == "array_of_id_objects"
    assert field.field_schema == {"type": "array", "items": "version"}
    assert field.required_level == "soft"
    assert field.needs_user_input is True


def test_transition_field_value_tracks_source_and_destructive_state() -> None:
    """Field values preserve source, change state, and evidence."""
    value = TransitionFieldValue(
        value=[{"id": "12345"}],
        source=TransitionFieldSource.USER_SELECTION,
        changed=True,
        destructive=False,
        confidence="high",
        evidence=[{"type": "comment", "id": "77717"}],
    )

    assert value.source == TransitionFieldSource.USER_SELECTION
    assert value.changed is True
    assert value.destructive is False
    assert value.evidence[0]["id"] == "77717"


def test_transition_plan_dump_uses_schema_alias() -> None:
    """Serialized plans expose Jira-facing schema keys."""
    plan = TransitionPlan(
        plan_id="RY-8714:771:test",
        issue_key="RY-8714",
        transition_id="771",
        transition_name="完成分析",
        schema_hash="abc",
        issue_updated="2026-06-16T10:00:00.000+0800",
        fields=[
            TransitionFieldPlan(
                field_key="customfield_11405",
                name="引入版本",
                schema={"type": "array", "items": "version"},
            )
        ],
    )

    payload = plan.to_simplified_dict()

    assert payload["fields"][0]["schema"] == {"type": "array", "items": "version"}
    assert "field_schema" not in payload["fields"][0]


def test_transition_plan_records_stale_checks_and_preview_hashes() -> None:
    """Plans store stale-check state and last preview identifiers."""
    checks = TransitionStaleChecks(
        issue_updated="2026-06-16T10:00:00.000+0800",
        status_id="3",
        transition_id="771",
        schema_hash="abc",
        latest_comment_id="77717",
        latest_comment_updated="2026-06-16T10:10:00.000+0800",
    )
    plan = TransitionPlan(
        plan_id="RY-8714:771:test",
        issue_key="RY-8714",
        transition_id="771",
        transition_name="完成分析",
        schema_hash="abc",
        issue_updated="2026-06-16T10:00:00.000+0800",
        stale_checks=checks,
        last_preview_id="preview-1",
        last_payload_hash="payload-hash",
    )

    assert plan.stale_checks == checks
    assert plan.last_preview_id == "preview-1"
    assert plan.last_payload_hash == "payload-hash"
