"""Government credentials must stay on Government OAuth and API endpoints."""

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.servers.dependencies import _create_user_config_for_fetcher
from mcp_atlassian.servers.main import _resolve_upstream_oauth_endpoints
from mcp_atlassian.utils.cloud import COMMERCIAL, GOV_MODERATE, cloud_endpoints
from mcp_atlassian.utils.oauth import OAuthConfig

GOV_URL = "https://example.atlassian-us-gov-mod.net"


def oauth(url: str) -> OAuthConfig:
    """Build an isolated test configuration without real credentials."""
    return OAuthConfig(
        client_id="test-id",
        client_secret="test-secret",
        redirect_uri="https://gateway.example/callback",
        scope="read:jira-work",
        cloud_id="test-cloud",
        service_url=url,
        access_token="test-access",
        refresh_token="test-refresh",
        expires_at=9999999999,
    )


@pytest.mark.parametrize(
    "url,endpoints",
    [
        (GOV_URL, GOV_MODERATE),
        (GOV_URL.upper() + "/wiki", GOV_MODERATE),
        ("https://api.atlassian-us-gov-mod.com", GOV_MODERATE),
        ("https://tenant.atlassian.net", COMMERCIAL),
        ("https://tenant.atlassian-us-gov-mod.net.attacker.example", COMMERCIAL),
    ],
)
def test_endpoint_selection(url: str, endpoints: object) -> None:
    assert cloud_endpoints(url) == endpoints


def test_unknown_government_domain_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unsupported Government"):
        cloud_endpoints("https://tenant.atlassian-us-gov.net")


@pytest.mark.parametrize("url", [GOV_URL, "https://tenant.atlassian.net"])
def test_authorization_and_proxy_endpoints(url: str) -> None:
    config = oauth(url)
    endpoints = cloud_endpoints(url)
    parsed = urlparse(config.get_authorization_url("test-state"))
    query = parse_qs(parsed.query)
    assert parsed.netloc == endpoints.auth_host
    assert query["audience"] == [endpoints.api_host]
    assert query["state"] == ["test-state"]
    assert query["prompt"] == ["consent"]
    assert _resolve_upstream_oauth_endpoints(url) == (
        endpoints.authorize_url,
        endpoints.token_url,
    )


def test_dc_endpoints_unchanged() -> None:
    config = OAuthConfig(
        "id",
        "secret",
        "https://local/callback",
        "READ",
        base_url="https://jira.internal",
    )
    assert config.token_url == "https://jira.internal/rest/oauth2/latest/token"
    assert "audience" not in parse_qs(urlparse(config.get_authorization_url("s")).query)


@pytest.mark.parametrize("operation", ["exchange", "refresh", "discovery"])
def test_government_token_requests(operation: str) -> None:
    config = oauth(GOV_URL)
    response = MagicMock()
    response.json.return_value = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 3600,
    }
    with (
        patch("mcp_atlassian.utils.oauth.requests.post", return_value=response) as post,
        patch("mcp_atlassian.utils.oauth.requests.get", return_value=response) as get,
        patch.object(config, "_save_tokens"),
    ):
        if operation == "exchange":
            assert config.exchange_code_for_tokens("test-code")
            assert post.call_args.args[0] == GOV_MODERATE.token_url
        elif operation == "refresh":
            assert config.refresh_access_token()
            assert post.call_args.args[0] == GOV_MODERATE.token_url
        else:
            response.json.return_value = [{"id": "test-cloud", "url": GOV_URL}]
            config._get_cloud_id()
            assert get.call_args.args[0] == GOV_MODERATE.resources_url


def test_minimal_env_and_per_user_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLASSIAN_OAUTH_ENABLE", "true")
    monkeypatch.setenv("ATLASSIAN_OAUTH_CLOUD_ID", "test-cloud")
    config = OAuthConfig.from_env(service_url=GOV_URL, service_type="jira")
    assert config is not None
    assert config.token_url == GOV_MODERATE.token_url
    base = JiraConfig(url=GOV_URL, auth_type="oauth", oauth_config=config)
    user = _create_user_config_for_fetcher(
        base,
        "oauth",
        {"oauth_access_token": "user-token"},
    )
    assert user.oauth_config is not None
    assert user.oauth_config.service_url == GOV_URL
    assert user.oauth_config.access_token == "user-token"


@pytest.mark.parametrize("service", ["jira", "confluence"])
def test_government_api_client(service: str) -> None:
    config_class = JiraConfig if service == "jira" else ConfluenceConfig
    client_class = JiraClient if service == "jira" else ConfluenceClient
    # Direct callers may construct OAuthConfig without service_url.
    token = oauth("https://tenant.atlassian.net")
    config = config_class(url=GOV_URL, auth_type="oauth", oauth_config=token)
    module = f"mcp_atlassian.{service}.client"
    with (
        patch(f"{module}.{service.title()}") as client,
        patch(f"{module}.configure_oauth_session", return_value=True),
        patch(f"{module}.configure_ssl_verification"),
    ):
        client_class(config=config)
        assert client.call_args.kwargs["url"] == (
            f"{GOV_MODERATE.api_url}/ex/{service}/test-cloud"
        )
        assert token.token_url == GOV_MODERATE.token_url


def test_proxy_build_uses_government_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_atlassian.servers.main import _build_auth_provider

    for key, value in {
        "ATLASSIAN_OAUTH_PROXY_ENABLE": "true",
        "ATLASSIAN_OAUTH_INSTANCE_URL": GOV_URL,
        "ATLASSIAN_OAUTH_CLIENT_ID": "test-id",
        "ATLASSIAN_OAUTH_CLIENT_SECRET": "test-secret",
        "ATLASSIAN_OAUTH_REDIRECT_URI": "https://mcp.example/callback",
    }.items():
        monkeypatch.setenv(key, value)
    with patch("mcp_atlassian.servers.main.HardenedOAuthProxy") as proxy:
        _build_auth_provider()
    config = proxy.call_args.kwargs
    assert config["upstream_authorization_endpoint"] == GOV_MODERATE.authorize_url
    assert config["upstream_token_endpoint"] == GOV_MODERATE.token_url
    assert config["extra_authorize_params"] == {
        "audience": GOV_MODERATE.api_host,
        "prompt": "consent",
    }


def test_government_forms_rejected_before_network() -> None:
    from mcp_atlassian.jira.forms_api import FormsApiMixin

    client = object.__new__(FormsApiMixin)
    client.config = JiraConfig(
        url=GOV_URL, auth_type="oauth", oauth_config=oauth(GOV_URL)
    )
    client._cloud_id = "test-cloud"
    client.jira = MagicMock()
    with pytest.raises(ValueError, match="not supported for Government Cloud"):
        client._make_forms_api_request("GET", "/issue/TEST-1/form")
    assert not client.jira.mock_calls
