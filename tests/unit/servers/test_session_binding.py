"""MCP transport sessions belong to the credential that opened them.

A caller who learns another caller's session id must get the same answer as
for an unknown session, while the owner keeps using it.
"""

from __future__ import annotations

import base64
import json
import socket
import threading
import time
from collections.abc import Iterator

import fastmcp
import httpx
import pytest

from mcp_atlassian.servers.main import main_mcp

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "0"},
    },
}
_INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}
_A = {"authorization": "Token dummy-principal-a"}
_B = {"authorization": "Token dummy-principal-b"}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ALLOW_GLOBAL_CRED_FALLBACK",
        "IGNORE_HEADER_AUTH",
        "FASTMCP_HTTP_HOST_ORIGIN_PROTECTION",
        "JIRA_URL",
        "CONFLUENCE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = fastmcp.settings.__class__(_env_file=None)
    monkeypatch.setattr("mcp_atlassian.servers.main.fastmcp_settings", settings)
    monkeypatch.setattr(fastmcp, "settings", settings)


def _ping(request_id: int) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "method": "ping"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "other",
    [
        _B,
        {"authorization": "Basic " + base64.b64encode(b"b@example.test:x").decode()},
        {
            "x-atlassian-jira-personal-token": "dummy-principal-a",
            "x-atlassian-jira-url": "https://other.atlassian.net",
        },
    ],
)
async def test_streamable_session_refuses_other_credentials(
    monkeypatch: pytest.MonkeyPatch, other: dict[str, str]
) -> None:
    from mcp_atlassian.utils import urls

    monkeypatch.setattr(urls, "_check_dns_resolution", lambda *a, **k: None)
    app = main_mcp.http_app(transport="streamable-http")
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
        ) as client,
    ):
        opened = await client.post("/mcp", headers={**_HEADERS, **_A}, json=_INITIALIZE)
        assert opened.status_code == 200
        session = {"mcp-session-id": opened.headers["mcp-session-id"]}
        await client.post(
            "/mcp", headers={**_HEADERS, **_A, **session}, json=_INITIALIZED
        )

        foreign = {**_HEADERS, **other, **session}
        assert (
            await client.post("/mcp", headers=foreign, json=_ping(2))
        ).status_code == 404
        cancel = {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": 7},
        }
        assert (
            await client.post("/mcp", headers=foreign, json=cancel)
        ).status_code == 404
        assert (await client.delete("/mcp", headers=foreign)).status_code == 404

        own = await client.post(
            "/mcp", headers={**_HEADERS, **_A, **session}, json=_ping(3)
        )
        assert own.status_code == 200
        assert (
            await client.delete("/mcp", headers={**_A, **session})
        ).status_code == 200


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def sse_server() -> Iterator[str]:
    import uvicorn

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            main_mcp.http_app(transport="sse"),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(10)


def test_sse_session_refuses_other_credentials(sse_server: str) -> None:
    with httpx.Client(base_url=sse_server, timeout=10) as client:
        with client.stream("GET", "/sse", headers=_A) as stream:
            lines = stream.iter_lines()
            endpoint = next(
                line.split(":", 1)[1].strip()
                for line in lines
                if line.startswith("data:")
            )
            post = {"content-type": "application/json"}
            assert (
                client.post(
                    endpoint, headers={**post, **_A}, json=_INITIALIZE
                ).status_code
                == 202
            )
            assert (
                client.post(
                    endpoint, headers={**post, **_B}, json=_ping(4242)
                ).status_code
                == 404
            )
            assert (
                client.post(endpoint, headers={**post, **_A}, json=_ping(5)).status_code
                == 202
            )

            replies = []
            for line in lines:
                if line.startswith("data:"):
                    replies.append(json.loads(line[5:]))
                    if replies[-1].get("id") == 5:
                        break
            assert 4242 not in [reply.get("id") for reply in replies]


def _jwt(claims: dict[str, object]) -> str:
    def part(value: dict[str, object]) -> str:
        raw = json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256'})}.{part(claims)}.c2ln"


@pytest.mark.anyio
async def test_token_claims_do_not_name_the_user() -> None:
    """Tokens that claim the same account are still different principals.

    The verifier does not check signatures, so a claim inside a token would
    let a forged token take another user's identity.
    """
    from mcp.server.auth.middleware.bearer_auth import (
        AuthenticatedUser,
        authorization_context,
    )

    from mcp_atlassian.utils.token_verifier import AtlassianOpaqueTokenVerifier

    verifier = AtlassianOpaqueTokenVerifier()

    async def owner(token: str) -> object:
        access = await verifier.verify_token(token)
        assert access is not None
        return authorization_context(AuthenticatedUser(access))

    claims = {"iss": "https://auth.atlassian.com", "sub": "acct-victim"}
    genuine = await owner(_jwt({**claims, "jti": "1"}))
    forged = await owner(_jwt({**claims, "jti": "2"}))
    assert genuine != forged
    assert genuine == await owner(_jwt({**claims, "jti": "1"}))
    assert "acct-victim" not in json.dumps(genuine)


@pytest.mark.anyio
async def test_changed_bearer_token_gets_404_on_its_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A session opened with one Bearer token answers 404 to a new token.

    404 is what tells an MCP client to open a new session; 401 or 403 would
    send it into re-authentication instead.
    """
    app = main_mcp.http_app(transport="streamable-http")
    forged = {
        "authorization": "Bearer "
        + _jwt({"iss": "https://auth.atlassian.com", "sub": "acct-a", "jti": "x"})
    }
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
        ) as client,
    ):
        first = {
            "authorization": "Bearer "
            + _jwt({"iss": "https://auth.atlassian.com", "sub": "acct-a", "jti": "1"})
        }
        opened = await client.post(
            "/mcp", headers={**_HEADERS, **first}, json=_INITIALIZE
        )
        session = {"mcp-session-id": opened.headers["mcp-session-id"]}
        refreshed = {"authorization": "Bearer refreshed-token"}
        for other in (refreshed, forged):
            answer = await client.post(
                "/mcp", headers={**_HEADERS, **other, **session}, json=_ping(2)
            )
            assert answer.status_code == 404
        same = await client.post(
            "/mcp", headers={**_HEADERS, **first, **session}, json=_ping(3)
        )
        assert same.status_code == 200
