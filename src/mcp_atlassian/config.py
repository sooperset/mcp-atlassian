from dataclasses import dataclass


@dataclass
class ConfluenceConfig:
    """Confluence API configuration."""

    url: str  # Base URL for Confluence
    username: str  # Email or username
    api_token: str  # API token used as password

    @property
    def is_cloud(self) -> bool:
        """Check if this is a cloud instance."""
        return "atlassian.net" in self.url


@dataclass
class JiraConfig:
    """Jira API configuration."""

    url: str  # Base URL for Jira
    username: str = ""  # Email or username
    api_token: str = ""  # API token used as password for cloud
    personal_token: str = ""  # Personal Access Token used for Server/Data Center
    verify_ssl: bool = True  # Whether to verify SSL certificates

    @property
    def is_cloud(self) -> bool:
        """Check if this is a cloud instance."""
        return "atlassian.net" in self.url
