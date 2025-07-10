"""Base client module for Confluence API interactions."""

import logging
import os

from atlassian import Confluence
from requests import Session

from ..exceptions import MCPAtlassianAuthenticationError
from ..utils.logging import get_masked_session_headers, log_config_param, mask_sensitive
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

            # Initialize Confluence with the session
            self.confluence = Confluence(
                url=api_url,
                session=session,
                cloud=True,  # OAuth is only for Cloud
                verify_ssl=self.config.ssl_verify,
            )
        elif self.config.auth_type == "pat":
            logger.debug(
                f"Initializing Confluence client with Token (PAT) auth. "
                f"URL: {self.config.url}, "
                f"Token (masked): {mask_sensitive(str(self.config.personal_token))}"
            )
            self.confluence = Confluence(
                url=self.config.url,
                token=self.config.personal_token,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )
        else:  # basic auth
            logger.debug(
                f"Initializing Confluence client with Basic auth. "
                f"URL: {self.config.url}, Username: {self.config.username}, "
                f"API Token present: {bool(self.config.api_token)}, "
                f"Is Cloud: {self.config.is_cloud}"
            )
            self.confluence = Confluence(
                url=self.config.url,
                username=self.config.username,
                password=self.config.api_token,  # API token is used as password
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )
            logger.debug(
                f"Confluence client initialized. "
                f"Session headers (Authorization masked): "
                f"{get_masked_session_headers(dict(self.confluence._session.headers))}"
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

        # Apply custom headers if configured
        if self.config.custom_headers:
            self._apply_custom_headers()

        # Import here to avoid circular imports
        from ..preprocessing.confluence import ConfluencePreprocessor

        self.preprocessor = ConfluencePreprocessor(base_url=self.config.url)

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
                "Testing Confluence authentication by making a simple API call..."
            )
            # Make a simple API call to test authentication
            spaces = self.confluence.get_all_spaces(start=0, limit=1)
            if spaces is not None:
                logger.info(
                    f"Confluence authentication successful. "
                    f"API call returned {len(spaces.get('results', []))} spaces."
                )
            else:
                logger.warning(
                    "Confluence authentication test returned None - "
                    "this may indicate an issue"
                )
        except Exception as e:
            error_msg = f"Confluence authentication validation failed: {e}"
            logger.error(error_msg)
            logger.debug(
                f"Authentication headers during failure: "
                f"{get_masked_session_headers(dict(self.confluence._session.headers))}"
            )
            raise MCPAtlassianAuthenticationError(error_msg) from e

    def _apply_custom_headers(self) -> None:
        """Apply custom headers to the Confluence session."""
        if not self.config.custom_headers:
            return

        logger.debug(
            f"Applying {len(self.config.custom_headers)} custom headers to Confluence session"
        )
        for header_name, header_value in self.config.custom_headers.items():
            self.confluence._session.headers[header_name] = header_value
            logger.debug(f"Applied custom header: {header_name}")

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
        return self.preprocessor.process_html_content(
            html_content, space_key, self.confluence
        )
