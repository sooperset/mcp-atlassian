"""Tests for the Jira VelocityMixin."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira.velocity import VelocityMixin


@pytest.fixture
def velocity_mixin(jira_fetcher) -> VelocityMixin:
    """Create a VelocityMixin instance with mocked dependencies."""
    return jira_fetcher


def test_get_sprint_velocity_success(velocity_mixin: VelocityMixin) -> None:
    """Sprint velocity aggregates committed and completed points."""

    def get_side_effect(*args, **kwargs):
        path = kwargs.get("path") or args[0]
        if path == "rest/agile/1.0/board/42/configuration":
            return {
                "estimation": {
                    "field": {
                        "fieldId": "customfield_10016",
                    }
                }
            }
        if path == "rest/agile/1.0/sprint/101":
            return {
                "id": 101,
                "name": "Sprint 101",
                "state": "closed",
                "startDate": "2026-01-01",
                "endDate": "2026-01-14",
            }
        if path == "rest/agile/1.0/sprint/101/issue":
            return {
                "issues": [
                    {
                        "id": "1",
                        "fields": {
                            "customfield_10016": 5,
                            "status": {
                                "statusCategory": {
                                    "key": "done",
                                    "name": "Done",
                                }
                            },
                            "assignee": {"displayName": "Alice"},
                        },
                    },
                    {
                        "id": "2",
                        "fields": {
                            "customfield_10016": 3,
                            "status": {
                                "statusCategory": {
                                    "key": "indeterminate",
                                    "name": "In Progress",
                                }
                            },
                            "assignee": {"displayName": "Bob"},
                        },
                    },
                ],
                "total": 2,
                "isLast": True,
            }
        return {}

    velocity_mixin.jira.get = MagicMock(side_effect=get_side_effect)

    result = velocity_mixin.get_sprint_velocity(board_id="42", sprint_id="101")

    assert result["committed_points"] == pytest.approx(8.0)
    assert result["completed_points"] == pytest.approx(5.0)
    assert result["completion_rate"] == pytest.approx(62.5)
    assert result["story_points_field"] == "customfield_10016"
    assert len(result["per_assignee"]) == 2


def test_get_sprint_velocity_requires_story_points_field(
    velocity_mixin: VelocityMixin,
) -> None:
    """Sprint velocity raises when board has no estimations field."""
    velocity_mixin.jira.get = MagicMock(return_value={})

    with pytest.raises(
        ValueError,
        match="Could not determine Story Points field from board configuration.",
    ):
        velocity_mixin.get_sprint_velocity(board_id="42", sprint_id="101")


def test_get_velocity_report_builds_trend(velocity_mixin: VelocityMixin) -> None:
    """Velocity report computes aggregate averages and trend."""
    velocity_mixin.get_all_sprints_from_board = MagicMock(
        return_value=[
            {"id": 1, "completeDate": "2026-01-10"},
            {"id": 2, "completeDate": "2026-01-24"},
            {"id": 3, "completeDate": "2026-02-07"},
        ]
    )
    velocity_mixin.get_sprint_velocity = MagicMock(
        side_effect=[
            {"sprint_id": "1", "completed_points": 10.0, "completion_rate": 70.0},
            {"sprint_id": "2", "completed_points": 12.0, "completion_rate": 80.0},
            {"sprint_id": "3", "completed_points": 15.0, "completion_rate": 90.0},
        ]
    )

    report = velocity_mixin.get_velocity_report(board_id="42", num_sprints=3)

    assert report["num_sprints_analyzed"] == 3
    assert report["average_completed_points"] == pytest.approx(12.33)
    assert report["average_completion_rate"] == pytest.approx(80.0)
    assert report["velocity_trend"] == "increasing"


def test_get_team_sprint_summary_aggregates_assignees(
    velocity_mixin: VelocityMixin,
) -> None:
    """Team summary aggregates assignee stats across sprints."""
    velocity_mixin.get_velocity_report = MagicMock(
        return_value={
            "num_sprints_analyzed": 2,
            "average_completed_points": 20.0,
            "average_completion_rate": 88.0,
            "velocity_trend": "stable",
            "sprints": [
                {
                    "per_assignee": [
                        {
                            "assignee": "Alice",
                            "issue_count": 2,
                            "committed_points": 8.0,
                            "completed_points": 6.0,
                        },
                        {
                            "assignee": "Bob",
                            "issue_count": 1,
                            "committed_points": 3.0,
                            "completed_points": 3.0,
                        },
                    ]
                },
                {
                    "per_assignee": [
                        {
                            "assignee": "Alice",
                            "issue_count": 1,
                            "committed_points": 5.0,
                            "completed_points": 5.0,
                        }
                    ]
                },
            ],
        }
    )

    summary = velocity_mixin.get_team_sprint_summary(board_id="42", num_sprints=2)

    assert summary["num_sprints"] == 2
    assert summary["velocity"]["trend"] == "stable"
    assert summary["per_assignee"][0]["assignee"] == "Alice"
    assert summary["per_assignee"][0]["completed_points"] == pytest.approx(11.0)
