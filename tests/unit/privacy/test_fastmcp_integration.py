"""Full-stack integration tests for the privacy filter against FastMCP.

Earlier privacy-module tests use synthetic ``MiddlewareContext`` stand-ins
to verify the pipeline wiring in isolation. These tests close the loop:
they spin up a real :class:`fastmcp.FastMCP` server, register tools that
emit known-PII payloads, install the privacy middleware via the public
:func:`install_privacy_filter` API, and dispatch tool calls through
FastMCP's in-process :class:`fastmcp.client.transports.FastMCPTransport`.

The transport plumbs the request through FastMCP's middleware chain
exactly as it does in production (no network, no stdio), so anything that
breaks the chain — ordering, context shape, ``ToolResult`` reconstruction,
``call_next`` semantics — surfaces here.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from mcp_atlassian.privacy import PrivacyConfig, install_privacy_filter


def _build_server(payloads: dict[str, Any]) -> FastMCP[None]:
    """Build a tiny FastMCP server with one tool per ``payloads`` entry.

    Each tool returns ``json.dumps(payloads[tool_name])`` — i.e. the exact
    shape upstream Atlassian tools emit (see
    ``servers/jira.py`` / ``servers/confluence.py``: every tool ends with
    ``return json.dumps(result, indent=2, ensure_ascii=False)``).
    """
    server: FastMCP[None] = FastMCP(name="privacy-test")

    def _make_tool(name: str, value: Any) -> None:
        @server.tool(name=name)
        async def _tool() -> str:
            return json.dumps(value, indent=2, ensure_ascii=False)

        # Defeat the unused-name lint; the decorator registers via name.
        _ = _tool

    for tool_name, payload in payloads.items():
        _make_tool(name=tool_name, value=payload)
    return server


async def _call(server: FastMCP[None], tool_name: str) -> str:
    """Call ``tool_name`` via FastMCP's in-process client and return the
    raw text content of the first content block (every test tool emits
    a single ``TextContent`` block)."""
    async with Client(server) as client:
        result = await client.call_tool(name=tool_name, arguments={})
    # Result here is `CallToolResult` — content is a list of ContentBlocks.
    content = result.content
    assert content, "expected at least one content block"
    block = content[0]
    text = getattr(block, "text", None)
    assert isinstance(text, str), f"expected TextContent, got {block!r}"
    return text


JIRA_ISSUE_PAYLOAD: dict[str, Any] = {
    "id": "10001",
    "key": "PROJ-1",
    "summary": "Bug: alice@example.com cannot log in from 10.0.0.42",
    "description": "Cardholder 4242 4242 4242 4242 hit error AKIAIOSFODNN7EXAMPLE",
    "reporter": {
        "display_name": "Alice Müller",
        "name": "Alice Müller",
        "email": "alice@example.com",
        "avatar_url": "https://x/secure/avatar/12345",
    },
    "assignee": {
        "display_name": "Bob",
        "name": "Bob",
        "email": "bob@example.com",
        "avatar_url": "https://x/secure/avatar/99999",
    },
    "comments": [
        {
            "id": "20001",
            "body": "ping carol@example.com — she has the AKIA key",
            "author": {"display_name": "Dave", "email": "dave@example.com"},
        }
    ],
    "labels": ["public"],
}

JIRA_SEARCH_PAYLOAD: dict[str, Any] = {
    "total": 3,
    "start_at": 0,
    "max_results": 50,
    "issues": [
        {
            "key": "PUB-1",
            "labels": ["public"],
            "summary": "Public issue",
            "assignee": {"email": "ann@example.com"},
        },
        {
            "key": "RED-1",
            "labels": ["confidential"],
            "summary": "Confidential — should be dropped",
            "assignee": {"email": "secret@example.com"},
        },
        {
            "key": "PRIV-99",
            "summary": "Project denied",
            "project": {"key": "PRIV"},
        },
    ],
}

CONFLUENCE_PAGE_PAYLOAD: dict[str, Any] = {
    "metadata": {
        "id": "p-1",
        "title": "Onboarding for Eve",
        "url": "https://x/wiki/p/p-1",
        "space": {"key": "ENG", "name": "Engineering"},
        "version": "v2",
    },
    "content": {
        "value": (
            "Eve's IBAN is DE89370400440532013000. Reach her on +49 30 1234 5678."
        )
    },
}

CONFLUENCE_HR_SEARCH_PAYLOAD: dict[str, Any] = {
    "total_size": 2,
    "start": 0,
    "limit": 50,
    "results": [
        {"id": "1", "title": "Eng wiki", "space": {"key": "ENG"}},
        {"id": "2", "title": "HR policy", "space": {"key": "HR"}},
    ],
    "cql_query": "type = page",
    "search_duration": 5,
}


@pytest.fixture
def server_with_disabled_filter() -> FastMCP[None]:
    """Sanity check: filter installed but not enabled → no transformation."""
    server = _build_server(payloads={"jira_get_issue": JIRA_ISSUE_PAYLOAD})
    installed = install_privacy_filter(
        server=server, config=PrivacyConfig(enabled=False)
    )
    assert installed is False
    return server


@pytest.mark.asyncio
async def test_disabled_filter_passes_payload_unchanged(
    server_with_disabled_filter: FastMCP[None],
) -> None:
    text = await _call(server=server_with_disabled_filter, tool_name="jira_get_issue")
    parsed = json.loads(text)
    assert parsed == JIRA_ISSUE_PAYLOAD


@pytest.fixture
def server_full_pipeline() -> FastMCP[None]:
    """Server with a full pipeline: PII regex + field rules + denylist."""
    server = _build_server(
        payloads={
            "jira_get_issue": JIRA_ISSUE_PAYLOAD,
            "jira_search": JIRA_SEARCH_PAYLOAD,
            "confluence_get_page": CONFLUENCE_PAGE_PAYLOAD,
            "confluence_search": CONFLUENCE_HR_SEARCH_PAYLOAD,
        }
    )
    config = PrivacyConfig.from_env(
        env={
            "PRIVACY_FILTER_ENABLED": "true",
            "PRIVACY_PII_PATTERNS": "email,phone,ipv4,iban,credit_card",
            "PRIVACY_PII_CUSTOM_REGEX": r"\bAKIA[0-9A-Z]{16}\b",
            "PRIVACY_DENY_LABELS": "confidential",
            "PRIVACY_DENY_SPACE_KEYS": "HR",
            "PRIVACY_DENY_PROJECT_KEYS": "PRIV",
            "PRIVACY_DROP_FIELDS": json.dumps(
                {"jira_issue": ["reporter.email", "assignee.email"]}
            ),
            "PRIVACY_MASK_FIELDS": json.dumps(
                {
                    "jira_issue": ["assignee.display_name"],
                    "confluence_page": ["content.value"],
                }
            ),
            "PRIVACY_MASK_TOKEN": "[X]",
        }
    )
    installed = install_privacy_filter(server=server, config=config)
    assert installed is True
    return server


@pytest.mark.asyncio
async def test_field_drop_removes_documented_paths(
    server_full_pipeline: FastMCP[None],
) -> None:
    text = await _call(server=server_full_pipeline, tool_name="jira_get_issue")
    out = json.loads(text)
    assert "email" not in out["reporter"], "reporter.email must be dropped"
    assert "email" not in out["assignee"], "assignee.email must be dropped"
    # Adjacent fields preserved.
    assert "display_name" in out["reporter"]


@pytest.mark.asyncio
async def test_field_mask_replaces_with_token(
    server_full_pipeline: FastMCP[None],
) -> None:
    text = await _call(server=server_full_pipeline, tool_name="jira_get_issue")
    out = json.loads(text)
    assert out["assignee"]["display_name"] == "[X]"


@pytest.mark.asyncio
async def test_pii_patterns_redact_in_free_text(
    server_full_pipeline: FastMCP[None],
) -> None:
    text = await _call(server=server_full_pipeline, tool_name="jira_get_issue")
    out = json.loads(text)
    flat = json.dumps(out)
    # Built-in patterns:
    assert "@example.com" not in flat
    assert "10.0.0.42" not in flat
    assert "4242 4242 4242 4242" not in flat
    # Custom regex:
    assert "AKIAIOSFODNN7EXAMPLE" not in flat
    # Mask token shows up where redactions happened:
    assert "[X]" in flat


@pytest.mark.asyncio
async def test_resource_denylist_drops_matching_issues(
    server_full_pipeline: FastMCP[None],
) -> None:
    text = await _call(server=server_full_pipeline, tool_name="jira_search")
    out = json.loads(text)
    keys = [issue.get("key") for issue in out["issues"]]
    # PUB-1 keeps; RED-1 dropped (label); PRIV-99 dropped (project key).
    assert keys == ["PUB-1"]


@pytest.mark.asyncio
async def test_confluence_page_content_field_masked(
    server_full_pipeline: FastMCP[None],
) -> None:
    text = await _call(server=server_full_pipeline, tool_name="confluence_get_page")
    out = json.loads(text)
    assert out["content"]["value"] == "[X]", (
        "content.value should be masked, not redacted-by-PII"
    )
    # Metadata survives entirely.
    assert out["metadata"]["title"] == "Onboarding for Eve"
    assert out["metadata"]["space"]["key"] == "ENG"


@pytest.mark.asyncio
async def test_confluence_search_drops_hr_space(
    server_full_pipeline: FastMCP[None],
) -> None:
    text = await _call(server=server_full_pipeline, tool_name="confluence_search")
    out = json.loads(text)
    space_keys = [r["space"]["key"] for r in out["results"]]
    assert space_keys == ["ENG"]


@pytest.mark.asyncio
async def test_unknown_tool_still_gets_pii_redaction() -> None:
    """A tool whose name isn't in tool_map.TOOL_RESOURCE_TYPES still
    benefits from PII redaction (field rules safely skip)."""
    payload = {
        "summary": "Reach me at carol@example.com",
        "data": {"phone": "+1 (415) 555-2671"},
    }
    server = _build_server(payloads={"my_custom_tool": payload})
    install_privacy_filter(
        server=server,
        config=PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email", "phone"],
            mask_token="[X]",
        ),
    )
    text = await _call(server=server, tool_name="my_custom_tool")
    out = json.loads(text)
    assert "carol@example.com" not in out["summary"]
    assert "555-2671" not in out["data"]["phone"]
    assert "[X]" in out["summary"]


@pytest.mark.asyncio
async def test_filter_does_not_run_when_pipeline_is_noop() -> None:
    """If config is enabled but has no rules, install returns False and
    the server emits payload unchanged."""
    server = _build_server(payloads={"jira_get_issue": JIRA_ISSUE_PAYLOAD})
    installed = install_privacy_filter(
        server=server, config=PrivacyConfig(enabled=True)
    )
    assert installed is False, "no-op pipeline should not install middleware"
    text = await _call(server=server, tool_name="jira_get_issue")
    out = json.loads(text)
    assert out == JIRA_ISSUE_PAYLOAD


@pytest.mark.asyncio
async def test_install_with_default_env_off() -> None:
    """install_privacy_filter() with no explicit config and no env var
    is a no-op — the default safe behaviour for upstream PR users who
    haven't opted in."""
    server = _build_server(payloads={"jira_get_issue": JIRA_ISSUE_PAYLOAD})
    # Ensure PRIVACY_FILTER_ENABLED is not set.
    import os

    os.environ.pop("PRIVACY_FILTER_ENABLED", None)
    installed = install_privacy_filter(server=server)
    assert installed is False
    text = await _call(server=server, tool_name="jira_get_issue")
    out = json.loads(text)
    assert out == JIRA_ISSUE_PAYLOAD


@pytest.mark.asyncio
async def test_middleware_chain_runs_for_every_call() -> None:
    """Multiple back-to-back tool calls all get filtered (the middleware
    is registered once and re-applied per call)."""
    server = _build_server(payloads={"jira_get_issue": JIRA_ISSUE_PAYLOAD})
    install_privacy_filter(
        server=server,
        config=PrivacyConfig(
            enabled=True, pii_pattern_names=["email"], mask_token="[X]"
        ),
    )
    async with Client(server) as client:
        for _ in range(3):
            result = await client.call_tool(name="jira_get_issue", arguments={})
            text = result.content[0].text  # type: ignore[union-attr]
            assert "@example.com" not in text
            assert "[X]" in text
