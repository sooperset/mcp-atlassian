"""Unit tests for Atlassian opaque token verifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastmcp.server.auth.auth import AccessToken

from mcp_atlassian.utils.token_verifier import AtlassianOpaqueTokenVerifier


@pytest.mark.anyio
async def test_verify_token_returns_fastmcp_access_token() -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        instance_url="https://acme.atlassian.net",
        required_scopes=["read:jira-work"],
    )

    async def _resources(_token: str) -> list[dict]:
        return [
            {
                "id": "cloud-1",
                "url": "https://acme.atlassian.net",
                "scopes": ["read:jira-work", "write:jira-work"],
            }
        ]

    verifier._fetch_accessible_resources = _resources  # type: ignore[method-assign]

    token = await verifier.verify_token("opaque-token")

    assert isinstance(token, AccessToken)
    assert token is not None
    assert token.token == "opaque-token"
    assert "read:jira-work" in token.scopes


@pytest.mark.anyio
async def test_verify_token_caches_successful_validation() -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        instance_url="https://acme.atlassian.net",
        required_scopes=["read:jira-work"],
    )
    fetch_resources = AsyncMock(
        return_value=[
            {
                "id": "cloud-1",
                "url": "https://acme.atlassian.net",
                "scopes": ["read:jira-work"],
            }
        ]
    )
    verifier._fetch_accessible_resources = fetch_resources

    first = await verifier.verify_token("opaque-token")
    second = await verifier.verify_token("opaque-token")

    assert first is second
    assert "opaque-token" not in verifier._token_cache
    fetch_resources.assert_awaited_once_with("opaque-token")

    verifier._token_cache.expire(time=float("inf"))
    third = await verifier.verify_token("opaque-token")

    assert third is not None
    assert fetch_resources.await_count == 2


@pytest.mark.anyio
async def test_verify_token_rejects_unbound_cloud_resource() -> None:
    verifier = AtlassianOpaqueTokenVerifier(required_scopes=["read:jira-work"])

    async def _resources(_token: str) -> list[dict]:
        return [
            {
                "id": "cloud-1",
                "url": "https://acme.atlassian.net",
                "scopes": ["read:jira-work"],
            }
        ]

    verifier._fetch_accessible_resources = _resources  # type: ignore[method-assign]

    token = await verifier.verify_token("opaque-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_rejects_malformed_cloud_resource() -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        instance_url="https://acme.atlassian.net",
        required_scopes=[],
    )
    fetch_resources = AsyncMock(
        return_value=[
            {
                "id": "cloud-1",
                "url": "https://acme.atlassian.net",
            }
        ]
    )
    verifier._fetch_accessible_resources = fetch_resources

    token = await verifier.verify_token("opaque-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_accepts_offline_access_as_non_resource_scope() -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        instance_url="https://acme.atlassian.net",
        required_scopes=["read:jira-work", "offline_access"],
    )

    async def _resources(_token: str) -> list[dict]:
        return [
            {
                "id": "cloud-1",
                "url": "https://acme.atlassian.net",
                "scopes": ["read:jira-work"],
            }
        ]

    verifier._fetch_accessible_resources = _resources  # type: ignore[method-assign]

    token = await verifier.verify_token("opaque-token")

    assert token is not None
    assert token.scopes == ["offline_access", "read:jira-work"]


@pytest.mark.anyio
async def test_verify_token_rejects_resource_from_another_cloud_instance() -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        instance_url="https://expected.atlassian.net/wiki",
        required_scopes=["read:confluence-content.all"],
    )

    async def _resources(_token: str) -> list[dict]:
        return [
            {
                "id": "cloud-1",
                "url": "https://other.atlassian.net",
                "scopes": ["read:confluence-content.all"],
            }
        ]

    verifier._fetch_accessible_resources = _resources  # type: ignore[method-assign]

    token = await verifier.verify_token("opaque-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_returns_none_for_empty_token() -> None:
    verifier = AtlassianOpaqueTokenVerifier(required_scopes=[])

    token = await verifier.verify_token("")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_returns_none_when_required_scope_missing() -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        instance_url="https://acme.atlassian.net",
        required_scopes=["write:jira-work"],
    )

    async def _resources(_token: str) -> list[dict]:
        return [
            {
                "id": "cloud-1",
                "url": "https://acme.atlassian.net",
                "scopes": ["read:jira-work"],
            }
        ]

    verifier._fetch_accessible_resources = _resources  # type: ignore[method-assign]

    token = await verifier.verify_token("opaque-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_returns_none_when_validation_fails() -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        instance_url="https://acme.atlassian.net",
        required_scopes=["read:jira-work"],
    )

    async def _raise(_token: str) -> list[dict]:
        raise ValueError("validation failed")

    verifier._fetch_accessible_resources = _raise  # type: ignore[method-assign]

    token = await verifier.verify_token("opaque-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_validates_against_data_center_instance() -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        instance_url="https://jira.example.com",
        is_cloud=False,
        required_scopes=["READ"],
    )
    validate_dc_token = AsyncMock(return_value=True)
    verifier._validate_dc_token = validate_dc_token

    token = await verifier.verify_token("dc-token")

    assert token is not None
    assert token.scopes == ["READ"]
    validate_dc_token.assert_awaited_once_with("dc-token")


@pytest.mark.anyio
async def test_data_center_validation_tries_jira_then_confluence() -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        instance_url="https://confluence.example.com/confluence",
        is_cloud=False,
    )
    jira_response = httpx.Response(404)
    confluence_response = httpx.Response(
        200,
        json={"type": "known", "username": "alice"},
    )
    client = AsyncMock()
    client.get.side_effect = [jira_response, confluence_response]
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "mcp_atlassian.utils.token_verifier.httpx.AsyncClient",
        return_value=client_context,
    ):
        valid = await verifier._validate_dc_token("dc-token")

    assert valid is True
    assert [call.args[0] for call in client.get.await_args_list] == [
        "https://confluence.example.com/confluence/rest/api/2/myself",
        "https://confluence.example.com/confluence/rest/api/user/current",
    ]


@pytest.mark.anyio
async def test_data_center_validation_rejects_anonymous_user() -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        instance_url="https://confluence.example.com/confluence",
        is_cloud=False,
    )
    client = AsyncMock()
    client.get.side_effect = [
        httpx.Response(404),
        httpx.Response(200, json={"type": "anonymous"}),
    ]
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "mcp_atlassian.utils.token_verifier.httpx.AsyncClient",
        return_value=client_context,
    ):
        valid = await verifier._validate_dc_token("invalid-token")

    assert valid is False


@pytest.mark.anyio
async def test_data_center_validation_rejects_user_type_without_identity() -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        instance_url="https://confluence.example.com/confluence",
        is_cloud=False,
    )
    client = AsyncMock()
    client.get.side_effect = [
        httpx.Response(404),
        httpx.Response(200, json={"type": "known"}),
    ]
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "mcp_atlassian.utils.token_verifier.httpx.AsyncClient",
        return_value=client_context,
    ):
        valid = await verifier._validate_dc_token("invalid-token")

    assert valid is False
