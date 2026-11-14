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


# --- epic and parent references (GHSA-qx5g-fhgg-wm59) --------------------------

_EPIC_FIELDS = {"epic_link": "customfield_10014", "epic_name": "customfield_10011"}


def _epic_fetcher(projects_filter: str | None = "ALLOWED") -> JiraFetcher:
    fetcher = _fetcher(projects_filter)
    fetcher.get_field_ids_to_epic = MagicMock(  # type: ignore[method-assign]
        return_value=dict(_EPIC_FIELDS)
    )
    fetcher._generate_field_map = MagicMock(  # type: ignore[method-assign]
        return_value={"summary": "summary", "epic link": "customfield_10014"}
    )
    fetcher.get_field_by_id = MagicMock(return_value=None)  # type: ignore[method-assign]
    fetcher.jira.issue.side_effect = lambda key, fields=None: _issue(
        key.rsplit("-", 1)[0], key=key
    )
    return fetcher


def _issue_linked_to_epic(epic_key: str) -> dict[str, Any]:
    return {
        "id": "1",
        "key": "ALLOWED-1",
        "fields": {
            "summary": "s",
            "project": {"key": "ALLOWED"},
            "issuetype": {"name": "Task"},
            "customfield_10014": epic_key,
        },
    }


def _epic(epic_key: str) -> dict[str, Any]:
    return {
        "id": "9",
        "key": epic_key,
        "fields": {
            "summary": "Hidden epic summary",
            "project": {"key": epic_key.rsplit("-", 1)[0]},
            "issuetype": {"name": "Epic"},
            "customfield_10011": "Hidden Epic Name",
        },
    }


def _serve(fetcher: JiraFetcher, epic_key: str) -> None:
    def get_issue(key: str, **_: Any) -> dict[str, Any]:
        return _issue_linked_to_epic(epic_key) if key == "ALLOWED-1" else _epic(key)

    fetcher.jira.get_issue.side_effect = get_issue


def test_get_issue_does_not_fetch_epic_outside_allowlist() -> None:
    fetcher = _epic_fetcher()
    _serve(fetcher, "SECRET-9")

    result = fetcher.get_issue("ALLOWED-1", fields="*all").to_simplified_dict()

    fetched = [c.args[0] for c in fetcher.jira.get_issue.call_args_list]
    assert fetched == ["ALLOWED-1"]
    dumped = repr(result)
    assert "SECRET" not in dumped
    assert "Hidden" not in dumped


def test_get_issue_keeps_epic_inside_allowlist() -> None:
    fetcher = _epic_fetcher("ALLOWED")
    _serve(fetcher, "ALLOWED-9")

    result = fetcher.get_issue("ALLOWED-1", fields="*all").to_simplified_dict()

    assert result["epic_key"] == "ALLOWED-9"
    assert result["epic_name"] == "Hidden Epic Name"


def test_get_issue_epic_untouched_without_allowlist() -> None:
    fetcher = _epic_fetcher(None)
    _serve(fetcher, "SECRET-9")

    result = fetcher.get_issue("ALLOWED-1", fields="*all").to_simplified_dict()

    assert result["epic_key"] == "SECRET-9"
    assert result["epic_name"] == "Hidden Epic Name"


@pytest.mark.parametrize("with_names", [True, False])
def test_restrict_references_clears_epic_name_and_epic_fields(
    with_names: bool,
) -> None:
    from mcp_atlassian.models.jira import JiraIssue

    data = _issue_linked_to_epic("SECRET-9")
    data["fields"]["customfield_10011"] = "Hidden Epic Name"
    if with_names:
        data["names"] = {
            "customfield_10014": "Epic Link",
            "customfield_10011": "Epic Name",
        }

    issue = JiraIssue.from_api_response(
        data, requested_fields="*all", allowed_projects=frozenset({"ALLOWED"})
    )

    assert issue.epic_key is None
    assert issue.epic_name is None
    dumped = repr(issue.to_simplified_dict())
    assert "SECRET" not in dumped
    assert "Hidden" not in dumped


def test_restrict_references_keeps_own_epic_name() -> None:
    from mcp_atlassian.models.jira import JiraIssue

    data = _epic("ALLOWED-9")
    data["names"] = {"customfield_10011": "Epic Name"}

    issue = JiraIssue.from_api_response(
        data, requested_fields="*all", allowed_projects=frozenset({"ALLOWED"})
    )

    assert issue.epic_name == "Hidden Epic Name"


def _created(fetcher: JiraFetcher) -> None:
    fetcher.jira.create_issue.return_value = {"key": "ALLOWED-2"}
    fetcher.jira.create_issues.return_value = {"issues": [{"key": "ALLOWED-2"}]}
    fetcher.jira.get_issue.return_value = _issue("ALLOWED", key="ALLOWED-2")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"parent": "SECRET-1"},
        {"parent": {"key": "SECRET-1"}},
        {"epicKey": "SECRET-1"},
        {"customfield_10014": "SECRET-1"},
        {"Epic Link": "SECRET-1"},
    ],
)
def test_create_issue_refuses_parent_or_epic_outside_allowlist(
    kwargs: dict[str, Any],
) -> None:
    fetcher = _epic_fetcher()
    _created(fetcher)

    with pytest.raises(ScopeViolationError, match="JIRA_PROJECTS_FILTER"):
        fetcher.create_issue("ALLOWED", "s", "Task", **kwargs)

    fetcher.jira.create_issue.assert_not_called()


def test_create_subtask_refuses_parent_outside_allowlist() -> None:
    fetcher = _epic_fetcher()
    _created(fetcher)
    fetcher._find_subtask_issue_type_id = MagicMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(ScopeViolationError):
        fetcher.create_issue("ALLOWED", "s", "Subtask", parent="SECRET-1")

    fetcher.jira.create_issue.assert_not_called()


def test_create_issue_accepts_parent_inside_allowlist() -> None:
    fetcher = _epic_fetcher()
    _created(fetcher)

    fetcher.create_issue("ALLOWED", "s", "Task", parent="ALLOWED-1")

    sent = fetcher.jira.create_issue.call_args.kwargs["fields"]
    assert sent["parent"] == {"key": "ALLOWED-1"}


def test_batch_create_refuses_epic_link_outside_allowlist() -> None:
    fetcher = _epic_fetcher()
    _created(fetcher)

    with pytest.raises(ScopeViolationError):
        fetcher.batch_create_issues(
            [
                {
                    "project_key": "ALLOWED",
                    "summary": "s",
                    "issue_type": "Task",
                    "customfield_10014": "SECRET-1",
                }
            ]
        )

    fetcher.jira.create_issues.assert_not_called()


@pytest.mark.parametrize(
    ("fields", "kwargs"),
    [
        (None, {"parent": "SECRET-1"}),
        ({"parent": {"key": "SECRET-1"}}, {}),
        (None, {"epic_link": "SECRET-1"}),
        ({"customfield_10014": "SECRET-1"}, {}),
        (None, {"parent": "SECRET-1", "status": "Done"}),
    ],
)
def test_update_issue_refuses_parent_or_epic_outside_allowlist(
    fields: dict[str, Any] | None, kwargs: dict[str, Any]
) -> None:
    fetcher = _epic_fetcher()
    fetcher.jira.get_issue.return_value = _issue("ALLOWED")

    with pytest.raises(ScopeViolationError, match="JIRA_PROJECTS_FILTER"):
        fetcher.update_issue("ALLOWED-1", fields=fields, **kwargs)

    fetcher.jira.update_issue.assert_not_called()
    fetcher.jira.put.assert_not_called()


def test_update_issue_allows_clearing_parent() -> None:
    fetcher = _epic_fetcher()
    fetcher.config.url = "https://example.atlassian.net"
    fetcher.jira.get_issue.return_value = _issue("ALLOWED")

    fetcher.update_issue("ALLOWED-1", parent=None)

    sent = fetcher.jira.update_issue.call_args.kwargs["update"]["fields"]
    assert sent["parent"] is None


@pytest.mark.parametrize(
    ("fields", "update_data"),
    [
        ({"parent": {"key": "SECRET-1"}}, None),
        ({"customfield_10014": "SECRET-1"}, None),
        (None, {"parent": [{"set": {"key": "SECRET-1"}}]}),
        (None, {"customfield_10014": [{"set": "SECRET-1"}]}),
        (
            None,
            {
                "issuelinks": [
                    {
                        "add": {
                            "type": {"name": "Blocks"},
                            "outwardIssue": {"key": "SECRET-1"},
                        }
                    }
                ]
            },
        ),
    ],
)
def test_transition_refuses_references_outside_allowlist(
    fields: dict[str, Any] | None, update_data: dict[str, Any] | None
) -> None:
    fetcher = _epic_fetcher()
    fetcher.get_transitions_models = MagicMock(return_value=[])  # type: ignore[method-assign]

    with pytest.raises(ScopeViolationError):
        fetcher.transition_issue(
            "ALLOWED-1", "31", fields=fields, update_data=update_data
        )

    fetcher.jira.set_issue_status.assert_not_called()
    fetcher.jira.post.assert_not_called()
