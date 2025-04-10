"""Base client module for Jira API interactions."""

import logging

from atlassian import Jira

from mcp_atlassian.preprocessing import JiraPreprocessor
from mcp_atlassian.utils.ssl import configure_ssl_verification

from .config import JiraConfig

# Configure logging
logger = logging.getLogger("mcp-jira")


class JiraClient:
    """Base client for Jira API interactions."""

    def __init__(self, config: JiraConfig | None = None) -> None:
        """Initialize the Jira client with a given configuration.

        Args:
            config: Jira configuration object. If None, will be loaded from environment variables.

        Raises:
            TypeError: If configuration is invalid.

        """
        if config is None:
            self.config = JiraConfig.from_env()
        else:
            self.config = config

        # Initialize the Jira client based on auth type
        if self.config.auth_type == "token":
            self.jira = Jira(
                url=self.config.url,
                token=self.config.personal_token,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )
        else:  # basic auth
            self.jira = Jira(
                url=self.config.url,
                username=self.config.username,
                password=self.config.api_token,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )

        # Configure SSL verification using the shared utility
        configure_ssl_verification(
            service_name="Jira",
            url=self.config.url,
            session=self.jira._session,
            ssl_verify=self.config.ssl_verify,
        )

        # Initialize the text preprocessor for text processing capabilities
        self.preprocessor = JiraPreprocessor(base_url=self.config.url)

        # Cache for frequently used data
        self._field_ids: dict[str, str] | None = None
        self._current_user_account_id: str | None = None

    def _clean_text(self, text: str) -> str:
        """Clean text content by:
        1. Processing user mentions and links
        2. Converting HTML/wiki markup to markdown.

        Args:
            text: Text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Otherwise create a temporary one
        _ = self.config.url if hasattr(self, "config") else ""
        return self.preprocessor.clean_jira_text(text)

    def _markdown_to_jira(self, markdown_text: str) -> str:
        """Convert Markdown syntax to Jira markup syntax.

        Args:
            markdown_text: Text in Markdown format

        Returns:
            Text in Jira markup format
        """
        if not markdown_text:
            return ""

        # Use the shared preprocessor if available
        if hasattr(self, "preprocessor"):
            return self.preprocessor.markdown_to_jira(markdown_text)

        # Otherwise create a temporary one
        _ = self.config.url if hasattr(self, "config") else ""
        return self.preprocessor.markdown_to_jira(markdown_text)
