"""Base client module for Jira API interactions."""

import logging
import os
from typing import Any, Literal

from atlassian import Jira
from requests import Session

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.preprocessing import JiraPreprocessor
from mcp_atlassian.utils.logging import (
    get_masked_session_headers,
    log_config_param,
    mask_sensitive,
)
from mcp_atlassian.utils.oauth import configure_oauth_session
from mcp_atlassian.utils.ssl import configure_ssl_verification

from .config import JiraConfig

# Configure logging
logger = logging.getLogger("mcp-jira")


class JiraClient:
    """Base client for Jira API interactions."""

    _field_ids_cache: list[dict[str, Any]] | None
    _current_user_account_id: str | None

    config: JiraConfig
    preprocessor: JiraPreprocessor

    def __init__(self, config: JiraConfig | None = None) -> None:
        """Initialize the Jira client with configuration options.

        Args:
            config: Optional configuration object (will use env vars if not provided)

        Raises:
            ValueError: If configuration is invalid or required credentials are missing
            MCPAtlassianAuthenticationError: If OAuth authentication fails
        """
        # Load configuration from environment variables if not provided
        self.config = config or JiraConfig.from_env()

        # Initialize the Jira client based on auth type
        if self.config.auth_type == "oauth":
            if not self.config.oauth_config or not self.config.oauth_config.cloud_id:
                error_msg = "OAuth authentication requires a valid cloud_id"
                raise ValueError(error_msg)

            # Create a session for OAuth
            session = Session()

            # Configure the session with OAuth authentication
            if not configure_oauth_session(session, self.config.oauth_config):
                error_msg = "Failed to configure OAuth session"
                raise MCPAtlassianAuthenticationError(error_msg)

            # The Jira API URL with OAuth is different
            api_url = (
                f"https://api.atlassian.com/ex/jira/{self.config.oauth_config.cloud_id}"
            )

            # Initialize Jira with the session
            self.jira = Jira(
                url=api_url,
                session=session,
                cloud=True,  # OAuth is only for Cloud
                verify_ssl=self.config.ssl_verify,
            )
        elif self.config.auth_type == "pat":
            logger.debug(
                f"Initializing Jira client with Token (PAT) auth. "
                f"URL: {self.config.url}, "
                f"Token (masked): {mask_sensitive(str(self.config.personal_token))}"
            )
            self.jira = Jira(
                url=self.config.url,
                token=self.config.personal_token,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )
        else:  # basic auth
            logger.debug(
                f"Initializing Jira client with Basic auth. "
                f"URL: {self.config.url}, Username: {self.config.username}, "
                f"API Token present: {bool(self.config.api_token)}, "
                f"Is Cloud: {self.config.is_cloud}"
            )
            self.jira = Jira(
                url=self.config.url,
                username=self.config.username,
                password=self.config.api_token,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )
            logger.debug(
                f"Jira client initialized. Session headers (Authorization masked): "
                f"{get_masked_session_headers(dict(self.jira._session.headers))}"
            )

        # Configure SSL verification using the shared utility
        configure_ssl_verification(
            service_name="Jira",
            url=self.config.url,
            session=self.jira._session,
            ssl_verify=self.config.ssl_verify,
        )

        # Proxy configuration
        proxies = {}
        if self.config.http_proxy:
            proxies["http"] = self.config.http_proxy
        if self.config.https_proxy:
            proxies["https"] = self.config.https_proxy
        if self.config.socks_proxy:
            proxies["socks"] = self.config.socks_proxy
        if proxies:
            self.jira._session.proxies.update(proxies)
            for k, v in proxies.items():
                log_config_param(
                    logger, "Jira", f"{k.upper()}_PROXY", v, sensitive=True
                )
        if self.config.no_proxy and isinstance(self.config.no_proxy, str):
            os.environ["NO_PROXY"] = self.config.no_proxy
            log_config_param(logger, "Jira", "NO_PROXY", self.config.no_proxy)

        # Apply custom headers if configured
        if self.config.custom_headers:
            self._apply_custom_headers()

        # Initialize the text preprocessor for text processing capabilities
        self.preprocessor = JiraPreprocessor(base_url=self.config.url)
        self._field_ids_cache = None
        self._current_user_account_id = None

        # Test authentication during initialization (in debug mode only)
        if logger.isEnabledFor(logging.DEBUG):
            try:
                self._validate_authentication()
            except MCPAtlassianAuthenticationError:
                logger.warning(
                    "Authentication validation failed during client initialization - "
                    "continuing anyway"
                )

    def _validate_authentication(self) -> None:
        """Validate authentication by making a simple API call."""
        try:
            logger.debug(
                "Testing Jira authentication by retrieving current user info..."
            )
            current_user = self.jira.myself()
            if current_user:
                logger.info(
                    f"Jira authentication successful. "
                    f"Current user: {current_user.get('displayName', 'Unknown')} "
                    f"({current_user.get('emailAddress', 'No email')})"
                )
            else:
                logger.warning(
                    "Jira authentication test returned empty user info - "
                    "this may indicate an issue"
                )
        except Exception as e:
            error_msg = f"Jira authentication validation failed: {e}"
            logger.error(error_msg)
            logger.debug(
                f"Authentication headers during failure: "
                f"{get_masked_session_headers(dict(self.jira._session.headers))}"
            )
            raise MCPAtlassianAuthenticationError(error_msg) from e

    def _apply_custom_headers(self) -> None:
        """Apply custom headers to the Jira session."""
        if not self.config.custom_headers:
            return

        logger.debug(
            f"Applying {len(self.config.custom_headers)} custom headers to Jira session"
        )
        for header_name, header_value in self.config.custom_headers.items():
            self.jira._session.headers[header_name] = header_value
            logger.debug(f"Applied custom header: {header_name}")

    def _clean_text(self, text: str) -> str:
        """Clean text content by:
        1. Processing user mentions and links
        2. Converting HTML/wiki markup to markdown

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
        """
        Convert Markdown syntax to Jira markup syntax.

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

    def get_paged(
        self,
        method: Literal["get", "post"],
        url: str,
        params_or_json: dict | None = None,
        *,
        absolute: bool = False,
    ) -> list[dict]:
        """
        Repeatly fetch paged data from Jira API using `nextPageToken` to paginate.

        Args:
            method: The HTTP method to use
            url: The URL to retrieve data from
            params_or_json: Optional query parameters or JSON data to send
            absolute: Whether to use absolute URL

        Returns:
            List of requested json data

        Raises:
            ValueError: If using paged request on non-cloud Jira
        """

        if not self.config.is_cloud:
            raise ValueError(
                "Paged requests are only available for Jira Cloud platform"
            )

        all_results: list[dict] = []
        current_data = params_or_json or {}

        while True:
            if method == "get":
                api_result = self.jira.get(
                    path=url, params=current_data, absolute=absolute
                )
            else:
                api_result = self.jira.post(
                    path=url, json=current_data, absolute=absolute
                )

            if not isinstance(api_result, dict):
                error_message = f"API result is not a dictionary: {api_result}"
                logger.error(error_message)
                raise ValueError(error_message)

            # Extract values from response
            all_results.append(api_result)

            # Check if this is the last page
            if "nextPageToken" not in api_result:
                break

            # Update for next iteration
            current_data["nextPageToken"] = api_result["nextPageToken"]

        return all_results

    def create_version(
        self,
        project: str,
        name: str,
        start_date: str = None,
        release_date: str = None,
        description: str = None,
    ) -> dict[str, Any]:
        """
        Create a new version in a Jira project.

        Args:
            project: The project key (e.g., 'PROJ')
            name: The name of the version
            start_date: The start date (YYYY-MM-DD, optional)
            release_date: The release date (YYYY-MM-DD, optional)
            description: Description of the version (optional)

        Returns:
            The created version object as returned by Jira
        """
        payload = {"project": project, "name": name}
        if start_date:
            payload["startDate"] = start_date
        if release_date:
            payload["releaseDate"] = release_date
        if description:
            payload["description"] = description
        logger.info(f"Creating Jira version: {payload}")
        result = self.jira.post("/rest/api/3/version", json=payload)
        if not isinstance(result, dict):
            error_message = f"Unexpected response from Jira API: {result}"
            raise ValueError(error_message)
        return result
