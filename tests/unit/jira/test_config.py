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
    # Cloud instance
    config = JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="user",
        api_token="token",
    )
    assert config.is_cloud is True

    # Server/Data Center instance
    config = JiraConfig(
        url="https://jira.example.com",
        auth_type="token",
        personal_token="token",
    )
    assert config.is_cloud is False
