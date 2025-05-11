"""Base client module for Confluence API interactions."""

import logging
import os
from typing import Any

from atlassian import Confluence
from requests import Session

from ..exceptions import MCPAtlassianAuthenticationError
from ..utils.logging import log_config_param
from ..utils.oauth import configure_oauth_session
from ..utils.ssl import configure_ssl_verification
from .config import ConfluenceConfig

# Configure logging
logger = logging.getLogger("mcp-atlassian")


class ConfluenceClient:
    """Base client for Confluence API interactions."""

    def __init__(self, config: ConfluenceConfig | None = None) -> None:
        """Initialize the Confluence client with given or environment config.

        Args:
            config: Configuration for Confluence client. If None, will load from
                environment.

        Raises:
            ValueError: If configuration is invalid or environment variables are missing
            MCPAtlassianAuthenticationError: If OAuth authentication fails
        """
        self.config = config or ConfluenceConfig.from_env()

        # Initialize the Confluence client based on auth type
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

            # The Confluence API URL with OAuth is different
            api_url = f"https://api.atlassian.com/ex/confluence/{self.config.oauth_config.cloud_id}"

            logger.debug(
                f"Initializing Confluence client with OAuth. API URL: {api_url}, Session Headers (before API init): {session.headers}"
            )
            # Initialize Confluence with the session
            self.confluence = Confluence(
                url=api_url,
                session=session,
                cloud=True,  # OAuth is only for Cloud
                verify_ssl=self.config.ssl_verify,
            )
            logger.debug(
                f"Confluence client _session after init: {self.confluence._session.__dict__}"
            )
        elif self.config.auth_type == "token":
            logger.debug(
                f"Initializing Confluence client with Token (PAT) auth. URL: {self.config.url}, Token (first 10): {str(self.config.personal_token)[:10] if self.config.personal_token else 'None'}"
            )
            self.confluence = Confluence(
                url=self.config.url,
                token=self.config.personal_token,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )
        else:  # basic auth
            logger.debug(
                f"Initializing Confluence client with Basic auth. URL: {self.config.url}, Username: {self.config.username}"
            )
            self.confluence = Confluence(
                url=self.config.url,
                username=self.config.username,
                password=self.config.api_token,  # API token is used as password
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )

        # Configure SSL verification using the shared utility
        configure_ssl_verification(
            service_name="Confluence",
            url=self.config.url,
            session=self.confluence._session,
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
            self.confluence._session.proxies.update(proxies)
            for k, v in proxies.items():
                log_config_param(
                    logger, "Confluence", f"{k.upper()}_PROXY", v, sensitive=True
                )
        if self.config.no_proxy and isinstance(self.config.no_proxy, str):
            os.environ["NO_PROXY"] = self.config.no_proxy
            log_config_param(logger, "Confluence", "NO_PROXY", self.config.no_proxy)

        # Import here to avoid circular imports
        from ..preprocessing.confluence import ConfluencePreprocessor

        self.preprocessor = ConfluencePreprocessor(
            base_url=self.config.url, confluence_client=self.confluence
        )

    def get_user_details_by_accountid(
        self, account_id: str, expand: str = None
    ) -> dict[str, Any]:
        """Get user details by account ID.

        Args:
            account_id: The account ID of the user
            expand: OPTIONAL expand for get status of user.
                Possible param is "status". Results are "Active, Deactivated"

        Returns:
            User details as a dictionary

        Raises:
            Various exceptions from the Atlassian API if user doesn't exist or
            if there are permission issues
        """
        return self.confluence.get_user_details_by_accountid(account_id, expand)

    def _process_html_content(
        self, html_content: str, space_key: str
    ) -> tuple[str, str]:
        """Process HTML content into both HTML and markdown formats.

        Args:
            html_content: Raw HTML content from Confluence
            space_key: The key of the space containing the content

        Returns:
            Tuple of (processed_html, processed_markdown)
        """
        return self.preprocessor.process_html_content(html_content, space_key)

    def get_current_user_info(self) -> dict[str, Any]:
        """
        Retrieve details for the currently authenticated user by calling Confluence's '/rest/api/user/current' endpoint.

        Returns:
            dict[str, Any]: The user details as returned by the API.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails or the response is not valid user data.
        """
        from requests.exceptions import HTTPError

        try:
            user_data = self.confluence.get("rest/api/user/current")
            if not isinstance(user_data, dict):
                logger.error(
                    f"Confluence /rest/api/user/current endpoint returned non-dict data type: {type(user_data)}. "
                    f"Response text (partial): {str(user_data)[:500]}"
                )
                raise MCPAtlassianAuthenticationError(
                    "Confluence token validation failed: Did not receive valid JSON user data from /rest/api/user/current endpoint."
                )
            return user_data
        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code in [
                401,
                403,
            ]:
                logger.warning(
                    f"Confluence token validation failed with HTTP {http_err.response.status_code} for /rest/api/user/current."
                )
                raise MCPAtlassianAuthenticationError(
                    f"Confluence token validation failed: {http_err.response.status_code} from /rest/api/user/current"
                ) from http_err
            logger.error(
                f"HTTPError when calling Confluence /rest/api/user/current: {http_err}",
                exc_info=True,
            )
            raise MCPAtlassianAuthenticationError(
                f"Confluence token validation failed with HTTPError: {http_err}"
            ) from http_err
        except Exception as e:
            logger.error(
                f"Unexpected error fetching current Confluence user details: {e}",
                exc_info=True,
            )
            raise MCPAtlassianAuthenticationError(
                f"Confluence token validation failed: {e}"
            ) from e
