"""Tool handlers keep the event loop free while a fetcher call blocks.

Each test calls a real tool through a FastMCP client. The stubbed fetcher
method blocks until a sibling coroutine releases it. If the handler ran the
call on the event-loop thread, the sibling could not run, and the stub would
give up after a safety timeout and report that it was never released.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from fastmcp import Client, FastMCP
from fastmcp.client import FastMCPTransport

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.jira import JiraFetcher

SAFETY_TIMEOUT_S = 5.0


class BlockingStub:
    """Blocks until released from another coroutine; records where it ran."""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.entered = threading.Event()
        self.release = threading.Event()
        self.released_while_blocked: bool | None = None
        self.thread_id: int | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.thread_id = threading.get_ident()
        self.entered.set()
        self.released_while_blocked = self.release.wait(SAFETY_TIMEOUT_S)
        return self.result


async def _call_with_sibling(
    client: Client, stub: BlockingStub, tool: str, args: dict[str, Any]
) -> None:
    async def sibling() -> None:
        while not stub.entered.is_set():
            await anyio.sleep(0.001)
        stub.release.set()

    async with anyio.create_task_group() as tg:
        tg.start_soon(sibling)
        result = await client.call_tool(tool, args, raise_on_error=False)
        tg.cancel_scope.cancel()
    assert not result.is_error, result.content
    loop_thread = threading.get_ident()
    assert stub.entered.is_set(), "the stubbed fetcher method was not called"
    assert stub.thread_id != loop_thread, "fetcher call ran on the event loop"
    assert stub.released_while_blocked, "event loop was blocked by the call"


def _server(tool_funcs: list[Callable[..., Any]]) -> FastMCP:
    mcp = FastMCP("event-loop-test")
    for func in tool_funcs:
        mcp.add_tool(func)
    return mcp


def _jira_fetcher() -> MagicMock:
    fetcher = MagicMock(spec=JiraFetcher)
    fetcher.config = MagicMock()
    fetcher.config.url = "https://jira.example.test"
    fetcher.config.read_only = False
    fetcher.config.projects_filter = None
    return fetcher


def _confluence_fetcher() -> MagicMock:
    fetcher = MagicMock(spec=ConfluenceFetcher)
    fetcher.config = MagicMock()
    fetcher.config.url = "https://wiki.example.test"
    fetcher.config.spaces_filter = None
    return fetcher


JIRA_CASES = [
    (
        "download_attachments",
        "get_issue_attachment_contents",
        {"success": True, "issue_key": "PROJ-1", "attachments": [], "failed": []},
        {"issue_key": "PROJ-1"},
    ),
    ("get_worklog", "get_worklogs", [], {"issue_key": "PROJ-1"}),
    ("get_issue_watchers", "get_issue_watchers", {}, {"issue_key": "PROJ-1"}),
]

CONFLUENCE_CASES = [
    ("search", "search", [], {"query": "type=page", "limit": 5}),
    ("get_comments", "get_page_comments", [], {"page_id": "1"}),
    ("get_page_children", "get_page_children", [], {"parent_id": "1"}),
]


@pytest.mark.anyio
@pytest.mark.parametrize(("tool", "method", "result", "args"), JIRA_CASES)
async def test_jira_tool_does_not_block_event_loop(
    tool: str, method: str, result: Any, args: dict[str, Any]
) -> None:
    from mcp_atlassian.servers import jira as jira_tools

    fetcher = _jira_fetcher()
    stub = BlockingStub(result)
    getattr(fetcher, method).side_effect = stub
    mcp = _server([getattr(jira_tools, tool)])
    with patch.object(jira_tools, "get_jira_fetcher", AsyncMock(return_value=fetcher)):
        async with Client(transport=FastMCPTransport(mcp)) as client:
            await _call_with_sibling(client, stub, tool, args)


@pytest.mark.anyio
@pytest.mark.parametrize(("tool", "method", "result", "args"), CONFLUENCE_CASES)
async def test_confluence_tool_does_not_block_event_loop(
    tool: str, method: str, result: Any, args: dict[str, Any]
) -> None:
    from mcp_atlassian.servers import confluence as confluence_tools

    fetcher = _confluence_fetcher()
    stub = BlockingStub(result)
    getattr(fetcher, method).side_effect = stub
    mcp = _server([getattr(confluence_tools, tool)])
    with patch.object(
        confluence_tools, "get_confluence_fetcher", AsyncMock(return_value=fetcher)
    ):
        async with Client(transport=FastMCPTransport(mcp)) as client:
            await _call_with_sibling(client, stub, tool, args)


class _HeaderPatState:
    """Request state for a header-PAT caller (no ``user_atlassian_token``)."""

    def __init__(self, headers: dict[str, str]) -> None:
        self.jira_fetcher = None
        self.user_atlassian_auth_type = "pat"
        self.user_atlassian_email = None
        self.atlassian_service_headers = headers


@pytest.mark.anyio
async def test_header_pat_validation_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Building and validating a per-request fetcher runs off the event loop.

    The header-PAT config also takes the operator's JIRA_TIMEOUT.
    """
    from mcp_atlassian.servers import dependencies

    monkeypatch.setenv("JIRA_TIMEOUT", "4")
    stub = BlockingStub("account-id")
    built_configs: list[Any] = []

    class StubFetcher:
        def __init__(self, config: Any) -> None:
            built_configs.append(config)
            self.config = config
            self.jira = MagicMock()

        get_current_user_account_id = staticmethod(stub)

    request = MagicMock()
    request.state = _HeaderPatState(
        {
            "X-Atlassian-Jira-Url": "https://slow.example.test",
            "X-Atlassian-Jira-Personal-Token": "event-loop-test-token",
        }
    )

    async def sibling() -> None:
        while not stub.entered.is_set():
            await anyio.sleep(0.001)
        stub.release.set()

    with (
        patch.object(dependencies, "get_http_request", return_value=request),
        patch.object(dependencies, "JiraFetcher", StubFetcher),
        patch.object(dependencies, "_get_global_config", side_effect=ValueError),
    ):
        async with anyio.create_task_group() as tg:
            tg.start_soon(sibling)
            fetcher = await dependencies.get_jira_fetcher(MagicMock())
            tg.cancel_scope.cancel()

    assert isinstance(fetcher, StubFetcher)
    assert stub.thread_id != threading.get_ident(), "validation ran on the loop"
    assert stub.released_while_blocked, "event loop was blocked by validation"
    assert built_configs[0].timeout == 4


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "method", "args"),
    [
        ("get_worklog", "get_worklogs", {"issue_key": "PROJ-1"}),
        (
            "batch_get_changelogs",
            "batch_get_changelogs",
            {"issue_ids_or_keys": "PROJ-1"},
        ),
    ],
)
async def test_jira_tools_report_truncated_reads(
    tool: str, method: str, args: dict[str, Any]
) -> None:
    """A marked (cut-short) fetcher result is visible in the tool response."""
    import json

    from mcp_atlassian.servers import jira as jira_tools
    from mcp_atlassian.utils.truncation import mark_truncated

    fetcher = _jira_fetcher()
    fetcher.config.is_cloud = True
    getattr(fetcher, method).return_value = mark_truncated([], certain=True)
    mcp = _server([getattr(jira_tools, tool)])
    with patch.object(jira_tools, "get_jira_fetcher", AsyncMock(return_value=fetcher)):
        async with Client(transport=FastMCPTransport(mcp)) as client:
            result = await client.call_tool(tool, args)
    body = json.loads(result.content[0].text)

    if isinstance(body, list):
        assert body[-1]["truncated"] is True
    else:
        assert body["truncated"] is True
        assert body["hint"]
