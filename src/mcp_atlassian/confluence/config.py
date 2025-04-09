"""Configuration module for the Confluence client."""

import os
from dataclasses import dataclass
from typing import Literal

from ..utils import is_atlassian_cloud_url
from ..utils.io import is_multi_user_mode


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
    def from_env(cls) -> "ConfluenceConfig | None":
        """Create configuration from environment variables.

        Returns:
            ConfluenceConfig with values from environment variables or None if in multi-user mode
            and required variables are missing.

        Raises:
            ValueError: If any required environment variable is missing
        """
        url = cls.get_url()

        # Determine authentication type based on available environment variables
        username = os.getenv("CONFLUENCE_USERNAME")
        api_token = os.getenv("CONFLUENCE_API_TOKEN")
        personal_token = os.getenv("CONFLUENCE_PERSONAL_TOKEN")

        # Use the shared utility function directly
        is_cloud = is_atlassian_cloud_url(url)

        match (is_cloud, bool(username and api_token), bool(personal_token)):
            case (True, True, _):
                auth_type = "basic"
            case (True, False, _):
                msg = "Cloud authentication requires CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN"
                raise ValueError(msg)
            case (False, _, True):
                auth_type = "token"
            case (False, True, False):
                auth_type = "basic"
            case (False, False, False):
                msg = "Server/Data Center authentication requires CONFLUENCE_PERSONAL_TOKEN"
                raise ValueError(msg)

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

    @classmethod
    def from_request(
        cls,
        username: str | None = None,
        api_token: str | None = None,
        personal_token: str | None = None,
        ssl_verify: bool = True,
        spaces_filter: str | None = None,
    ) -> "ConfluenceConfig":
        """Create configuration directly from provided details."""
        url = cls.get_url()

        # SSL verification (for Server/DC)
        ssl_verify_env = os.getenv("JIRA_SSL_VERIFY", "true").lower()
        ssl_verify = ssl_verify_env not in {"false", "0", "no"}

        is_cloud = is_atlassian_cloud_url(url)

        match (is_cloud, bool(username and api_token), bool(personal_token)):
            case (True, True, _):
                auth_type = "basic"
            case (True, False, _):
                msg = "Cloud authentication requires username and api_token."
                raise ValueError(msg)
            case (False, _, True):
                auth_type = "token"
            case (False, True, False):
                auth_type = "basic"
            case (False, False, False):
                msg = "Server/DC authentication requires personal_token or (username and api_token)."
                raise ValueError(msg)

        return cls(
            url=url,
            auth_type=auth_type,
            username=username,
            api_token=api_token,
            personal_token=personal_token,
            ssl_verify=ssl_verify,
            spaces_filter=spaces_filter,
        )

    @staticmethod
    def get_url() -> str:
        """Get the Confluence URL from environment variables.

        Returns:
            The Confluence URL
        """
        url = os.getenv("CONFLUENCE_URL")
        if not url:
            error_msg = "Missing required CONFLUENCE_URL environment variable"
            raise ValueError(error_msg)
        return url