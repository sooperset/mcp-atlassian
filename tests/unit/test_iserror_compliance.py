"""Regression tests for isError-compliance in mcp-atlassian.

5 `@jira_mcp.tool()` handlers caught exceptions and returned a JSON-encoded
`{"success": False, "error": ...}` string. FastMCP wraps the return value
as success content with `isError=false`, so MCP clients treat the failure
as data and the LLM often proceeds as if the call had succeeded.

The fix introduces `MCPAtlassianError` (base class for Atlassian-side
failures) and replaces each swallowed-error return with `raise
MCPAtlassianError(...) from e` so FastMCP sets `isError=true` on the wire
while preserving the formatted message in `content` for the LLM.

Reference: https://composio.dev/blog/mcp-security-vulnerabilities (Dayna
Blackwell MCP security audit, June 2026).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_atlassian.exceptions import MCPAtlassianError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "fetcher_method", "tool_kwargs"),
    [
        ("get_all_projects", "get_all_projects", {"include_archived": False}),
        ("get_issue_dates", "get_issue_dates", {"issue_key": "PROJ-1"}),
        ("get_issue_sla", "get_issue_sla", {"issue_key": "PROJ-1"}),
        (
            "get_issue_development_info",
            "get_issue_development_info",
            {"issue_key": "PROJ-1"},
        ),
        (
            "get_issues_development_info",
            "get_issues_development_info",
            {"issue_keys": "PROJ-1,PROJ-2"},
        ),
    ],
)
async def test_jira_handler_failure_raises_iserror(
    tool_name: str,
    fetcher_method: str,
    tool_kwargs: dict[str, object],
) -> None:
    """Each targeted Jira handler must surface failures as MCP errors."""
    from mcp_atlassian.servers import jira as jira_server

    fake_fetcher = MagicMock()
    original_error = RuntimeError("api down")
    getattr(fake_fetcher, fetcher_method).side_effect = original_error

    fake_ctx = MagicMock()

    with patch(
        "mcp_atlassian.servers.jira.get_jira_fetcher",
        new=AsyncMock(return_value=fake_fetcher),
    ):
        with pytest.raises(MCPAtlassianError) as exc_info:
            await getattr(jira_server, tool_name).fn(ctx=fake_ctx, **tool_kwargs)

    assert str(exc_info.value) == "api down"
    assert exc_info.value.__cause__ is original_error


def test_mcp_atlassian_error_is_subclass_of_exception() -> None:
    """Sanity: the new base class is a real Exception subclass so it
    can be raised from `except Exception` clauses and propagate cleanly."""
    assert issubclass(MCPAtlassianError, Exception)


def test_existing_authentication_error_still_subclass() -> None:
    """Backward compat: MCPAtlassianAuthenticationError must remain a
    subclass of the new base so `except MCPAtlassianError` catches it."""
    from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError

    assert issubclass(MCPAtlassianAuthenticationError, MCPAtlassianError)
