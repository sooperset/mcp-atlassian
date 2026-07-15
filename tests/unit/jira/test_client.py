"""Tests for the Jira client module."""

import os
from copy import deepcopy
from typing import Literal
from unittest.mock import MagicMock, call, patch

import pytest
from requests.sessions import Session

from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.ssl import NoProxyAdapter


class DeepcopyMock(MagicMock):
    """A Mock that creates a deep copy of its arguments before storing them."""

    def __call__(self, /, *args, **kwargs):
        args = deepcopy(args)
        kwargs = deepcopy(kwargs)
        return super().__call__(*args, **kwargs)


def test_init_with_basic_auth():
    """Test initializing the client with basic auth configuration."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch(
            "mcp_atlassian.jira.client.configure_ssl_verification"
        ) as mock_configure_ssl,
    ):
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="basic",
            username="test_username",
            api_token="test_token",
        )

        client = JiraClient(config=config)

        # Verify Jira was initialized correctly
        mock_jira.assert_called_once_with(
            url="https://test.atlassian.net",
            username="test_username",
            password="test_token",
            cloud=True,
            verify_ssl=True,
            timeout=75,
        )

        # Verify SSL verification was configured
        mock_configure_ssl.assert_called_once_with(
            service_name="Jira",
            url="https://test.atlassian.net",
            session=mock_jira.return_value._session,
            ssl_verify=True,
            client_cert=None,
            client_key=None,
            client_key_password=None,
            no_proxy=None,
        )

        assert client.config == config
        assert client._field_ids_cache is None
        assert client._current_user_account_id is None


@pytest.mark.security_regression
def test_base_session_has_ssrf_redirect_hook():
    """Every fetcher's underlying session must validate redirects for SSRF, not
    only the per-user HTTP path. Direct ``self.jira._session.get()`` calls (e.g.
    jira/development.py, jira/users.py) and global/stdio fetchers previously
    followed redirects unhooked. Closes GHSA-v9m3-wfh8-5646, GHSA-5wf4-jqxh-8gm3.
    """
    import requests

    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        mock_jira.return_value._session = requests.Session()
        client = JiraClient(
            config=JiraConfig(
                url="https://test.atlassian.net",
                auth_type="basic",
                username="u",
                api_token="t",
            )
        )

    hooks = client.jira._session.hooks["response"]
    assert len(hooks) > 0, "base session must carry an SSRF redirect hook"

    # The hook must actually block a redirect to an internal/metadata host.
    internal_redirect = MagicMock()
    internal_redirect.is_redirect = True
    internal_redirect.url = "https://test.atlassian.net/start"
    internal_redirect.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
    with pytest.raises(ValueError, match="SSRF"):
        for hook in hooks:
            hook(internal_redirect)

    # And the base session must use the DNS-pinning adapter (rebind protection).
    from mcp_atlassian.utils.ssrf_adapter import SsrfPinningAdapter

    assert isinstance(
        client.jira._session.get_adapter("https://example.atlassian.net"),
        SsrfPinningAdapter,
    ), "base session must mount the SSRF DNS-pinning adapter for https"


@pytest.mark.security_regression
def test_http_hardening_survives_ssrf_pinning_mount(monkeypatch):
    """The opt-in HTTP hardening wrappers patch ``adapter.send`` in place, so
    they must be applied AFTER ``mount_ssrf_pinning`` replaces the generic
    http/https adapters — otherwise the pinning mount silently drops the
    concurrency/rate-limit/circuit-breaker wrappers (retries survive via the
    max_retries carry-over, the send wrappers do not).
    """
    import requests

    from mcp_atlassian.utils.http import (
        _reset_concurrency_semaphore_for_tests,
        _reset_rate_limit_bucket_for_tests,
    )
    from mcp_atlassian.utils.ssrf_adapter import SsrfPinningAdapter

    monkeypatch.setenv("ATLASSIAN_MAX_CONCURRENT_REQUESTS", "2")
    _reset_concurrency_semaphore_for_tests()
    try:
        with (
            patch("mcp_atlassian.jira.client.Jira") as mock_jira,
            patch("mcp_atlassian.jira.client.configure_ssl_verification"),
        ):
            mock_jira.return_value._session = requests.Session()
            client = JiraClient(
                config=JiraConfig(
                    url="https://test.atlassian.net",
                    auth_type="basic",
                    username="u",
                    api_token="t",
                )
            )

        adapter = client.jira._session.get_adapter("https://example.atlassian.net")
        assert isinstance(adapter, SsrfPinningAdapter)
        assert getattr(adapter, "_mcp_atlassian_throttled", False), (
            "concurrency wrapper must be present on the pinning adapter — "
            "hardening was applied before mount_ssrf_pinning replaced it"
        )
    finally:
        _reset_concurrency_semaphore_for_tests()
        _reset_rate_limit_bucket_for_tests()


def test_init_with_token_auth():
    """Test initializing the client with token auth configuration."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch(
            "mcp_atlassian.jira.client.configure_ssl_verification"
        ) as mock_configure_ssl,
    ):
        config = JiraConfig(
            url="https://jira.example.com",
            auth_type="pat",
            personal_token="test_personal_token",
            ssl_verify=False,
        )

        client = JiraClient(config=config)

        # Verify Jira was initialized correctly
        mock_jira.assert_called_once_with(
            url="https://jira.example.com",
            token="test_personal_token",
            cloud=False,
            verify_ssl=False,
            timeout=75,
        )

        # Verify SSL verification was configured with ssl_verify=False
        mock_configure_ssl.assert_called_once_with(
            service_name="Jira",
            url="https://jira.example.com",
            session=mock_jira.return_value._session,
            ssl_verify=False,
            client_cert=None,
            client_key=None,
            client_key_password=None,
            no_proxy=None,
        )

        assert client.config == config


def test_init_from_env():
    """Test initializing the client from environment variables."""
    with (
        patch("mcp_atlassian.jira.config.JiraConfig.from_env") as mock_from_env,
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        mock_config = MagicMock()
        mock_config.auth_type = "basic"  # needed for the if condition
        mock_from_env.return_value = mock_config

        client = JiraClient()

        mock_from_env.assert_called_once()
        assert client.config == mock_config


def test_clean_text():
    """Test the _clean_text method."""
    with (
        patch("mcp_atlassian.jira.client.Jira"),
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        client = JiraClient(
            config=JiraConfig(
                url="https://test.atlassian.net",
                auth_type="basic",
                username="test_username",
                api_token="test_token",
            )
        )

        # Test with HTML
        assert client._clean_text("<p>Test content</p>") == "Test content"

        # Test with empty string
        assert client._clean_text("") == ""

        # Test with spaces and newlines
        assert client._clean_text("  \n  Test with spaces  \n  ") == "Test with spaces"


def _test_get_paged(method: Literal["get", "post"]):
    """Test the get_paged method."""
    with (
        patch(
            "mcp_atlassian.jira.client.Jira.get", new_callable=DeepcopyMock
        ) as mock_get,
        patch(
            "mcp_atlassian.jira.client.Jira.post", new_callable=DeepcopyMock
        ) as mock_post,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="basic",
            username="test_username",
            api_token="test_token",
        )
        client = JiraClient(config=config)

        # Mock paged responses
        mock_responses = [
            {"data": "page1", "nextPageToken": "token1"},
            {"data": "page2", "nextPageToken": "token2"},
            {"data": "page3"},  # Last page does not have nextPageToken
        ]

        # Create mock method with side effect to return responses in sequence
        if method == "get":
            mock_get.side_effect = mock_responses
            mock_post.side_effect = RuntimeError("This should not be called")
        else:
            mock_post.side_effect = mock_responses
            mock_get.side_effect = RuntimeError("This should not be called")

        # Run the method
        params = {"initial": "params"}
        results = client.get_paged(method, "/test/url", params)

        # Verify the results
        assert results == mock_responses

        # Verify call parameters
        if method == "get":
            expected_calls = [
                call(path="/test/url", params={"initial": "params"}, absolute=False),
                call(
                    path="/test/url",
                    params={"initial": "params", "nextPageToken": "token1"},
                    absolute=False,
                ),
                call(
                    path="/test/url",
                    params={"initial": "params", "nextPageToken": "token2"},
                    absolute=False,
                ),
            ]
            assert mock_get.call_args_list == expected_calls
        else:
            expected_calls = [
                call(path="/test/url", json={"initial": "params"}, absolute=False),
                call(
                    path="/test/url",
                    json={"initial": "params", "nextPageToken": "token1"},
                    absolute=False,
                ),
                call(
                    path="/test/url",
                    json={"initial": "params", "nextPageToken": "token2"},
                    absolute=False,
                ),
            ]
            assert mock_post.call_args_list == expected_calls


def test_get_paged_get():
    """Test the get_paged method for GET requests."""
    _test_get_paged("get")


def test_get_paged_post():
    """Test the get_paged method for POST requests."""
    _test_get_paged("post")


def test_get_paged_without_cloud():
    """Test the get_paged method without cloud."""
    with patch("mcp_atlassian.jira.client.configure_ssl_verification"):
        config = JiraConfig(
            url="https://jira.example.com",
            auth_type="pat",
            personal_token="test_token",
        )
        client = JiraClient(config=config)
        with pytest.raises(
            ValueError,
            match="Paged requests are only available for Jira Cloud platform",
        ):
            client.get_paged("get", "/test/url")


def test_init_sets_proxies_and_no_proxy(monkeypatch):
    """Test that JiraClient sets session proxies and NO_PROXY env var from config."""
    # Patch Jira and its _session
    mock_jira = MagicMock()
    mock_session = MagicMock()
    mock_session.proxies = {}  # Use a real dict for proxies
    mock_jira._session = mock_session
    monkeypatch.setattr("mcp_atlassian.jira.client.Jira", lambda **kwargs: mock_jira)
    monkeypatch.setattr(
        "mcp_atlassian.jira.client.configure_ssl_verification", lambda **kwargs: None
    )

    # Patch environment
    monkeypatch.setenv("NO_PROXY", "")

    config = JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="user",
        api_token="pat",
        http_proxy="http://proxy:8080",
        https_proxy="https://proxy:8443",
        socks_proxy="socks5://user:pass@proxy:1080",
        no_proxy="localhost,127.0.0.1",
    )
    client = JiraClient(config=config)
    assert mock_session.proxies["http"] == "http://proxy:8080"
    assert mock_session.proxies["https"] == "https://proxy:8443"
    assert mock_session.proxies["socks"] == "socks5://user:pass@proxy:1080"
    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1"


def test_init_configures_no_proxy_adapter_from_config(monkeypatch):
    """Test that client no_proxy config is visible during SSL setup."""
    mock_jira = MagicMock()
    mock_jira._session = Session()
    monkeypatch.setattr("mcp_atlassian.jira.client.Jira", lambda **kwargs: mock_jira)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

    config = JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="user",
        api_token="pat",
        http_proxy="http://proxy:8080",
        no_proxy="test.atlassian.net",
    )

    JiraClient(config=config)

    assert os.environ["NO_PROXY"] == "test.atlassian.net"
    assert mock_jira._session.proxies["http"] == "http://proxy:8080"
    assert isinstance(
        mock_jira._session.get_adapter("https://test.atlassian.net"),
        NoProxyAdapter,
    )


def test_init_no_proxies(monkeypatch):
    """Test that JiraClient does not set proxies if not configured."""
    # Patch Jira and its _session
    mock_jira = MagicMock()
    mock_session = MagicMock()
    mock_session.proxies = {}  # Use a real dict for proxies
    mock_jira._session = mock_session
    monkeypatch.setattr("mcp_atlassian.jira.client.Jira", lambda **kwargs: mock_jira)
    monkeypatch.setattr(
        "mcp_atlassian.jira.client.configure_ssl_verification", lambda **kwargs: None
    )

    config = JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="user",
        api_token="pat",
    )
    client = JiraClient(config=config)
    assert mock_session.proxies == {}


def test_jira_client_passes_timeout_to_constructor():
    """Test that JiraClient passes custom timeout to Jira constructor."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="basic",
            username="test_user",
            api_token="test_token",
            timeout=120,
        )
        JiraClient(config=config)

        mock_jira.assert_called_once_with(
            url="https://test.atlassian.net",
            username="test_user",
            password="test_token",
            cloud=True,
            verify_ssl=True,
            timeout=120,
        )


def test_jira_client_pat_disables_trust_env():
    """Test that PAT auth disables trust_env to prevent .netrc override (#860)."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        mock_session = MagicMock()
        mock_session.trust_env = True  # Default
        mock_jira.return_value._session = mock_session

        config = JiraConfig(
            url="https://jira.example.com",
            auth_type="pat",
            personal_token="test_pat",
        )
        JiraClient(config=config)

        assert mock_session.trust_env is False


def test_jira_client_oauth_disables_trust_env():
    """Test that OAuth auth disables trust_env to prevent .netrc override (#860)."""
    from mcp_atlassian.utils.oauth import OAuthConfig

    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
        patch("mcp_atlassian.jira.client.configure_oauth_session", return_value=True),
    ):
        mock_session = MagicMock()
        mock_session.trust_env = True
        mock_jira.return_value._session = mock_session

        oauth_cfg = OAuthConfig(
            client_id="cid",
            client_secret="cs",
            redirect_uri="http://localhost",
            scope="read",
            cloud_id="cloud-123",
            access_token="token",
        )
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="oauth",
            oauth_config=oauth_cfg,
        )
        JiraClient(config=config)

        # The OAuth session is created manually, but after Jira client init
        # trust_env should be disabled on the Jira client's session
        assert mock_jira.return_value._session.trust_env is False


def test_jira_client_basic_auth_preserves_trust_env():
    """Test that basic auth preserves trust_env (netrc valid for basic auth)."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        mock_session = MagicMock()
        mock_session.trust_env = True
        mock_jira.return_value._session = mock_session

        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="basic",
            username="user",
            api_token="token",
        )
        JiraClient(config=config)

        assert mock_session.trust_env is True


# ---------------------------------------------------------------------------
# mTLS client certificate auth tests
# ---------------------------------------------------------------------------


def test_init_cert_auth() -> None:
    """Test that cert auth initializes without credentials and disables trust_env."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch(
            "mcp_atlassian.jira.client.configure_ssl_verification"
        ) as mock_configure_ssl,
    ):
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_jira.return_value._session = mock_session

        config = JiraConfig(
            url="https://jira.example.com",
            auth_type="cert",
            client_cert="/path/to/cert.pem",
        )

        JiraClient(config=config)

        mock_jira.assert_called_once_with(
            url="https://jira.example.com",
            cloud=False,
            verify_ssl=True,
            timeout=75,
        )
        assert mock_session.trust_env is False
        mock_configure_ssl.assert_called_once_with(
            service_name="Jira",
            url="https://jira.example.com",
            session=mock_session,
            ssl_verify=True,
            client_cert="/path/to/cert.pem",
            client_key=None,
            client_key_password=None,
            no_proxy=None,
        )


def test_jira_client_sets_default_user_agent() -> None:
    """An explicit User-Agent is set so WAFs don't block the requests default."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        headers: dict[str, str] = {}
        mock_jira.return_value._session.headers = headers

        config = JiraConfig(
            url="https://jira.example.com",
            auth_type="pat",
            personal_token="pat",
        )
        JiraClient(config=config)

        assert headers["User-Agent"].startswith("mcp-atlassian/")


def test_jira_client_custom_user_agent_overrides_default() -> None:
    """Custom headers must still win over the built-in User-Agent default."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        headers: dict[str, str] = {}
        mock_jira.return_value._session.headers = headers

        config = JiraConfig(
            url="https://jira.example.com",
            auth_type="pat",
            personal_token="pat",
            custom_headers={"User-Agent": "my-app/1.0"},
        )
        JiraClient(config=config)

        assert headers["User-Agent"] == "my-app/1.0"


@pytest.mark.parametrize(
    "url",
    [
        "https://test.atlassian.net",
        "https://jira.example.com",
    ],
    ids=["cloud", "server_dc"],
)
def test_create_version_uses_rest_v2_endpoint(url: str) -> None:
    """Test that create_version uses the REST v2 endpoint on all Jira platforms."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        mock_jira.return_value._session.headers = {}
        mock_jira.return_value.post.return_value = {"id": "100", "name": "v1.0"}

        config = JiraConfig(url=url, auth_type="pat", personal_token="test_token")
        client = JiraClient(config=config)
        client.create_version(project="PROJ", name="v1.0")

        mock_jira.return_value.resource_url.assert_not_called()
        mock_jira.return_value.post.assert_called_once_with(
            "/rest/api/2/version", json={"project": "PROJ", "name": "v1.0"}
        )


def test_update_version_sends_only_provided_fields() -> None:
    """Test that update_version sends only fields explicitly provided."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        mock_response = {"id": "10001", "name": "v2.0", "archived": False}
        mock_jira.return_value.put.return_value = mock_response

        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="pat",
            personal_token="test_token",
        )
        client = JiraClient(config=config)
        result = client.update_version("10001", name="v2.0", archived=False)

        assert result == mock_response
        mock_jira.return_value.put.assert_called_once_with(
            "/rest/api/2/version/10001",
            data={"name": "v2.0", "archived": False},
        )


def test_update_version_requires_at_least_one_field() -> None:
    """Test that update_version rejects empty update payloads."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="pat",
            personal_token="test_token",
        )
        client = JiraClient(config=config)

        with pytest.raises(ValueError, match="requires at least one field"):
            client.update_version("10001")

        mock_jira.return_value.put.assert_not_called()


def test_update_version_rejects_non_dict_response() -> None:
    """Test that update_version rejects unexpected Jira responses."""
    with (
        patch("mcp_atlassian.jira.client.Jira") as mock_jira,
        patch("mcp_atlassian.jira.client.configure_ssl_verification"),
    ):
        mock_jira.return_value.put.return_value = ["not", "a", "dict"]

        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="pat",
            personal_token="test_token",
        )
        client = JiraClient(config=config)

        with pytest.raises(ValueError, match="Unexpected response from Jira API"):
            client.update_version("10001", released=True)
