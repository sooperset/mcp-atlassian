"""
Unit tests for proxy handling in Jira and Confluence clients (mocked requests).
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from pypac import get_pac
from pypac.parser import MalformedPacError
from requests import PreparedRequest, Session
from requests.adapters import HTTPAdapter
from requests.exceptions import ProxyError

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.utils.proxy import (
    DEFAULT_PROXY_WPAD_URL,
    _load_pac_file,
    _NoProxyAwarePACSession,
    apply_proxy_configuration,
    get_proxy_settings_from_env,
)
from mcp_atlassian.utils.ssl import NoProxyAdapter, configure_proxy_bypass
from tests.utils.base import BaseAuthTest
from tests.utils.mocks import MockEnvironment


def test_jira_client_passes_proxies_to_requests(monkeypatch):
    """Test that JiraClient passes proxies to requests.Session.request."""
    mock_jira = MagicMock()
    mock_session = MagicMock()
    # Create a proper proxies dictionary that can be updated
    mock_session.proxies = {}
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
        http_proxy="http://proxy:8080",
        https_proxy="https://proxy:8443",
        socks_proxy="socks5://user:pass@proxy:1080",
        no_proxy="localhost,127.0.0.1",
    )
    client = JiraClient(config=config)
    # Simulate a request
    client.jira._session.request(
        "GET", "https://test.atlassian.net/rest/api/2/issue/TEST-1"
    )
    assert mock_session.proxies["http"] == "http://proxy:8080"
    assert mock_session.proxies["https"] == "https://proxy:8443"
    assert mock_session.proxies["socks"] == "socks5://user:pass@proxy:1080"


def test_confluence_client_passes_proxies_to_requests(monkeypatch):
    """Test that ConfluenceClient passes proxies to requests.Session.request."""
    mock_confluence = MagicMock()
    mock_session = MagicMock()
    # Create a proper proxies dictionary that can be updated
    mock_session.proxies = {}
    mock_confluence._session = mock_session
    monkeypatch.setattr(
        "mcp_atlassian.confluence.client.Confluence", lambda **kwargs: mock_confluence
    )
    monkeypatch.setattr(
        "mcp_atlassian.confluence.client.configure_ssl_verification",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "mcp_atlassian.preprocessing.confluence.ConfluencePreprocessor",
        lambda **kwargs: MagicMock(),
    )
    config = ConfluenceConfig(
        url="https://test.atlassian.net/wiki",
        auth_type="basic",
        username="user",
        api_token="pat",
        http_proxy="http://proxy:8080",
        https_proxy="https://proxy:8443",
        socks_proxy="socks5://user:pass@proxy:1080",
        no_proxy="localhost,127.0.0.1",
    )
    client = ConfluenceClient(config=config)
    # Simulate a request
    client.confluence._session.request(
        "GET", "https://test.atlassian.net/wiki/rest/api/content/123"
    )
    assert mock_session.proxies["http"] == "http://proxy:8080"
    assert mock_session.proxies["https"] == "https://proxy:8443"
    assert mock_session.proxies["socks"] == "socks5://user:pass@proxy:1080"


def test_jira_client_no_proxy_env(monkeypatch):
    """Test that JiraClient sets NO_PROXY in the process environment."""
    mock_jira = MagicMock()
    mock_session = MagicMock()
    mock_jira._session = mock_session
    monkeypatch.setattr("mcp_atlassian.jira.client.Jira", lambda **kwargs: mock_jira)
    monkeypatch.setattr(
        "mcp_atlassian.jira.client.configure_ssl_verification", lambda **kwargs: None
    )
    monkeypatch.setenv("NO_PROXY", "")
    config = JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="user",
        api_token="pat",
        http_proxy="http://proxy:8080",
        no_proxy="localhost,127.0.0.1",
    )
    _client = JiraClient(config=config)
    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1"


class TestProxyConfigurationEnhanced(BaseAuthTest):
    """Enhanced proxy configuration tests using test utilities."""

    def test_proxy_configuration_from_environment(self):
        """Test proxy configuration loaded from environment variables."""
        with MockEnvironment.basic_auth_env():
            # Set proxy environment variables in os.environ directly
            proxy_vars = {
                "HTTP_PROXY": "http://proxy.company.com:8080",
                "HTTPS_PROXY": "https://proxy.company.com:8443",
                "NO_PROXY": "*.internal.com,localhost",
            }

            # Patch environment with proxy settings
            with patch.dict(os.environ, proxy_vars):
                # Jira should pick up proxy settings
                jira_config = JiraConfig.from_env()
                assert jira_config.http_proxy == "http://proxy.company.com:8080"
                assert jira_config.https_proxy == "https://proxy.company.com:8443"
                assert jira_config.no_proxy == "*.internal.com,localhost"

                # Confluence should pick up proxy settings
                confluence_config = ConfluenceConfig.from_env()
                assert confluence_config.http_proxy == "http://proxy.company.com:8080"
                assert confluence_config.https_proxy == "https://proxy.company.com:8443"
                assert confluence_config.no_proxy == "*.internal.com,localhost"

    def test_proxy_authentication_in_url(self):
        """Test proxy URLs with authentication credentials."""
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="basic",
            username="user",
            api_token="token",
            http_proxy="http://proxyuser:proxypass@proxy.company.com:8080",
            https_proxy="https://proxyuser:proxypass@proxy.company.com:8443",
        )

        # Verify proxy URLs contain authentication
        assert "proxyuser:proxypass" in config.http_proxy
        assert "proxyuser:proxypass" in config.https_proxy

    def test_socks_proxy_configuration(self, monkeypatch):
        """Test SOCKS proxy configuration for both services."""
        mock_jira = MagicMock()
        mock_session = MagicMock()
        # Create a proper proxies dictionary that can be updated
        mock_session.proxies = {}
        mock_jira._session = mock_session
        monkeypatch.setattr(
            "mcp_atlassian.jira.client.Jira", lambda **kwargs: mock_jira
        )
        monkeypatch.setattr(
            "mcp_atlassian.jira.client.configure_ssl_verification",
            lambda **kwargs: None,
        )

        # Test SOCKS5 proxy
        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="basic",
            username="user",
            api_token="token",
            socks_proxy="socks5://socksuser:sockspass@socks.company.com:1080",
        )

        _client = JiraClient(config=config)
        assert (
            mock_session.proxies["socks"]
            == "socks5://socksuser:sockspass@socks.company.com:1080"
        )

    def test_proxy_bypass_for_internal_domains(self, monkeypatch):
        """Test that requests to NO_PROXY domains bypass the proxy."""
        # Set up environment
        monkeypatch.setenv("NO_PROXY", "*.internal.com,localhost,127.0.0.1")

        config = JiraConfig(
            url="https://jira.internal.com",  # Internal domain
            auth_type="basic",
            username="user",
            api_token="token",
            http_proxy="http://proxy.company.com:8080",
            no_proxy="*.internal.com,localhost,127.0.0.1",
        )

        # Verify NO_PROXY is set in environment
        assert os.environ["NO_PROXY"] == "*.internal.com,localhost,127.0.0.1"
        assert "internal.com" in config.no_proxy

    def test_proxy_error_handling(self, monkeypatch):
        """Test proper error handling when proxy connection fails."""
        # Mock to simulate proxy connection failure
        mock_jira = MagicMock()
        mock_jira.side_effect = ProxyError("Unable to connect to proxy")
        monkeypatch.setattr("mcp_atlassian.jira.client.Jira", mock_jira)

        config = JiraConfig(
            url="https://test.atlassian.net",
            auth_type="basic",
            username="user",
            api_token="token",
            http_proxy="http://unreachable.proxy.com:8080",
        )

        # Creating client should raise proxy error
        with pytest.raises(ProxyError, match="Unable to connect to proxy"):
            JiraClient(config=config)

    def test_proxy_configuration_precedence(self):
        """Test that explicit proxy config takes precedence over environment."""
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://env.proxy.com:8080",
                "HTTPS_PROXY": "https://env.proxy.com:8443",
            },
        ):
            # Explicit configuration should override environment
            config = JiraConfig(
                url="https://test.atlassian.net",
                auth_type="basic",
                username="user",
                api_token="token",
                http_proxy="http://explicit.proxy.com:8080",
                https_proxy="https://explicit.proxy.com:8443",
            )

            assert config.http_proxy == "http://explicit.proxy.com:8080"
            assert config.https_proxy == "https://explicit.proxy.com:8443"

    def test_mixed_proxy_and_ssl_configuration(self, monkeypatch):
        """Test proxy configuration works correctly with SSL verification disabled."""
        mock_confluence = MagicMock()
        mock_session = MagicMock()
        # Create a proper proxies dictionary that can be updated
        mock_session.proxies = {}
        mock_confluence._session = mock_session
        monkeypatch.setattr(
            "mcp_atlassian.confluence.client.Confluence",
            lambda **kwargs: mock_confluence,
        )
        monkeypatch.setattr(
            "mcp_atlassian.confluence.client.configure_ssl_verification",
            lambda **kwargs: None,
        )
        monkeypatch.setattr(
            "mcp_atlassian.preprocessing.confluence.ConfluencePreprocessor",
            lambda **kwargs: MagicMock(),
        )

        # Configure with both proxy and SSL disabled
        config = ConfluenceConfig(
            url="https://test.atlassian.net/wiki",
            auth_type="basic",
            username="user",
            api_token="token",
            http_proxy="http://proxy.company.com:8080",
            ssl_verify=False,
        )

        _client = ConfluenceClient(config=config)

        # Both proxy and SSL settings should be applied
        assert mock_session.proxies["http"] == "http://proxy.company.com:8080"
        assert config.ssl_verify is False

    def test_proxy_with_oauth_configuration(self):
        """Test proxy configuration works with OAuth authentication."""
        with MockEnvironment.oauth_env() as env_vars:
            # Add proxy configuration to env_vars directly, then patch os.environ
            proxy_vars = {
                "HTTP_PROXY": "http://proxy.company.com:8080",
                "HTTPS_PROXY": "https://proxy.company.com:8443",
                "NO_PROXY": "localhost,127.0.0.1",
            }

            # Merge with OAuth env vars
            all_vars = {**env_vars, **proxy_vars}

            # Use patch.dict to ensure environment variables are set
            with patch.dict(os.environ, all_vars):
                # OAuth should still respect proxy settings
                assert os.environ.get("HTTP_PROXY") == "http://proxy.company.com:8080"
                assert os.environ.get("HTTPS_PROXY") == "https://proxy.company.com:8443"
                assert os.environ.get("NO_PROXY") == "localhost,127.0.0.1"


def test_get_proxy_settings_from_env_uses_default_wpad_url():
    """Test global WPAD enable defaults to the built-in PAC URL."""
    with patch.dict(
        os.environ,
        {
            "ATLASSIAN_PROXY_WPAD_ENABLE": "true",
        },
        clear=True,
    ):
        proxy_settings = get_proxy_settings_from_env("JIRA")

    assert proxy_settings["proxy_wpad_enable"] is True
    assert proxy_settings["proxy_wpad_url"] == DEFAULT_PROXY_WPAD_URL


def test_get_proxy_settings_from_env_service_specific_disable_overrides_global():
    """Test service-specific disable flag overrides globally enabled WPAD."""
    with patch.dict(
        os.environ,
        {
            "ATLASSIAN_PROXY_WPAD_ENABLE": "true",
            "ATLASSIAN_PROXY_WPAD_URL": "http://global-wpad.example.com/wpad.dat",
            "CONFLUENCE_PROXY_WPAD_ENABLE": "false",
        },
        clear=True,
    ):
        proxy_settings = get_proxy_settings_from_env("CONFLUENCE")

    assert proxy_settings["proxy_wpad_enable"] is False
    assert proxy_settings["proxy_wpad_url"] == "http://global-wpad.example.com/wpad.dat"


def test_apply_proxy_configuration_returns_same_session_for_explicit_proxies(
    monkeypatch,
):
    """Test explicit proxy settings win over WPAD and mutate the original session."""
    session = Session()
    monkeypatch.delenv("NO_PROXY", raising=False)

    config = JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="user",
        api_token="token",
        http_proxy="http://proxy:8080",
        https_proxy="https://proxy:8443",
        socks_proxy="socks5://proxy:1080",
        no_proxy="localhost,127.0.0.1",
        proxy_wpad_enable=True,
        proxy_wpad_url="http://wpad.example.com/wpad.dat",
    )

    result = apply_proxy_configuration(
        logger=MagicMock(),
        service_name="Jira",
        session=session,
        config=config,
        target_url=config.url,
    )

    assert result is session
    assert session.proxies["http"] == "http://proxy:8080"
    assert session.proxies["https"] == "https://proxy:8443"
    assert session.proxies["socks"] == "socks5://proxy:1080"
    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1"


def test_apply_proxy_configuration_wraps_session_for_wpad():
    """Test WPAD configuration upgrades the session and validates the target URL."""
    source_session = Session()
    source_session.headers["X-Test"] = "1"
    source_session.cookies.set("cookie", "value")
    source_session.trust_env = False
    response_hook = MagicMock()
    source_session.hooks["response"].append(response_hook)
    custom_adapter = HTTPAdapter()
    source_session.mount("https://", custom_adapter)

    config = JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="user",
        api_token="token",
        proxy_wpad_enable=True,
        proxy_wpad_url="http://wpad.example.com/wpad.dat",
    )

    pac = MagicMock()
    pac_session = Session()

    with (
        patch(
            "mcp_atlassian.utils.proxy._load_pac_file", return_value=pac
        ) as mock_load_pac,
        patch(
            "mcp_atlassian.utils.proxy._validate_pac_for_target_url"
        ) as mock_validate,
        patch(
            "mcp_atlassian.utils.proxy._NoProxyAwarePACSession",
            return_value=pac_session,
        ) as mock_pac_session,
    ):
        result = apply_proxy_configuration(
            logger=MagicMock(),
            service_name="Jira",
            session=source_session,
            config=config,
            target_url="https://api.atlassian.com/ex/jira/cloud-id",
        )

    assert result is pac_session
    mock_pac_session.assert_called_once_with(pac=pac, no_proxy=None)
    mock_load_pac.assert_called_once_with(
        pac_url="http://wpad.example.com/wpad.dat",
        verify=source_session.verify,
        cert=source_session.cert,
        trust_env=False,
    )
    mock_validate.assert_called_once_with(
        pac=pac, target_url="https://api.atlassian.com/ex/jira/cloud-id"
    )
    assert pac_session.headers["X-Test"] == "1"
    assert pac_session.cookies.get("cookie") == "value"
    assert pac_session.trust_env is False
    assert pac_session.hooks["response"] == [response_hook]
    assert pac_session.get_adapter("https://example.com") is custom_adapter


@pytest.mark.parametrize(
    ("url", "expected_proxies"),
    [
        (
            "https://external.example.com/api",
            {
                "http": "http://proxy.example.com:8080",
                "https": "http://proxy.example.com:8080",
            },
        ),
        (
            "https://internal.example.com/api",
            {"http": None, "https": None},
        ),
    ],
)
def test_pac_session_routes_requests_and_preserves_no_proxy(
    url: str, expected_proxies: dict[str, str | None]
) -> None:
    """Test PAC evaluation routes requests while NO_PROXY forces direct access."""
    pac = get_pac(
        js=(
            "function FindProxyForURL(url, host) { "
            'return "PROXY proxy.example.com:8080"; }'
        )
    )
    session = _NoProxyAwarePACSession(
        pac=pac,
        no_proxy="internal.example.com",
    )

    with patch.object(Session, "request", return_value=MagicMock()) as mock_request:
        session.get(url)

    assert mock_request.call_args.kwargs["proxies"] == expected_proxies


def test_pac_session_no_proxy_handles_empty_proxy_mapping() -> None:
    """An empty caller proxy map must not disable the NO_PROXY bypass."""
    pac = get_pac(
        js=(
            "function FindProxyForURL(url, host) { "
            'return "PROXY proxy.example.com:8080"; }'
        )
    )
    session = _NoProxyAwarePACSession(
        pac=pac,
        no_proxy="internal.example.com",
    )

    with patch.object(Session, "request", return_value=MagicMock()) as mock_request:
        session.get("https://internal.example.com/api", proxies={})

    assert mock_request.call_args.kwargs["proxies"] == {
        "http": None,
        "https": None,
    }


def test_pac_session_no_proxy_handles_positional_proxy_mapping() -> None:
    """A positional proxy map must be replaced without a duplicate argument."""
    pac = get_pac(
        js=(
            "function FindProxyForURL(url, host) { "
            'return "PROXY proxy.example.com:8080"; }'
        )
    )
    session = _NoProxyAwarePACSession(
        pac=pac,
        no_proxy="internal.example.com",
    )

    with patch.object(Session, "request", return_value=MagicMock()) as mock_request:
        session.request("GET", "https://internal.example.com/api", {})

    assert mock_request.call_args.kwargs["proxies"] == {
        "http": None,
        "https": None,
    }


def test_apply_proxy_configuration_raises_for_malformed_pac():
    """Test malformed PAC files produce a clear service-specific error."""
    config = JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="user",
        api_token="token",
        proxy_wpad_enable=True,
        proxy_wpad_url="http://wpad.example.com/wpad.dat",
    )

    with patch(
        "mcp_atlassian.utils.proxy._load_pac_file",
        side_effect=MalformedPacError("broken pac"),
    ):
        with pytest.raises(
            ValueError,
            match="Jira PAC file at http://wpad.example.com/wpad.dat is malformed",
        ):
            apply_proxy_configuration(
                logger=MagicMock(),
                service_name="Jira",
                session=Session(),
                config=config,
                target_url=config.url,
            )


def test_load_pac_file_is_cached():
    """Test PAC loads are cached for identical PAC URL and TLS settings."""
    _load_pac_file.cache_clear()
    pac = object()

    try:
        with patch(
            "mcp_atlassian.utils.proxy.get_pac", return_value=pac
        ) as mock_get_pac:
            first = _load_pac_file(
                "http://wpad/wpad.dat",
                verify=True,
                cert=None,
                trust_env=False,
            )
            second = _load_pac_file(
                "http://wpad/wpad.dat",
                verify=True,
                cert=None,
                trust_env=False,
            )

        assert first is pac
        assert second is pac
        assert mock_get_pac.call_count == 1
        mock_get_pac.assert_called_once_with(
            url="http://wpad/wpad.dat",
            session=mock_get_pac.call_args.kwargs["session"],
            timeout=10,
            allowed_content_types=[
                "application/x-ns-proxy-autoconfig",
                "application/x-javascript-config",
                "application/x-javascript",
                "text/plain",
            ],
        )
        bootstrap_session = mock_get_pac.call_args.kwargs["session"]
        assert bootstrap_session.verify is True
        assert bootstrap_session.cert is None
        assert bootstrap_session.trust_env is False
    finally:
        _load_pac_file.cache_clear()


def test_load_pac_file_requires_optional_wpad_dependency(monkeypatch):
    """PAC loading explains how to enable WPAD when the extra is absent."""
    _load_pac_file.cache_clear()
    monkeypatch.setattr("mcp_atlassian.utils.proxy.get_pac", None)

    with pytest.raises(ValueError, match=r"mcp-atlassian\[wpad\]"):
        _load_pac_file(
            "http://wpad/wpad.dat",
            verify=True,
            cert=None,
            trust_env=False,
        )


class TestNoProxyAdapter:
    """Tests for NoProxyAdapter and configure_proxy_bypass."""

    def _make_request(self, url: str) -> PreparedRequest:
        req = PreparedRequest()
        req.url = url
        return req

    def test_clears_proxies_when_url_matches_no_proxy(self, monkeypatch):
        """Proxies are cleared when the request URL matches NO_PROXY."""
        monkeypatch.setenv("NO_PROXY", "internal.example.com")
        adapter = NoProxyAdapter()
        proxies = {"https": "https://proxy:8443"}

        with patch.object(adapter.__class__.__bases__[0], "send") as mock_send:
            mock_send.return_value = MagicMock()
            adapter.send(
                self._make_request("https://internal.example.com/api"),
                proxies=proxies,
            )
            _, kwargs = mock_send.call_args
            assert kwargs["proxies"] is None

    def test_preserves_proxies_when_url_does_not_match_no_proxy(self, monkeypatch):
        """Proxies are kept when the request URL is not in NO_PROXY."""
        monkeypatch.setenv("NO_PROXY", "other.example.com")
        adapter = NoProxyAdapter()
        proxies = {"https": "https://proxy:8443"}

        with patch.object(adapter.__class__.__bases__[0], "send") as mock_send:
            mock_send.return_value = MagicMock()
            adapter.send(
                self._make_request("https://external.example.com/api"),
                proxies=proxies,
            )
            _, kwargs = mock_send.call_args
            assert kwargs["proxies"] == proxies

    def test_no_effect_when_no_proxy_not_set(self, monkeypatch):
        """Proxies are untouched when NO_PROXY is not set."""
        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)
        adapter = NoProxyAdapter()
        proxies = {"https": "https://proxy:8443"}

        with patch.object(adapter.__class__.__bases__[0], "send") as mock_send:
            mock_send.return_value = MagicMock()
            adapter.send(
                self._make_request("https://internal.example.com/api"),
                proxies=proxies,
            )
            _, kwargs = mock_send.call_args
            assert kwargs["proxies"] == proxies

    def test_configure_proxy_bypass_mounts_adapter_when_no_proxy_set(self, monkeypatch):
        """configure_proxy_bypass mounts NoProxyAdapter when NO_PROXY is set."""
        monkeypatch.setenv("NO_PROXY", "example.com")
        session = Session()
        configure_proxy_bypass("TestService", "https://example.com", session)
        assert isinstance(session.get_adapter("https://example.com"), NoProxyAdapter)
        assert isinstance(session.get_adapter("http://example.com"), NoProxyAdapter)

    def test_configure_proxy_bypass_does_nothing_when_no_proxy_not_set(
        self, monkeypatch
    ):
        """configure_proxy_bypass does not mount an adapter when NO_PROXY is absent."""
        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)
        session = Session()
        default_https_adapter = session.get_adapter("https://example.com")
        configure_proxy_bypass("TestService", "https://example.com", session)
        assert session.get_adapter("https://example.com") is default_https_adapter
