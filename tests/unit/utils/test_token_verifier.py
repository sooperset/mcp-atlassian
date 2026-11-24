"""Unit tests for Atlassian opaque token verifier."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
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
async def test_verify_token_without_cloud_validation_never_calls_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default (validate_cloud_token=False) path must make no network call."""
    verifier = AtlassianOpaqueTokenVerifier(required_scopes=["read:jira-work"])

    async def _must_not_call(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "client.get must not be called without validate_cloud_token"
        )

    monkeypatch.setattr(verifier._client, "get", _must_not_call)

    token = await verifier.verify_token("opaque-token")

    assert token is not None


class _FakeResponse:
    def __init__(
        self, status_code: int, json_body: Any = None, raise_json_error: bool = False
    ) -> None:
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self._json_body = json_body
        self._raise_json_error = raise_json_error

    def json(self) -> Any:
        if self._raise_json_error:
            raise ValueError("not json")
        return self._json_body


def _patch_get(
    verifier: AtlassianOpaqueTokenVerifier,
    monkeypatch: pytest.MonkeyPatch,
    response: Any = None,
    exc: Any = None,
) -> dict:
    """Patch the verifier's own async client, not a module-level function.

    verify_token reuses one httpx.AsyncClient per verifier instance (real
    connection pooling, no thread pool), so that is what must be patched to
    intercept the outbound request.
    """
    calls: dict[str, Any] = {"count": 0}

    async def _fake_get(url: str, *, headers: dict[str, str]) -> Any:
        calls["count"] += 1
        calls["url"] = url
        calls["headers"] = headers
        if exc is not None:
            raise exc
        return response

    monkeypatch.setattr(verifier._client, "get", _fake_get)
    return calls


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_accepts_live_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        required_scopes=["read:jira-work"], validate_cloud_token=True
    )
    calls = _patch_get(
        verifier, monkeypatch, response=_FakeResponse(200, [{"id": "cloud-site-1"}])
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
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)
    _patch_get(verifier, monkeypatch, response=_FakeResponse(401))

    token = await verifier.verify_token("fabricated-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_rejects_empty_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)
    _patch_get(verifier, monkeypatch, response=_FakeResponse(200, []))

    token = await verifier.verify_token("fabricated-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_rejects_non_list_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)
    _patch_get(verifier, monkeypatch, response=_FakeResponse(200, {"not": "a list"}))

    token = await verifier.verify_token("fabricated-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_rejects_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)
    _patch_get(
        verifier, monkeypatch, response=_FakeResponse(200, raise_json_error=True)
    )

    token = await verifier.verify_token("fabricated-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_rejects_on_request_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)
    _patch_get(verifier, monkeypatch, exc=httpx.ConnectError("boom"))

    token = await verifier.verify_token("fabricated-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_with_cloud_validation_still_rejects_empty_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)

    async def _must_not_call(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("client.get must not be called for an empty token")

    monkeypatch.setattr(verifier._client, "get", _must_not_call)

    token = await verifier.verify_token("")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_caches_a_live_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repeated call with the same token within the TTL must not re-query Atlassian.

    verify_token runs on every request through load_access_token, not just at
    login, so an uncached check would call Atlassian's API on every tool call.
    """
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)
    calls = _patch_get(
        verifier, monkeypatch, response=_FakeResponse(200, [{"id": "cloud-site-1"}])
    )

    first = await verifier.verify_token("live-token")
    second = await verifier.verify_token("live-token")

    assert first is not None
    assert second is not None
    assert calls["count"] == 1


@pytest.mark.anyio
async def test_verify_token_does_not_cache_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed check must be retried on the next call, not cached as rejected.

    Otherwise a transient Atlassian-side error (a timeout, a 5xx) would lock
    out an otherwise-valid token for the whole cache window.
    """
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)
    calls = _patch_get(verifier, monkeypatch, response=_FakeResponse(503))

    first = await verifier.verify_token("live-token")
    second = await verifier.verify_token("live-token")

    assert first is None
    assert second is None
    assert calls["count"] == 2


@pytest.mark.anyio
async def test_verify_token_cache_is_per_token(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)
    calls = _patch_get(
        verifier, monkeypatch, response=_FakeResponse(200, [{"id": "cloud-site-1"}])
    )

    await verifier.verify_token("token-a")
    await verifier.verify_token("token-b")
    await verifier.verify_token("token-a")

    assert calls["count"] == 2


@pytest.mark.anyio
async def test_verify_token_clears_cookies_after_each_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shared client's cookie jar must not carry state between callers.

    One verifier instance's client is reused across every token it checks;
    a cookie picked up for one caller must never be sent back on a later,
    unrelated caller's request.
    """
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)
    _patch_get(
        verifier, monkeypatch, response=_FakeResponse(200, [{"id": "cloud-site-1"}])
    )
    verifier._client.cookies.set("session", "leftover-from-another-user")

    await verifier.verify_token("live-token")

    assert len(verifier._client.cookies) == 0


@pytest.mark.anyio
async def test_verify_token_binds_to_configured_cloud_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live token for an unrelated Atlassian Cloud site must be rejected
    when the verifier is bound to a specific instance."""
    verifier = AtlassianOpaqueTokenVerifier(
        validate_cloud_token=True, cloud_site_hostname="mycompany.atlassian.net"
    )
    _patch_get(
        verifier,
        monkeypatch,
        response=_FakeResponse(
            200,
            [
                {
                    "id": "other-site",
                    "url": "https://someone-elses-site.atlassian.net",
                }
            ],
        ),
    )

    token = await verifier.verify_token("someone-elses-live-token")

    assert token is None


@pytest.mark.anyio
async def test_verify_token_accepts_matching_cloud_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        validate_cloud_token=True, cloud_site_hostname="mycompany.atlassian.net"
    )
    _patch_get(
        verifier,
        monkeypatch,
        response=_FakeResponse(
            200,
            [
                {"id": "unrelated", "url": "https://someone-elses-site.atlassian.net"},
                {"id": "this-one", "url": "https://mycompany.atlassian.net"},
            ],
        ),
    )

    token = await verifier.verify_token("live-token")

    assert token is not None


@pytest.mark.anyio
async def test_verify_token_without_site_binding_accepts_any_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no cloud_site_hostname configured, any accessible resource passes
    (the pre-existing, less strict behavior) — documented, not silently
    stricter than what callers that omit the argument asked for."""
    verifier = AtlassianOpaqueTokenVerifier(validate_cloud_token=True)
    _patch_get(
        verifier,
        monkeypatch,
        response=_FakeResponse(
            200,
            [{"id": "other-site", "url": "https://someone-elses-site.atlassian.net"}],
        ),
    )

    token = await verifier.verify_token("some-live-token")

    assert token is not None


@pytest.mark.parametrize(
    "gateway_hostname",
    ["auth.atlassian.com", "api.atlassian.com", "AUTH.ATLASSIAN.COM"],
)
def test_generic_cloud_gateway_hostname_is_not_bound(gateway_hostname: str) -> None:
    """Binding to Atlassian's own gateway host would reject every live token:
    accessible-resources never returns a resource hosted at either gateway,
    only at a tenant's own *.atlassian.net site."""
    verifier = AtlassianOpaqueTokenVerifier(
        validate_cloud_token=True, cloud_site_hostname=gateway_hostname
    )

    assert verifier._cloud_site_hostname is None


@pytest.mark.anyio
async def test_verify_token_with_gateway_hostname_still_accepts_any_live_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = AtlassianOpaqueTokenVerifier(
        validate_cloud_token=True, cloud_site_hostname="auth.atlassian.com"
    )
    _patch_get(
        verifier,
        monkeypatch,
        response=_FakeResponse(
            200, [{"id": "any-site", "url": "https://mycompany.atlassian.net"}]
        ),
    )

    token = await verifier.verify_token("live-token")

    assert token is not None
