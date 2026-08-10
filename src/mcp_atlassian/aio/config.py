"""Configuration module for AIO Tests API interactions."""

import logging
import os
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from ..utils.env import get_custom_headers, is_env_ssl_verify, is_env_truthy
from ..utils.urls import is_atlassian_cloud_url
from .constants import AIO_CLOUD_API_BASE, AIO_CLOUD_HOSTNAME, AIO_SERVER_API_PATH

logger = logging.getLogger("mcp-atlassian.aio.config")


def _resolve_base_url(explicit_url: str | None, jira_url: str | None) -> str | None:
    """Resolve the AIO Tests API base URL.

    Args:
        explicit_url: Value of AIO_URL, if set.
        jira_url: Value of JIRA_URL, if set.

    Returns:
        The API base URL without a trailing slash, or None if it cannot be
        determined.
    """
    if explicit_url:
        return explicit_url.rstrip("/")
    if not jira_url:
        # Cloud is reachable without JIRA_URL: the AIO token identifies the tenant.
        return AIO_CLOUD_API_BASE if os.getenv("AIO_API_TOKEN") else None
    if is_atlassian_cloud_url(jira_url):
        return AIO_CLOUD_API_BASE
    return f"{jira_url.rstrip('/')}{AIO_SERVER_API_PATH}"


@dataclass
class AIOConfig:
    """AIO Tests API configuration.

    AIO Tests is a Jira app with its own REST API, so authentication differs by
    deployment:

    - Cloud: an AIO Tests access token sent as ``Authorization: AioAuth <token>``.
    - Server/Data Center: the Jira credentials (personal access token or basic
      auth), because the API is served from the Jira base URL.
    """

    url: str  # Base URL of the AIO Tests API (no trailing slash)
    auth_type: Literal["token", "pat", "basic"]  # Authentication type
    api_token: str | None = None  # AIO Tests access token (Cloud)
    username: str | None = None  # Email or username (Server/DC basic auth)
    password: str | None = None  # API token or password (Server/DC basic auth)
    personal_token: str | None = None  # Personal access token (Server/DC)
    ssl_verify: bool = True  # Whether to verify SSL certificates
    http_proxy: str | None = None  # HTTP proxy URL
    https_proxy: str | None = None  # HTTPS proxy URL
    no_proxy: str | None = None  # Comma-separated list of hosts to bypass proxy
    socks_proxy: str | None = None  # SOCKS proxy URL
    custom_headers: dict[str, str] | None = None  # Custom HTTP headers
    client_cert: str | None = None  # Client certificate file path (.pem)
    client_key: str | None = None  # Client private key file path (.pem)
    client_key_password: str | None = None  # Password for encrypted private key

    @property
    def is_cloud(self) -> bool:
        """Check whether this configuration targets AIO Tests Cloud.

        Returns:
            True when the API base URL points at the AIO Tests Cloud service.
        """
        return urlparse(self.url).hostname == AIO_CLOUD_HOSTNAME

    @classmethod
    def from_env(cls) -> "AIOConfig":
        """Create configuration from environment variables.

        Returns:
            AIOConfig with values from environment variables.

        Raises:
            ValueError: If the API base URL or credentials cannot be determined.
        """
        jira_url = os.getenv("JIRA_URL")
        url = _resolve_base_url(os.getenv("AIO_URL"), jira_url)
        if not url:
            raise ValueError(
                "Cannot determine the AIO Tests API URL. Set AIO_API_TOKEN for "
                "AIO Tests Cloud, or set JIRA_URL (Server/Data Center), or set "
                "AIO_URL explicitly."
            )

        api_token = os.getenv("AIO_API_TOKEN")
        # Server/DC serves the AIO API from Jira, so fall back to Jira credentials.
        personal_token = os.getenv("AIO_PERSONAL_TOKEN") or os.getenv(
            "JIRA_PERSONAL_TOKEN"
        )
        username = os.getenv("AIO_USERNAME") or os.getenv("JIRA_USERNAME")
        password = os.getenv("AIO_PASSWORD") or os.getenv("JIRA_API_TOKEN")

        is_cloud = urlparse(url).hostname == AIO_CLOUD_HOSTNAME
        auth_type: Literal["token", "pat", "basic"]
        if api_token:
            auth_type = "token"
        elif is_cloud:
            raise ValueError(
                "AIO Tests Cloud requires an access token. Set AIO_API_TOKEN "
                "(generate one in Jira under AIO Tests > API Access Token)."
            )
        elif personal_token:
            auth_type = "pat"
        elif username and password:
            auth_type = "basic"
        else:
            raise ValueError(
                "AIO Tests Server/Data Center authentication requires "
                "AIO_PERSONAL_TOKEN or JIRA_PERSONAL_TOKEN, or a username and "
                "password/API token pair."
            )

        return cls(
            url=url,
            auth_type=auth_type,
            api_token=api_token,
            username=username,
            password=password,
            personal_token=personal_token,
            ssl_verify=is_env_ssl_verify("AIO_SSL_VERIFY"),
            http_proxy=os.getenv("AIO_HTTP_PROXY", os.getenv("HTTP_PROXY")),
            https_proxy=os.getenv("AIO_HTTPS_PROXY", os.getenv("HTTPS_PROXY")),
            no_proxy=os.getenv("AIO_NO_PROXY", os.getenv("NO_PROXY")),
            socks_proxy=os.getenv("AIO_SOCKS_PROXY", os.getenv("SOCKS_PROXY")),
            custom_headers=get_custom_headers("AIO_CUSTOM_HEADERS"),
            client_cert=os.getenv("AIO_CLIENT_CERT", os.getenv("JIRA_CLIENT_CERT")),
            client_key=os.getenv("AIO_CLIENT_KEY", os.getenv("JIRA_CLIENT_KEY")),
            client_key_password=os.getenv(
                "AIO_CLIENT_KEY_PASSWORD", os.getenv("JIRA_CLIENT_KEY_PASSWORD")
            ),
        )

    def is_auth_configured(self) -> bool:
        """Check whether authentication is complete enough to call the API.

        Returns:
            True if authentication is fully configured, False otherwise.
        """
        if self.auth_type == "token":
            return bool(self.api_token)
        if self.auth_type == "pat":
            return bool(self.personal_token)
        if self.auth_type == "basic":
            return bool(self.username and self.password)
        logger.warning(f"Unknown or unsupported auth_type: {self.auth_type}")
        return False


def is_aio_enabled() -> bool:
    """Check whether AIO Tests support should be activated.

    AIO Tests Cloud opts in implicitly by providing an access token. Server/Data
    Center reuses the Jira credentials, so it requires the explicit AIO_ENABLED
    flag - otherwise every Jira deployment without the app installed would expose
    tools that cannot work.

    Returns:
        True if AIO Tests tools should be registered.
    """
    if os.getenv("AIO_API_TOKEN"):
        return True
    if not is_env_truthy("AIO_ENABLED"):
        return False
    return bool(os.getenv("AIO_URL") or os.getenv("JIRA_URL"))
