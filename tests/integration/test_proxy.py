"""
Integration tests for proxy handling in Jira and Confluence clients (mocked requests).
"""

import os
from unittest.mock import MagicMock

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig


def test_jira_client_passes_proxies_to_requests(monkeypatch):
    """Test that JiraClient passes proxies to requests.Session.request."""
    mock_jira = MagicMock()
    mock_session = MagicMock()
    mock_jira._session = mock_session
    monkeypatch.setattr("mcp_atlassian.jira.client.Jira", lambda **kwargs: mock_jira)
    monkeypatch.setattr(
        "mcp_atlassian.jira.client.configure_ssl_verification", lambda **kwargs: None
    )
    config = JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="user",
        api_token="token",
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
        api_token="token",
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
        api_token="token",
        http_proxy="http://proxy:8080",
        no_proxy="localhost,127.0.0.1",
    )
    client = JiraClient(config=config)
    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1"
