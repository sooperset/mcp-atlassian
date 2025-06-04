"""Tests for the Zephyr Essential configuration module."""

import os
import pytest
from unittest.mock import patch

from mcp_atlassian.zephyr.config import ZephyrConfig


class TestZephyrConfig:
    """Test class for Zephyr Essential configuration."""

    def test_zephyr_config_init(self):
        """Test initializing ZephyrConfig with direct values."""
        config = ZephyrConfig(
            base_url="https://test-api.zephyr.com",
            access_key="test-access-key",
            secret_key="test-secret-key"
        )

        assert config.base_url == "https://test-api.zephyr.com"
        assert config.access_key == "test-access-key"
        assert config.secret_key == "test-secret-key"

    @patch.dict(os.environ, {
        "ZAPI_BASE_URL": "https://test-api.zephyr.com",
        "ZAPI_ACCESS_KEY": "test-access-key",
        "ZAPI_SECRET_KEY": "test-secret-key"
    })
    def test_from_env_with_all_variables(self):
        """Test creating ZephyrConfig from environment variables."""
        config = ZephyrConfig.from_env()

        assert config.base_url == "https://test-api.zephyr.com"
        assert config.access_key == "test-access-key"
        assert config.secret_key == "test-secret-key"

    @patch.dict(os.environ, {
        "ZAPI_ACCESS_KEY": "test-access-key",
        "ZAPI_SECRET_KEY": "test-secret-key"
    })
    def test_from_env_with_default_url(self):
        """Test creating ZephyrConfig with default base URL."""
        config = ZephyrConfig.from_env()

        assert config.base_url == "https://prod-api.zephyr4jiracloud.com/v2"
        assert config.access_key == "test-access-key"
        assert config.secret_key == "test-secret-key"

    @patch.dict(os.environ, {
        "ZAPI_BASE_URL": "https://test-api.zephyr.com/",  # With trailing slash
        "ZAPI_ACCESS_KEY": "test-access-key",
        "ZAPI_SECRET_KEY": "test-secret-key"
    })
    def test_from_env_with_trailing_slash(self):
        """Test creating ZephyrConfig with URL that has trailing slash."""
        config = ZephyrConfig.from_env()

        # Verify trailing slash is removed
        assert config.base_url == "https://test-api.zephyr.com"
        assert config.access_key == "test-access-key"
        assert config.secret_key == "test-secret-key"

    @patch.dict(os.environ, {
        "ZAPI_BASE_URL": "https://test-api.zephyr.com",
        "ZAPI_SECRET_KEY": "test-secret-key"
    })
    def test_from_env_missing_access_key(self):
        """Test creating ZephyrConfig with missing access key."""
        with pytest.raises(ValueError) as excinfo:
            ZephyrConfig.from_env()

        assert "ZAPI_ACCESS_KEY" in str(excinfo.value)

    @patch.dict(os.environ, {
        "ZAPI_BASE_URL": "https://test-api.zephyr.com",
        "ZAPI_ACCESS_KEY": "test-access-key"
    })
    def test_from_env_missing_secret_key(self):
        """Test creating ZephyrConfig with missing secret key."""
        with pytest.raises(ValueError) as excinfo:
            ZephyrConfig.from_env()

        assert "ZAPI_SECRET_KEY" in str(excinfo.value)