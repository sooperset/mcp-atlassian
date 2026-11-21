"""Tool arguments that end up in a REST path stay one path segment.

Each tool runs through the FastMCP client with a real fetcher, the real scope
guard and the real requests session. Only the HTTP adapter's ``send`` is
replaced, so the recorded URL is the one the session would put on the wire.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

import pytest
import requests
from fastmcp import Client
from fastmcp.client import FastMCPTransport
from fastmcp.exceptions import ToolError

from mcp_atlassian.confluence import ConfluenceConfig, ConfluenceFetcher
from mcp_atlassian.jira import JiraConfig, JiraFetcher
from mcp_atlassian.servers.confluence import confluence_mcp
from mcp_atlassian.servers.jira import jira_mcp
from mcp_atlassian.utils.oauth import BYOAccessTokenOAuthConfig
from mcp_atlassian.utils.ssrf_adapter import SsrfPinningAdapter

Router = Callable[[str, str], Any]
Sent = list[tuple[str, str]]


def _response(request: requests.PreparedRequest, payload: Any) -> Any:
    response = requests.Response()
    response.status_code = 200
    response.url = str(request.url)
    response.request = request
    response.headers["Content-Type"] = "application/json"
    response._content = json.dumps(payload).encode()
    return response


@pytest.fixture
def wire() -> Iterator[Callable[[Router], Sent]]:
    sent: Sent = []

    def install(router: Router) -> Sent:
        def send(self: Any, request: Any, **kwargs: Any) -> Any:
            target = urlsplit(request.url)
            path = target.path + (f"?{target.query}" if target.query else "")
            sent.append((request.method, path))
            return _response(request, router(request.method, target.path))

        patcher = patch.object(SsrfPinningAdapter, "send", send)
        patcher.start()
        patchers.append(patcher)
        return sent

    patchers: list[Any] = []
    yield install
    for patcher in patchers:
        patcher.stop()


def _jira(url: str = "https://example.atlassian.net", **kwargs: Any) -> JiraFetcher:
    return JiraFetcher(
        config=JiraConfig(
            url=url,
            auth_type="basic",
            username="u@example.invalid",
            api_token="dummy",
            projects_filter="ALLOWED",
            **kwargs,
        )
    )


def _jira_server() -> JiraFetcher:
    return JiraFetcher(
        config=JiraConfig(
            url="https://jira.example.test",
            auth_type="pat",
            personal_token="dummy",
            projects_filter="ALLOWED",
        )
    )


def _jira_router(method: str, path: str) -> Any:
    if "/issue/ALLOWED-1" in path and method == "GET" and "comment" not in path:
        return {
            "id": "1",
            "key": "ALLOWED-1",
            "fields": {"project": {"key": "ALLOWED"}},
        }
    if method == "GET" and path.endswith("/rest/api/2/version/10001"):
        return {"id": "10001", "projectId": "1"}
    if path.endswith("/rest/api/2/project/1"):
        return {"id": "1", "key": "ALLOWED"}
    if path.rstrip("/").endswith("/servicedesk/4"):
        return {"id": "4", "projectKey": "ALLOWED"}
    if "/comment/" in path:
        return {"id": "10000", "body": "old", "author": {"displayName": "x"}}
    return {"values": [], "isLast": True, "size": 0}


async def _call_jira(fetcher: JiraFetcher, tool: str, args: dict[str, Any]) -> Any:
    with patch(
        "mcp_atlassian.servers.jira.get_jira_fetcher",
        AsyncMock(return_value=fetcher),
    ):
        async with Client(transport=FastMCPTransport(jira_mcp)) as client:
            return await client.call_tool(tool, args)


def _sink_requests(sent: Sent, marker: str) -> Sent:
    return [(m, p) for m, p in sent if marker in p]


# --- Jira sub-object ids --------------------------------------------------------

_JIRA_CASES = [
    pytest.param(
        "edit_comment",
        {"issue_key": "ALLOWED-1", "body": "b"},
        "comment_id",
        "/comment",
        _jira,
        id="edit_comment",
    ),
    pytest.param(
        "get_queue_issues",
        {"service_desk_id": "4"},
        "queue_id",
        "/queue",
        _jira_server,
        id="get_queue_issues",
    ),
    pytest.param(
        "get_request_type_fields",
        {"service_desk_id": "4"},
        "request_type_id",
        "/requesttype",
        _jira_server,
        id="get_request_type_fields",
    ),
    pytest.param(
        "get_create_fields",
        {"project_key": "ALLOWED"},
        "issue_type_id",
        "/createmeta",
        _jira_server,
        id="get_create_fields",
    ),
    pytest.param(
        "get_field_options",
        {"field_id": "customfield_10001"},
        "context_id",
        "/field/",
        _jira,
        id="get_field_options-context",
    ),
    pytest.param(
        "get_field_options",
        {},
        "field_id",
        "/field/",
        _jira,
        id="get_field_options-field",
    ),
]

_BAD_IDS = [
    "../../SECRET-1/comment/10000",
    "../../9/queue/6",
    "../../../request?x=",
    "..%2F..%2F9",
    "10000/x",
    "10000?x=",
    "10000#x",
    " 10000",
    "",
]


@pytest.mark.anyio
@pytest.mark.parametrize("bad", _BAD_IDS)
@pytest.mark.parametrize(("tool", "args", "param", "sink", "make"), _JIRA_CASES)
async def test_jira_sub_object_id_is_refused_before_any_sink_request(
    wire: Callable[[Router], Sent],
    tool: str,
    args: dict[str, Any],
    param: str,
    sink: str,
    make: Callable[[], JiraFetcher],
    bad: str,
) -> None:
    sent = wire(_jira_router)
    with pytest.raises(ToolError):
        await _call_jira(make(), tool, {**args, param: bad})
    assert _sink_requests(sent, sink) == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "args", "expected"),
    [
        pytest.param(
            "edit_comment",
            {"issue_key": "ALLOWED-1", "comment_id": "10000", "body": "b"},
            ("PUT", "/rest/api/3/issue/ALLOWED-1/comment/10000"),
            id="edit_comment",
        ),
        pytest.param(
            "get_field_options",
            {"field_id": "customfield_10001", "context_id": "10100"},
            (
                "GET",
                "/rest/api/3/field/customfield_10001/context/10100/option"
                "?startAt=0&maxResults=100",
            ),
            id="get_field_options",
        ),
    ],
)
async def test_jira_valid_sub_object_id_reaches_its_endpoint(
    wire: Callable[[Router], Sent],
    tool: str,
    args: dict[str, Any],
    expected: tuple[str, str],
) -> None:
    sent = wire(_jira_router)
    try:
        await _call_jira(_jira(), tool, args)
    except ToolError:
        pass  # The canned body may not parse; only the wire path matters.
    assert expected in sent


@pytest.mark.anyio
async def test_jira_server_queue_id_reaches_its_endpoint(
    wire: Callable[[Router], Sent],
) -> None:
    sent = wire(_jira_router)
    try:
        await _call_jira(
            _jira_server(),
            "get_queue_issues",
            {"service_desk_id": "4", "queue_id": "47"},
        )
    except ToolError:
        pass
    assert (
        "GET",
        "/rest/servicedeskapi/servicedesk/4/queue/47/issue?start=0&limit=50",
    ) in sent


@pytest.mark.anyio
@pytest.mark.parametrize(
    "version_id",
    ["../../../../wiki/rest/api/space/SECRET", "10001/x", "10001?x="],
)
async def test_jira_update_version_id_is_refused(
    wire: Callable[[Router], Sent], version_id: str
) -> None:
    sent = wire(_jira_router)
    with pytest.raises(ToolError):
        await _call_jira(
            _jira(), "update_version", {"version_id": version_id, "name": "renamed"}
        )
    assert [m for m, _ in sent if m != "GET"] == []
    assert _sink_requests(sent, "/wiki") == []


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        pytest.param(
            lambda f: f.get_queue_issues(service_desk_id="4", queue_id="6/issue?x"),
            "/rest/servicedeskapi/servicedesk/4/queue/6%2Fissue%3Fx",
            id="queue",
        ),
        pytest.param(
            lambda f: f.get_request_type_fields("4", "9/x"),
            "/rest/servicedeskapi/servicedesk/4/requesttype/9%2Fx/field",
            id="request_type",
        ),
        pytest.param(
            lambda f: f.update_version("1/x", name="n"),
            "/rest/api/2/version/1%2Fx",
            id="version",
        ),
    ],
)
def test_jira_library_calls_encode_path_segments(
    wire: Callable[[Router], Sent], call: Callable[[JiraFetcher], Any], expected: str
) -> None:
    sent = wire(_jira_router)
    fetcher = _jira_server()
    try:
        call(fetcher)
    except Exception:  # noqa: BLE001 - only the wire path matters
        pass
    assert any(path.startswith(expected) for _, path in sent), sent


def test_jira_cloud_library_calls_encode_path_segments(
    wire: Callable[[Router], Sent],
) -> None:
    sent = wire(_jira_router)
    fetcher = _jira()
    for call in (
        lambda: fetcher.edit_comment("ALLOWED-1", "1/x", "b"),
        lambda: fetcher.get_field_contexts("customfield_1/x"),
        lambda: fetcher.get_field_options("customfield_1", context_id="2/x"),
    ):
        try:
            call()
        except Exception:  # noqa: BLE001 - only the wire path matters
            pass
    paths = [p for _, p in sent]
    assert any(p.startswith("/rest/api/3/issue/ALLOWED-1/comment/1%2Fx") for p in paths)
    assert any(
        p.startswith("/rest/api/3/field/customfield_1%2Fx/context") for p in paths
    )
    assert any(
        p.startswith("/rest/api/3/field/customfield_1/context/2%2Fx/option")
        for p in paths
    )


_LONG_ID = "123456789012345678"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "args", "make", "expected"),
    [
        pytest.param(
            "edit_comment",
            {"issue_key": "ALLOWED-1", "comment_id": cid, "body": "b"},
            _jira,
            ("PUT", f"/rest/api/3/issue/ALLOWED-1/comment/{cid}"),
            id=f"comment-{cid}",
        )
        for cid in ("1", "10000", _LONG_ID)
    ]
    + [
        pytest.param(
            "get_field_options",
            {"field_id": fid},
            _jira,
            ("GET", f"/rest/api/3/field/{fid}/context?maxResults=100"),
            id=f"field-{fid}",
        )
        for fid in ("customfield_10001", "priority", "statusCategory")
    ]
    + [
        pytest.param(
            "get_queue_issues",
            {"service_desk_id": "4", "queue_id": _LONG_ID},
            _jira_server,
            (
                "GET",
                f"/rest/servicedeskapi/servicedesk/4/queue/{_LONG_ID}/issue"
                "?start=0&limit=50",
            ),
            id="queue-long",
        ),
        pytest.param(
            "get_request_type_fields",
            {"service_desk_id": "4", "request_type_id": "23"},
            _jira_server,
            ("GET", "/rest/servicedeskapi/servicedesk/4/requesttype/23/field"),
            id="request-type",
        ),
        pytest.param(
            "update_version",
            {"version_id": "10001", "name": "renamed"},
            _jira,
            ("PUT", "/rest/api/2/version/10001"),
            id="version",
        ),
    ],
)
async def test_jira_valid_ids_pass_the_tool_schema(
    wire: Callable[[Router], Sent],
    tool: str,
    args: dict[str, Any],
    make: Callable[[], JiraFetcher],
    expected: tuple[str, str],
) -> None:
    sent = wire(_jira_router)
    try:
        await _call_jira(make(), tool, args)
    except ToolError as error:
        # The canned body may not parse; a schema refusal must not happen.
        assert "validation error" not in str(error).lower(), error
    assert expected in sent, sent


# --- Confluence page move -------------------------------------------------------


def _confluence_cloud_oauth() -> ConfluenceFetcher:
    return ConfluenceFetcher(
        config=ConfluenceConfig(
            url="https://example.atlassian.net/wiki",
            auth_type="oauth",
            oauth_config=BYOAccessTokenOAuthConfig(
                cloud_id="cid-0000", access_token="dummy-token"
            ),
            spaces_filter="ALLOWED",
        )
    )


def _confluence_router(method: str, path: str) -> Any:
    for page, space in (("111", "1"), ("222", "1"), ("999", "2")):
        if path.endswith(f"/api/v2/pages/{page}") or path.endswith(
            f"/rest/api/content/{page}"
        ):
            return {
                "id": page,
                "title": "t",
                "spaceId": space,
                "space": {"key": "ALLOWED" if space == "1" else "SECRET"},
                "version": {"number": 1},
                "body": {"storage": {"value": "<p>x</p>"}},
            }
    if path.endswith("/api/v2/spaces/1"):
        return {"id": "1", "key": "ALLOWED"}
    if path.endswith("/api/v2/spaces/2"):
        return {"id": "2", "key": "SECRET"}
    return {}


def _confluence_server() -> ConfluenceFetcher:
    return ConfluenceFetcher(
        config=ConfluenceConfig(
            url="https://confluence.example.test",
            auth_type="pat",
            personal_token="dummy",
        )
    )


async def _move(
    args: dict[str, Any],
    make: Callable[[], ConfluenceFetcher] = _confluence_cloud_oauth,
) -> Any:
    with patch(
        "mcp_atlassian.servers.confluence.get_confluence_fetcher",
        AsyncMock(return_value=make()),
    ):
        async with Client(transport=FastMCPTransport(confluence_mcp)) as client:
            return await client.call_tool("move_page", args)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("args"),
    [
        {
            "page_id": "111",
            "target_parent_id": "222",
            "position": "../../999/move/append",
        },
        {"page_id": "111", "target_space_key": "ALLOWED", "position": "append/999"},
        {"page_id": "111", "target_parent_id": "222", "position": "append?x="},
        {"page_id": "111", "target_parent_id": "222", "position": "APPEND"},
    ],
)
async def test_confluence_move_position_outside_the_enum_sends_no_put(
    wire: Callable[[Router], Sent], args: dict[str, Any]
) -> None:
    sent = wire(_confluence_router)
    with pytest.raises(ToolError):
        await _move(args)
    assert [m for m, _ in sent if m == "PUT"] == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("position", "api_position"),
    [
        ("append", "append"),
        ("above", "before"),
        ("below", "after"),
        ("before", "before"),
        ("after", "after"),
    ],
)
async def test_confluence_cloud_move_sends_the_rest_position(
    wire: Callable[[Router], Sent], position: str, api_position: str
) -> None:
    sent = wire(_confluence_router)
    try:
        await _move({"page_id": "111", "target_parent_id": "222", "position": position})
    except ToolError:
        pass  # The re-fetch after the move may not parse the canned body.
    puts = [p for m, p in sent if m == "PUT"]
    assert puts == [
        f"/ex/confluence/cid-0000/rest/api/content/111/move/{api_position}/222"
    ]


def test_confluence_adapter_move_encodes_ids_and_rejects_unknown_position(
    wire: Callable[[Router], Sent],
) -> None:
    sent = wire(_confluence_router)
    adapter = _confluence_cloud_oauth()._v2_adapter
    assert adapter is not None
    with pytest.raises(ValueError):
        adapter.move_page(page_id="111", position="append/999", target_id="222")
    assert sent == []
    adapter.move_page(page_id="1/x", position="append", target_id="2?y")
    assert sent == [
        ("PUT", "/ex/confluence/cid-0000/rest/api/content/1%2Fx/move/append/2%3Fy")
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("position", "action_position"),
    [
        ("append", "append"),
        ("above", "above"),
        ("below", "below"),
        ("before", "above"),
        ("after", "below"),
    ],
)
async def test_confluence_server_move_sends_the_action_position(
    wire: Callable[[Router], Sent], position: str, action_position: str
) -> None:
    sent = wire(_confluence_router)
    try:
        await _move(
            {"page_id": "111", "target_parent_id": "222", "position": position},
            make=_confluence_server,
        )
    except ToolError:
        pass  # The move check reads canned pages that may not match.
    posts = [p for m, p in sent if m == "POST" and "movepage.action" in p]
    assert len(posts) == 1, sent
    assert f"position={action_position}" in posts[0]
