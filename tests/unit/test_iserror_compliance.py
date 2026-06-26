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

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_atlassian.exceptions import MCPAtlassianError
from mcp_atlassian.servers.jira import jira_mcp


@pytest.mark.asyncio
async def test_get_all_projects_failure_raises_iserror() -> None:
    """A failing get_all_projects call must surface as MCPAtlassianError
    → isError=true on the MCP wire, not as a JSON-encoded success content."""
    from mcp_atlassian.servers.jira import get_all_projects

    fake_fetcher = MagicMock()
    fake_fetcher.get_all_projects.side_effect = RuntimeError("api down")

    fake_ctx = MagicMock()
    fake_ctx.request_context.lifespan_context = {"jira": fake_fetcher}

    with patch(
        "mcp_atlassian.servers.jira.get_jira_fetcher", new=AsyncMock(return_value=fake_fetcher)
    ):
        with pytest.raises(MCPAtlassianError) as exc_info:
            await get_all_projects.fn(ctx=fake_ctx, include_archived=False)
        assert "api down" in str(exc_info.value) or "Network" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_issue_dates_failure_raises_iserror() -> None:
    """A failing get_issue_dates call must surface as MCPAtlassianError."""
    from mcp_atlassian.servers.jira import get_issue_dates

    fake_fetcher = MagicMock()
    fake_fetcher.get_issue_dates = MagicMock(side_effect=ValueError("missing key"))

    fake_ctx = MagicMock()
    fake_ctx.request_context.lifespan_context = {"jira": fake_fetcher}

    with patch(
        "mcp_atlassian.servers.jira.get_jira_fetcher", new=AsyncMock(return_value=fake_fetcher)
    ):
        with pytest.raises(MCPAtlassianError) as exc_info:
            await get_issue_dates.fn(
                ctx=fake_ctx,
                issue_key="PROJ-1",
            )
        assert "missing key" in str(exc_info.value)


def test_mcp_atlassian_error_is_subclass_of_exception() -> None:
    """Sanity: the new base class is a real Exception subclass so it
    can be raised from `except Exception` clauses and propagate cleanly."""
    assert issubclass(MCPAtlassianError, Exception)


def test_existing_authentication_error_still_subclass() -> None:
    """Backward compat: MCPAtlassianAuthenticationError must remain a
    subclass of the new base so `except MCPAtlassianError` catches it."""
    from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError

    assert issubclass(MCPAtlassianAuthenticationError, MCPAtlassianError)
