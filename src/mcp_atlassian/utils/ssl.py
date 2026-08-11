"""SSL and proxy utility functions for MCP Atlassian."""

import logging
import os
import ssl
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from requests import PreparedRequest, Response
from requests.sessions import Session
from requests.utils import should_bypass_proxies
from urllib3.poolmanager import PoolManager

from .ssrf_adapter import (
    SsrfPinningAdapter,
    _PinnedHTTPConnectionPool,
    _PinnedHTTPSConnectionPool,
)

logger = logging.getLogger("mcp-atlassian")


class NoProxyAdapter(SsrfPinningAdapter):
    """HTTP adapter that respects NO_PROXY environment variable.

    A custom transport adapter that ensures NO_PROXY is honored even when
    proxies are explicitly configured on the session. By default, the requests
    library only checks NO_PROXY during auto-detection from environment variables,
    not when proxies are explicitly set on session.proxies. The adapter also
    preserves the DNS-pinning SSRF protection used by the default transport.

    The no-proxy list is captured on the adapter when it is mounted. This keeps
    each mounted adapter bound to its own configuration, so multiple clients
    running in the same process (e.g. Jira and Confluence with different
    ``JIRA_NO_PROXY`` / ``CONFLUENCE_NO_PROXY`` values) cannot overwrite one
    another via the shared process environment. When no value is captured, the
    adapter falls back to the ``NO_PROXY`` environment variable.
    """

    def __init__(self, *args: Any, no_proxy: str | None = None, **kwargs: Any) -> None:
        """Initialize the adapter, capturing the configured no-proxy list.

        Args:
            no_proxy: The no-proxy list this adapter should honor. When omitted,
                the adapter falls back to the ``NO_PROXY`` environment variable
                at send time.
        """
        self._no_proxy = no_proxy
        super().__init__(*args, **kwargs)

    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float, float] | None = None,
        verify: bool | str = True,
        cert: bytes | str | tuple[bytes | str, bytes | str] | None = None,
        proxies: Mapping[str, str] | None = None,
    ) -> Response:
        """Send a request, respecting NO_PROXY environment variable.

        This override ensures that NO_PROXY is respected even when proxies are
        explicitly configured on the session.

        Args:
            request: The prepared request to send
            stream: Whether to stream the response
            timeout: Request timeout
            verify: SSL verification setting
            cert: Client certificate
            proxies: Proxy configuration

        Returns:
            The response from the server
        """
        # Check if we should bypass proxies for this URL. Prefer the value
        # captured when the adapter was mounted so concurrent clients with
        # different no-proxy lists stay isolated; fall back to the environment.
        no_proxy = (
            self._no_proxy or os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
        )
        if (
            request.url
            and proxies
            and no_proxy
            and should_bypass_proxies(request.url, no_proxy)
        ):
            logger.debug(
                f"Bypassing proxy for {request.url} due to NO_PROXY setting: {no_proxy}"
            )
            proxies = None

        return super().send(
            request,
            stream=stream,
            timeout=timeout,
            verify=verify,
            cert=cert,
            proxies=proxies,
        )


class SSLIgnoreAdapter(NoProxyAdapter):
    """HTTP adapter that ignores SSL verification and respects NO_PROXY.

    A custom transport adapter that:
    1. Disables SSL certificate verification for specific domains
    2. Respects NO_PROXY environment variable even when proxies are explicitly set

    This implementation ensures that both verify_mode is set to CERT_NONE and check_hostname
    is disabled, which is required for properly ignoring SSL certificates.

    Note that this reduces security and should only be used when absolutely necessary.
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

        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=context,
            **pool_kwargs,
        )
        # This adapter mounts at a more specific prefix than the session-wide
        # SsrfPinningAdapter and would otherwise silently replace it — keep the
        # DNS-pinning connection classes so disabling SSL verification does not
        # also disable the SSRF rebinding guard.
        self.poolmanager.pool_classes_by_scheme = {  # type: ignore[attr-defined]
            "http": _PinnedHTTPConnectionPool,
            "https": _PinnedHTTPSConnectionPool,
        }

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

    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float, float] | None = None,
        verify: bool | str = True,
        cert: bytes | str | tuple[bytes | str, bytes | str] | None = None,
        proxies: Mapping[str, str] | None = None,
    ) -> Response:
        """Send a request with SSL verification disabled.

        Args:
            request: The prepared request to send
            stream: Whether to stream the response
            timeout: Request timeout
            verify: SSL verification setting (ignored, always False for this adapter)
            cert: Client certificate
            proxies: Proxy configuration

        Returns:
            The response from the server
        """
        # Let parent class handle NO_PROXY, but always disable SSL verification
        return super().send(
            request,
            stream=stream,
            timeout=timeout,
            verify=False,  # Always disable SSL verification for this adapter
            cert=cert,
            proxies=proxies,
        )


def configure_proxy_bypass(
    service_name: str,
    url: str,
    session: Session,
    no_proxy: str | None = None,
) -> None:
    """Configure the session to respect NO_PROXY environment variable.

    This function mounts a custom adapter that ensures NO_PROXY is honored
    even when proxies are explicitly configured on the session. The no-proxy
    list is captured on the mounted adapter so it is not affected by later
    changes to the process environment made by other clients.

    Args:
        service_name: Name of the service for logging (e.g., "Confluence", "Jira")
        url: The base URL of the service
        session: The requests session to configure
        no_proxy: The no-proxy list to honor. Defaults to the ``NO_PROXY``
            environment variable when not provided.
    """
    no_proxy = no_proxy or os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    if no_proxy:
        logger.debug(
            f"{service_name}: Configuring proxy bypass adapter for NO_PROXY={no_proxy}"
        )
        # Get the domain from the configured URL
        domain = urlparse(url).netloc

        # Mount the adapter to handle requests to this domain
        adapter = NoProxyAdapter(no_proxy=no_proxy)
        session.mount(f"https://{domain}", adapter)
        session.mount(f"http://{domain}", adapter)


def configure_ssl_verification(
    service_name: str,
    url: str,
    session: Session,
    ssl_verify: bool,
    client_cert: str | None = None,
    client_key: str | None = None,
    client_key_password: str | None = None,
    no_proxy: str | None = None,
) -> None:
    """Configure SSL verification and client certificates for a specific service.

    If SSL verification is disabled, this function will configure the session
    to use a custom SSL adapter that bypasses certificate validation for the
    service's domain. This adapter also respects NO_PROXY.

    If SSL verification is enabled but NO_PROXY is set, a proxy bypass adapter
    is mounted to ensure NO_PROXY is respected.

    If client certificate paths are provided, they will be configured for
    mutual TLS authentication.

    Args:
        service_name: Name of the service for logging (e.g., "Confluence", "Jira")
        url: The base URL of the service
        session: The requests session to configure
        ssl_verify: Whether SSL verification should be enabled
        client_cert: Path to client certificate file (.pem)
        client_key: Path to client private key file (.pem)
        client_key_password: Password for encrypted private key (optional)
        no_proxy: The no-proxy list to honor on the mounted adapter. Defaults to
            the ``NO_PROXY`` environment variable when not provided.
    """
    no_proxy = no_proxy or os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    # Configure client certificate if provided (must be actual string paths).
    # requests accepts either a combined PEM path or a (cert, key) tuple.
    if isinstance(client_cert, str):
        # Encrypted private keys are not supported by the requests library
        if isinstance(client_key_password, str) and client_key_password:
            raise ValueError(
                f"{service_name} client certificate authentication with encrypted "
                "private keys is not supported. Please decrypt your private key first "
                "(e.g., using 'openssl rsa -in encrypted.key -out decrypted.key')."
            )

        if isinstance(client_key, str):
            session.cert = (client_cert, client_key)
        else:
            session.cert = client_cert

        cert_configured = True
        key_configured = isinstance(client_key, str)
        logger.info(
            "%s client certificate authentication configured "
            "(cert configured: %s, key configured: %s)",
            service_name,
            cert_configured,
            key_configured,
        )

    if not ssl_verify:
        logger.warning(
            f"{service_name} SSL verification disabled. This is insecure and "
            "should only be used in testing environments."
        )

        # Mount the SSL ignore adapter which also handles NO_PROXY
        domain = urlparse(url).netloc
        adapter = SSLIgnoreAdapter(no_proxy=no_proxy)
        session.mount(f"https://{domain}", adapter)
        session.mount(f"http://{domain}", adapter)
    else:
        # Even with SSL verification enabled, we may need to handle NO_PROXY
        if no_proxy:
            logger.debug(
                f"{service_name}: Mounting proxy bypass adapter for NO_PROXY={no_proxy}"
            )
            domain = urlparse(url).netloc
            adapter = NoProxyAdapter(no_proxy=no_proxy)
            session.mount(f"https://{domain}", adapter)
            session.mount(f"http://{domain}", adapter)
