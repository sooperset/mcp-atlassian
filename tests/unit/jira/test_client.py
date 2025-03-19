"""Tests for the Jira client module."""

from unittest.mock import MagicMock, patch

from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig


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
        assert client._field_ids is None
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
            auth_type="token",
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

        # Test with None
        assert client._clean_text(None) == ""

        # Test with spaces and newlines
        assert client._clean_text("  \n  Test with spaces  \n  ") == "Test with spaces"
