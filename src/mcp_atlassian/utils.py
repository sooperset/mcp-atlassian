"""Utility functions for the MCP Atlassian integration."""

import logging
import os
import ssl
from typing import Any
from urllib.parse import urlparse

from requests.adapters import HTTPAdapter
from requests.sessions import Session
from urllib3.poolmanager import PoolManager

# Configure logging
logger = logging.getLogger("mcp-atlassian")


def is_atlassian_cloud_url(url: str) -> bool:
    """Determine if a URL belongs to Atlassian Cloud or Server/Data Center.

    Args:
        url: The URL to check

    Returns:
        True if the URL is for an Atlassian Cloud instance, False for Server/Data Center
    """
    # Localhost and IP-based URLs are always Server/Data Center
    if "localhost" in url or "127.0.0.1" in url:
        return False

    # The standard check for Atlassian cloud domains
    return "atlassian.net" in url


class SSLIgnoreAdapter(HTTPAdapter):
    """HTTP adapter that ignores SSL verification.

    A custom transport adapter that disables SSL certificate verification for specific domains.
    This implementation ensures that both verify_mode is set to CERT_NONE and check_hostname
    is disabled, which is required for properly ignoring SSL certificates.

    This adapter also enables legacy SSL renegotiation which may be required for some older servers.
    Note that this reduces security and should only be used when absolutely necessary.

    Example:
        session = requests.Session()
        adapter = SSLIgnoreAdapter()
        session.mount('https://example.com', adapter)  # Disable SSL verification for example.com

    Warning:
        Only use this adapter when SSL verification must be disabled for specific use cases.
        Disabling SSL verification and enabling legacy renegotiation reduces security by making
        the connection vulnerable to man-in-the-middle attacks and other SSL/TLS vulnerabilities.
    """

    def init_poolmanager(
        self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any
    ) -> None:
        """Initialize the connection pool manager with SSL verification disabled.

        This method is called when the adapter is created, and it's the proper place to
        disable SSL verification completely.

        Args:
            connections: Number of connections to save in the pool
            maxsize: Maximum number of connections in the pool
            block: Whether to block when the pool is full
            pool_kwargs: Additional arguments for the pool manager
        """
        # Configure SSL context to disable verification completely
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        # Enable legacy SSL renegotiation
        context.options |= 0x4  # SSL_OP_LEGACY_SERVER_CONNECT
        context.options |= 0x40000  # SSL_OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION

        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=context,
            **pool_kwargs,
        )

    def cert_verify(self, conn: Any, url: str, verify: bool, cert: Any | None) -> None:
        """Override cert verification to disable SSL verification.

        This method is still included for backward compatibility, but the main
        SSL disabling happens in init_poolmanager.

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


def is_read_only_mode() -> bool:
    """Check if the server is running in read-only mode.

    Read-only mode prevents all write operations (create, update, delete)
    while allowing all read operations. This is useful for working with
    production Atlassian instances where you want to prevent accidental
    modifications.

    Returns:
        True if read-only mode is enabled, False otherwise
    """
    value = os.getenv("READ_ONLY_MODE", "false")
    return value.lower() in ("true", "1", "yes", "y", "on")
