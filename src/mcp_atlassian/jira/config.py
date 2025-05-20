"""Configuration module for Jira API interactions."""

import logging
import os
from dataclasses import dataclass
from typing import Literal

from ..utils.oauth import OAuthConfig
from ..utils.urls import is_atlassian_cloud_url


@dataclass
class JiraConfig:
    """Jira API configuration.

    Handles authentication for Jira Cloud and Server/Data Center:
    - Cloud: username/API token (basic auth) or OAuth 2.0 (3LO)
    - Server/DC: personal access token or basic auth
    """

    url: str  # Base URL for Jira
    auth_type: Literal["basic", "token", "oauth"]  # Authentication type
    username: str | None = None  # Email or username (Cloud)
    api_token: str | None = None  # API token (Cloud)
    personal_token: str | None = None  # Personal access token (Server/DC)
    oauth_config: OAuthConfig | None = None  # OAuth 2.0 configuration
    ssl_verify: bool = True  # Whether to verify SSL certificates
    projects_filter: str | None = None  # List of project keys to filter searches
    http_proxy: str | None = None  # HTTP proxy URL
    https_proxy: str | None = None  # HTTPS proxy URL
    no_proxy: str | None = None  # Comma-separated list of hosts to bypass proxy
    socks_proxy: str | None = None  # SOCKS proxy URL (optional)

    @property
    def is_cloud(self) -> bool:
        """Check if this is a cloud instance.

        Returns:
            True if this is a cloud instance (atlassian.net), False otherwise.
            Localhost URLs are always considered non-cloud (Server/Data Center).
        """
        return is_atlassian_cloud_url(self.url)

    @property
    def verify_ssl(self) -> bool:
        """Compatibility property for old code.

        Returns:
            The ssl_verify value
        """
        return self.ssl_verify

    @classmethod
    def from_env(cls) -> "JiraConfig":
        """Create configuration from environment variables.

        Returns:
            JiraConfig with values from environment variables

        Raises:
            ValueError: If required environment variables are missing or invalid
        """
        url = os.getenv("JIRA_URL")
        if not url:
            error_msg = "Missing required JIRA_URL environment variable"
            raise ValueError(error_msg)

        # Determine authentication type based on available environment variables
        username = os.getenv("JIRA_USERNAME")
        api_token = os.getenv("JIRA_API_TOKEN")
        personal_token = os.getenv("JIRA_PERSONAL_TOKEN")

        # Check for OAuth configuration
        oauth_config = OAuthConfig.from_env()
        auth_type = None

        # Use the shared utility function directly
        is_cloud = is_atlassian_cloud_url(url)

        if oauth_config and oauth_config.cloud_id:
            # OAuth takes precedence if fully configured
            auth_type = "oauth"
        elif is_cloud:
            if username and api_token:
                auth_type = "basic"
            else:
                error_msg = "Cloud authentication requires JIRA_USERNAME and JIRA_API_TOKEN, or OAuth configuration"
                raise ValueError(error_msg)
        else:  # Server/Data Center
            if personal_token:
                auth_type = "token"
            elif username and api_token:
                # Allow basic auth for Server/DC too
                auth_type = "basic"
            else:
                error_msg = "Server/Data Center authentication requires JIRA_PERSONAL_TOKEN or JIRA_USERNAME and JIRA_API_TOKEN"
                raise ValueError(error_msg)

        # SSL verification (for Server/DC)
        ssl_verify_env = os.getenv("JIRA_SSL_VERIFY", "true").lower()
        ssl_verify = ssl_verify_env not in ("false", "0", "no")

        # Get the projects filter if provided
        projects_filter = os.getenv("JIRA_PROJECTS_FILTER")

        # Proxy settings
        http_proxy = os.getenv("JIRA_HTTP_PROXY", os.getenv("HTTP_PROXY"))
        https_proxy = os.getenv("JIRA_HTTPS_PROXY", os.getenv("HTTPS_PROXY"))
        no_proxy = os.getenv("JIRA_NO_PROXY", os.getenv("NO_PROXY"))
        socks_proxy = os.getenv("JIRA_SOCKS_PROXY", os.getenv("SOCKS_PROXY"))

        return cls(
            url=url,
            auth_type=auth_type,
            username=username,
            api_token=api_token,
            personal_token=personal_token,
            oauth_config=oauth_config,
            ssl_verify=ssl_verify,
            projects_filter=projects_filter,
            http_proxy=http_proxy,
            https_proxy=https_proxy,
            no_proxy=no_proxy,
            socks_proxy=socks_proxy,
        )

    def is_auth_configured(self) -> bool:
        """Check if the current authentication configuration is complete and valid for making API calls.

        Returns:
            bool: True if authentication is fully configured, False otherwise.
        """
        logger = logging.getLogger("mcp-atlassian.jira.config")
        if self.auth_type == "oauth":
            return bool(
                self.oauth_config
                and self.oauth_config.client_id
                and self.oauth_config.client_secret
                and self.oauth_config.redirect_uri
                and self.oauth_config.scope
                and self.oauth_config.cloud_id
            )
        elif self.auth_type == "token":
            return bool(self.personal_token)
        elif self.auth_type == "basic":
            return bool(self.username and self.api_token)
        logger.warning(
            f"Unknown or unsupported auth_type: {self.auth_type} in JiraConfig"
        )
        return False
