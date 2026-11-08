"""Tests for JIRA_PROJECTS_FILTER resolution in ScopeMixin and its callers."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from mcp_atlassian.exceptions import ScopeViolationError
from mcp_atlassian.jira import JiraConfig, JiraFetcher
from mcp_atlassian.utils.query_scope import UnsafeQueryError


def _fetcher(projects_filter: str | None = "ALLOWED, other") -> JiraFetcher:
    fetcher = JiraFetcher(
        config=JiraConfig(
            url="https://example.atlassian.net",
            auth_type="basic",
            username="u",
            api_token="t",
            projects_filter=projects_filter,
        )
    )
    fetcher.jira = MagicMock()
    return fetcher


def _issue(project: str, key: str | None = None) -> dict[str, Any]:
    return {"key": key or f"{project}-1", "fields": {"project": {"key": project}}}


def test_allowed_projects_parses_filter() -> None:
    assert _fetcher().allowed_projects() == frozenset({"ALLOWED", "OTHER"})
    assert _fetcher(None).allowed_projects() is None
    assert _fetcher(" , ").allowed_projects() is None


def test_no_filter_makes_no_api_calls() -> None:
    fetcher = _fetcher(None)
    fetcher.ensure_issue_allowed("ANY-1")
    fetcher.ensure_board_allowed("1")
    fetcher.ensure_project_allowed("ANY")
    assert fetcher.jira.method_calls == []


def test_issue_in_allowlist_passes() -> None:
    fetcher = _fetcher()
    fetcher.jira.issue.return_value = _issue("ALLOWED")
    fetcher.ensure_issue_allowed("ALLOWED-1")
    fetcher.jira.issue.assert_called_once_with("ALLOWED-1", fields="project")


def test_issue_moved_out_of_allowlist_is_denied() -> None:
    # Jira resolves the old key of a moved issue to its new project.
    fetcher = _fetcher()
    fetcher.jira.issue.return_value = _issue("SECRET", key="SECRET-9")
    with pytest.raises(ScopeViolationError, match="JIRA_PROJECTS_FILTER"):
        fetcher.ensure_issue_allowed("ALLOWED-1")


def test_numeric_issue_id_is_resolved() -> None:
    fetcher = _fetcher()
    fetcher.jira.issue.return_value = _issue("SECRET")
    with pytest.raises(ScopeViolationError):
        fetcher.ensure_issue_allowed("10001")


def test_issue_lookup_failure_denies() -> None:
    fetcher = _fetcher()
    fetcher.jira.issue.side_effect = RuntimeError("404")
    with pytest.raises(ScopeViolationError, match="could not be verified"):
        fetcher.ensure_issue_allowed("ALLOWED-404")


def test_issue_list_checks_every_entry() -> None:
    fetcher = _fetcher()
    fetcher.jira.issue.side_effect = [_issue("ALLOWED"), _issue("SECRET")]
    with pytest.raises(ScopeViolationError):
        fetcher.ensure_issues_allowed("ALLOWED-1, SECRET-1")


def test_project_key_is_case_insensitive() -> None:
    fetcher = _fetcher()
    fetcher.ensure_project_allowed("allowed")
    with pytest.raises(ScopeViolationError):
        fetcher.ensure_project_allowed("SECRET")


@pytest.mark.parametrize(
    ("method", "responses"),
    [
        (
            "ensure_board_allowed",
            {"rest/agile/1.0/board/5": {"location": {"projectKey": "SECRET"}}},
        ),
        (
            "ensure_sprint_allowed",
            {
                "rest/agile/1.0/sprint/5": {"originBoardId": 3},
                "rest/agile/1.0/board/3": {"location": {"projectKey": "SECRET"}},
            },
        ),
        (
            "ensure_version_allowed",
            {
                "rest/api/2/version/5": {"projectId": 10},
                "rest/api/2/project/10": {"key": "SECRET"},
            },
        ),
        (
            "ensure_service_desk_allowed",
            {"rest/servicedeskapi/servicedesk/5": {"projectKey": "SECRET"}},
        ),
        # A board that lives in a user's profile has no project: deny.
        ("ensure_board_allowed", {"rest/agile/1.0/board/5": {"location": {}}}),
    ],
)
def test_indirect_identifiers_resolve_to_their_project(
    method: str, responses: dict[str, Any]
) -> None:
    fetcher = _fetcher()
    fetcher.jira.get.side_effect = lambda path: responses[path]
    with pytest.raises(ScopeViolationError):
        getattr(fetcher, method)("5")


def test_issue_link_requires_both_ends_allowed() -> None:
    fetcher = _fetcher()
    fetcher.jira.get.return_value = {
        "inwardIssue": {"key": "ALLOWED-1"},
        "outwardIssue": {"key": "SECRET-1"},
    }
    fetcher.jira.issue.side_effect = [_issue("ALLOWED"), _issue("SECRET")]
    with pytest.raises(ScopeViolationError):
        fetcher.ensure_issue_link_allowed("5")


def test_identifier_is_path_encoded() -> None:
    fetcher = _fetcher()
    fetcher.jira.get.return_value = {"location": {"projectKey": "ALLOWED"}}
    fetcher.ensure_board_allowed("1/../../2")
    fetcher.jira.get.assert_called_once_with("rest/agile/1.0/board/1%2F..%2F..%2F2")


def test_search_rejects_unbalanced_jql_under_filter() -> None:
    fetcher = _fetcher("ALLOWED")
    payload = 'created >= "1970/01/01") OR (created >= "1970/01/01"'
    with pytest.raises(Exception, match="JQL query rejected"):
        fetcher.search_issues(payload)
    fetcher.jira.jql.assert_not_called()
    fetcher.jira.post.assert_not_called()


def test_board_issues_reject_unbalanced_jql_under_filter() -> None:
    fetcher = _fetcher("ALLOWED")
    with pytest.raises(Exception, match="JQL query rejected"):
        fetcher.get_board_issues("1", jql="x = 1) OR (project = SECRET")
    fetcher.jira.get_issues_for_board.assert_not_called()


def test_project_key_injection_in_project_issues_is_contained() -> None:
    # project_key is quoted into JQL; an injected value cannot leave the
    # allowlist wrapper even before the tool guard rejects it.
    fetcher = _fetcher("ALLOWED")
    with pytest.raises(UnsafeQueryError):
        fetcher._apply_projects_filter('project = "X") OR (created >= "2020-01-01"')


def test_agile_boards_outside_filter_are_hidden() -> None:
    fetcher = _fetcher("ALLOWED")
    fetcher.jira.get_all_agile_boards.return_value = {
        "values": [
            {"id": 1, "location": {"projectKey": "ALLOWED"}},
            {"id": 2, "location": {"projectKey": "SECRET"}},
            {"id": 3, "location": {}},
        ]
    }
    assert [b["id"] for b in fetcher.get_all_agile_boards()] == [1]


def test_additional_fields_cannot_replace_project() -> None:
    fetcher = _fetcher("ALLOWED")
    fetcher._generate_field_map = MagicMock(  # type: ignore[method-assign]
        return_value={"project": "project", "priority": "priority"}
    )
    fetcher.get_field_by_id = MagicMock(return_value=None)  # type: ignore[method-assign]
    fields: dict[str, Any] = {"project": {"key": "ALLOWED"}}
    fetcher._process_additional_fields(
        fields, {"project": {"key": "SECRET"}, "priority": {"name": "High"}}
    )
    assert fields["project"] == {"key": "ALLOWED"}
    assert "priority" in fields


# --- nested references in responses ------------------------------------------


def _raw_issue_with_references() -> dict[str, Any]:
    return {
        "id": "1",
        "key": "ALLOWED-1",
        "fields": {
            "summary": "s",
            "project": {"key": "ALLOWED"},
            "parent": {
                "key": "SECRET-7",
                "fields": {"summary": "secret parent", "project": {"key": "SECRET"}},
            },
            "subtasks": [
                {"key": "ALLOWED-2", "fields": {"summary": "ok"}},
                {"key": "SECRET-3", "fields": {"summary": "secret sub"}},
            ],
            "issuelinks": [
                {
                    "id": "10",
                    "type": {"name": "Blocks", "inward": "is blocked by"},
                    "inwardIssue": {
                        "key": "SECRET-4",
                        "fields": {"summary": "secret linked"},
                    },
                },
                {
                    "id": "11",
                    "type": {"name": "Relates", "outward": "relates to"},
                    "outwardIssue": {
                        "key": "OTHER-5",
                        "fields": {"summary": "allowed linked"},
                    },
                },
            ],
        },
    }


def test_get_issue_drops_references_outside_allowlist() -> None:
    fetcher = _fetcher()
    fetcher.jira.get_issue.return_value = _raw_issue_with_references()
    fetcher.jira.issue.return_value = _raw_issue_with_references()

    result = fetcher.get_issue("ALLOWED-1", fields="*all").to_simplified_dict()

    dumped = repr(result)
    assert "SECRET" not in dumped
    assert "secret" not in dumped
    assert "parent" not in result
    assert [s["key"] for s in result["subtasks"]] == ["ALLOWED-2"]
    assert [link["outward_issue"]["key"] for link in result["issuelinks"]] == [
        "OTHER-5"
    ]


def test_references_kept_without_allowlist() -> None:
    fetcher = _fetcher(None)
    fetcher.jira.get_issue.return_value = _raw_issue_with_references()
    fetcher.jira.issue.return_value = _raw_issue_with_references()

    result = fetcher.get_issue("ALLOWED-1", fields="*all").to_simplified_dict()

    assert result["parent"]["key"] == "SECRET-7"
    assert len(result["subtasks"]) == 2
    assert len(result["issuelinks"]) == 2


def test_search_results_drop_references_outside_allowlist() -> None:
    fetcher = _fetcher()
    fetcher.config.url = "https://example.atlassian.net"
    response = {"issues": [_raw_issue_with_references()], "total": 1}
    fetcher.jira.enhanced_jql_get_list_of_tickets.return_value = response["issues"]
    fetcher.jira.jql.return_value = response
    fetcher.jira.post.return_value = response
    fetcher.jira.get.return_value = response
    fetcher.jira.resource_url.return_value = "rest/api/3/search/jql"

    result = fetcher.search_issues("project = ALLOWED", fields="*all")

    dumped = repr([i.to_simplified_dict() for i in result.issues])
    assert result.issues
    assert "SECRET" not in dumped


def test_cross_project_dependencies_hide_disallowed_targets() -> None:
    fetcher = _fetcher()
    response = {"issues": [_raw_issue_with_references()], "total": 1}
    fetcher.jira.enhanced_jql_get_list_of_tickets.return_value = response["issues"]
    fetcher.jira.jql.return_value = response
    fetcher.jira.post.return_value = response
    fetcher.jira.get.return_value = response

    result = fetcher.get_cross_project_dependencies("ALLOWED")

    assert "SECRET" not in repr(result)
    assert "OTHER" in result["by_project"]


# --- boards without a location project -----------------------------------------

_USER_BOARD = {"rest/agile/1.0/board/5": {"location": {"type": "user"}}}


def _board_projects(keys: list[str], *, is_last: bool = True) -> dict[str, Any]:
    return {
        "rest/agile/1.0/board/5/project": {
            "isLast": is_last,
            "total": len(keys) + (0 if is_last else 1),
            "values": [{"key": k} for k in keys],
        }
    }


def test_board_without_location_project_allowed_when_all_projects_allowed() -> None:
    fetcher = _fetcher()
    responses = {**_USER_BOARD, **_board_projects(["ALLOWED", "other"])}
    fetcher.jira.get.side_effect = lambda path, **kw: responses[path]
    fetcher.ensure_board_allowed("5")


@pytest.mark.parametrize(
    "projects",
    [
        _board_projects(["ALLOWED", "SECRET"]),
        _board_projects([]),
        _board_projects(["ALLOWED"], is_last=False),
    ],
    ids=["one-project-outside", "no-projects", "incomplete-list"],
)
def test_board_without_location_project_denied_without_full_signal(
    projects: dict[str, Any],
) -> None:
    fetcher = _fetcher()
    responses = {**_USER_BOARD, **projects}
    fetcher.jira.get.side_effect = lambda path, **kw: responses[path]
    with pytest.raises(ScopeViolationError):
        fetcher.ensure_board_allowed("5")


def test_board_listing_keeps_unlocated_board_inside_filter() -> None:
    fetcher = _fetcher("ALLOWED")
    fetcher.jira.get_all_agile_boards.return_value = {
        "values": [
            {"id": 1, "location": {"projectKey": "ALLOWED"}},
            {"id": 5, "location": {"type": "user"}},
            {"id": 6, "location": {"type": "user"}},
        ]
    }
    responses = {
        **_board_projects(["ALLOWED"]),
        "rest/agile/1.0/board/6/project": {
            "isLast": True,
            "values": [{"key": "SECRET"}],
        },
    }
    fetcher.jira.get.side_effect = lambda path, **kw: responses[path]
    assert [b["id"] for b in fetcher.get_all_agile_boards()] == [1, 5]
