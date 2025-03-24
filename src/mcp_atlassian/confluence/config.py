"""Configuration module for the Confluence client."""

import os
from dataclasses import dataclass
from typing import Literal

from ..utils import is_atlassian_cloud_url


@dataclass
class ConfluenceConfig:
    """Confluence API configuration."""

    url: str  # Base URL for Confluence
    auth_type: Literal["basic", "token"]  # Authentication type
    username: str | None = None  # Email or username
    api_token: str | None = None  # API token used as password
    personal_token: str | None = None  # Personal access token (Server/DC)
    ssl_verify: bool = True  # Whether to verify SSL certificates
    spaces_filter: str | None = None  # List of space keys to filter searches

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
    def from_env(cls) -> "ConfluenceConfig":
        """Create configuration from environment variables.

        Returns:
            ConfluenceConfig with values from environment variables

        Raises:
            ValueError: If any required environment variable is missing
        """
        url = os.getenv("CONFLUENCE_URL")
        if not url:
            error_msg = "Missing required CONFLUENCE_URL environment variable"
            raise ValueError(error_msg)

        # Determine authentication type based on available environment variables
        username = os.getenv("CONFLUENCE_USERNAME")
        api_token = os.getenv("CONFLUENCE_API_TOKEN")
        personal_token = os.getenv("CONFLUENCE_PERSONAL_TOKEN")

        # Use the shared utility function directly
        is_cloud = is_atlassian_cloud_url(url)

        if is_cloud:
            if username and api_token:
                auth_type = "basic"
            else:
                error_msg = "Cloud authentication requires CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN"
                raise ValueError(error_msg)
        else:  # Server/Data Center
            if personal_token:
                auth_type = "token"
            elif username and api_token:
                # Allow basic auth for Server/DC too
                auth_type = "basic"
            else:
                error_msg = "Server/Data Center authentication requires CONFLUENCE_PERSONAL_TOKEN"
                raise ValueError(error_msg)

        # SSL verification (for Server/DC)
        ssl_verify_env = os.getenv("CONFLUENCE_SSL_VERIFY", "true").lower()
        ssl_verify = ssl_verify_env not in ("false", "0", "no")

        # Get the spaces filter if provided
        spaces_filter = os.getenv("CONFLUENCE_SPACES_FILTER")

        return cls(
            url=url,
            auth_type=auth_type,
            username=username,
            api_token=api_token,
            personal_token=personal_token,
            ssl_verify=ssl_verify,
            spaces_filter=spaces_filter,
        )
