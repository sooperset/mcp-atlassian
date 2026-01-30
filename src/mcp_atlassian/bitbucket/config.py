"""Configuration module for Bitbucket API interactions."""

import logging
import os
from dataclasses import dataclass
from typing import Literal

from ..utils.env import get_custom_headers, is_env_ssl_verify
from ..utils.oauth import (
    BYOAccessTokenOAuthConfig,
    OAuthConfig,
    get_oauth_config_from_env,
)

logger = logging.getLogger("mcp-bitbucket")


@dataclass
class BitbucketConfig:
    """Configuration for Bitbucket API access.

    Supports multiple authentication methods:
    - Basic auth (username + app password)
    - Personal Access Token (PAT)
    - OAuth 2.0
    """

    url: str
    auth_type: Literal["basic", "pat", "oauth"]
    username: str | None = None
    password: str | None = None
    personal_token: str | None = None
    oauth_config: OAuthConfig | BYOAccessTokenOAuthConfig | None = None
    ssl_verify: bool | str = True
    custom_headers: dict[str, str] | None = None
    is_cloud: bool = True

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.auth_type == "basic":
            if not self.username or not self.password:
                error_msg = "Basic authentication requires both username and password"
                raise ValueError(error_msg)
        elif self.auth_type == "pat":
            if not self.personal_token:
                error_msg = "PAT authentication requires personal_token"
                raise ValueError(error_msg)
        elif self.auth_type == "oauth":
            if not self.oauth_config:
                error_msg = "OAuth authentication requires oauth_config"
                raise ValueError(error_msg)

    @classmethod
    def from_env(cls) -> "BitbucketConfig":
        """Create configuration from environment variables.

        Environment variables:
            BITBUCKET_URL: Bitbucket instance URL (required)
            BITBUCKET_USERNAME: Username for basic auth
            BITBUCKET_PASSWORD: App password for basic auth
            BITBUCKET_PERSONAL_TOKEN: Personal access token
            BITBUCKET_IS_CLOUD: Whether using Bitbucket Cloud (default: true)
            BITBUCKET_SSL_VERIFY: SSL verification setting
            BITBUCKET_CUSTOM_HEADERS: Custom HTTP headers (JSON format)

        Returns:
            BitbucketConfig instance

        Raises:
            ValueError: If required configuration is missing or invalid
        """
        url = os.getenv("BITBUCKET_URL")
        if not url:
            error_msg = "BITBUCKET_URL environment variable is required"
            raise ValueError(error_msg)

        # Remove trailing slash from URL
        url = url.rstrip("/")

        # Determine auth type and load credentials
        personal_token = os.getenv("BITBUCKET_PERSONAL_TOKEN")
        username = os.getenv("BITBUCKET_USERNAME")
        password = os.getenv("BITBUCKET_PASSWORD")

        # Check for OAuth configuration
        oauth_config = get_oauth_config_from_env("BITBUCKET")

        if oauth_config:
            auth_type = "oauth"
        elif personal_token:
            auth_type = "pat"
        elif username and password:
            auth_type = "basic"
        else:
            error_msg = (
                "No valid authentication credentials found. "
                "Provide either BITBUCKET_PERSONAL_TOKEN, or both "
                "BITBUCKET_USERNAME and BITBUCKET_PASSWORD, or OAuth credentials."
            )
            raise ValueError(error_msg)

        # Determine if using Bitbucket Cloud or Server
        is_cloud_str = os.getenv("BITBUCKET_IS_CLOUD", "true").lower()
        is_cloud = is_cloud_str in ("true", "1", "yes")

        # SSL verification
        ssl_verify = is_env_ssl_verify("BITBUCKET_SSL_VERIFY")

        # Custom headers
        custom_headers = get_custom_headers("BITBUCKET_CUSTOM_HEADERS")

        return cls(
            url=url,
            auth_type=auth_type,
            username=username,
            password=password,
            personal_token=personal_token,
            oauth_config=oauth_config,
            ssl_verify=ssl_verify,
            custom_headers=custom_headers,
            is_cloud=is_cloud,
        )

    def is_auth_configured(self) -> bool:
        """Check if authentication is properly configured.

        Returns:
            True if authentication is configured, False otherwise
        """
        if self.auth_type == "basic":
            return bool(self.username and self.password)
        elif self.auth_type == "pat":
            return bool(self.personal_token)
        elif self.auth_type == "oauth":
            return bool(self.oauth_config)
        return False
