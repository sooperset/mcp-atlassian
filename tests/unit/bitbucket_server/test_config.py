"""Tests for Bitbucket Server configuration module."""

import pytest

from mcp_atlassian.bitbucket_server.config import BitbucketServerConfig
from mcp_atlassian.bitbucket_server.constants import (
    AUTH_TYPE_BASIC,
    AUTH_TYPE_PERSONAL_TOKEN,
    ENV_BITBUCKET_API_TOKEN,
    ENV_BITBUCKET_PERSONAL_TOKEN,
    ENV_BITBUCKET_PROJECTS_FILTER,
    ENV_BITBUCKET_SSL_VERIFY,
    ENV_BITBUCKET_URL,
    ENV_BITBUCKET_USERNAME,
)


def test_bitbucket_server_config_basic():
    """Test BitbucketServerConfig with basic auth."""
    config = BitbucketServerConfig(
        url="https://bitbucket.example.com",
        auth_type=AUTH_TYPE_BASIC,
        username="username",
        api_token="api_token",
    )

    assert config.url == "https://bitbucket.example.com"
    assert config.auth_type == AUTH_TYPE_BASIC
    assert config.username == "username"
    assert config.api_token == "api_token"
    assert config.personal_token is None
    assert config.ssl_verify is True
    assert config.projects_filter is None


def test_bitbucket_server_config_token():
    """Test BitbucketServerConfig with token auth."""
    config = BitbucketServerConfig(
        url="https://bitbucket.example.com",
        auth_type=AUTH_TYPE_PERSONAL_TOKEN,
        personal_token="personal_token",
    )

    assert config.url == "https://bitbucket.example.com"
    assert config.auth_type == AUTH_TYPE_PERSONAL_TOKEN
    assert config.username is None
    assert config.api_token is None
    assert config.personal_token == "personal_token"
    assert config.ssl_verify is True
    assert config.projects_filter is None


def test_bitbucket_server_config_validate_basic_missing_creds():
    """Test validation fails when missing credentials for basic auth."""
    with pytest.raises(ValueError) as excinfo:
        BitbucketServerConfig(
            url="https://bitbucket.example.com",
            auth_type=AUTH_TYPE_BASIC,
            username="username",  # missing api_token
        )

    assert "both username and API token are required" in str(excinfo.value)


def test_bitbucket_server_config_validate_token_missing_creds():
    """Test validation fails when missing credentials for token auth."""
    with pytest.raises(ValueError) as excinfo:
        BitbucketServerConfig(
            url="https://bitbucket.example.com",
            auth_type=AUTH_TYPE_PERSONAL_TOKEN,
            # missing personal_token
        )

    assert "personal token is required" in str(excinfo.value)


def test_bitbucket_server_config_from_env_basic(mock_env_vars):
    """Test creating config from environment variables with basic auth."""
    config = BitbucketServerConfig.from_env()

    assert config.url == "https://bitbucket.example.com"
    assert config.auth_type == AUTH_TYPE_BASIC
    assert config.username == "username"
    assert config.api_token == "api_token"
    assert config.personal_token is None
    assert config.ssl_verify is True
    assert config.projects_filter == "PROJ,TEST"


def test_bitbucket_server_config_from_env_personal_token(mock_env_vars_personal_token):
    """Test creating config from environment variables with personal token."""
    config = BitbucketServerConfig.from_env()

    assert config.url == "https://bitbucket.example.com"
    assert config.auth_type == AUTH_TYPE_PERSONAL_TOKEN
    assert config.username is None
    assert config.api_token is None
    assert config.personal_token == "personal_token"
    assert config.ssl_verify is True
    assert config.projects_filter == "PROJ,TEST"


def test_bitbucket_server_config_from_env_missing_url():
    """Test error when URL is missing from environment."""
    with pytest.raises(ValueError) as excinfo:
        with pytest.MonkeyPatch.context() as mp:
            # Ensure no environment variables are set
            for var in [
                ENV_BITBUCKET_URL,
                ENV_BITBUCKET_USERNAME,
                ENV_BITBUCKET_API_TOKEN,
                ENV_BITBUCKET_PERSONAL_TOKEN,
                ENV_BITBUCKET_SSL_VERIFY,
                ENV_BITBUCKET_PROJECTS_FILTER,
            ]:
                mp.delenv(var, raising=False)

            BitbucketServerConfig.from_env()

    assert f"Environment variable {ENV_BITBUCKET_URL} is required" in str(excinfo.value)


def test_bitbucket_server_config_from_env_missing_auth():
    """Test error when auth credentials are missing from environment."""
    with pytest.raises(ValueError) as excinfo:
        with pytest.MonkeyPatch.context() as mp:
            # Set URL but no auth credentials
            mp.setenv(ENV_BITBUCKET_URL, "https://bitbucket.example.com")
            for var in [
                ENV_BITBUCKET_USERNAME,
                ENV_BITBUCKET_API_TOKEN,
                ENV_BITBUCKET_PERSONAL_TOKEN,
            ]:
                mp.delenv(var, raising=False)

            BitbucketServerConfig.from_env()

    assert "No valid authentication credentials found" in str(excinfo.value)


def test_bitbucket_server_config_get_auth_basic():
    """Test get_auth returns correct format for basic auth."""
    config = BitbucketServerConfig(
        url="https://bitbucket.example.com",
        auth_type=AUTH_TYPE_BASIC,
        username="username",
        api_token="api_token",
    )

    auth = config.get_auth()
    assert auth == ("username", "api_token")


def test_bitbucket_server_config_get_auth_token():
    """Test get_auth returns correct format for token auth."""
    config = BitbucketServerConfig(
        url="https://bitbucket.example.com",
        auth_type=AUTH_TYPE_PERSONAL_TOKEN,
        personal_token="personal_token",
    )

    auth = config.get_auth()
    assert auth == {"Authorization": "Bearer personal_token"}


def test_bitbucket_server_config_get_auth_invalid():
    """Test get_auth raises error for invalid auth type."""
    config = BitbucketServerConfig(
        url="https://bitbucket.example.com",
        auth_type="invalid",
        username="username",
        api_token="api_token",
    )

    with pytest.raises(ValueError) as excinfo:
        config.get_auth()

    assert "Unsupported auth type: invalid" in str(excinfo.value)


def test_bitbucket_server_config_strip_trailing_slash():
    """Test URL trailing slash is stripped."""
    config = BitbucketServerConfig(
        url="https://bitbucket.example.com/",
        auth_type=AUTH_TYPE_BASIC,
        username="username",
        api_token="api_token",
    )

    assert config.url == "https://bitbucket.example.com"


def test_bitbucket_server_config_repr():
    """Test __repr__ representation."""
    config = BitbucketServerConfig(
        url="https://bitbucket.example.com",
        auth_type=AUTH_TYPE_BASIC,
        username="username",
        api_token="api_token",
        personal_token="personal_token",
    )

    repr_str = repr(config)
    # Basic object __repr__ should include the class name and its module
    assert "BitbucketServerConfig" in repr_str
