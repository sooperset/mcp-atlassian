"""Base client module for Confluence API interactions."""

import logging
import os

from atlassian import Confluence
from requests import Session
from requests.exceptions import ConnectionError as RequestsConnectionError

from ..exceptions import MCPAtlassianAuthenticationError
from ..utils.http import (
    configure_circuit_breaker,
    configure_concurrency,
    configure_rate_limit,
    configure_retry,
)
from ..utils.logging import get_masked_session_headers, log_config_param, mask_sensitive
from ..utils.oauth import configure_oauth_session
from ..utils.proxy import apply_proxy_configuration
from ..utils.ssl import configure_ssl_verification
from ..utils.ssrf_adapter import mount_ssrf_pinning
from ..utils.urls import make_ssrf_redirect_hook
from ..utils.user_agent import get_default_user_agent
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
        transport_url = self.config.url

        # Initialize the Confluence client based on auth type
        if self.config.auth_type == "oauth":
            if not self.config.oauth_config:
                error_msg = "OAuth authentication requires oauth_config"
                raise ValueError(error_msg)

            # Determine Cloud vs Data Center OAuth
            is_dc_oauth = (
                getattr(self.config.oauth_config, "is_data_center", False) is True
            )

            if not is_dc_oauth and not self.config.oauth_config.cloud_id:
                error_msg = "Cloud OAuth authentication requires a valid cloud_id"
                raise ValueError(error_msg)

            # Create a session for OAuth
            session = Session()

            # Configure the session with OAuth authentication
            if not configure_oauth_session(session, self.config.oauth_config):
                error_msg = "Failed to configure OAuth session"
                raise MCPAtlassianAuthenticationError(error_msg)

            if is_dc_oauth:
                # Data Center: use the instance URL directly
                api_url = self.config.url
                is_cloud = False
            else:
                # Cloud: use the Atlassian Cloud API URL
                api_url = f"https://api.atlassian.com/ex/confluence/{self.config.oauth_config.cloud_id}"
                is_cloud = True
            transport_url = api_url

            # Initialize Confluence with the session
            self.confluence = Confluence(
                url=api_url,
                session=session,
                cloud=is_cloud,
                verify_ssl=self.config.ssl_verify,
                timeout=self.config.timeout,
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
                timeout=self.config.timeout,
            )
        elif self.config.auth_type == "cert":
            logger.debug(
                f"Initializing Confluence client with mTLS certificate auth. "
                f"URL: {self.config.url}, "
                f"Cert configured: {bool(self.config.client_cert)}"
            )
            self.confluence = Confluence(
                url=self.config.url,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
                timeout=self.config.timeout,
            )
            self.confluence._session.trust_env = False
        elif self.config.auth_type == "external":
            logger.debug(
                f"Initializing Confluence client in external auth passthrough mode. "
                f"URL: {self.config.url}"
            )
            session = Session()
            session.trust_env = False
            self.confluence = Confluence(
                url=self.config.url,
                session=session,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
                timeout=self.config.timeout,
            )
            # Ensure no Authorization header is carried over from defaults
            self.confluence._session.headers.pop("Authorization", None)
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
                timeout=self.config.timeout,
            )
            logger.debug(
                f"Confluence client initialized. "
                f"Session headers (Authorization masked): "
                f"{get_masked_session_headers(dict(self.confluence._session.headers))}"
            )

        # Disable trust_env for PAT and OAuth to prevent .netrc from overriding
        # explicit credentials (#860). Basic auth can safely use .netrc.
        if self.config.auth_type in ("pat", "oauth"):
            self.confluence._session.trust_env = False

        if self.config.no_proxy and isinstance(self.config.no_proxy, str):
            os.environ["NO_PROXY"] = self.config.no_proxy
            log_config_param(logger, "Confluence", "NO_PROXY", self.config.no_proxy)

        # Configure SSL verification using the shared utility
        configure_ssl_verification(
            service_name="Confluence",
            url=transport_url,
            session=self.confluence._session,
            ssl_verify=self.config.ssl_verify,
            client_cert=self.config.client_cert,
            client_key=self.config.client_key,
            client_key_password=self.config.client_key_password,
            no_proxy=self.config.no_proxy,
        )

        # Validate redirects for SSRF on every outbound call from this session
        # (covers direct _session.get() paths and global/stdio fetchers, not just
        # the per-user HTTP path).
        self.confluence._session.hooks["response"].append(make_ssrf_redirect_hook())
        # Pin DNS resolution against rebinding: resolve+validate once and connect
        # to that address, closing the validate→reconnect TOCTOU. Preserves TLS SNI.
        mount_ssrf_pinning(self.confluence._session, transport_url)

        # Apply opt-in HTTP hardening after SSL setup and after the pinning
        # adapter is mounted: these wrappers patch send() in place on whatever
        # adapters are mounted now, so mounting the pinning adapter later would
        # silently drop them.
        configure_retry(self.confluence._session, service="Confluence")
        configure_concurrency(self.confluence._session, service="Confluence")
        configure_rate_limit(self.confluence._session, service="Confluence")
        configure_circuit_breaker(self.confluence._session, service="Confluence")

        self.confluence._session = apply_proxy_configuration(
            logger=logger,
            service_name="Confluence",
            session=self.confluence._session,
            config=self.config,
            target_url=transport_url,
        )

        # Set an explicit User-Agent so requests aren't blocked by WAFs that
        # reject the default ``python-requests/X.Y`` header. User-supplied
        # custom headers below can still override this.
        self.confluence._session.headers["User-Agent"] = get_default_user_agent()

        # Apply custom headers if configured
        if self.config.custom_headers:
            self._apply_custom_headers()

        # Import here to avoid circular imports
        from ..preprocessing.confluence import ConfluencePreprocessor

        self.preprocessor = ConfluencePreprocessor(base_url=self.config.url)

        # Test authentication during initialization (in debug mode only)
        if logger.isEnabledFor(logging.DEBUG) and self.config.auth_type != "external":
            try:
                self._validate_authentication()
            except MCPAtlassianAuthenticationError:
                logger.warning(
                    "Authentication validation failed during client initialization - "
                    "continuing anyway"
                )

    def _v1_rest_base_url(self) -> str:
        """Return the base URL for direct Confluence REST API v1 calls.

        Confluence Cloud OAuth uses the Atlassian API gateway base URL stored on
        the underlying client. V1 REST calls through that gateway require the
        ``/wiki`` product prefix before ``/rest/api``.

        Returns:
            Base URL suitable for appending ``/rest/api/...``.
        """
        if self.config.auth_type == "oauth" and self.config.is_cloud:
            base_url = self.confluence.url.rstrip("/")
        else:
            base_url = self.config.url.rstrip("/")

        if self.config.is_cloud and not base_url.endswith("/wiki"):
            base_url = f"{base_url}/wiki"
        return base_url

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
        except RequestsConnectionError as e:
            error_msg = (
                f"Could not connect to Confluence at {self.config.url}. "
                "Check that CONFLUENCE_URL is correct and the instance is reachable."
            )
            logger.error(error_msg)
            raise MCPAtlassianAuthenticationError(error_msg) from e
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
