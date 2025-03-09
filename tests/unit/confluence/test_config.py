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


def test_from_env_missing_vars():
    """Test that from_env raises ValueError when environment variables are missing."""
    # Clear all environment variables
    original_env = os.environ.copy()
    try:
        os.environ.clear()
        with pytest.raises(
            ValueError, match="Missing required Confluence environment variables"
        ):
            ConfluenceConfig.from_env()

        # Test with partial variables
        os.environ["CONFLUENCE_URL"] = "https://test.atlassian.net/wiki"
        with pytest.raises(
            ValueError, match="Missing required Confluence environment variables"
        ):
            ConfluenceConfig.from_env()
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


def test_is_cloud():
    """Test that is_cloud property returns correct value."""
    # Cloud instance
    config = ConfluenceConfig(
        url="https://test.atlassian.net/wiki",
        username="user",
        api_token="token",
    )
    assert config.is_cloud is True

    # Server instance
    config = ConfluenceConfig(
        url="https://confluence.company.com",
        username="user",
        api_token="token",
    )
    assert config.is_cloud is False
