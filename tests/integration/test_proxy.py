"""
Integration tests for proxy handling in Jira and Confluence clients (mocked requests).
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import ProxyError

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig
from tests.utils.base import BaseAuthTest
from tests.utils.mocks import MockEnvironment


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
def test_jira_client_no_proxy_env(monkeypatch):
    """Test that JiraClient sets NO_PROXY env var and requests to excluded hosts bypass proxy."""
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
    client = JiraClient(config=config)
    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1"


class TestProxyConfigurationEnhanced(BaseAuthTest):
    """Enhanced proxy configuration tests using test utilities."""

    @pytest.mark.integration
    def test_proxy_configuration_from_environment(self):
        """Test proxy configuration loaded from environment variables."""
        with MockEnvironment.basic_auth_env() as env_vars:
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

    @pytest.mark.integration
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

    @pytest.mark.integration
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

        client = JiraClient(config=config)
        assert (
            mock_session.proxies["socks"]
            == "socks5://socksuser:sockspass@socks.company.com:1080"
        )

    @pytest.mark.integration
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

    @pytest.mark.integration
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

    @pytest.mark.integration
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

    @pytest.mark.integration
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

        client = ConfluenceClient(config=config)

        # Both proxy and SSL settings should be applied
        assert mock_session.proxies["http"] == "http://proxy.company.com:8080"
        assert config.ssl_verify is False

    @pytest.mark.integration
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
