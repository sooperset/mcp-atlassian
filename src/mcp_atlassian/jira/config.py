"""Configuration module for Jira API interactions."""

import os
from dataclasses import dataclass
from typing import Literal

from ..utils import is_atlassian_cloud_url
from ..utils.io import is_multi_user_mode


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
    def from_env(cls) -> "JiraConfig | None":
        """Create configuration from environment variables.

        Returns:
            JiraConfig with values from environment variables or None if in multi-user mode
            and required variables are missing.

        Raises:
            ValueError: If required environment variables are missing or invalid
        """
        url = cls.get_url()

        # Determine authentication type based on available environment variables
        username = os.getenv("JIRA_USERNAME")
        api_token = os.getenv("JIRA_API_TOKEN")
        personal_token = os.getenv("JIRA_PERSONAL_TOKEN")

        # Use the shared utility function directly
        is_cloud = is_atlassian_cloud_url(url)

        match (is_cloud, bool(username and api_token), bool(personal_token)):
            case (True, True, _):
                auth_type = "basic"
            case (True, False, _):
                msg = "Cloud authentication requires JIRA_USERNAME and JIRA_API_TOKEN"
                raise ValueError(msg)
            case (False, _, True):
                auth_type = "token"
            case (False, True, False):
                auth_type = "basic"
            case (False, False, False):
                msg = "Server/Data Center authentication requires JIRA_PERSONAL_TOKEN"
                raise ValueError(msg)

        # SSL verification (for Server/DC)
        ssl_verify_env = os.getenv("JIRA_SSL_VERIFY", "true").lower()
        ssl_verify = ssl_verify_env not in {"false", "0", "no"}

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

    @classmethod
    def from_request(
        cls,
        username: str | None = None,
        api_token: str | None = None,
        personal_token: str | None = None,
        projects_filter: str | None = None,
    ) -> "JiraConfig":
        """Create configuration directly from provided details.

        Returns:
            JiraConfig with provided values.

        Raises:
            ValueError: If required environment variables are missing or invalid
        """
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
            projects_filter=projects_filter,
        )

    @staticmethod
    def get_url() -> str:
        """Get the Jira URL from environment variables.

        Returns:
            The Jira URL
        """
        url = os.getenv("JIRA_URL")
        if not url:
            error_msg = "Missing required JIRA_URL environment variable"
            raise ValueError(error_msg)
        return url