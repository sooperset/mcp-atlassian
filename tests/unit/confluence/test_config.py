"""Unit tests for the ConfluenceConfig class."""

import os
from unittest.mock import patch

import pytest

from mcp_atlassian.confluence.config import ConfluenceConfig


def test_from_env_success():
    """Test that from_env successfully creates a config from environment variables."""
    # Need to clear and reset the environment for this test
    with patch.dict(
        "os.environ",
        {
            "CONFLUENCE_URL": "https://test.atlassian.net/wiki",
            "CONFLUENCE_USERNAME": "test_username",
            "CONFLUENCE_API_TOKEN": "test_token",
        },
        clear=True,  # Clear existing environment variables
    ):
        config = ConfluenceConfig.from_env()
        assert config.url == "https://test.atlassian.net/wiki"
        assert config.username == "test_username"
        assert config.api_token == "test_token"


def test_from_env_missing_url():
    """Test that from_env raises ValueError when URL is missing."""
    original_env = os.environ.copy()
    try:
        os.environ.clear()
        with pytest.raises(
            ValueError, match="Missing required CONFLUENCE_URL environment variable"
        ):
            ConfluenceConfig.from_env()
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


def test_from_env_missing_cloud_auth():
    """Test that from_env raises ValueError when cloud auth credentials are missing."""
    with patch.dict(
        os.environ,
        {
            "CONFLUENCE_URL": "https://test.atlassian.net",  # Cloud URL
        },
        clear=True,
    ):
        with pytest.raises(
            ValueError,
            match="Cloud authentication requires CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN",
        ):
            ConfluenceConfig.from_env()


def test_from_env_missing_server_auth():
    """Test that from_env raises ValueError when server auth credentials are missing."""
    with patch.dict(
        os.environ,
        {
            "CONFLUENCE_URL": "https://confluence.example.com",  # Server URL
        },
        clear=True,
    ):
        with pytest.raises(
            ValueError,
            match="Server/Data Center authentication requires CONFLUENCE_PERSONAL_TOKEN",
        ):
            ConfluenceConfig.from_env()


def test_is_cloud():
    """Test that is_cloud property returns correct value."""
    # Arrange & Act - Cloud URL
    config = ConfluenceConfig(
        url="https://example.atlassian.net/wiki",
        auth_type="basic",
        username="test",
        api_token="test",
    )

    # Assert
    assert config.is_cloud is True

    # Arrange & Act - Server URL
    config = ConfluenceConfig(
        url="https://confluence.example.com",
        auth_type="token",
        personal_token="test",
    )

    # Assert
    assert config.is_cloud is False

    # Arrange & Act - Localhost URL (Data Center/Server)
    config = ConfluenceConfig(
        url="http://localhost:8090",
        auth_type="token",
        personal_token="test",
    )

    # Assert
    assert config.is_cloud is False

    # Arrange & Act - IP localhost URL (Data Center/Server)
    config = ConfluenceConfig(
        url="http://127.0.0.1:8090",
        auth_type="token",
        personal_token="test",
    )

    # Assert
    assert config.is_cloud is False
