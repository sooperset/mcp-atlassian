"""Base client module for Bitbucket API interactions."""

import logging
from typing import Any

from requests import Session

from ..exceptions import MCPAtlassianAuthenticationError
from ..utils.logging import mask_sensitive
from ..utils.oauth import configure_oauth_session
from ..utils.ssl import configure_ssl_verification
from .config import BitbucketConfig

logger = logging.getLogger("mcp-bitbucket")


class BitbucketClient:
    """Base client for Bitbucket API interactions."""

    config: BitbucketConfig
    session: Session

    def __init__(self, config: BitbucketConfig | None = None) -> None:
        """Initialize the Bitbucket client with configuration options.

        Args:
            config: Optional configuration object (will use env vars if not provided)

        Raises:
            ValueError: If configuration is invalid or required credentials are missing
            MCPAtlassianAuthenticationError: If OAuth authentication fails
        """
        # Load configuration from environment variables if not provided
        self.config = config or BitbucketConfig.from_env()

        # Create a session
        self.session = Session()

        # Configure SSL verification
        configure_ssl_verification(self.session, self.config.ssl_verify)

        # Set up authentication based on auth type
        if self.config.auth_type == "oauth":
            if not self.config.oauth_config:
                error_msg = "OAuth authentication requires oauth_config"
                raise ValueError(error_msg)

            # Configure the session with OAuth authentication
            if not configure_oauth_session(self.session, self.config.oauth_config):
                error_msg = "Failed to configure OAuth session"
                raise MCPAtlassianAuthenticationError(error_msg)

            logger.debug("Initialized Bitbucket client with OAuth authentication")

        elif self.config.auth_type == "pat":
            # For Bitbucket Cloud, use Bearer token
            # For Bitbucket Server, use HTTP Basic Auth with token as password
            if self.config.is_cloud:
                self.session.headers.update(
                    {
                        "Authorization": f"Bearer {self.config.personal_token}",
                        "Accept": "application/json",
                    }
                )
                logger.debug(
                    f"Initialized Bitbucket Cloud client with PAT authentication. "
                    f"URL: {self.config.url}, "
                    f"Token (masked): {mask_sensitive(str(self.config.personal_token))}"
                )
            else:
                # Bitbucket Server uses HTTP Basic Auth with token
                self.session.auth = ("x-token-auth", self.config.personal_token)
                self.session.headers.update({"Accept": "application/json"})
                logger.debug(
                    f"Initialized Bitbucket Server client with PAT authentication. "
                    f"URL: {self.config.url}"
                )

        else:  # basic auth
            self.session.auth = (self.config.username, self.config.password)
            self.session.headers.update({"Accept": "application/json"})
            logger.debug(
                f"Initialized Bitbucket client with Basic authentication. "
                f"URL: {self.config.url}, Username: {self.config.username}"
            )

        # Add custom headers if provided
        if self.config.custom_headers:
            self.session.headers.update(self.config.custom_headers)

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Make a GET request to the Bitbucket API.

        Args:
            endpoint: API endpoint (relative to base URL)
            params: Optional query parameters

        Returns:
            Response data (usually dict or list)

        Raises:
            requests.HTTPError: If the request fails
        """
        url = f"{self.config.url}{endpoint}"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, json_data: dict[str, Any] | None = None) -> Any:
        """Make a POST request to the Bitbucket API.

        Args:
            endpoint: API endpoint (relative to base URL)
            json_data: Optional JSON data to send

        Returns:
            Response data (usually dict)

        Raises:
            requests.HTTPError: If the request fails
        """
        url = f"{self.config.url}{endpoint}"
        response = self.session.post(url, json=json_data)
        response.raise_for_status()
        return response.json()

    def _put(self, endpoint: str, json_data: dict[str, Any] | None = None) -> Any:
        """Make a PUT request to the Bitbucket API.

        Args:
            endpoint: API endpoint (relative to base URL)
            json_data: Optional JSON data to send

        Returns:
            Response data (usually dict)

        Raises:
            requests.HTTPError: If the request fails
        """
        url = f"{self.config.url}{endpoint}"
        response = self.session.put(url, json=json_data)
        response.raise_for_status()
        return response.json()

    def _delete(self, endpoint: str) -> Any:
        """Make a DELETE request to the Bitbucket API.

        Args:
            endpoint: API endpoint (relative to base URL)

        Returns:
            Response data (if any)

        Raises:
            requests.HTTPError: If the request fails
        """
        url = f"{self.config.url}{endpoint}"
        response = self.session.delete(url)
        response.raise_for_status()
        if response.text:
            return response.json()
        return None
