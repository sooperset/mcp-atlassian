"""Configuration module for the Confluence client."""

import logging
import os
from dataclasses import dataclass
from typing import Literal

from ..utils.env import (
    get_custom_headers,
    get_header_names,
    is_env_ssl_verify,
    is_env_truthy,
)
from ..utils.oauth import (
    BYOAccessTokenOAuthConfig,
    OAuthConfig,
    get_oauth_config_from_env,
)
from ..utils.proxy import get_proxy_settings_from_env
from ..utils.urls import is_atlassian_cloud_url


@dataclass
class ConfluenceConfig:
    """Confluence API configuration.

    Handles authentication for Confluence Cloud and Server/Data Center:
    - Cloud: username/API token (basic auth) or OAuth 2.0 (3LO)
    - Server/DC: personal access token or basic auth
    """

    url: str  # Base URL for Confluence
    auth_type: Literal[
        "basic", "pat", "oauth", "cert", "external"
    ]  # Authentication type
    username: str | None = None  # Email or username
    api_token: str | None = None  # API token used as password
    personal_token: str | None = None  # Personal access token (Server/DC)
    oauth_config: OAuthConfig | BYOAccessTokenOAuthConfig | None = None
    ssl_verify: bool = True  # Whether to verify SSL certificates
    spaces_filter: str | None = None  # List of space keys to filter searches
    http_proxy: str | None = None  # HTTP proxy URL
    https_proxy: str | None = None  # HTTPS proxy URL
    no_proxy: str | None = None  # Comma-separated list of hosts to bypass proxy
    socks_proxy: str | None = None  # SOCKS proxy URL (optional)
    proxy_wpad_enable: bool = False  # Whether to load PAC/WPAD configuration
    proxy_wpad_url: str | None = None  # PAC URL used when WPAD is enabled
    custom_headers: dict[str, str] | None = None  # Custom HTTP headers
    passthrough_headers: list[str] | None = None  # Request headers to pass through
    client_cert: str | None = None  # Client certificate file path (.pem)
    client_key: str | None = None  # Client private key file path (.pem)
    client_key_password: str | None = None  # Password for encrypted private key
    timeout: int = 75  # Connection timeout in seconds
    # Cloud removed the legacy /download/attachments/... endpoint (CHANGE-2735);
    # it now 401s for API-token / scoped-token auth. Controls whether attachment
    # downloads use the v1 REST endpoint
    # (/rest/api/content/{id}/child/attachment/{aid}/download) instead:
    #   None  -> auto: v1 on Cloud, legacy link on Server/DC (default)
    #   True  -> always v1
    #   False -> always the legacy link
    attachment_download_use_v1: bool | None = None

    @property
    def is_cloud(self) -> bool:
        """Check if this is a cloud instance.

        Returns:
            True if this is a cloud instance (atlassian.net), False otherwise.
            Localhost URLs are always considered non-cloud (Server/Data Center).
        """
        # OAuth with cloud_id uses api.atlassian.com which is always Cloud
        if (
            self.auth_type == "oauth"
            and self.oauth_config
            and self.oauth_config.cloud_id
        ):
            return True

        # DC OAuth has base_url but no cloud_id — not Cloud
        if (
            self.auth_type == "oauth"
            and self.oauth_config
            and hasattr(self.oauth_config, "base_url")
            and self.oauth_config.base_url
            and not self.oauth_config.cloud_id
        ):
            return False

        # For other auth types, check the URL
        return is_atlassian_cloud_url(self.url) if self.url else False

    @property
    def verify_ssl(self) -> bool:
        """Compatibility property for old code.

        Returns:
            The ssl_verify value
        """
        return self.ssl_verify

    @classmethod
    def from_env(cls) -> "ConfluenceConfig":
        """Create configuration from environment variables.

        Returns:
            ConfluenceConfig with values from environment variables

        Raises:
            ValueError: If any required environment variable is missing
        """
        url = os.getenv("CONFLUENCE_URL")
        if (
            not url
            and not os.getenv("ATLASSIAN_OAUTH_ENABLE")
            and not is_env_truthy("ATLASSIAN_EXTERNAL_AUTH_ENABLE")
        ):
            error_msg = (
                "Missing required CONFLUENCE_URL environment variable. "
                "Set CONFLUENCE_URL to your Confluence base URL, for example "
                "https://your-company.atlassian.net/wiki"
            )
            raise ValueError(error_msg)

        # Determine authentication type based on available environment variables
        username = os.getenv("CONFLUENCE_USERNAME")
        api_token = os.getenv("CONFLUENCE_API_TOKEN")
        personal_token = os.getenv("CONFLUENCE_PERSONAL_TOKEN")
        client_cert_env = os.getenv("CONFLUENCE_CLIENT_CERT")

        # Check for OAuth configuration (pass service info for DC detection)
        oauth_config = get_oauth_config_from_env(
            service_url=url, service_type="confluence"
        )
        auth_type = None

        # Use the shared utility function directly
        is_cloud = is_atlassian_cloud_url(url) if url else False

        # External auth passthrough mode — no credentials needed
        if (
            is_env_truthy("ATLASSIAN_EXTERNAL_AUTH_ENABLE")
            and not username
            and not api_token
            and not personal_token
            and not oauth_config
        ):
            auth_type = "external"
        elif is_cloud:
            # Cloud: OAuth takes priority, then basic auth
            if oauth_config:
                auth_type = "oauth"
            elif username and api_token:
                auth_type = "basic"
            else:
                missing_fields: list[str] = []
                if not username:
                    missing_fields.append("CONFLUENCE_USERNAME")
                if not api_token:
                    missing_fields.append("CONFLUENCE_API_TOKEN")
                missing_fields_text = ", ".join(missing_fields)
                error_msg = (
                    "Cloud authentication requires CONFLUENCE_USERNAME and "
                    "CONFLUENCE_API_TOKEN, or OAuth configuration "
                    "(set ATLASSIAN_OAUTH_ENABLE=true for user-provided tokens). "
                    "Confluence Cloud authentication is incomplete. Missing: "
                    f"{missing_fields_text}. "
                    "Set CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN, or "
                    "enable OAuth with ATLASSIAN_OAUTH_ENABLE=true."
                )
                raise ValueError(error_msg)
        else:  # Server/Data Center
            # Server/DC: PAT takes priority over OAuth (fixes #824)
            if personal_token:
                if oauth_config:
                    logger = logging.getLogger("mcp-atlassian.confluence.config")
                    logger.warning(
                        "Both PAT and OAuth configured for Server/DC. Using PAT."
                    )
                auth_type = "pat"
            elif oauth_config:
                auth_type = "oauth"
            elif username and api_token:
                auth_type = "basic"
            elif client_cert_env:
                auth_type = "cert"
            else:
                error_msg = (
                    "Server/Data Center authentication requires "
                    "CONFLUENCE_PERSONAL_TOKEN, CONFLUENCE_USERNAME and "
                    "CONFLUENCE_API_TOKEN, or CONFLUENCE_CLIENT_CERT for mTLS. "
                    "Confluence Server/Data Center authentication is incomplete. "
                    "Set CONFLUENCE_PERSONAL_TOKEN, set both "
                    "CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN, "
                    "or set CONFLUENCE_CLIENT_CERT."
                )
                raise ValueError(error_msg)

        # SSL verification (for Server/DC)
        ssl_verify = is_env_ssl_verify("CONFLUENCE_SSL_VERIFY")

        # Get the spaces filter if provided
        spaces_filter = os.getenv("CONFLUENCE_SPACES_FILTER")

        # Proxy settings
        proxy_settings = get_proxy_settings_from_env("CONFLUENCE")

        # Custom headers - service-specific only
        custom_headers = get_custom_headers("CONFLUENCE_CUSTOM_HEADERS")
        passthrough_headers = get_header_names("CONFLUENCE_PASSTHROUGH_HEADERS")

        # Client certificate settings
        client_cert = os.getenv("CONFLUENCE_CLIENT_CERT")
        client_key = os.getenv("CONFLUENCE_CLIENT_KEY")
        client_key_password = os.getenv("CONFLUENCE_CLIENT_KEY_PASSWORD")

        # Timeout setting
        timeout = 75  # Default timeout
        if (
            os.getenv("CONFLUENCE_TIMEOUT")
            and os.getenv("CONFLUENCE_TIMEOUT", "").isdigit()
        ):
            timeout = int(os.getenv("CONFLUENCE_TIMEOUT", "75"))

        # Unset or empty/whitespace -> None (auto); only an explicit value forces.
        _use_v1_raw = os.getenv("CONFLUENCE_ATTACHMENT_DOWNLOAD_USE_V1")
        attachment_download_use_v1 = (
            None
            if _use_v1_raw is None or not _use_v1_raw.strip()
            else is_env_truthy("CONFLUENCE_ATTACHMENT_DOWNLOAD_USE_V1")
        )

        return cls(
            url=url or "",
            auth_type=auth_type,
            username=username,
            api_token=api_token,
            personal_token=personal_token,
            oauth_config=oauth_config,
            ssl_verify=ssl_verify,
            spaces_filter=spaces_filter,
            http_proxy=proxy_settings["http_proxy"],
            https_proxy=proxy_settings["https_proxy"],
            no_proxy=proxy_settings["no_proxy"],
            socks_proxy=proxy_settings["socks_proxy"],
            proxy_wpad_enable=bool(proxy_settings["proxy_wpad_enable"]),
            proxy_wpad_url=proxy_settings["proxy_wpad_url"],
            custom_headers=custom_headers,
            passthrough_headers=passthrough_headers,
            client_cert=client_cert,
            client_key=client_key,
            client_key_password=client_key_password,
            timeout=timeout,
            attachment_download_use_v1=attachment_download_use_v1,
        )

    def is_auth_configured(self) -> bool:
        """Check if the current authentication configuration is complete and valid for making API calls.

        Returns:
            bool: True if authentication is fully configured, False otherwise.
        """
        logger = logging.getLogger("mcp-atlassian.confluence.config")
        if self.auth_type == "oauth":
            if self.oauth_config:
                # Minimal OAuth (user-provided tokens mode)
                if isinstance(self.oauth_config, OAuthConfig):
                    if (
                        not self.oauth_config.client_id
                        and not self.oauth_config.client_secret
                    ):
                        logger.debug(
                            "Minimal OAuth config detected - "
                            "expecting user-provided tokens via headers"
                        )
                        return True
                    # DC OAuth: needs client_id + client_secret (no cloud_id needed)
                    if hasattr(self.oauth_config, "is_data_center"):
                        if self.oauth_config.is_data_center:
                            return bool(
                                self.oauth_config.client_id
                                and self.oauth_config.client_secret
                            )
                    # Cloud OAuth: full set required
                    if (
                        self.oauth_config.client_id
                        and self.oauth_config.client_secret
                        and self.oauth_config.redirect_uri
                        and self.oauth_config.scope
                        and self.oauth_config.cloud_id
                    ):
                        return True
                # BYO Access Token mode
                elif isinstance(self.oauth_config, BYOAccessTokenOAuthConfig):
                    if self.oauth_config.access_token:
                        # DC BYO: access_token is enough
                        if hasattr(self.oauth_config, "is_data_center"):
                            if self.oauth_config.is_data_center:
                                return True
                        # Cloud BYO: needs cloud_id + access_token
                        if self.oauth_config.cloud_id:
                            return True

            logger.warning("Incomplete OAuth configuration detected")
            return False
        elif self.auth_type == "pat":
            return bool(self.personal_token)
        elif self.auth_type == "basic":
            return bool(self.username and self.api_token)
        elif self.auth_type == "cert":
            return bool(self.client_cert)
        elif self.auth_type == "external":
            return True
        logger.warning(
            f"Unknown or unsupported auth_type: {self.auth_type} in ConfluenceConfig"
        )
        return False
