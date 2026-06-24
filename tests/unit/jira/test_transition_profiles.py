"""Tests for Jira transition workflow profiles."""

from unittest.mock import MagicMock

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.transition_profiles import get_transition_profile
from tests.unit.jira.test_transition_planning import _issue, _transition


def test_gyenno_profile_maps_known_fields() -> None:
    profile = get_transition_profile("gyenno_defect_analysis")

    assert profile["name"] == "gyenno_defect_analysis"
    assert profile["soft_required"] is True
    assert set(profile["transitions"]) == {"完成分析", "更新信息"}
    assert set(profile["fields"]) == {
        "引入版本",
        "解决版本",
        "历史数据处理",
        "缺陷产生原因",
        "根因描述",
        "短期应对措施",
        "解决方案",
    }
    assert profile["fields"]["引入版本"]["semantic"] == "introduced_versions"


def test_unknown_profile_returns_empty_profile() -> None:
    assert get_transition_profile("unknown") == {}
    assert get_transition_profile(None) == {}


def test_prepare_transition_plan_applies_profile_soft_required(
    jira_fetcher: JiraFetcher,
) -> None:
    transition = _transition()
    fields = transition["fields"]
    assert isinstance(fields, dict)
    fields["customfield_12000"]["required"] = False

    jira_fetcher.get_issue = MagicMock(return_value=_issue())
    jira_fetcher.get_available_transitions = MagicMock(return_value=[transition])
    jira_fetcher.jira.issue_get_comments.return_value = {"comments": []}

    plan = jira_fetcher.prepare_transition_plan(
        "RY-8714",
        target_transition_name="更新信息",
        profile="gyenno_defect_analysis",
    )

    root_cause = next(
        field for field in plan.fields if field.field_key == "customfield_12000"
    )
    assert root_cause.required is False
    assert root_cause.required_level == "soft"
