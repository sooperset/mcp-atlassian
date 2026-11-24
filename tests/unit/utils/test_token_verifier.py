"""Unit tests for Atlassian opaque token verifier."""

from __future__ import annotations

from typing import Any

import pytest
import requests
from fastmcp.server.auth.auth import AccessToken

from mcp_atlassian.utils.token_verifier import (
    CLOUD_ACCESSIBLE_RESOURCES_URL,
    AtlassianOpaqueTokenVerifier,
)


@pytest.mark.anyio
async def test_verify_token_returns_fastmcp_access_token() -> None:
    verifier = AtlassianOpaqueTokenVerifier(required_scopes=["read:jira-work"])

    token = await verifier.verify_token("opaque-token")

    assert isinstance(token, AccessToken)
    assert token is not None
    assert token.token == "opaque-token"
    assert token.scopes == ["read:jira-work"]


@pytest.mark.anyio
async def test_verify_token_returns_none_for_empty_token() -> None:
    verifier = AtlassianOpaqueTokenVerifier(required_scopes=[])

    token = await verifier.verify_token("")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_without_cloud_validation_never_calls_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default (validate_cloud_token=False) path must make no network call."""

    def _must_not_call(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "requests.get must not be called without validate_cloud_token"
        )

    monkeypatch.setattr(requests, "get", _must_not_call)
    verifier = AtlassianOpaqueTokenVerifier(required_scopes=["read:jira-work"])

    token = await verifier.verify_token("opaque-token")

    assert token is not None


class _FakeResponse:
    def __init__(
        self, status_code: int, json_body: Any = None, raise_json_error: bool = False
    ) -> None:
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._json_body = json_body
        self._raise_json_error = raise_json_error

    def json(self) -> Any:
        if self._raise_json_error:
            raise ValueError("not json")
        return self._json_body


def _patch_get(
    monkeypatch: pytest.MonkeyPatch, response: Any = None, exc: Any = None
) -> dict:
    calls: dict[str, Any] = {}

    def _fake_get(url: str, *, headers: dict[str, str], timeout: float) -> Any:
        calls["url"] = url
        calls["headers"] = headers
        calls["timeout"] = timeout
        if exc is not None:
            raise exc
        return response

    monkeypatch.setattr(requests, "get", _fake_get)
    return calls


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_accepts_live_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_get(
        monkeypatch, response=_FakeResponse(200, [{"id": "cloud-site-1"}])
    )
    verifier = AtlassianOpaqueTokenVerifier(
        required_scopes=["read:jira-work"], validate_cloud_token=True
    )

    token = await verifier.verify_token("live-token")

    assert token is not None
    assert token.token == "live-token"
    assert calls["url"] == CLOUD_ACCESSIBLE_RESOURCES_URL
    assert calls["headers"]["Authorization"] == "Bearer live-token"


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_rejects_non_2xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get(monkeypatch, response=_FakeResponse(401))
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)

    token = await verifier.verify_token("fabricated-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_rejects_empty_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get(monkeypatch, response=_FakeResponse(200, []))
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)

    token = await verifier.verify_token("fabricated-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_rejects_non_list_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get(monkeypatch, response=_FakeResponse(200, {"not": "a list"}))
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)

    token = await verifier.verify_token("fabricated-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_rejects_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get(monkeypatch, response=_FakeResponse(200, raise_json_error=True))
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)

    token = await verifier.verify_token("fabricated-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_rejects_on_request_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get(monkeypatch, exc=requests.ConnectionError("boom"))
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)

    token = await verifier.verify_token("fabricated-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_still_rejects_empty_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _must_not_call(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("requests.get must not be called for an empty token")

    monkeypatch.setattr(requests, "get", _must_not_call)
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)

    token = await verifier.verify_token("")

    assert token is None
