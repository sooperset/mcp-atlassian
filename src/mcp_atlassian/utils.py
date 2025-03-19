"""Utility functions for the MCP Atlassian integration."""

import logging
from typing import Any
from urllib.parse import urlparse

from requests.adapters import HTTPAdapter
from requests.sessions import Session

# Configure logging
logger = logging.getLogger("mcp-atlassian")


class SSLIgnoreAdapter(HTTPAdapter):
    """HTTP adapter that ignores SSL verification.

    A custom transport adapter that disables SSL certificate verification for specific domains.

    The adapter overrides the cert_verify method to force verify=False, ensuring SSL verification
    is bypassed regardless of the verify parameter passed to the request. This only affects
    domains where the adapter is explicitly mounted.

    Example:
        session = requests.Session()
        adapter = SSLIgnoreAdapter()
        session.mount('https://example.com', adapter)  # Disable SSL verification for example.com

    Warning:
        Only use this adapter when SSL verification must be disabled for specific use cases.
        Disabling SSL verification reduces security by making the connection vulnerable to
        man-in-the-middle attacks.
    """

    def cert_verify(self, conn: Any, url: str, verify: bool, cert: Any | None) -> None:
        """Override cert verification to disable SSL verification.

        Args:
            conn: The connection
            url: The URL being requested
            verify: The original verify parameter (ignored)
            cert: Client certificate path
        """
        super().cert_verify(conn, url, verify=False, cert=cert)


def configure_ssl_verification(
    service_name: str, url: str, session: Session, ssl_verify: bool
) -> None:
    """Configure SSL verification for a specific service.

    If SSL verification is disabled, this function will configure the session
    to use a custom SSL adapter that bypasses certificate validation for the
    service's domain.

    Args:
        service_name: Name of the service for logging (e.g., "Confluence", "Jira")
        url: The base URL of the service
        session: The requests session to configure
        ssl_verify: Whether SSL verification should be enabled
    """
    if not ssl_verify:
        logger.warning(
            f"SSL verification is disabled for {service_name}. This may be insecure."
        )

        # Get the domain from the configured URL
        domain = urlparse(url).netloc

        # Mount the adapter to handle requests to this domain
        adapter = SSLIgnoreAdapter()
        session.mount(f"https://{domain}", adapter)
        session.mount(f"http://{domain}", adapter)
