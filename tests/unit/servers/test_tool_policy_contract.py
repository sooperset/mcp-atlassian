"""Public MCP client contracts for server-side tool policy."""

import importlib
from pathlib import Path

import pytest
from fastmcp import Client


@pytest.mark.anyio
@pytest.mark.security_regression
async def test_read_only_hidden_tool_cannot_be_called(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A write tool hidden from discovery must also be unknown at dispatch."""
    monkeypatch.setenv("READ_ONLY_MODE", "true")
    monkeypatch.setenv("JIRA_URL", "https://jira.example.test")
    monkeypatch.setenv("JIRA_PERSONAL_TOKEN", "policy-contract-placeholder")
    monkeypatch.setenv("ATLASSIAN_OAUTH_PROXY_ENABLE", "false")
    monkeypatch.setenv("TOOLSETS", "all")
    monkeypatch.setenv("FASTMCP_HOME", str(tmp_path / "fastmcp-home"))

    main_module = importlib.import_module("mcp_atlassian.servers.main")

    async with Client(main_module.main_mcp) as client:
        hidden_call = await client.call_tool_mcp("jira_create_issue", {})
        tools = await client.list_tools()

    hidden_error = " ".join(
        getattr(content, "text", "") for content in hidden_call.content
    )
    is_error = getattr(hidden_call, "is_error", None)
    if is_error is None:
        is_error = hidden_call.isError

    assert is_error
    assert "Unknown tool" in hidden_error
    assert "jira_create_issue" not in {tool.name for tool in tools}
