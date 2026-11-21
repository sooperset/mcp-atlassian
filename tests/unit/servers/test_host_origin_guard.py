"""Host and Origin checks on the HTTP transports.

When header-less requests are served with the operator's global credentials
(``ALLOW_GLOBAL_CRED_FALLBACK`` or ``IGNORE_HEADER_AUTH``), a page in the
operator's browser must not be able to reach the listener under a foreign
hostname. Other deployments keep FastMCP's default.
"""

from __future__ import annotations

from typing import Any

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


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ALLOW_GLOBAL_CRED_FALLBACK",
        "IGNORE_HEADER_AUTH",
        "FASTMCP_HTTP_HOST_ORIGIN_PROTECTION",
        "FASTMCP_HTTP_ALLOWED_HOSTS",
        "FASTMCP_HTTP_ALLOWED_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)
    _reload_settings(monkeypatch)


def _reload_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = fastmcp.settings.__class__(_env_file=None)
    monkeypatch.setattr("mcp_atlassian.servers.main.fastmcp_settings", settings)
    monkeypatch.setattr(fastmcp, "settings", settings)


async def _post(
    transport_name: str,
    headers: dict[str, str],
    base_url: str = "http://127.0.0.1:8000",
    **app_kwargs: Any,
) -> int:
    app = main_mcp.http_app(transport=transport_name, **app_kwargs)
    path = "/mcp" if transport_name == "streamable-http" else "/sse"
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=base_url
        ) as client,
    ):
        response = await client.post(
            path,
            headers={
                "accept": "application/json, text/event-stream",
                "content-type": "application/json",
                **headers,
            },
            json=_INITIALIZE,
        )
    return response.status_code


_FOREIGN_HOST = {"host": "rebind.attacker.test:8000"}
_FOREIGN_ORIGIN = {
    "host": "127.0.0.1:8000",
    "origin": "http://rebind.attacker.test:8000",
}


@pytest.mark.anyio
@pytest.mark.parametrize("transport_name", ["streamable-http", "sse"])
@pytest.mark.parametrize("mode", ["ALLOW_GLOBAL_CRED_FALLBACK", "IGNORE_HEADER_AUTH"])
async def test_operator_credential_mode_refuses_foreign_host_and_origin(
    monkeypatch: pytest.MonkeyPatch, transport_name: str, mode: str
) -> None:
    monkeypatch.setenv(mode, "true")
    assert await _post(transport_name, _FOREIGN_HOST) == 421
    assert await _post(transport_name, _FOREIGN_ORIGIN) == 403


@pytest.mark.anyio
async def test_operator_credential_mode_still_serves_local_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_GLOBAL_CRED_FALLBACK", "true")
    status = await _post(
        "streamable-http",
        {"host": "127.0.0.1:8000", "origin": "http://localhost:3000"},
    )
    assert status not in (421, 403)


_LAN = "http://10.0.0.5:8000"


@pytest.mark.anyio
@pytest.mark.parametrize("transport_name", ["streamable-http", "sse"])
async def test_operator_credential_mode_refuses_foreign_origin_on_any_address(
    monkeypatch: pytest.MonkeyPatch, transport_name: str
) -> None:
    monkeypatch.setenv("ALLOW_GLOBAL_CRED_FALLBACK", "true")
    headers = {"host": "10.0.0.5:8000", "origin": "http://rebind.attacker.test:8000"}
    assert await _post(transport_name, headers, base_url=_LAN) == 403


@pytest.mark.anyio
@pytest.mark.parametrize("transport_name", ["streamable-http", "sse"])
@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({"host": "mcp.example.com"}, id="proxy-without-origin"),
        pytest.param({"host": "10.0.0.5:8000"}, id="container-address"),
        pytest.param(
            {"host": "mcp.example.com", "origin": "http://localhost:3000"},
            id="local-origin",
        ),
        pytest.param(
            {"host": "mcp.example.com", "origin": "http://[::1]:3000"},
            id="local-ipv6-origin",
        ),
    ],
)
async def test_operator_credential_mode_behind_a_proxy_is_not_refused(
    monkeypatch: pytest.MonkeyPatch, transport_name: str, headers: dict[str, str]
) -> None:
    # A container bound to 0.0.0.0 receives the proxy's public hostname on a
    # non-loopback address; the default must not refuse it.
    monkeypatch.setenv("IGNORE_HEADER_AUTH", "true")
    assert await _post(transport_name, headers, base_url=_LAN) not in (421, 403)


@pytest.mark.anyio
async def test_operator_origin_allowlist_admits_a_browser_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_GLOBAL_CRED_FALLBACK", "true")
    monkeypatch.setenv("FASTMCP_HTTP_ALLOWED_ORIGINS", '["https://mcp.example.com"]')
    _reload_settings(monkeypatch)
    headers = {"host": "mcp.example.com", "origin": "https://mcp.example.com"}
    assert await _post("streamable-http", headers, base_url=_LAN) not in (421, 403)
    headers["origin"] = "https://other.example"
    assert await _post("streamable-http", headers, base_url=_LAN) == 403


@pytest.mark.anyio
async def test_operator_allowlist_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_GLOBAL_CRED_FALLBACK", "true")
    monkeypatch.setenv("FASTMCP_HTTP_HOST_ORIGIN_PROTECTION", "true")
    monkeypatch.setenv("FASTMCP_HTTP_ALLOWED_HOSTS", '["mcp.example.com"]')
    _reload_settings(monkeypatch)
    lan = "http://192.168.50.5:8000"
    assert await _post("streamable-http", _FOREIGN_HOST, base_url=lan) == 421
    status = await _post("streamable-http", {"host": "mcp.example.com"}, base_url=lan)
    assert status not in (421, 403)


@pytest.mark.anyio
async def test_explicit_opt_out_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_GLOBAL_CRED_FALLBACK", "true")
    monkeypatch.setenv("FASTMCP_HTTP_HOST_ORIGIN_PROTECTION", "false")
    _reload_settings(monkeypatch)
    assert await _post("streamable-http", _FOREIGN_HOST) not in (421, 403)


@pytest.mark.anyio
async def test_header_auth_deployment_keeps_fastmcp_default() -> None:
    # Without operator-credential mode an unauthenticated request is refused
    # with 401 anyway; the Host check stays as FastMCP configures it.
    assert await _post("streamable-http", _FOREIGN_HOST) == 401
