"""Hermetic client-facing OAuth DCR and PKCE integration tests."""

from __future__ import annotations

import inspect
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, get_type_hints

import httpx
import pytest
from pydantic import AnyHttpUrl
from starlette.applications import Starlette

from mcp_atlassian.servers.oauth_proxy import HardenedOAuthProxy
from mcp_atlassian.utils.token_verifier import AtlassianOpaqueTokenVerifier
from tests.utils.oauth_dcr_harness import (
    FakeUpstreamIssuer,
    LocalTLSOAuthIssuer,
    LocalTLSServer,
    OAuthDCRClientHarness,
    RegisteredClient,
    build_client_ssl_context,
)


@dataclass
class OAuthProxyTestbed:
    """In-process proxy app plus disposable TLS upstream issuer."""

    harness: OAuthDCRClientHarness
    issuer: FakeUpstreamIssuer


def _build_proxy(
    upstream_base_url: str,
    proxy_base_url: AnyHttpUrl | str,
    redirect_path: str | None = "/callback",
) -> HardenedOAuthProxy:
    provider_kwargs: dict[str, object] = {
        "upstream_authorization_endpoint": f"{upstream_base_url}/authorize",
        "upstream_token_endpoint": f"{upstream_base_url}/token",
        "upstream_client_id": "upstream-client-id",
        "upstream_client_secret": "upstream-client-secret",
        "token_verifier": AtlassianOpaqueTokenVerifier(
            required_scopes=["read:jira-work"]
        ),
        "allowed_grant_types": ["authorization_code", "refresh_token"],
        "forced_scopes": ["read:jira-work"],
        "require_authorization_consent": False,
    }
    if redirect_path is not None:
        provider_kwargs["redirect_path"] = redirect_path

    return HardenedOAuthProxy(
        base_url=proxy_base_url,
        **provider_kwargs,
    )


def _build_proxy_app(
    upstream_base_url: str,
    proxy_base_url: AnyHttpUrl | str,
    redirect_path: str | None = "/callback",
) -> Starlette:
    provider = _build_proxy(upstream_base_url, proxy_base_url, redirect_path)
    return Starlette(routes=provider.get_routes("/mcp"))


@pytest.fixture
async def oauth_proxy_testbed(
    tmp_path, monkeypatch
) -> AsyncIterator[OAuthProxyTestbed]:
    """Start an HTTPS upstream while mounting the proxy through ASGI transport."""
    issuer = FakeUpstreamIssuer()
    upstream_server = LocalTLSOAuthIssuer(tmp_path / "upstream", issuer)
    monkeypatch.setenv("SSL_CERT_FILE", str(upstream_server.ca_certificate_path))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    await upstream_server.start()
    proxy_app = _build_proxy_app(upstream_server.base_url, "https://mcp.test")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=proxy_app), base_url="https://mcp.test"
    ) as client:
        yield OAuthProxyTestbed(
            harness=OAuthDCRClientHarness(client, upstream_server.ca_certificate_path),
            issuer=issuer,
        )

    await upstream_server.stop()


@pytest.mark.anyio
async def test_oauth_proxy_dcr_pkce_authorization_code_exchange(
    oauth_proxy_testbed: OAuthProxyTestbed,
) -> None:
    """A client can discover, register, authorize with PKCE, and exchange a code."""
    harness = oauth_proxy_testbed.harness
    protected_resource, authorization_server = await harness.discover()

    assert protected_resource["resource"] == "https://mcp.test/mcp"
    assert authorization_server["registration_endpoint"].endswith("/register")
    assert authorization_server["authorization_endpoint"].endswith("/authorize")
    assert authorization_server["token_endpoint"].endswith("/token")

    registered_client = await harness.register("http://127.0.0.1:4242/callback")
    authorization_code, verifier = await harness.authorize_with_pkce(registered_client)
    response = await harness.exchange_code(
        registered_client, authorization_code, verifier
    )

    assert response.status_code == 200
    token_response = response.json()
    assert token_response["access_token"]
    assert token_response["token_type"].lower() == "bearer"
    assert (
        oauth_proxy_testbed.issuer.authorize_requests[0]["code_challenge_method"]
        == "S256"
    )
    assert oauth_proxy_testbed.issuer.token_requests[0]["code"] == (
        oauth_proxy_testbed.issuer.authorization_code
    )
    assert oauth_proxy_testbed.issuer.token_requests[0]["grant_type"] == (
        "authorization_code"
    )


@pytest.mark.anyio
async def test_oauth_proxy_rejects_unregistered_redirect_uri(
    oauth_proxy_testbed: OAuthProxyTestbed,
) -> None:
    """A DCR client cannot substitute an unregistered browser callback URI."""
    harness = oauth_proxy_testbed.harness
    registered_client = await harness.register("http://127.0.0.1:4242/callback")

    response = await harness._client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": registered_client.client_id,
            "redirect_uri": "https://attacker.example/callback",
            "scope": "read:jira-work",
            "state": "harness-client-state",
            "code_challenge": "challenge",
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )

    assert response.status_code >= 400


@pytest.mark.anyio
@pytest.mark.parametrize(
    "redirect_uri",
    [
        "https://mcp.test/callback",
        "https://mcp.test/callback/",
        "https://mcp.test/%63allback",
        "https://mcp.test/other/../callback",
        "https://mcp.test.:443/callback",
    ],
)
async def test_oauth_proxy_rejects_own_callback_as_dcr_redirect_uri(
    oauth_proxy_testbed: OAuthProxyTestbed,
    redirect_uri: str,
) -> None:
    """A DCR client cannot use the proxy's IdP callback as its callback."""
    response = await oauth_proxy_testbed.harness._client.post(
        "/register",
        json={
            "client_name": "callback-collision-client",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )

    assert 400 <= response.status_code < 500
    assert "callback" in response.text.lower()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("proxy_base_url", "redirect_path", "collision_uri"),
    [
        (AnyHttpUrl("https://mcp.test"), "/callback", "https://mcp.test/callback"),
        ("https://mcp.test", None, "https://mcp.test/auth/callback"),
    ],
)
async def test_oauth_proxy_preserves_fastmcp_callback_constructor_contract(
    proxy_base_url: AnyHttpUrl | str,
    redirect_path: str | None,
    collision_uri: str,
) -> None:
    """DCR collision protection supports FastMCP's URL and callback defaults."""
    proxy_app = _build_proxy_app("https://issuer.test", proxy_base_url, redirect_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=proxy_app), base_url="https://mcp.test"
    ) as client:
        collision_response = await client.post(
            "/register",
            json={
                "client_name": "callback-collision-client",
                "redirect_uris": [collision_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )
        valid_response = await client.post(
            "/register",
            json={
                "client_name": "valid-callback-client",
                "redirect_uris": ["http://127.0.0.1:4242/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )

    assert 400 <= collision_response.status_code < 500
    assert "callback" in collision_response.text.lower()
    assert 200 <= valid_response.status_code < 300


def test_oauth_proxy_preserves_fastmcp_constructor_signature() -> None:
    """The subclass must retain FastMCP's URL and callback-default contract."""
    type_hints = get_type_hints(HardenedOAuthProxy.__init__)
    signature = inspect.signature(HardenedOAuthProxy.__init__)

    assert type_hints["base_url"] == AnyHttpUrl | str
    assert signature.parameters["redirect_path"].default is None


def test_oauth_proxy_normalizes_omitted_callback_path_after_super() -> None:
    """Collision checks use FastMCP-normalized values after initialization."""
    provider = _build_proxy(
        "https://issuer.test", AnyHttpUrl("https://mcp.test"), redirect_path=None
    )

    assert str(provider.base_url) == "https://mcp.test/"
    assert provider._redirect_path == "/auth/callback"


@pytest.mark.anyio
async def test_oauth_proxy_rejects_default_callback_with_subpath_base_url() -> None:
    """The inherited callback default includes a path-bearing public base URL."""
    proxy_app = _build_proxy_app(
        "https://issuer.test", AnyHttpUrl("https://mcp.test/prefix"), None
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=proxy_app), base_url="https://mcp.test"
    ) as client:
        response = await client.post(
            "/register",
            json={
                "client_name": "subpath-collision-client",
                "redirect_uris": ["https://mcp.test/prefix/auth/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )

    assert 400 <= response.status_code < 500
    assert "callback" in response.text.lower()


@pytest.mark.anyio
async def test_oauth_proxy_rejects_token_exchange_with_wrong_pkce_verifier(
    oauth_proxy_testbed: OAuthProxyTestbed,
) -> None:
    """A code bound to one PKCE verifier cannot be redeemed with another."""
    harness = oauth_proxy_testbed.harness
    registered_client = await harness.register("http://127.0.0.1:4242/callback")
    authorization_code, _ = await harness.authorize_with_pkce(registered_client)

    response = await harness.exchange_code(
        registered_client, authorization_code, "wrong-oauth-dcr-harness-verifier"
    )

    assert response.status_code >= 400
    assert response.json()["error"] == "invalid_grant"


@pytest.mark.anyio
async def test_oauth_proxy_distinguishes_unknown_code_from_missing_client_state(
    oauth_proxy_testbed: OAuthProxyTestbed,
) -> None:
    """A registered client reaches code validation instead of client lookup failure."""
    harness = oauth_proxy_testbed.harness
    registered_client = await harness.register("http://127.0.0.1:4242/callback")
    verifier = "oauth-dcr-harness-verifier-0123456789-abcdefghijklmnopqrstuvwxyz"

    response = await harness.exchange_code(
        registered_client, "unknown-authorization-code", verifier
    )

    assert response.status_code >= 400
    payload = response.json()
    assert payload["error"] == "invalid_grant"
    assert "client information" not in payload.get("error_description", "").lower()


@pytest.mark.anyio
async def test_oauth_proxy_dcr_happy_path_over_loopback_tls(
    tmp_path, monkeypatch
) -> None:
    """The full happy path works through real HTTPS loopback listeners."""
    issuer = FakeUpstreamIssuer()
    upstream_server = LocalTLSOAuthIssuer(tmp_path / "upstream", issuer)
    proxy_server = LocalTLSServer(tmp_path / "proxy")
    monkeypatch.setenv("SSL_CERT_FILE", str(upstream_server.ca_certificate_path))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    try:
        await upstream_server.start()
        await proxy_server.start(
            _build_proxy_app(upstream_server.base_url, proxy_server.base_url)
        )
        async with httpx.AsyncClient(
            base_url=proxy_server.base_url,
            verify=build_client_ssl_context(proxy_server.ca_certificate_path),
            trust_env=False,
        ) as client:
            harness = OAuthDCRClientHarness(client, upstream_server.ca_certificate_path)
            await harness.discover()
            registered_client = await harness.register("http://127.0.0.1:4242/callback")
            authorization_code, verifier = await harness.authorize_with_pkce(
                registered_client
            )
            response = await harness.exchange_code(
                registered_client, authorization_code, verifier
            )
    finally:
        await proxy_server.stop()
        await upstream_server.stop()

    assert response.status_code == 200
    assert response.json()["access_token"]


@pytest.mark.anyio
@pytest.mark.security_regression
@pytest.mark.parametrize(
    "extra",
    [
        {"client_name": "n" * 1024},
        {"contacts": [f"user{i}@example.com" for i in range(2000)]},
    ],
    ids=["long-client-name", "large-metadata"],
)
async def test_oauth_proxy_rejects_oversized_registration(
    tmp_path, monkeypatch, extra
) -> None:
    """A registration record is bounded in size before it is stored."""
    import fastmcp

    monkeypatch.setattr(fastmcp.settings, "home", tmp_path)
    proxy_app = _build_proxy_app("https://issuer.test", "https://mcp.test")
    registration = {
        "redirect_uris": ["http://127.0.0.1:4242/cb"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=proxy_app), base_url="https://mcp.test"
    ) as client:
        rejected = await client.post("/register", json={**registration, **extra})
        accepted = await client.post(
            "/register", json={**registration, "client_name": "Claude Code"}
        )

    assert rejected.status_code == 400
    assert rejected.json()["error"] == "invalid_client_metadata"
    assert accepted.status_code == 201


async def _login(
    harness: OAuthDCRClientHarness,
) -> tuple[RegisteredClient, dict[str, str]]:
    registered = await harness.register("http://127.0.0.1:4242/callback")
    code, verifier = await harness.authorize_with_pkce(registered)
    response = await harness.exchange_code(registered, code, verifier)
    assert response.status_code == 200
    return registered, response.json()


_MCP_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}
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


def _ping(request_id: int) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "method": "ping"}


@pytest.mark.anyio
async def test_oauth_user_keeps_identity_across_refresh(tmp_path, monkeypatch) -> None:
    """A refreshed token keeps its open MCP session; another login does not.

    The MCP SDK binds transport sessions to the grant's identity, so after a
    refresh the same session keeps answering, while a separate login that
    received the same upstream token gets 404 on it.
    """
    import fastmcp

    issuer = FakeUpstreamIssuer()
    upstream = LocalTLSOAuthIssuer(tmp_path / "upstream", issuer)
    monkeypatch.setenv("SSL_CERT_FILE", str(upstream.ca_certificate_path))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    await upstream.start()
    provider = _build_proxy(upstream.base_url, "https://mcp.test")
    app = fastmcp.FastMCP("refresh-test", auth=provider).http_app(
        path="/mcp", transport="streamable-http"
    )
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="https://mcp.test"
            ) as client,
        ):
            harness = OAuthDCRClientHarness(client, upstream.ca_certificate_path)
            await harness.discover()

            async def upstream_token(token: str) -> str:
                access = await provider.load_access_token(token)
                assert access is not None
                return access.token

            def bearer(token: str) -> dict[str, str]:
                return {**_MCP_HEADERS, "authorization": f"Bearer {token}"}

            registered, tokens = await _login(harness)
            first_upstream = await upstream_token(tokens["access_token"])
            opened = await client.post(
                "/mcp", headers=bearer(tokens["access_token"]), json=_INITIALIZE
            )
            assert opened.status_code == 200
            session = {"mcp-session-id": opened.headers["mcp-session-id"]}

            refresh = {
                "grant_type": "refresh_token",
                "client_id": registered.client_id,
                "refresh_token": tokens["refresh_token"],
            }
            if registered.client_secret:
                refresh["client_secret"] = registered.client_secret
            refreshed = await client.post("/token", data=refresh)
            assert refreshed.status_code == 200
            new_token = refreshed.json()["access_token"]
            new_upstream = await upstream_token(new_token)
            same_session = await client.post(
                "/mcp", headers={**bearer(new_token), **session}, json=_ping(2)
            )

            # Same upstream token string, separate login.
            _, other_tokens = await _login(harness)
            other_upstream = await upstream_token(other_tokens["access_token"])
            other_session = await client.post(
                "/mcp",
                headers={**bearer(other_tokens["access_token"]), **session},
                json=_ping(3),
            )
    finally:
        await upstream.stop()

    assert new_upstream != first_upstream
    assert same_session.status_code == 200
    assert other_upstream == first_upstream
    assert other_session.status_code == 404


class _MappingStoreError(Exception):
    pass


@pytest.mark.anyio
@pytest.mark.parametrize("second_lookup", ["missing", "error"])
async def test_oauth_token_rejected_when_grant_lookup_fails(
    tmp_path, monkeypatch, second_lookup: str
) -> None:
    """A token whose grant cannot be read again is rejected.

    The request must not fall back to a token-based identity, which would
    name a different owner than the one its transport session was bound to.
    """
    from unittest.mock import AsyncMock, MagicMock

    issuer = FakeUpstreamIssuer()
    upstream = LocalTLSOAuthIssuer(tmp_path / "upstream", issuer)
    monkeypatch.setenv("SSL_CERT_FILE", str(upstream.ca_certificate_path))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    await upstream.start()
    provider = _build_proxy(upstream.base_url, "https://mcp.test")
    app = Starlette(routes=provider.get_routes("/mcp"))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://mcp.test"
        ) as client:
            harness = OAuthDCRClientHarness(client, upstream.ca_certificate_path)
            await harness.discover()
            _, tokens = await _login(harness)
            token = tokens["access_token"]
            assert await provider.load_access_token(token) is not None

            real_store = provider._jti_mapping_store
            first = await real_store.get(
                key=provider.jwt_issuer.verify_token(token)["jti"]
            )
            later: object = (
                None if second_lookup == "missing" else _MappingStoreError("store down")
            )
            store = MagicMock(spec_set=["get"])
            store.get = AsyncMock(side_effect=[first, later])
            monkeypatch.setattr(provider, "_jti_mapping_store", store)

            access = await provider.load_access_token(token)
    finally:
        await upstream.stop()

    assert store.get.await_count == 2
    assert access is None


_UPSTREAM = "https://issuer.test"
_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def _authorize_params(**overrides: str) -> dict[str, str]:
    params = {
        "response_type": "code",
        "client_id": "upstream-client-id",
        "redirect_uri": "http://127.0.0.1:4242/callback",
        "state": "x" * 43,
        "code_challenge": _CHALLENGE,
        "code_challenge_method": "S256",
    }
    params.update(overrides)
    return params


@pytest.fixture
def bounded_proxy(tmp_path, monkeypatch) -> tuple[HardenedOAuthProxy, Starlette]:
    import fastmcp

    monkeypatch.setattr(fastmcp.settings, "home", tmp_path)
    provider = _build_proxy(_UPSTREAM, "https://mcp.test")
    return provider, Starlette(routes=provider.get_routes("/mcp"))


@pytest.mark.anyio
@pytest.mark.security_regression
@pytest.mark.parametrize(
    "overrides",
    [
        {"state": "s" * 4096},
        {"redirect_uri": "http://127.0.0.1:4242/" + "p" * 4096},
        {"code_challenge": "c" * 10},
        {"code_challenge": "c" * 4096},
    ],
    ids=["state", "redirect-uri", "short-challenge", "long-challenge"],
)
async def test_authorize_rejects_oversized_fields(bounded_proxy, overrides) -> None:
    """Oversized pre-authentication fields never start an upstream login."""
    _, app = bounded_proxy
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://mcp.test"
    ) as client:
        rejected = await client.post(
            "/authorize", data=_authorize_params(**overrides), follow_redirects=False
        )
        accepted = await client.post(
            "/authorize", data=_authorize_params(), follow_redirects=False
        )

    assert not rejected.headers.get("location", "").startswith(_UPSTREAM)
    assert accepted.headers["location"].startswith(f"{_UPSTREAM}/authorize")


@pytest.mark.anyio
@pytest.mark.security_regression
async def test_authorize_body_is_limited(bounded_proxy) -> None:
    _, app = bounded_proxy
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://mcp.test"
    ) as client:
        response = await client.post(
            "/authorize",
            data={**_authorize_params(), "padding": "p" * (64 * 1024)},
            follow_redirects=False,
        )

    assert response.status_code == 413


@pytest.mark.anyio
@pytest.mark.security_regression
async def test_default_storage_writes_no_pending_login_files(
    bounded_proxy, tmp_path
) -> None:
    """Pending logins do not outlive their TTL as files in the data directory."""
    _, app = bounded_proxy

    def stored_files() -> set[str]:
        return {
            str(p) for p in tmp_path.rglob("*.json") if not p.name.endswith("info.json")
        }

    before = stored_files()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://mcp.test"
    ) as client:
        for _ in range(3):
            response = await client.post(
                "/authorize", data=_authorize_params(), follow_redirects=False
            )
            assert response.headers["location"].startswith(_UPSTREAM)

    assert stored_files() == before


@pytest.fixture
async def lifetime_testbed(tmp_path, monkeypatch):
    """Proxy with its provider exposed, a TLS fake upstream and an ASGI client."""
    import fastmcp

    monkeypatch.setattr(fastmcp.settings, "home", tmp_path / "home")
    issuer = FakeUpstreamIssuer()
    upstream_server = LocalTLSOAuthIssuer(tmp_path / "upstream", issuer)
    monkeypatch.setenv("SSL_CERT_FILE", str(upstream_server.ca_certificate_path))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    await upstream_server.start()
    provider = _build_proxy(upstream_server.base_url, "https://mcp.test")
    app = Starlette(routes=provider.get_routes("/mcp"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://mcp.test"
    ) as client:
        harness = OAuthDCRClientHarness(client, upstream_server.ca_certificate_path)
        yield provider, harness, client
    await upstream_server.stop()


_DAY = 24 * 60 * 60


async def _client_ttl(provider: HardenedOAuthProxy, client_id: str) -> float:
    _, ttl = await provider._client_store.ttl(client_id)
    assert ttl is not None
    return ttl


@pytest.mark.anyio
@pytest.mark.security_regression
async def test_unused_registration_is_short_lived_until_authorized(
    lifetime_testbed,
) -> None:
    provider, harness, _ = lifetime_testbed
    registered = await harness.register("http://127.0.0.1:4242/callback")

    assert await _client_ttl(provider, registered.client_id) <= _DAY

    code, verifier = await harness.authorize_with_pkce(registered)
    response = await harness.exchange_code(registered, code, verifier)
    assert response.status_code == 200

    assert await _client_ttl(provider, registered.client_id) > 89 * _DAY


@pytest.mark.anyio
@pytest.mark.security_regression
async def test_refresh_only_client_keeps_renewing(lifetime_testbed) -> None:
    """A client that only refreshes tokens counts as used and is not cut off."""
    provider, harness, client = lifetime_testbed
    registered = await harness.register("http://127.0.0.1:4242/callback")
    code, verifier = await harness.authorize_with_pkce(registered)
    tokens = (await harness.exchange_code(registered, code, verifier)).json()
    # Pretend the record is near the end of its lifetime.
    stored = await provider._client_store.get(registered.client_id)
    await provider._client_store.put(registered.client_id, stored, ttl=60)

    response = await client.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "client_id": registered.client_id,
            "refresh_token": tokens["refresh_token"],
        },
    )

    assert response.status_code == 200
    assert await _client_ttl(provider, registered.client_id) > 89 * _DAY


@pytest.mark.anyio
@pytest.mark.security_regression
async def test_expiry_keeps_used_clients_and_removed_clients_register_again(
    lifetime_testbed, monkeypatch
) -> None:
    """Only expired records go; a used client outlives an unused one."""
    from mcp_atlassian.servers import oauth_proxy

    provider, harness, client = lifetime_testbed
    used = await harness.register("http://127.0.0.1:4242/callback")
    code, verifier = await harness.authorize_with_pkce(used)
    assert (await harness.exchange_code(used, code, verifier)).status_code == 200
    unused = await harness.register("http://127.0.0.1:4242/cb")

    later = time.time() + 26 * 60 * 60
    monkeypatch.setattr(oauth_proxy, "_now", lambda: later)
    # Another instance on the same storage starts and sweeps.
    other = _build_proxy("https://issuer.test", "https://mcp.test")

    assert await other._client_store.get(used.client_id) is not None
    assert await other._client_store.get(unused.client_id) is None

    # A removed client is told to register again.
    token = await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": unused.client_id,
            "code": "x",
            "redirect_uri": unused.redirect_uri,
            "code_verifier": "v" * 43,
        },
    )
    authorize = await client.get(
        "/authorize",
        params=_authorize_params(client_id=unused.client_id),
        follow_redirects=False,
    )
    assert token.status_code == 401
    assert token.json()["error"] == "invalid_client"
    assert authorize.status_code == 400


def _registration() -> dict[str, object]:
    return {
        "redirect_uris": ["http://127.0.0.1:4242/callback"],
        "token_endpoint_auth_method": "none",
    }


async def _register_on(provider: HardenedOAuthProxy, count: int) -> list[str]:
    app = Starlette(routes=provider.get_routes("/mcp"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://mcp.test"
    ) as client:
        ids = []
        for _ in range(count):
            response = await client.post("/register", json=_registration())
            assert response.status_code == 201
            ids.append(response.json()["client_id"])
    return ids


@pytest.mark.anyio
@pytest.mark.security_regression
async def test_expired_unused_registrations_are_deleted_from_disk(
    tmp_path, monkeypatch
) -> None:
    import fastmcp

    from mcp_atlassian.servers import oauth_proxy

    monkeypatch.setattr(fastmcp.settings, "home", tmp_path)
    old = await _register_on(_build_proxy(_UPSTREAM, "https://mcp.test"), 2)

    def record_files() -> int:
        return sum(
            1
            for p in tmp_path.rglob("*.json")
            if "client" in p.parent.name.lower()
            and "registry" not in p.parent.name
            and not p.name.endswith("info.json")
        )

    assert record_files() == 2
    later = time.time() + 26 * 60 * 60
    monkeypatch.setattr(oauth_proxy, "_now", lambda: later)
    restarted = _build_proxy(_UPSTREAM, "https://mcp.test")
    await _register_on(restarted, 1)

    assert record_files() == 1
    for client_id in old:
        assert await restarted._client_store.get(client_id) is None


@pytest.mark.anyio
@pytest.mark.security_regression
async def test_pending_logins_leave_memory_when_they_expire(monkeypatch) -> None:
    from mcp_atlassian.servers import oauth_proxy

    clock = [time.time()]
    monkeypatch.setattr(oauth_proxy, "_now", lambda: clock[0])
    store = oauth_proxy._TimedMemoryStore(max_entries_per_collection=10)
    await store.put(key="old", value={"v": 1}, collection="c", ttl=60)

    clock[0] += 120  # the old entry's expiry has passed
    await store.put(key="new", value={"v": 2}, collection="c", ttl=15 * 60)

    cache = store._cache["c"]._cache
    assert "old" not in cache
    assert "new" in cache


def test_missing_fastmcp_internals_stop_startup(tmp_path, monkeypatch) -> None:
    import fastmcp
    from fastmcp.server.auth.oauth_proxy import OAuthProxy

    monkeypatch.setattr(fastmcp.settings, "home", tmp_path)
    original = OAuthProxy.__init__

    def without_code_store(self: Any, *args: object, **kwargs: object) -> None:
        original(self, *args, **kwargs)
        del self._code_store

    monkeypatch.setattr(OAuthProxy, "__init__", without_code_store)
    with pytest.raises(RuntimeError, match="_code_store"):
        _build_proxy(_UPSTREAM, "https://mcp.test")


@pytest.mark.anyio
@pytest.mark.security_regression
async def test_recently_expired_records_are_kept_for_an_hour(
    tmp_path, monkeypatch
) -> None:
    """A renewal that read a record just before expiry cannot lose it."""
    import fastmcp

    from mcp_atlassian.servers import oauth_proxy

    monkeypatch.setattr(fastmcp.settings, "home", tmp_path)
    await _register_on(_build_proxy(_UPSTREAM, "https://mcp.test"), 1)

    def record_files() -> int:
        return sum(
            1
            for p in tmp_path.rglob("*.json")
            if "client" in p.parent.name.lower() and not p.name.endswith("info.json")
        )

    assert record_files() == 1
    just_expired = time.time() + 24 * 60 * 60 + 30 * 60
    monkeypatch.setattr(oauth_proxy, "_now", lambda: just_expired)
    _build_proxy(_UPSTREAM, "https://mcp.test")  # start-up sweep

    assert record_files() == 1


@pytest.mark.anyio
@pytest.mark.security_regression
async def test_cleanup_failure_does_not_block_registration(
    tmp_path, monkeypatch
) -> None:
    from pathlib import Path

    import fastmcp

    from mcp_atlassian.servers import oauth_proxy

    monkeypatch.setattr(fastmcp.settings, "home", tmp_path)
    await _register_on(_build_proxy(_UPSTREAM, "https://mcp.test"), 1)
    later = time.time() + 26 * 60 * 60
    monkeypatch.setattr(oauth_proxy, "_now", lambda: later)

    def refuse(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(Path, "unlink", refuse)
    provider = _build_proxy(_UPSTREAM, "https://mcp.test")

    assert len(await _register_on(provider, 1)) == 1
