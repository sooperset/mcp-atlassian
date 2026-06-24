"""Tests for Jira transition planning."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.transition_schema import VERSION_LOOKUP_TOOL
from mcp_atlassian.models.jira import JiraIssue, JiraStatus
from mcp_atlassian.models.jira.common import JiraUser
from mcp_atlassian.models.jira.transition_plan import (
    TransitionFieldSource,
    TransitionFieldValue,
    TransitionPlanStatus,
)


def _issue() -> JiraIssue:
    return JiraIssue(
        id="8714",
        key="RY-8714",
        summary="Scale report analysis",
        updated="2026-06-16T10:00:00.000+0800",
        status=JiraStatus(id="10001", name="待处理"),
        assignee=JiraUser(name="jianghaitao", display_name="江海涛"),
        custom_fields={
            "customfield_11405": {
                "name": "引入版本",
                "value": [{"id": "20001", "name": "通用版V2.13.1"}],
            }
        },
    )


def _transition() -> dict[str, object]:
    return {
        "id": "761",
        "name": "更新信息",
        "to": {"id": "10002", "name": "处理中"},
        "to_status": "处理中",
        "fields": {
            "customfield_11405": {
                "required": False,
                "name": "引入版本",
                "schema": {
                    "type": "array",
                    "items": "version",
                    "custom": (
                        "com.atlassian.jira.plugin.system."
                        "customfieldtypes:multiversion"
                    ),
                    "customId": 11405,
                },
                "allowedValues": [
                    {"id": str(index), "name": f"V{index}"}
                    for index in range(100)
                ],
            },
            "customfield_12000": {
                "required": True,
                "name": "根因描述",
                "schema": {
                    "type": "string",
                    "custom": (
                        "com.atlassian.jira.plugin.system."
                        "customfieldtypes:textarea"
                    ),
                },
            },
        },
    }


@pytest.fixture
def planning_fetcher(jira_fetcher: JiraFetcher) -> JiraFetcher:
    jira_fetcher.get_issue = MagicMock(return_value=_issue())
    jira_fetcher.get_available_transitions = MagicMock(return_value=[_transition()])
    jira_fetcher.jira.issue_get_comments.return_value = {
        "comments": [
            {
                "id": "77717",
                "body": "影响范围：副作用监测量表第 3 题",
                "author": {"name": "jianghaitao", "displayName": "江海涛"},
                "created": "2026-06-16T11:00:00.000+0800",
                "updated": "2026-06-16T11:00:00.000+0800",
            }
        ]
    }
    return jira_fetcher


def test_prepare_transition_plan_resolves_transition_by_name(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
        profile="gyenno_defect_analysis",
    )

    assert plan.issue_key == "RY-8714"
    assert plan.transition_id == "761"
    assert plan.transition_name == "更新信息"
    assert plan.to_status == "处理中"
    assert plan.profile == "gyenno_defect_analysis"


def test_prepare_transition_plan_parses_fields_and_reuses_current_values(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )

    version_field = next(
        field for field in plan.fields if field.field_key == "customfield_11405"
    )
    assert version_field.interaction_type == "version_picker"
    assert version_field.lookup_tool == VERSION_LOOKUP_TOOL
    assert version_field.needs_user_input is True
    assert version_field.current_value == [{"id": "20001", "name": "通用版V2.13.1"}]

    root_cause_field = next(
        field for field in plan.fields if field.field_key == "customfield_12000"
    )
    assert root_cause_field.required is True
    assert root_cause_field.required_level == "hard"


def test_prepare_transition_plan_includes_weighted_comment_evidence(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )

    assert plan.comment_context["used"] == 1
    high_value = plan.comment_context["high_value_comments"][0]
    assert "assignee_analysis" in high_value["category"]
    assert "impact_scope" in high_value["category"]
    assert "副作用监测量表" in high_value["extracted_facts"][0]
    planning_fetcher.jira.issue_get_comments.assert_called_once_with("RY-8714")


def test_prepare_transition_plan_uses_random_plan_id(
    planning_fetcher: JiraFetcher,
) -> None:
    first = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    second = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )

    assert first.plan_id != second.plan_id
    assert not first.plan_id.startswith("RY-8714:761")
    assert len(first.plan_id) >= 20


def test_preview_reuses_current_issue_value_when_no_override(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )

    preview = planning_fetcher.preview_transition_plan(plan)

    assert preview["payload"]["fields"]["customfield_11405"] == [
        {"id": "20001"}
    ]
    assert preview["field_sources"]["customfield_11405"] == "current_issue"
    assert "customfield_11405" in preview["unchanged_reused_fields"]
    assert plan.last_preview_id == preview["preview_id"]
    assert plan.last_payload_hash == preview["payload_hash"]


def test_preview_value_priority_user_then_auto_then_current(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    version_field = next(
        field for field in plan.fields if field.field_key == "customfield_11405"
    )
    version_field.auto_draft = TransitionFieldValue(
        value=["30001"],
        source=TransitionFieldSource.AUTO_DRAFT,
        changed=True,
    )

    auto_preview = planning_fetcher.preview_transition_plan(plan)
    assert auto_preview["payload"]["fields"]["customfield_11405"] == [
        {"id": "30001"}
    ]
    assert auto_preview["field_sources"]["customfield_11405"] == "auto_draft"

    planning_fetcher.update_transition_plan(
        plan,
        field_values={"customfield_11405": ["40001"]},
    )
    user_preview = planning_fetcher.preview_transition_plan(plan)

    assert user_preview["payload"]["fields"]["customfield_11405"] == [
        {"id": "40001"}
    ]
    assert user_preview["field_sources"]["customfield_11405"] == "user_selection"
    assert "customfield_11405" in user_preview["changed_fields"]


def test_preview_omits_empty_optional_and_reports_missing_required(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )

    preview = planning_fetcher.preview_transition_plan(plan)

    assert "customfield_12000" not in preview["payload"]["fields"]
    assert preview["missing_fields"] == [
        {"field_key": "customfield_12000", "name": "根因描述"}
    ]


def test_preview_reports_soft_missing_fields(planning_fetcher: JiraFetcher) -> None:
    transition = _transition()
    fields = transition["fields"]
    assert isinstance(fields, dict)
    fields["customfield_12000"]["required"] = False
    planning_fetcher.get_available_transitions = MagicMock(return_value=[transition])

    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
        profile="gyenno_defect_analysis",
    )

    preview = planning_fetcher.preview_transition_plan(plan)

    assert preview["missing_fields"] == []
    assert preview["soft_missing_fields"] == [
        {"field_key": "customfield_12000", "name": "根因描述"}
    ]


def test_preview_transition_plan_rejects_stale_issue(
    planning_fetcher: JiraFetcher,
) -> None:
    """Test preview refuses to present a payload when the issue changed."""
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    changed_issue = _issue()
    changed_issue.updated = "2026-06-16T12:00:00.000+0800"
    planning_fetcher.get_issue = MagicMock(return_value=changed_issue)

    preview = planning_fetcher.preview_transition_plan(plan)

    assert preview["status"] == "stale"
    assert preview["freshness"]["hard_stale"] is True
    assert "payload" not in preview


def test_preview_marks_explicit_clear_as_destructive(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )

    planning_fetcher.update_transition_plan(
        plan,
        field_values={},
        cleared_fields=["customfield_11405"],
    )
    preview = planning_fetcher.preview_transition_plan(plan)

    assert preview["payload"]["fields"]["customfield_11405"] == []
    assert preview["destructive_changes"] == ["customfield_11405"]


def test_validate_transition_plan_detects_status_change(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    changed_issue = _issue()
    changed_issue.status = JiraStatus(id="10009", name="已处理")
    planning_fetcher.get_issue = MagicMock(return_value=changed_issue)

    result = planning_fetcher.validate_transition_plan_freshness(plan)

    assert result["fresh"] is False
    assert result["hard_stale"] is True
    assert "issue status changed" in result["reasons"]


def test_validate_transition_plan_detects_issue_updated_change(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    changed_issue = _issue()
    changed_issue.updated = "2026-06-16T12:00:00.000+0800"
    planning_fetcher.get_issue = MagicMock(return_value=changed_issue)

    result = planning_fetcher.validate_transition_plan_freshness(plan)

    assert result["fresh"] is False
    assert result["hard_stale"] is True
    assert "issue was updated after planning" in result["reasons"]


def test_validate_transition_plan_detects_missing_transition(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    planning_fetcher.get_available_transitions = MagicMock(return_value=[])

    result = planning_fetcher.validate_transition_plan_freshness(plan)

    assert result["fresh"] is False
    assert result["hard_stale"] is True
    assert "transition is no longer available" in result["reasons"]


def test_validate_transition_plan_detects_schema_change(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    changed_transition = _transition()
    changed_fields = changed_transition["fields"]
    assert isinstance(changed_fields, dict)
    changed_fields["customfield_12000"]["required"] = False
    planning_fetcher.get_available_transitions = MagicMock(
        return_value=[changed_transition]
    )

    result = planning_fetcher.validate_transition_plan_freshness(plan)

    assert result["fresh"] is False
    assert result["hard_stale"] is True
    assert "transition schema changed" in result["reasons"]


def test_validate_transition_plan_requires_reconfirm_for_new_assignee_comment(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    planning_fetcher.jira.issue_get_comments.return_value = {
        "comments": [
            {
                "id": "77717",
                "body": "影响范围：副作用监测量表第 3 题",
                "author": {"name": "jianghaitao", "displayName": "江海涛"},
                "updated": "2026-06-16T11:00:00.000+0800",
            },
            {
                "id": "77718",
                "body": "影响范围：报告生成和历史数据处理",
                "author": {"name": "jianghaitao", "displayName": "江海涛"},
                "updated": "2026-06-16T12:00:00.000+0800",
            },
        ]
    }

    result = planning_fetcher.validate_transition_plan_freshness(plan)

    assert result["fresh"] is False
    assert result["hard_stale"] is False
    assert result["requires_reconfirmation"] is True
    assert "new high-value assignee comment" in result["reasons"]


def test_validate_transition_plan_ignores_new_low_value_comment(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    planning_fetcher.jira.issue_get_comments.return_value = {
        "comments": [
            {
                "id": "77717",
                "body": "影响范围：副作用监测量表第 3 题",
                "author": {"name": "jianghaitao", "displayName": "江海涛"},
                "updated": "2026-06-16T11:00:00.000+0800",
            },
            {
                "id": "77718",
                "body": "",
                "author": {"name": "other", "displayName": "Other"},
                "updated": "2026-06-16T12:00:00.000+0800",
            },
        ]
    }

    result = planning_fetcher.validate_transition_plan_freshness(plan)

    assert result["fresh"] is True
    assert result["hard_stale"] is False
    assert result["requires_reconfirmation"] is False
    assert "new high-value assignee comment" not in result["reasons"]


def test_validate_transition_plan_requires_reconfirm_for_edited_assignee_comment(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    planning_fetcher.jira.issue_get_comments.return_value = {
        "comments": [
            {
                "id": "77717",
                "body": "影响范围：报告生成和历史数据处理",
                "author": {"name": "jianghaitao", "displayName": "江海涛"},
                "updated": "2026-06-16T12:00:00.000+0800",
            },
        ]
    }

    result = planning_fetcher.validate_transition_plan_freshness(plan)

    assert result["fresh"] is False
    assert result["requires_reconfirmation"] is True
    assert "new high-value assignee comment" in result["reasons"]


def test_apply_transition_plan_requires_confirmation_and_matching_hash(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    planning_fetcher.update_transition_plan(
        plan,
        field_values={"customfield_12000": "字段解析缺失"},
    )

    unconfirmed = planning_fetcher.apply_transition_plan(plan)
    assert unconfirmed["success"] is False
    assert unconfirmed["status"] == "confirmation_required"

    preview = planning_fetcher.preview_transition_plan(plan)
    mismatched = planning_fetcher.apply_transition_plan(
        plan,
        confirmed=True,
        payload_hash="wrong",
    )
    assert mismatched["success"] is False
    assert mismatched["status"] == "payload_hash_mismatch"

    planning_fetcher.transition_issue = MagicMock(return_value=_issue())
    applied = planning_fetcher.apply_transition_plan(
        plan,
        confirmed=True,
        payload_hash=preview["payload_hash"],
    )

    assert applied["success"] is True
    assert applied["status"] == "applied"
    planning_fetcher.transition_issue.assert_called_once_with(
        "RY-8714",
        "761",
        fields={
            "customfield_11405": [{"id": "20001"}],
            "customfield_12000": "字段解析缺失",
        },
    )


def test_apply_transition_plan_requires_prior_preview(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    planning_fetcher.update_transition_plan(
        plan,
        field_values={"customfield_12000": "字段解析缺失"},
    )

    result = planning_fetcher.apply_transition_plan(
        plan,
        confirmed=True,
        payload_hash="hash-from-nowhere",
    )

    assert result["success"] is False
    assert result["status"] == "preview_required"


def test_apply_transition_plan_refuses_already_applied_plan(
    planning_fetcher: JiraFetcher,
) -> None:
    plan = planning_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
    )
    plan.status = TransitionPlanStatus.APPLIED

    result = planning_fetcher.apply_transition_plan(plan, confirmed=True)

    assert result["success"] is False
    assert result["status"] == "already_applied"
