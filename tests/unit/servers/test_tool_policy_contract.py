"""Public MCP client contracts for server-side tool policy."""

import importlib
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client

_VALID_WRITE_ARGUMENTS = {
    "project_key": "TEST",
    "summary": "Policy contract must not create this issue",
    "issue_type": "Task",
}
_POLICY_CASES = [
    pytest.param(
        {
            "READ_ONLY_MODE": "true",
            "ENABLED_TOOLS": None,
            "TOOLSETS": "all",
        },
        id="read-only",
    ),
    pytest.param(
        {
            "READ_ONLY_MODE": "false",
            "ENABLED_TOOLS": "jira_get_issue",
            "TOOLSETS": "all",
        },
        id="enabled-tools",
    ),
    pytest.param(
        {
            "READ_ONLY_MODE": "false",
            "ENABLED_TOOLS": None,
            "TOOLSETS": "jira_comments",
        },
        id="toolsets",
    ),
]


def _is_error(result: Any) -> bool:
    """Read the tool-result error flag across MCP SDK v1/v2 field names."""
    value = getattr(result, "is_error", None)
    if value is None:
        value = result.isError
    return bool(value)


def _error_text(result: Any) -> str:
    """Return text content from a public MCP tool result."""
    return " ".join(getattr(content, "text", "") for content in result.content)


def _configure_jira(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    policy_env: dict[str, str | None],
) -> None:
    """Configure a hermetic Jira server lifespan for a policy test."""
    monkeypatch.setenv("JIRA_URL", "https://jira.example.test")
    monkeypatch.setenv("JIRA_PERSONAL_TOKEN", "policy-contract-placeholder")
    monkeypatch.setenv("ATLASSIAN_OAUTH_PROXY_ENABLE", "false")
    monkeypatch.setenv("FASTMCP_HOME", str(tmp_path / "fastmcp-home"))
    for name, value in policy_env.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


@pytest.mark.parametrize("policy_env", _POLICY_CASES)
@pytest.mark.anyio
@pytest.mark.security_regression
async def test_hidden_tool_is_absent_from_public_listing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    policy_env: dict[str, str | None],
) -> None:
    """Policy-hidden tools remain undiscoverable (GHSA-3r68, issue #1541)."""
    _configure_jira(monkeypatch, tmp_path, policy_env)
    main_module = importlib.import_module("mcp_atlassian.servers.main")

    async with Client(main_module.main_mcp) as client:
        tools = await client.list_tools()

    visible_tools = {tool.name for tool in tools}
    assert "jira_create_issue" not in visible_tools, (
        "tool visibility policy exposed jira_create_issue"
    )


@pytest.mark.parametrize("policy_env", _POLICY_CASES)
@pytest.mark.anyio
@pytest.mark.security_regression
async def test_hidden_tool_cannot_be_called_through_public_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    policy_env: dict[str, str | None],
) -> None:
    """Hidden tools remain unknown and unexecuted (GHSA-3r68, issue #1541)."""
    _configure_jira(monkeypatch, tmp_path, policy_env)

    main_module = importlib.import_module("mcp_atlassian.servers.main")

    with patch(
        "mcp_atlassian.servers.jira.get_jira_fetcher",
        new_callable=AsyncMock,
        side_effect=AssertionError("hidden write reached the Jira fetcher"),
    ) as get_jira_fetcher:
        async with Client(main_module.main_mcp) as client:
            hidden_call = await client.call_tool_mcp(
                "jira_create_issue", _VALID_WRITE_ARGUMENTS
            )
            unknown_call = await client.call_tool_mcp("jira_no_such_tool", {})

    get_jira_fetcher.assert_not_awaited()
    hidden_error = _error_text(hidden_call)
    unknown_error = _error_text(unknown_call)

    assert _is_error(hidden_call)
    assert _is_error(unknown_call)
    assert "Unknown tool" in hidden_error
    assert "Unknown tool" in unknown_error
    assert hidden_error.replace("jira_create_issue", "<tool>") == (
        unknown_error.replace("jira_no_such_tool", "<tool>")
    )


@pytest.mark.anyio
async def test_enabled_read_tool_uses_public_call_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An allowed read reaches its executor, guarding the FastMCP call ABI."""
    _configure_jira(
        monkeypatch,
        tmp_path,
        {
            "READ_ONLY_MODE": "true",
            "ENABLED_TOOLS": "jira_get_issue",
            "TOOLSETS": "jira_issues",
        },
    )
    main_module = importlib.import_module("mcp_atlassian.servers.main")
    issue = MagicMock()
    issue.to_simplified_dict.return_value = {
        "id": "10001",
        "key": "TEST-1",
        "summary": "Policy contract fixture",
    }
    jira_fetcher = MagicMock()
    jira_fetcher.get_issue.return_value = issue

    with patch(
        "mcp_atlassian.servers.jira.get_jira_fetcher",
        new_callable=AsyncMock,
        return_value=jira_fetcher,
    ) as get_jira_fetcher:
        async with Client(main_module.main_mcp) as client:
            tools = await client.list_tools()
            allowed_call = await client.call_tool_mcp(
                "jira_get_issue", {"issue_key": "TEST-1"}
            )

    assert "jira_get_issue" in {tool.name for tool in tools}
    assert not _is_error(allowed_call)
    get_jira_fetcher.assert_awaited_once()
    jira_fetcher.get_issue.assert_called_once()
