"""Tests for the Jira client module."""

import os
from copy import deepcopy
from typing import Literal
from unittest.mock import MagicMock, call, patch

import pytest

from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig


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
        )

        # Verify SSL verification was configured
        mock_configure_ssl.assert_called_once_with(
            service_name="Jira",
            url="https://test.atlassian.net",
            session=mock_jira.return_value._session,
            ssl_verify=True,
        )

        assert client.config == config
        assert client._field_ids_cache is None
        assert client._current_user_account_id is None


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
        )

        # Verify SSL verification was configured with ssl_verify=False
        mock_configure_ssl.assert_called_once_with(
            service_name="Jira",
            url="https://jira.example.com",
            session=mock_jira.return_value._session,
            ssl_verify=False,
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
