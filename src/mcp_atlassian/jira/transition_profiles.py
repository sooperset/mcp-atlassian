"""Workflow profiles for Jira transition planning."""

from typing import Any

GYENNO_DEFECT_ANALYSIS_PROFILE: dict[str, Any] = {
    "name": "gyenno_defect_analysis",
    "transitions": ["完成分析", "更新信息"],
    "soft_required": True,
    "fields": {
        "引入版本": {"semantic": "introduced_versions"},
        "解决版本": {"semantic": "fixed_versions"},
        "历史数据处理": {"semantic": "historical_data_handling"},
        "缺陷产生原因": {"semantic": "defect_cause"},
        "根因描述": {"semantic": "root_cause"},
        "短期应对措施": {"semantic": "short_term_action"},
        "解决方案": {"semantic": "solution"},
    },
}

_PROFILES = {
    GYENNO_DEFECT_ANALYSIS_PROFILE["name"]: GYENNO_DEFECT_ANALYSIS_PROFILE,
}


def get_transition_profile(name: str | None) -> dict[str, Any]:
    """Return a transition workflow profile by name."""
    if not name:
        return {}
    profile = _PROFILES.get(name)
    return dict(profile) if profile else {}
