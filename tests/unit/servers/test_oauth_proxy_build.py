"""Unit tests for OAuth proxy provider construction and hardening."""

from __future__ import annotations

import pytest
from mcp.server.auth.provider import RegistrationError
from mcp.shared.auth import OAuthClientInformationFull

from mcp_atlassian.servers.main import (
    DEFAULT_ALLOWED_REDIRECT_URIS,
    _build_auth_provider,
    _get_allowed_redirect_uris,
)
from mcp_atlassian.utils.oauth import CLOUD_AUTHORIZE_URL, CLOUD_TOKEN_URL


def _set_required_oauth_env(monkeypatch, *, redirect_uri: str) -> None:
    monkeypatch.setenv("ATLASSIAN_OAUTH_PROXY_ENABLE", "true")
    monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("ATLASSIAN_OAUTH_REDIRECT_URI", redirect_uri)


class _DummyProviderStorage:
    def __init__(self, config=None):
        self.factory_config = config

    async def get(self, *args, **kwargs):
        _ = args, kwargs
        return None

    async def put(self, *args, **kwargs):
        _ = args, kwargs
        return None

    async def delete(self, *args, **kwargs):
        _ = args, kwargs
        return True

    async def ttl(self, *args, **kwargs):
        _ = args, kwargs
        return None

    async def get_many(self, *args, **kwargs):
        _ = args, kwargs
        return {}

    async def put_many(self, *args, **kwargs):
        _ = args, kwargs
        return None

    async def delete_many(self, *args, **kwargs):
        _ = args, kwargs
        return 0

    async def ttl_many(self, *args, **kwargs):
        _ = args, kwargs
        return {}


def _dummy_provider_storage_factory(config=None):
    return _DummyProviderStorage(config=config)


def test_build_auth_provider_disabled_by_default(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("ATLASSIAN_OAUTH_REDIRECT_URI", "http://localhost:3000/callback")
    monkeypatch.delenv("ATLASSIAN_OAUTH_PROXY_ENABLE", raising=False)

    provider = _build_auth_provider()

    assert provider is None


def test_build_auth_provider_disabled_when_flag_false(monkeypatch):
    monkeypatch.setenv("ATLASSIAN_OAUTH_PROXY_ENABLE", "false")
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("ATLASSIAN_OAUTH_REDIRECT_URI", "http://localhost:3000/callback")

    provider = _build_auth_provider()

    assert provider is None


def test_build_auth_provider_falls_back_to_jira_url(monkeypatch):
    monkeypatch.delenv("ATLASSIAN_OAUTH_INSTANCE_URL", raising=False)
    monkeypatch.delenv("CONFLUENCE_URL", raising=False)
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(
        monkeypatch, redirect_uri="https://mcp.example.com/mcp-atlassian/callback"
    )

    provider = _build_auth_provider()

    assert provider is not None


def test_build_auth_provider_supports_service_specific_credentials(monkeypatch):
    monkeypatch.setenv("ATLASSIAN_OAUTH_PROXY_ENABLE", "true")
    monkeypatch.delenv("ATLASSIAN_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("ATLASSIAN_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("JIRA_OAUTH_CLIENT_ID", "jira-client-id")
    monkeypatch.setenv("JIRA_OAUTH_CLIENT_SECRET", "jira-client-secret")
    monkeypatch.setenv("ATLASSIAN_OAUTH_REDIRECT_URI", "http://localhost:3000/callback")
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")

    provider = _build_auth_provider()

    assert provider is not None
    assert provider._upstream_client_id == "jira-client-id"
    assert provider._upstream_client_secret.get_secret_value() == "jira-client-secret"


def test_build_auth_provider_uses_cloud_endpoints_for_atlassian_cloud(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://acme.atlassian.net")
    _set_required_oauth_env(monkeypatch, redirect_uri="http://localhost:3000/callback")

    provider = _build_auth_provider()

    assert provider is not None
    assert provider._upstream_authorization_endpoint == CLOUD_AUTHORIZE_URL
    assert provider._upstream_token_endpoint == CLOUD_TOKEN_URL
    assert provider._extra_authorize_params == {
        "audience": "api.atlassian.com",
        "prompt": "consent",
    }


def test_build_auth_provider_uses_dc_endpoints_for_datacenter_url(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(monkeypatch, redirect_uri="http://localhost:3000/callback")

    provider = _build_auth_provider()

    assert provider is not None
    assert (
        provider._upstream_authorization_endpoint
        == "https://jira.example.com/rest/oauth2/latest/authorize"
    )
    assert (
        provider._upstream_token_endpoint
        == "https://jira.example.com/rest/oauth2/latest/token"
    )


def test_build_auth_provider_infers_base_url_from_redirect_uri(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("ATLASSIAN_OAUTH_INSTANCE_URL", raising=False)
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(
        monkeypatch, redirect_uri="https://mcp.example.com/mcp-atlassian/callback"
    )

    provider = _build_auth_provider()

    assert provider is not None
    assert str(provider.base_url) == "https://mcp.example.com/mcp-atlassian"
    assert provider._redirect_path == "/callback"


def test_build_auth_provider_prefers_public_base_url(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://mcp.example.com/mcp-atlassian")
    monkeypatch.delenv("ATLASSIAN_OAUTH_INSTANCE_URL", raising=False)
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(
        monkeypatch, redirect_uri="https://mcp.example.com/mcp-atlassian/callback"
    )

    provider = _build_auth_provider()

    assert provider is not None
    assert str(provider.base_url) == "https://mcp.example.com/mcp-atlassian"
    assert provider._redirect_path == "/callback"


def test_build_auth_provider_supports_root_redirect_uri(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("ATLASSIAN_OAUTH_INSTANCE_URL", raising=False)
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(monkeypatch, redirect_uri="http://localhost:3000/callback")

    provider = _build_auth_provider()

    assert provider is not None
    assert str(provider.base_url).rstrip("/") == "http://localhost:3000"
    assert provider._redirect_path == "/callback"


def test_build_auth_provider_allows_chatgpt_oauth_redirect(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("ATLASSIAN_OAUTH_INSTANCE_URL", raising=False)
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(
        monkeypatch, redirect_uri="https://mcp.example.com/mcp-atlassian/callback"
    )

    provider = _build_auth_provider()

    assert provider is not None
    assert (
        "https://chatgpt.com/connector_platform_oauth_redirect"
        in provider._allowed_client_redirect_uris
    )


def test_build_auth_provider_uses_env_redirect_uris(monkeypatch):
    monkeypatch.setenv(
        "ATLASSIAN_OAUTH_ALLOWED_CLIENT_REDIRECT_URIS", "https://example.com/callback"
    )
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("ATLASSIAN_OAUTH_INSTANCE_URL", raising=False)
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(
        monkeypatch, redirect_uri="https://mcp.example.com/mcp-atlassian/callback"
    )

    provider = _build_auth_provider()

    assert provider is not None
    assert provider._allowed_client_redirect_uris == ["https://example.com/callback"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, DEFAULT_ALLOWED_REDIRECT_URIS),
        ("", []),
        ("   ", []),
        ("*", None),
        (" * ", None),
        ("None", ["None"]),
        (
            "https://client.example/callback,http://localhost:*",
            ["https://client.example/callback", "http://localhost:*"],
        ),
        (
            "*,https://client.example/callback",
            ["*", "https://client.example/callback"],
        ),
        (
            "https://client.example/callback *",
            ["https://client.example/callback", "*"],
        ),
        ("*,*", ["*", "*"]),
        (",*,", ["*"]),
        ("*,", ["*"]),
    ],
)
def test_allowed_redirect_uri_configuration(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: list[str] | None
) -> None:
    if raw is None:
        monkeypatch.delenv(
            "ATLASSIAN_OAUTH_ALLOWED_CLIENT_REDIRECT_URIS", raising=False
        )
    else:
        monkeypatch.setenv("ATLASSIAN_OAUTH_ALLOWED_CLIENT_REDIRECT_URIS", raw)

    assert _get_allowed_redirect_uris() == expected


@pytest.mark.parametrize(
    "raw",
    ["*,https://client.example/callback", "https://client.example/callback *"],
)
@pytest.mark.anyio
async def test_build_auth_provider_preserves_mixed_redirect_lists(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, raw: str
) -> None:
    monkeypatch.setenv("ATLASSIAN_OAUTH_ALLOWED_CLIENT_REDIRECT_URIS", raw)
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(
        monkeypatch, redirect_uri="https://mcp.example.com/mcp-atlassian/callback"
    )
    provider = _build_auth_provider()

    assert provider is not None
    assert provider._allowed_client_redirect_uris is not None
    assert "server-wide redirect URI allowlist" not in caplog.text
    await provider.register_client(
        OAuthClientInformationFull(
            client_id="legacy-client",
            redirect_uris=["https://client.example/callback"],
        )
    )
    with pytest.raises(RegistrationError):
        await provider.register_client(
            OAuthClientInformationFull(
                client_id="disallowed-client",
                redirect_uris=["https://other.example/callback"],
            )
        )


@pytest.mark.anyio
@pytest.mark.parametrize("open_dcr", [False, True])
async def test_build_auth_provider_registers_remote_clients_only_when_allowed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, open_dcr: bool
) -> None:
    monkeypatch.delenv("ATLASSIAN_OAUTH_ALLOWED_CLIENT_REDIRECT_URIS", raising=False)
    monkeypatch.delenv("ATLASSIAN_OAUTH_REQUIRE_CONSENT", raising=False)
    if open_dcr:
        monkeypatch.setenv("ATLASSIAN_OAUTH_ALLOWED_CLIENT_REDIRECT_URIS", "*")
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(
        monkeypatch, redirect_uri="https://mcp.example.com/mcp-atlassian/callback"
    )
    provider = _build_auth_provider()
    assert provider is not None
    assert provider._require_authorization_consent is True
    client = OAuthClientInformationFull(
        client_id="remote-client",
        redirect_uris=[
            "https://www.cursor.com/agents/mcp/oauth/callback",
            "http://localhost:8787/callback",
            "cursor://anysphere.cursor-mcp/oauth/callback",
        ],
    )

    if open_dcr:
        assert provider._allowed_client_redirect_uris is None
        await provider.register_client(client)
        stored = await provider._client_store.get(key="remote-client")
        assert stored is not None
        assert stored.redirect_uris == client.redirect_uris
        assert "server-wide redirect URI allowlist" in caplog.text
    else:
        with pytest.raises(RegistrationError):
            await provider.register_client(client)


def test_build_auth_provider_can_disable_consent(monkeypatch):
    monkeypatch.setenv("ATLASSIAN_OAUTH_REQUIRE_CONSENT", "false")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("ATLASSIAN_OAUTH_INSTANCE_URL", raising=False)
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(
        monkeypatch, redirect_uri="https://mcp.example.com/mcp-atlassian/callback"
    )

    provider = _build_auth_provider()

    assert provider is not None
    assert provider._require_authorization_consent is False


def test_build_auth_provider_exposes_discovery_and_dcr_routes(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(monkeypatch, redirect_uri="http://localhost:3000/callback")

    provider = _build_auth_provider()

    assert provider is not None
    route_paths = {route.path for route in provider.get_routes("/mcp")}
    assert "/authorize" in route_paths
    assert "/token" in route_paths
    assert "/register" in route_paths
    assert "/.well-known/oauth-authorization-server" in route_paths
    assert "/.well-known/oauth-protected-resource/mcp" in route_paths
    assert "/callback" in route_paths


def test_build_auth_provider_supports_custom_client_storage_factory(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(monkeypatch, redirect_uri="http://localhost:3000/callback")
    monkeypatch.setenv("ATLASSIAN_OAUTH_CLIENT_STORAGE_MODE", "factory")
    monkeypatch.setenv(
        "ATLASSIAN_OAUTH_CLIENT_STORAGE_FACTORY",
        "tests.unit.servers.test_oauth_proxy_build:_dummy_provider_storage_factory",
    )
    monkeypatch.setenv(
        "ATLASSIAN_OAUTH_CLIENT_STORAGE_CONFIG_JSON", '{"collection":"registrations"}'
    )

    provider = _build_auth_provider()

    assert provider is not None
    assert provider._client_storage is not None
    assert provider._client_storage.__class__.__name__ == "_DummyProviderStorage"
    assert callable(getattr(provider._client_storage, "get", None))
    assert callable(getattr(provider._client_storage, "put", None))
    assert callable(getattr(provider._client_storage, "delete", None))
    assert callable(getattr(provider._client_storage, "ttl", None))
    assert callable(getattr(provider._client_storage, "get_many", None))
    assert callable(getattr(provider._client_storage, "put_many", None))
    assert callable(getattr(provider._client_storage, "delete_many", None))
    assert callable(getattr(provider._client_storage, "ttl_many", None))
    assert provider._client_storage.factory_config == {"collection": "registrations"}


@pytest.mark.anyio
async def test_register_client_hardens_grant_types_and_scopes(monkeypatch):
    monkeypatch.setenv("ATLASSIAN_OAUTH_SCOPE", "read:jira-work")
    monkeypatch.setenv("ATLASSIAN_OAUTH_ALLOWED_GRANT_TYPES", "authorization_code")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("ATLASSIAN_OAUTH_INSTANCE_URL", raising=False)
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    _set_required_oauth_env(
        monkeypatch, redirect_uri="https://mcp.example.com/mcp-atlassian/callback"
    )

    provider = _build_auth_provider()

    assert provider is not None
    client = OAuthClientInformationFull(
        client_id="client-123",
        client_secret="secret",
        redirect_uris=["http://localhost:1234/callback"],
        grant_types=[
            "refresh_token",
            "authorization_code",
            "urn:ietf:params:oauth:grant-type:jwt-bearer",
        ],
        scope="read:jira-work write:jira-work",
    )

    await provider.register_client(client)
    stored = await provider._client_store.get(key="client-123")

    assert stored is not None
    assert stored.grant_types == ["authorization_code"]
    assert stored.scope == "read:jira-work"
