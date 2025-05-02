"""Config for Bitbucket Server integration."""

import os
from typing import Any

from .constants import (
    AUTH_TYPE_BASIC,
    AUTH_TYPE_PERSONAL_TOKEN,
    DEFAULT_SSL_VERIFY,
    ENV_BITBUCKET_API_TOKEN,
    ENV_BITBUCKET_PERSONAL_TOKEN,
    ENV_BITBUCKET_PROJECTS_FILTER,
    ENV_BITBUCKET_SSL_VERIFY,
    ENV_BITBUCKET_URL,
    ENV_BITBUCKET_USERNAME,
)


class BitbucketServerConfig:
    """Configuration for Bitbucket Server instance."""

    def __init__(
        self,
        url: str,
        auth_type: str,
        username: str | None = None,
        api_token: str | None = None,
        personal_token: str | None = None,
        ssl_verify: bool = DEFAULT_SSL_VERIFY,
        projects_filter: str | None = None,
    ) -> None:
        """Initialize Bitbucket Server Config.

        Args:
            url: Bitbucket Server URL
            auth_type: Auth type ("basic" or "personal_token")
            username: Username for basic auth
            api_token: API token for basic auth
            personal_token: Personal access token for token auth
            ssl_verify: Whether to verify SSL certificates
            projects_filter: Comma-separated list of project keys to filter by
        """
        self.url = url.rstrip("/")
        self.auth_type = auth_type
        self.username = username
        self.api_token = api_token
        self.personal_token = personal_token
        self.ssl_verify = ssl_verify
        self.projects_filter = projects_filter

        # Validate required auth params based on auth_type
        if auth_type == AUTH_TYPE_BASIC and (not username or not api_token):
            raise ValueError(
                "For basic authentication, both username and API token are required."
            )
        if auth_type == AUTH_TYPE_PERSONAL_TOKEN and not personal_token:
            raise ValueError(
                "For personal token authentication, a personal token is required."
            )

    @classmethod
    def from_env(cls) -> "BitbucketServerConfig":
        """Create Bitbucket Server config from environment variables.

        Returns:
            BitbucketServerConfig instance

        Raises:
            ValueError: If required environment variables are missing
        """
        url = os.getenv(ENV_BITBUCKET_URL)
        if not url:
            raise ValueError(f"Environment variable {ENV_BITBUCKET_URL} is required")

        # Determine auth type based on available credentials
        personal_token = os.getenv(ENV_BITBUCKET_PERSONAL_TOKEN)
        username = os.getenv(ENV_BITBUCKET_USERNAME)
        api_token = os.getenv(ENV_BITBUCKET_API_TOKEN)

        if personal_token:
            auth_type = AUTH_TYPE_PERSONAL_TOKEN
        elif username and api_token:
            auth_type = AUTH_TYPE_BASIC
        else:
            raise ValueError("No valid authentication credentials found in environment")

        # Parse SSL verification setting
        ssl_verify_str = os.getenv(ENV_BITBUCKET_SSL_VERIFY, str(DEFAULT_SSL_VERIFY))
        ssl_verify = ssl_verify_str.lower() != "false"

        # Get optional projects filter
        projects_filter = os.getenv(ENV_BITBUCKET_PROJECTS_FILTER)

        return cls(
            url=url,
            auth_type=auth_type,
            username=username,
            api_token=api_token,
            personal_token=personal_token,
            ssl_verify=ssl_verify,
            projects_filter=projects_filter,
        )

    def get_auth(self) -> Any:
        """Get authentication credentials in the format expected by the client.

        Returns:
            Authentication credentials as expected by the client
        """
        if self.auth_type == AUTH_TYPE_BASIC:
            return (self.username, self.api_token)
        elif self.auth_type == AUTH_TYPE_PERSONAL_TOKEN:
            return {"Authorization": f"Bearer {self.personal_token}"}
        else:
            raise ValueError(f"Unsupported auth type: {self.auth_type}")

    # Use default dataclass __repr__ method
