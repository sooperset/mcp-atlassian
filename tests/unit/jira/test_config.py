"""Tests for the Jira config module."""

import os
from unittest.mock import patch

import pytest

from mcp_atlassian.jira.config import JiraConfig


def test_from_env_basic_auth():
    """Test that from_env correctly loads basic auth configuration."""
    with patch.dict(
        os.environ,
        {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_USERNAME": "test_username",
            "JIRA_API_TOKEN": "test_token",
        },
        clear=True,
    ):
        config = JiraConfig.from_env()
        assert config.url == "https://test.atlassian.net"
        assert config.auth_type == "basic"
        assert config.username == "test_username"
        assert config.api_token == "test_token"
        assert config.personal_token is None
        assert config.ssl_verify is True


def test_from_env_token_auth():
    """Test that from_env correctly loads token auth configuration."""
    with patch.dict(
        os.environ,
        {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_PERSONAL_TOKEN": "test_personal_token",
            "JIRA_SSL_VERIFY": "false",
        },
        clear=True,
    ):
        config = JiraConfig.from_env()
        assert config.url == "https://jira.example.com"
        assert config.auth_type == "token"
        assert config.username is None
        assert config.api_token is None
        assert config.personal_token == "test_personal_token"
        assert config.ssl_verify is False


def test_from_env_missing_url():
    """Test that from_env raises ValueError when URL is missing."""
    original_env = os.environ.copy()
    try:
        os.environ.clear()
        with pytest.raises(
            ValueError, match="Missing required JIRA_URL environment variable"
        ):
            JiraConfig.from_env()
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


def test_from_env_missing_cloud_auth():
    """Test that from_env raises ValueError when cloud auth credentials are missing."""
    with patch.dict(
        os.environ,
        {
            "JIRA_URL": "https://test.atlassian.net",  # Cloud URL
        },
        clear=True,
    ):
        with pytest.raises(
            ValueError,
            match="Cloud authentication requires JIRA_USERNAME and JIRA_API_TOKEN",
        ):
            JiraConfig.from_env()


def test_from_env_missing_server_auth():
    """Test that from_env raises ValueError when server auth credentials are missing."""
    with patch.dict(
        os.environ,
        {
            "JIRA_URL": "https://jira.example.com",  # Server URL
        },
        clear=True,
    ):
        with pytest.raises(
            ValueError,
            match="Server/Data Center authentication requires JIRA_PERSONAL_TOKEN",
        ):
            JiraConfig.from_env()


def test_is_cloud():
    """Test that is_cloud property returns correct value."""
    # Arrange & Act - Cloud URL
    config = JiraConfig(
        url="https://example.atlassian.net",
        auth_type="basic",
        username="test",
        api_token="test",
    )

    # Assert
    assert config.is_cloud is True

    # Arrange & Act - Server URL
    config = JiraConfig(
        url="https://jira.example.com",
        auth_type="token",
        personal_token="test",
    )

    # Assert
    assert config.is_cloud is False

    # Arrange & Act - Localhost URL (Data Center/Server)
    config = JiraConfig(
        url="http://localhost:8080",
        auth_type="token",
        personal_token="test",
    )

    # Assert
    assert config.is_cloud is False

    # Arrange & Act - IP localhost URL (Data Center/Server)
    config = JiraConfig(
        url="http://127.0.0.1:8080",
        auth_type="token",
        personal_token="test",
    )

    # Assert
    assert config.is_cloud is False
