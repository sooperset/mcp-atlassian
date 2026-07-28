"""Hermetic client-facing OAuth DCR and PKCE integration tests."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import get_type_hints

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
