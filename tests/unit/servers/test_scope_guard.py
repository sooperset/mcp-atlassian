"""The project/space allowlist guards every Jira and Confluence tool.

These tests enumerate the registered tools instead of listing them by hand, so
a new tool (or a new argument on an existing tool) fails here until its
arguments are classified in ``mcp_atlassian.servers.scope_guard``.
"""

from __future__ import annotations

import inspect
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client
from fastmcp.client import FastMCPTransport
from fastmcp.exceptions import ToolError

from mcp_atlassian.confluence import ConfluenceConfig, ConfluenceFetcher
from mcp_atlassian.exceptions import ScopeViolationError
from mcp_atlassian.jira import JiraConfig, JiraFetcher
from mcp_atlassian.servers.confluence import confluence_mcp
from mcp_atlassian.servers.context import MainAppContext
from mcp_atlassian.servers.jira import jira_mcp
from mcp_atlassian.servers.scope_guard import (
    CONFLUENCE_SCOPE_POLICY,
    JIRA_SCOPE_POLICY,
    ScopePolicy,
    ToolScopeGuard,
)

# Tools that take no project/space identifier. Search tools are bounded by the
# allowlist inside the JQL/CQL; project listings filter their results; the
# rest return instance-wide metadata.
JIRA_TOOLS_WITHOUT_SCOPED_ARGS = {
    "get_user_profile",
    "search",
    "search_fields",
    "get_link_types",
    "get_all_projects",
    "search_projects",
}
CONFLUENCE_TOOLS_WITHOUT_SCOPED_ARGS = {"search", "search_user"}

SERVERS = [
    pytest.param(jira_mcp, JIRA_SCOPE_POLICY, id="jira"),
    pytest.param(confluence_mcp, CONFLUENCE_SCOPE_POLICY, id="confluence"),
]


def _run(coro: Any) -> Any:
    import anyio

    async def runner() -> Any:
        return await coro

    return anyio.run(runner)


def _tools(server: Any) -> list[Any]:
    return list(_run(server.list_tools()))


def _params(tool: Any) -> list[str]:
    return list(inspect.signature(tool.fn).parameters)


@pytest.mark.parametrize(("server", "policy"), SERVERS)
def test_every_tool_argument_is_classified(server: Any, policy: ScopePolicy) -> None:
    unclassified = {
        tool.name: [p for p in _params(tool) if policy.classify(p) is None]
        for tool in _tools(server)
    }
    assert {k: v for k, v in unclassified.items() if v} == {}


@pytest.mark.parametrize(
    ("server", "policy", "expected"),
    [
        pytest.param(
            jira_mcp, JIRA_SCOPE_POLICY, JIRA_TOOLS_WITHOUT_SCOPED_ARGS, id="jira"
        ),
        pytest.param(
            confluence_mcp,
            CONFLUENCE_SCOPE_POLICY,
            CONFLUENCE_TOOLS_WITHOUT_SCOPED_ARGS,
            id="confluence",
        ),
    ],
)
def test_tools_without_scoped_arguments_are_pinned(
    server: Any, policy: ScopePolicy, expected: set[str]
) -> None:
    without = {
        tool.name
        for tool in _tools(server)
        if not any(p in policy.checks for p in _params(tool))
    }
    assert without == expected


@pytest.mark.parametrize(
    ("policy", "fetcher_cls"),
    [(JIRA_SCOPE_POLICY, JiraFetcher), (CONFLUENCE_SCOPE_POLICY, ConfluenceFetcher)],
)
def test_scope_checks_name_real_fetcher_methods(
    policy: ScopePolicy, fetcher_cls: type
) -> None:
    for name, check in policy.checks.items():
        method = getattr(check, "__name__", "")
        if method.startswith("ensure_"):
            assert callable(getattr(fetcher_cls, method, None)), (name, method)


# --- every scoped tool rejects an out-of-allowlist target -------------------

FORBIDDEN = "SECRET"


def _jira_fetcher() -> JiraFetcher:
    fetcher = JiraFetcher(
        config=JiraConfig(
            url="https://example.atlassian.net",
            auth_type="basic",
            username="u",
            api_token="t",
            projects_filter="ALLOWED",
        )
    )
    backend = MagicMock()
    backend.issue.return_value = {
        "key": f"{FORBIDDEN}-1",
        "fields": {"project": {"key": FORBIDDEN}},
    }

    def get(path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if path.startswith("rest/agile/1.0/board/"):
            return {"location": {"projectKey": FORBIDDEN}}
        if path.startswith("rest/agile/1.0/sprint/"):
            return {"originBoardId": 7}
        if path.startswith("rest/api/2/version/"):
            return {"projectId": "10"}
        if path.startswith("rest/api/2/project/"):
            return {"key": FORBIDDEN}
        if path.startswith("rest/api/2/issueLink/"):
            return {
                "inwardIssue": {"key": f"{FORBIDDEN}-1"},
                "outwardIssue": {"key": f"{FORBIDDEN}-2"},
            }
        if path.startswith("rest/servicedeskapi/servicedesk/"):
            return {"projectKey": FORBIDDEN}
        raise AssertionError(f"unexpected Jira GET {path}")

    backend.get.side_effect = get
    fetcher.jira = backend
    return fetcher


def _confluence_fetcher() -> ConfluenceFetcher:
    fetcher = ConfluenceFetcher(
        config=ConfluenceConfig(
            url="https://example.atlassian.net/wiki",
            auth_type="basic",
            username="u",
            api_token="t",
            spaces_filter="ALLOWED",
        )
    )
    backend = MagicMock()
    backend.url = "https://example.atlassian.net/wiki"

    def session_get(url: str, *args: Any, **kwargs: Any) -> Any:
        if "/api/v2/spaces/" in url:
            payload: dict[str, Any] = {"key": FORBIDDEN}
        else:
            payload = {"space": {"key": FORBIDDEN}}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    backend._session.get.side_effect = session_get
    fetcher.confluence = backend
    return fetcher


_JIRA_VALUES: dict[str, Any] = {
    "issue_key": f"{FORBIDDEN}-1",
    "inward_issue_key": f"{FORBIDDEN}-1",
    "outward_issue_key": f"{FORBIDDEN}-2",
    "epic_key": f"{FORBIDDEN}-3",
    "issue_keys": f"{FORBIDDEN}-1",
    "issue_ids_or_keys": f"{FORBIDDEN}-1",
    "project_key": FORBIDDEN,
    "target_project_key": FORBIDDEN,
    "board_id": "7",
    "sprint_id": "8",
    "version_id": "9",
    "link_id": "10",
    "service_desk_id": "11",
    "issues": json.dumps(
        [{"project_key": FORBIDDEN, "summary": "s", "issue_type": "Task"}]
    ),
}
_CONFLUENCE_VALUES: dict[str, Any] = {
    "page_id": "123",
    "parent_id": "124",
    "target_parent_id": "125",
    "source_page_id": "126",
    "destination_parent_id": "127",
    "content_id": "128",
    "comment_id": "129",
    "attachment_id": "att130",
    "space_key": FORBIDDEN,
    "target_space_key": FORBIDDEN,
    "destination_space_key": FORBIDDEN,
    "space_id": "131",
    "template_id": "132",
}


def _schema_type(schema: dict[str, Any]) -> str | None:
    if "type" in schema:
        return schema["type"]
    for option in schema.get("anyOf", []):
        if option.get("type") != "null":
            return option.get("type")
    return None


def _dummy(schema: dict[str, Any]) -> Any:
    return {
        "string": "x",
        "integer": 1,
        "number": 1,
        "boolean": False,
        "array": [],
        "object": {},
    }.get(_schema_type(schema) or "string", "x")


def _arguments(tool: Any, values: dict[str, Any]) -> dict[str, Any]:
    props = tool.parameters.get("properties", {})
    required = set(tool.parameters.get("required", []))
    args: dict[str, Any] = {}
    for name, schema in props.items():
        if name in values:
            value = values[name]
            if _schema_type(schema) == "array" and isinstance(value, str):
                value = [value]
            elif _schema_type(schema) == "integer":
                value = int(value) if str(value).isdigit() else 1
            args[name] = value
        elif name in required:
            args[name] = _dummy(schema)
    return args


def _scoped_tool_ids(server: Any, policy: ScopePolicy) -> list[str]:
    return [
        tool.name
        for tool in _tools(server)
        if any(p in policy.checks for p in _params(tool))
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("tool_name", _scoped_tool_ids(jira_mcp, JIRA_SCOPE_POLICY))
async def test_every_jira_tool_rejects_forbidden_project(tool_name: str) -> None:
    fetcher = _jira_fetcher()
    tool = await jira_mcp.get_tool(tool_name)
    with patch(
        "mcp_atlassian.servers.jira.get_jira_fetcher",
        AsyncMock(return_value=fetcher),
    ):
        async with Client(transport=FastMCPTransport(jira_mcp)) as client:
            with pytest.raises(ToolError, match="outside the configured"):
                await client.call_tool(tool_name, _arguments(tool, _JIRA_VALUES))
    # Only scope lookups reached the backend: the tool body never ran.
    called = {call[0] for call in fetcher.jira.method_calls}
    assert called <= {"issue", "get"}, called


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool_name", _scoped_tool_ids(confluence_mcp, CONFLUENCE_SCOPE_POLICY)
)
async def test_every_confluence_tool_rejects_forbidden_space(tool_name: str) -> None:
    fetcher = _confluence_fetcher()
    tool = await confluence_mcp.get_tool(tool_name)
    with patch(
        "mcp_atlassian.servers.confluence.get_confluence_fetcher",
        AsyncMock(return_value=fetcher),
    ):
        async with Client(transport=FastMCPTransport(confluence_mcp)) as client:
            with pytest.raises(ToolError, match="outside the configured"):
                await client.call_tool(tool_name, _arguments(tool, _CONFLUENCE_VALUES))
    called = {call[0] for call in fetcher.confluence.method_calls}
    assert called <= {"_session.get"}, called


# --- guard behaviour ----------------------------------------------------------


def _ctx(app: MainAppContext | None) -> Any:
    lifespan = {"app_lifespan_context": app} if app is not None else {}
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=lifespan))


@pytest.mark.anyio
async def test_guard_skips_fetcher_when_no_filter_configured() -> None:
    getter = AsyncMock()
    guard = ToolScopeGuard(JIRA_SCOPE_POLICY, getter)
    app = MainAppContext(
        full_jira_config=JiraConfig(
            url="https://example.atlassian.net",
            auth_type="basic",
            username="u",
            api_token="t",
        )
    )
    await guard("get_issue", {"ctx": _ctx(app), "issue_key": "ANY-1"})
    getter.assert_not_awaited()


@pytest.mark.anyio
async def test_guard_allows_in_allowlist_target() -> None:
    fetcher = _jira_fetcher()
    fetcher.jira.issue.return_value = {
        "key": "ALLOWED-1",
        "fields": {"project": {"key": "ALLOWED"}},
    }
    guard = ToolScopeGuard(JIRA_SCOPE_POLICY, AsyncMock(return_value=fetcher))
    await guard("get_issue", {"ctx": _ctx(None), "issue_key": "ALLOWED-1"})


@pytest.mark.anyio
async def test_guard_refuses_unclassified_argument_under_filter() -> None:
    guard = ToolScopeGuard(JIRA_SCOPE_POLICY, AsyncMock(return_value=_jira_fetcher()))
    with pytest.raises(ScopeViolationError, match="cannot be used"):
        await guard("new_tool", {"ctx": _ctx(None), "mystery_id": "1"})


@pytest.mark.anyio
async def test_guard_ignores_empty_optional_targets() -> None:
    fetcher = _jira_fetcher()
    guard = ToolScopeGuard(JIRA_SCOPE_POLICY, AsyncMock(return_value=fetcher))
    await guard(
        "get_agile_boards",
        {"ctx": _ctx(None), "project_key": None, "board_name": "b"},
    )
    assert fetcher.jira.method_calls == []


@pytest.mark.anyio
async def test_guard_refuses_fetcher_without_operator_filter() -> None:
    """A per-request fetcher whose config lost the operator filter is refused."""
    fetcher = _jira_fetcher()
    fetcher.config.projects_filter = None
    guard = ToolScopeGuard(JIRA_SCOPE_POLICY, AsyncMock(return_value=fetcher))
    app = MainAppContext(
        full_jira_config=JiraConfig(
            url="https://example.atlassian.net",
            auth_type="basic",
            username="u",
            api_token="t",
            projects_filter="ALLOWED",
        )
    )
    with pytest.raises(ScopeViolationError):
        await guard("get_issue", {"ctx": _ctx(app), "issue_key": f"{FORBIDDEN}-1"})


@pytest.mark.anyio
async def test_guard_reads_operator_filter_from_env_without_lifespan_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Header-only deployments have no lifespan config; the env var still binds."""
    monkeypatch.setenv("JIRA_PROJECTS_FILTER", "ALLOWED")
    fetcher = _jira_fetcher()
    fetcher.config.projects_filter = None
    guard = ToolScopeGuard(JIRA_SCOPE_POLICY, AsyncMock(return_value=fetcher))
    with pytest.raises(ScopeViolationError):
        await guard("get_issue", {"ctx": _ctx(None), "issue_key": f"{FORBIDDEN}-1"})


@pytest.mark.anyio
async def test_guard_refuses_fetcher_with_different_filter() -> None:
    fetcher = _jira_fetcher()
    fetcher.config.projects_filter = f"ALLOWED,{FORBIDDEN}"
    guard = ToolScopeGuard(JIRA_SCOPE_POLICY, AsyncMock(return_value=fetcher))
    app = MainAppContext(
        full_jira_config=JiraConfig(
            url="https://example.atlassian.net",
            auth_type="basic",
            username="u",
            api_token="t",
            projects_filter="ALLOWED",
        )
    )
    with pytest.raises(ScopeViolationError):
        await guard("get_issue", {"ctx": _ctx(app), "issue_key": f"{FORBIDDEN}-1"})
