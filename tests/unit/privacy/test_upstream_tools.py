"""Full-stack tests against the **real upstream tool functions**.

Earlier integration tests use synthetic tools that emit hand-built JSON
shapes. This file goes a step further: it imports the actual upstream
``jira_mcp`` and ``confluence_mcp`` FastMCP instances (with every
``@jira_mcp.tool`` / ``@confluence_mcp.tool`` decorator already
registered), mocks only the ``JiraFetcher`` / ``ConfluenceFetcher``
return value, and exercises the privacy filter through the same code
path a live request takes:

    raw API response (from upstream test fixtures)
        ↓  JiraIssue.from_api_response(...)        ← real upstream code
    Pydantic model
        ↓  fetcher.get_issue() returns the model   ← mocked
    upstream @tool function
        ↓  issue.to_simplified_dict() + json.dumps ← real upstream code
    FastMCP transport + middleware chain
        ↓  PrivacyFilterMiddleware                 ← code under test
    filtered TextContent reaches the LLM

Only the network layer is replaced; everything from
``from_api_response`` through ``to_simplified_dict`` to the FastMCP
client is the real upstream pipeline. If upstream changes the
simplified-dict shape, these tests fail and surface the exact path the
filter expected.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.models.confluence.page import ConfluencePage
from mcp_atlassian.models.confluence.search import ConfluenceSearchResult
from mcp_atlassian.models.jira.issue import JiraIssue
from mcp_atlassian.models.jira.search import JiraSearchResult
from mcp_atlassian.privacy import PrivacyConfig, install_privacy_filter
from mcp_atlassian.servers import confluence as confluence_server_module
from mcp_atlassian.servers import jira as jira_server_module
from mcp_atlassian.servers.confluence import confluence_mcp
from mcp_atlassian.servers.jira import jira_mcp
from tests.fixtures.confluence_mocks import (  # type: ignore[import-not-found]
    MOCK_CQL_SEARCH_RESPONSE,
    MOCK_PAGE_RESPONSE,
)
from tests.fixtures.jira_mocks import (  # type: ignore[import-not-found]
    MOCK_JIRA_ISSUE_RESPONSE,
    MOCK_JIRA_JQL_RESPONSE,
)


def _build_parent_server(
    config: PrivacyConfig,
) -> FastMCP[Any]:
    """Mount upstream sub-servers on a parent and install the privacy filter."""
    parent: FastMCP[Any] = FastMCP(name="upstream-tools-test")
    parent.mount(jira_mcp, "jira")
    parent.mount(confluence_mcp, "confluence")
    install_privacy_filter(server=parent, config=config)
    return parent


def _patch_jira_fetcher(monkeypatch: pytest.MonkeyPatch, fetcher: Any) -> None:
    """Force every upstream Jira tool to receive ``fetcher`` from
    ``get_jira_fetcher``."""
    monkeypatch.setattr(
        jira_server_module,
        "get_jira_fetcher",
        AsyncMock(return_value=fetcher),
    )


def _patch_confluence_fetcher(monkeypatch: pytest.MonkeyPatch, fetcher: Any) -> None:
    monkeypatch.setattr(
        confluence_server_module,
        "get_confluence_fetcher",
        AsyncMock(return_value=fetcher),
    )


async def _call_text(server: FastMCP[Any], tool: str, args: dict[str, Any]) -> str:
    async with Client(server) as client:
        result = await client.call_tool(name=tool, arguments=args)
    text = result.content[0].text  # type: ignore[union-attr]
    assert isinstance(text, str)
    return text


# ---------------------------------------------------------------------------
# Jira: real `jira_get_issue` flow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_jira_get_issue_redacts_email_in_simplified_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The actual upstream ``get_issue`` tool serializes via
    ``JiraIssue.to_simplified_dict`` → JSON. Verify our filter intercepts
    that exact path and redacts the email at ``assignee.email``."""
    real_issue = JiraIssue.from_api_response(data=MOCK_JIRA_ISSUE_RESPONSE)
    fetcher = MagicMock(spec=JiraFetcher)
    fetcher.get_issue.return_value = real_issue
    _patch_jira_fetcher(monkeypatch=monkeypatch, fetcher=fetcher)

    server = _build_parent_server(
        config=PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            mask_token="[X]",
        )
    )

    text = await _call_text(
        server=server, tool="jira_get_issue", args={"issue_key": "TEST-1"}
    )
    out = json.loads(text)
    # Sanity: assignee.email exists in the simplified dict (mock has it).
    assert "assignee" in out
    # Filter must have replaced the email.
    assert out["assignee"]["email"] != "test@example.com"
    assert "[X]" in json.dumps(out)
    assert "@example.com" not in json.dumps(out)
    fetcher.get_issue.assert_called_once()


@pytest.mark.asyncio
async def test_real_jira_get_issue_drop_field_simplified_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Field rules target the *simplified-dict* path (snake_case, no
    ``fields.`` prefix). Verify ``assignee.email`` rule actually drops on
    the real upstream output."""
    real_issue = JiraIssue.from_api_response(data=MOCK_JIRA_ISSUE_RESPONSE)
    fetcher = MagicMock(spec=JiraFetcher)
    fetcher.get_issue.return_value = real_issue
    _patch_jira_fetcher(monkeypatch=monkeypatch, fetcher=fetcher)

    server = _build_parent_server(
        config=PrivacyConfig(
            enabled=True,
            drop_fields={"jira_issue": ["assignee.email"]},
        )
    )

    text = await _call_text(
        server=server, tool="jira_get_issue", args={"issue_key": "TEST-1"}
    )
    out = json.loads(text)
    assert "assignee" in out
    assert "email" not in out["assignee"], (
        f"assignee.email should be dropped; got: {out['assignee']!r}"
    )
    # Adjacent fields preserved (display_name, name, avatar_url).
    assert "display_name" in out["assignee"]


@pytest.mark.asyncio
async def test_real_jira_get_issue_top_level_drop_when_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single-issue tool returning a denied resource should be wiped to
    ``{}`` by the resource filter. Uses the real simplified-dict shape."""
    # Synthesize an API response whose simplified dict carries a
    # confidential label.
    hostile_response: dict[str, Any] = json.loads(json.dumps(MOCK_JIRA_ISSUE_RESPONSE))
    hostile_response["fields"]["labels"] = ["confidential"]
    real_issue = JiraIssue.from_api_response(data=hostile_response)
    fetcher = MagicMock(spec=JiraFetcher)
    fetcher.get_issue.return_value = real_issue
    _patch_jira_fetcher(monkeypatch=monkeypatch, fetcher=fetcher)

    server = _build_parent_server(
        config=PrivacyConfig(enabled=True, deny_labels=["confidential"])
    )

    text = await _call_text(
        server=server, tool="jira_get_issue", args={"issue_key": "TEST-1"}
    )
    out = json.loads(text)
    assert out == {}, f"top-level denied issue should become empty dict, got {out!r}"


# ---------------------------------------------------------------------------
# Jira: real `jira_search` flow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_jira_search_drops_denied_items_in_real_simplified_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``jira_search`` returns ``JiraSearchResult.to_simplified_dict()`` —
    a wrapper with ``issues`` list. Verify list-item filtering works on
    that exact shape."""
    real_search = JiraSearchResult.from_api_response(data=MOCK_JIRA_JQL_RESPONSE)
    fetcher = MagicMock(spec=JiraFetcher)
    fetcher.search_issues.return_value = real_search
    _patch_jira_fetcher(monkeypatch=monkeypatch, fetcher=fetcher)

    server = _build_parent_server(
        config=PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            mask_token="[X]",
        )
    )

    text = await _call_text(
        server=server,
        tool="jira_search",
        args={"jql": "project = TEST", "limit": 10, "fields": "summary"},
    )
    out = json.loads(text)
    # Real upstream search shape.
    assert "issues" in out
    flat = json.dumps(out)
    assert "@example.com" not in flat


# ---------------------------------------------------------------------------
# Confluence: real `confluence_get_page` flow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_confluence_get_page_pii_redaction_and_field_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``confluence_get_page`` wraps the simplified dict under
    ``metadata`` (or ``content`` when content is requested). Filter must
    handle that wrapper correctly."""
    real_page = ConfluencePage.from_api_response(data=MOCK_PAGE_RESPONSE)
    fetcher = MagicMock(spec=ConfluenceFetcher)
    fetcher.get_page_content.return_value = real_page
    _patch_confluence_fetcher(monkeypatch=monkeypatch, fetcher=fetcher)

    server = _build_parent_server(
        config=PrivacyConfig(
            enabled=True,
            drop_fields={"confluence_page": ["metadata.space.key"]},
        )
    )

    text = await _call_text(
        server=server,
        tool="confluence_get_page",
        args={"page_id": "123456789", "include_metadata": True},
    )
    out = json.loads(text)
    assert "metadata" in out
    # The space.key path was dropped.
    assert "key" not in out["metadata"].get("space", {}), (
        f"space.key should be dropped, got space={out['metadata'].get('space')!r}"
    )
    # space.name kept.
    assert "name" in out["metadata"]["space"]


# ---------------------------------------------------------------------------
# Confluence: real `confluence_search` flow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_confluence_search_resource_denylist_on_space_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``confluence_search`` returns a ``results`` list of pages.
    ``PRIVACY_DENY_SPACE_KEYS`` must drop pages whose ``space.key``
    matches, on the real simplified shape."""
    real_search = ConfluenceSearchResult.from_api_response(
        data=MOCK_CQL_SEARCH_RESPONSE
    )
    fetcher = MagicMock(spec=ConfluenceFetcher)
    fetcher.search.return_value = real_search.results
    _patch_confluence_fetcher(monkeypatch=monkeypatch, fetcher=fetcher)

    # The mock has space.key=TEAM. Deny it → results becomes empty.
    server = _build_parent_server(
        config=PrivacyConfig(enabled=True, deny_space_keys=["TEAM"])
    )

    text = await _call_text(
        server=server,
        tool="confluence_search",
        args={"query": "anything", "limit": 10},
    )
    out = json.loads(text)
    # Real upstream search returns a flat list of simplified pages.
    if isinstance(out, list):
        assert all(p.get("space", {}).get("key") != "TEAM" for p in out)
    else:
        # Wrapped form
        assert all(
            p.get("space", {}).get("key") != "TEAM" for p in out.get("results", [])
        )


# ---------------------------------------------------------------------------
# Verify PrivacyFilterMiddleware emits one log per real tool call
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_tool_emits_telemetry_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    real_issue = JiraIssue.from_api_response(data=MOCK_JIRA_ISSUE_RESPONSE)
    fetcher = MagicMock(spec=JiraFetcher)
    fetcher.get_issue.return_value = real_issue
    _patch_jira_fetcher(monkeypatch=monkeypatch, fetcher=fetcher)

    server = _build_parent_server(
        config=PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            mask_token="[X]",
        )
    )

    with caplog.at_level(logging.DEBUG, logger="mcp_atlassian.privacy.middleware"):
        await _call_text(
            server=server,
            tool="jira_get_issue",
            args={"issue_key": "TEST-1"},
        )

    privacy_logs = [
        r for r in caplog.records if "privacy filter applied" in r.getMessage()
    ]
    assert privacy_logs, "expected at least one telemetry log line"
    msg = privacy_logs[-1].getMessage()
    assert "tool=jira_get_issue" in msg
    # At least one PII redaction happened against the real shape.
    assert "pii_redactions=" in msg


# ---------------------------------------------------------------------------
# Disabled filter is a true pass-through on real tools
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_real_tool_unmodified_when_filter_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_issue = JiraIssue.from_api_response(data=MOCK_JIRA_ISSUE_RESPONSE)
    fetcher = MagicMock(spec=JiraFetcher)
    fetcher.get_issue.return_value = real_issue
    _patch_jira_fetcher(monkeypatch=monkeypatch, fetcher=fetcher)

    server = _build_parent_server(config=PrivacyConfig(enabled=False))

    text = await _call_text(
        server=server, tool="jira_get_issue", args={"issue_key": "TEST-1"}
    )
    out = json.loads(text)
    # Filter off → original simplified dict reaches the client unchanged.
    expected = real_issue.to_simplified_dict()
    assert out == expected
