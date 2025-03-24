"""Configuration module for Jira API interactions."""

import os
from dataclasses import dataclass
from typing import Literal

from ..utils import is_atlassian_cloud_url


@dataclass
class JiraConfig:
    """Jira API configuration.

    Handles authentication for both Jira Cloud (using username/API token)
    and Jira Server/Data Center (using personal access token).
    """

    url: str  # Base URL for Jira
    auth_type: Literal["basic", "token"]  # Authentication type
    username: str | None = None  # Email or username (Cloud)
    api_token: str | None = None  # API token (Cloud)
    personal_token: str | None = None  # Personal access token (Server/DC)
    ssl_verify: bool = True  # Whether to verify SSL certificates
    projects_filter: str | None = None  # List of project keys to filter searches

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

        # Use the shared utility function directly
        is_cloud = is_atlassian_cloud_url(url)

        if is_cloud:
            if username and api_token:
                auth_type = "basic"
            else:
                error_msg = (
                    "Cloud authentication requires JIRA_USERNAME and JIRA_API_TOKEN"
                )
                raise ValueError(error_msg)
        else:  # Server/Data Center
            if personal_token:
                auth_type = "token"
            elif username and api_token:
                # Allow basic auth for Server/DC too
                auth_type = "basic"
            else:
                error_msg = (
                    "Server/Data Center authentication requires JIRA_PERSONAL_TOKEN"
                )
                raise ValueError(error_msg)

        # SSL verification (for Server/DC)
        ssl_verify_env = os.getenv("JIRA_SSL_VERIFY", "true").lower()
        ssl_verify = ssl_verify_env not in ("false", "0", "no")

        # Get the projects filter if provided
        projects_filter = os.getenv("JIRA_PROJECTS_FILTER")

        return cls(
            url=url,
            auth_type=auth_type,
            username=username,
            api_token=api_token,
            personal_token=personal_token,
            ssl_verify=ssl_verify,
            projects_filter=projects_filter,
        )
