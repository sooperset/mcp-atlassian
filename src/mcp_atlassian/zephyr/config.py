"""Configuration module for Zephyr Scale API interactions."""

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
from ..utils.urls import is_atlassian_cloud_url


@dataclass
class ZephyrConfig:
    """Zephyr Scale API configuration.

    Handles authentication for Zephyr Scale Cloud and Server/Data Center:
    - Cloud: API token (bearer auth)
    - Server/DC: personal access token or basic auth
    """

    url: str  # Base URL for Zephyr Scale API
    auth_type: Literal["basic", "pat", "bearer", "oauth"]  # Authentication type
    api_token: str | None = None  # API token for Cloud (Bearer)
    username: str | None = None  # Username for Server/DC basic auth
    password: str | None = None  # Password for Server/DC basic auth
    personal_token: str | None = None  # Personal access token (Server/DC)
    oauth_config: OAuthConfig | BYOAccessTokenOAuthConfig | None = None
    ssl_verify: bool = True  # Whether to verify SSL certificates
    project_key: str | None = None  # Default project key for operations
    http_proxy: str | None = None  # HTTP proxy URL
    https_proxy: str | None = None  # HTTPS proxy URL
    no_proxy: str | None = None  # Comma-separated list of hosts to bypass proxy
    socks_proxy: str | None = None  # SOCKS proxy URL (optional)
    custom_headers: dict[str, str] | None = None  # Custom HTTP headers
    client_cert: str | None = None  # Client certificate file path (.pem)
    client_key: str | None = None  # Client private key file path (.pem)
    client_key_password: str | None = None  # Password for encrypted private key

    @property
    def is_cloud(self) -> bool:
        """Check if this is a cloud instance.

        Returns:
            True if this is a cloud instance (atlassian.net), False otherwise.
        """
        if (
            self.auth_type == "oauth"
            and self.oauth_config
            and self.oauth_config.cloud_id
        ):
            return True

        return is_atlassian_cloud_url(self.url) if self.url else False

    @property
    def verify_ssl(self) -> bool:
        """Compatibility property for old code.

        Returns:
            The ssl_verify value
        """
        return self.ssl_verify

    @classmethod
    def from_env(cls) -> "ZephyrConfig":
        """Create configuration from environment variables.

        Returns:
            ZephyrConfig with values from environment variables

        Raises:
            ValueError: If required environment variables are missing or invalid
        """
        url = os.getenv("ZEPHYR_URL")
        if not url and not os.getenv("ATLASSIAN_OAUTH_ENABLE"):
            error_msg = "Missing required ZEPHYR_URL environment variable"
            raise ValueError(error_msg)

        # Determine authentication type based on available environment variables
        api_token = os.getenv("ZEPHYR_API_TOKEN")
        username = os.getenv("ZEPHYR_USERNAME")
        password = os.getenv("ZEPHYR_PASSWORD")
        personal_token = os.getenv("ZEPHYR_PERSONAL_TOKEN")

        # Check for OAuth configuration
        oauth_config = get_oauth_config_from_env()
        auth_type = None

        # Use the shared utility function directly
        is_cloud = is_atlassian_cloud_url(url)

        if is_cloud:
            # Cloud: OAuth takes priority, then bearer token
            if oauth_config:
                auth_type = "oauth"
            elif api_token:
                auth_type = "bearer"
            else:
                error_msg = (
                    "Cloud authentication requires ZEPHYR_API_TOKEN, or OAuth "
                    "configuration (set ATLASSIAN_OAUTH_ENABLE=true for "
                    "user-provided tokens)"
                )
                raise ValueError(error_msg)
        else:  # Server/Data Center
            # Server/DC: PAT takes priority over OAuth
            if personal_token:
                if oauth_config:
                    logger = logging.getLogger("mcp-atlassian.zephyr.config")
                    logger.warning(
                        "Both PAT and OAuth configured for Server/DC. Using PAT."
                    )
                auth_type = "pat"
            elif oauth_config:
                auth_type = "oauth"
            elif username and password:
                auth_type = "basic"
            else:
                error_msg = (
                    "Server/Data Center authentication requires "
                    "ZEPHYR_PERSONAL_TOKEN or ZEPHYR_USERNAME and ZEPHYR_PASSWORD"
                )
                raise ValueError(error_msg)

        # SSL verification (for Server/DC)
        ssl_verify = is_env_ssl_verify("ZEPHYR_SSL_VERIFY")

        # Get the default project key if provided
        project_key = os.getenv("ZEPHYR_PROJECT_KEY")

        # Proxy settings
        http_proxy = os.getenv("ZEPHYR_HTTP_PROXY", os.getenv("HTTP_PROXY"))
        https_proxy = os.getenv("ZEPHYR_HTTPS_PROXY", os.getenv("HTTPS_PROXY"))
        no_proxy = os.getenv("ZEPHYR_NO_PROXY", os.getenv("NO_PROXY"))
        socks_proxy = os.getenv("ZEPHYR_SOCKS_PROXY", os.getenv("SOCKS_PROXY"))

        # Custom headers - service-specific only
        custom_headers = get_custom_headers("ZEPHYR_CUSTOM_HEADERS")

        # Client certificate settings
        client_cert = os.getenv("ZEPHYR_CLIENT_CERT")
        client_key = os.getenv("ZEPHYR_CLIENT_KEY")
        client_key_password = os.getenv("ZEPHYR_CLIENT_KEY_PASSWORD")

        return cls(
            url=url,
            auth_type=auth_type,
            api_token=api_token,
            username=username,
            password=password,
            personal_token=personal_token,
            oauth_config=oauth_config,
            ssl_verify=ssl_verify,
            project_key=project_key,
            http_proxy=http_proxy,
            https_proxy=https_proxy,
            no_proxy=no_proxy,
            socks_proxy=socks_proxy,
            custom_headers=custom_headers,
            client_cert=client_cert,
            client_key=client_key,
            client_key_password=client_key_password,
        )

    def is_auth_configured(self) -> bool:
        """Check if authentication configuration is complete and valid.

        Returns:
            bool: True if authentication is fully configured, False otherwise.
        """
        logger = logging.getLogger("mcp-atlassian.zephyr.config")
        if self.auth_type == "oauth":
            if self.oauth_config:
                if isinstance(self.oauth_config, OAuthConfig):
                    if (
                        self.oauth_config.client_id
                        and self.oauth_config.client_secret
                        and self.oauth_config.redirect_uri
                        and self.oauth_config.scope
                        and self.oauth_config.cloud_id
                    ):
                        return True
                    elif (
                        not self.oauth_config.client_id
                        and not self.oauth_config.client_secret
                    ):
                        logger.debug(
                            "Minimal OAuth config detected - expecting "
                            "user-provided tokens via headers"
                        )
                        return True
                elif isinstance(self.oauth_config, BYOAccessTokenOAuthConfig):
                    if self.oauth_config.cloud_id and self.oauth_config.access_token:
                        return True

            logger.warning("Incomplete OAuth configuration detected")
            return False
        elif self.auth_type == "bearer":
            return bool(self.api_token)
        elif self.auth_type == "pat":
            return bool(self.personal_token)
        elif self.auth_type == "basic":
            return bool(self.username and self.password)
        logger.warning(
            f"Unknown or unsupported auth_type: {self.auth_type} in ZephyrConfig"
        )
        return False
