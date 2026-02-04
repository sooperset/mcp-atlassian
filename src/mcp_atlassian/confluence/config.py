"""Configuration module for the Confluence client."""

import logging
import os
from dataclasses import dataclass
from typing import Literal

from ..utils.env import get_custom_headers, is_env_ssl_verify
from ..utils.oauth import (
    BYOAccessTokenOAuthConfig,
    OAuthConfig,
    get_oauth_config_from_env,
)
from ..utils.urls import is_atlassian_cloud_url


@dataclass
class ConfluenceConfig:
    """Confluence API configuration.

    Handles authentication for Confluence Cloud and Server/Data Center:
    - Cloud: username/API token (basic auth) or OAuth 2.0 (3LO)
    - Server/DC: personal access token or basic auth
    """

    url: str  # Base URL for Confluence
    auth_type: Literal["basic", "pat", "oauth"]  # Authentication type
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
    custom_headers: dict[str, str] | None = None  # Custom HTTP headers
    client_cert: str | None = None  # Client certificate file path (.pem)
    client_key: str | None = None  # Client private key file path (.pem)
    client_key_password: str | None = None  # Password for encrypted private key

    @property
    def is_cloud(self) -> bool:
        """Check if this is a cloud instance.

        Returns:
            True if this is a cloud instance (atlassian.net), False otherwise.
            Localhost URLs are always considered non-cloud (Server/Data Center).
        """
        # Multi-Cloud OAuth mode: URL might be None, but we use api.atlassian.com
        if (
            self.auth_type == "oauth"
            and self.oauth_config
            and self.oauth_config.cloud_id
        ):
            # OAuth with cloud_id uses api.atlassian.com which is always Cloud
            return True

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
        if not url and not os.getenv("ATLASSIAN_OAUTH_ENABLE"):
            error_msg = "Missing required CONFLUENCE_URL environment variable"
            raise ValueError(error_msg)

        # Determine authentication type based on available environment variables
        username = os.getenv("CONFLUENCE_USERNAME")
        api_token = os.getenv("CONFLUENCE_API_TOKEN")
        personal_token = os.getenv("CONFLUENCE_PERSONAL_TOKEN")

        # Check for OAuth configuration
        oauth_config = get_oauth_config_from_env()
        auth_type = None

        # Use the shared utility function directly
        is_cloud = is_atlassian_cloud_url(url)

        if is_cloud:
            # Cloud: OAuth takes priority, then basic auth
            if oauth_config:
                auth_type = "oauth"
            elif username and api_token:
                auth_type = "basic"
            else:
                error_msg = "Cloud authentication requires CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN, or OAuth configuration (set ATLASSIAN_OAUTH_ENABLE=true for user-provided tokens)"
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
            else:
                error_msg = "Server/Data Center authentication requires CONFLUENCE_PERSONAL_TOKEN or CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN"
                raise ValueError(error_msg)

        # SSL verification (for Server/DC)
        ssl_verify = is_env_ssl_verify("CONFLUENCE_SSL_VERIFY")

        # Get the spaces filter if provided
        spaces_filter = os.getenv("CONFLUENCE_SPACES_FILTER")

        # Proxy settings
        http_proxy = os.getenv("CONFLUENCE_HTTP_PROXY", os.getenv("HTTP_PROXY"))
        https_proxy = os.getenv("CONFLUENCE_HTTPS_PROXY", os.getenv("HTTPS_PROXY"))
        no_proxy = os.getenv("CONFLUENCE_NO_PROXY", os.getenv("NO_PROXY"))
        socks_proxy = os.getenv("CONFLUENCE_SOCKS_PROXY", os.getenv("SOCKS_PROXY"))

        # Custom headers - service-specific only
        custom_headers = get_custom_headers("CONFLUENCE_CUSTOM_HEADERS")

        # Client certificate settings
        client_cert = os.getenv("CONFLUENCE_CLIENT_CERT")
        client_key = os.getenv("CONFLUENCE_CLIENT_KEY")
        client_key_password = os.getenv("CONFLUENCE_CLIENT_KEY_PASSWORD")

        return cls(
            url=url,
            auth_type=auth_type,
            username=username,
            api_token=api_token,
            personal_token=personal_token,
            oauth_config=oauth_config,
            ssl_verify=ssl_verify,
            spaces_filter=spaces_filter,
            http_proxy=http_proxy,
            https_proxy=https_proxy,
            no_proxy=no_proxy,
            socks_proxy=socks_proxy,
            custom_headers=custom_headers,
            client_cert=client_cert,
            client_key=client_key,
            client_key_password=client_key_password,
        )

    @classmethod
    def from_env_multi(cls) -> dict[str, "ConfluenceConfig"]:
        """Load multiple Confluence instances from environment variables.

        Supports primary instance (CONFLUENCE_*) and numbered secondary instances
        (CONFLUENCE_2_*, CONFLUENCE_3_*, etc.).

        Returns:
            dict[str, ConfluenceConfig]: Dictionary mapping instance names to configurations.
                - Primary instance uses empty string "" as key
                - Secondary instances use CONFLUENCE_{N}_INSTANCE_NAME or default "confluence_{N}"

        Raises:
            ValueError: If instance name is invalid or reserved.

        Example:
            ```bash
            CONFLUENCE_URL=https://prod.atlassian.net/wiki
            CONFLUENCE_USERNAME=user@example.com
            CONFLUENCE_API_TOKEN=token1

            CONFLUENCE_2_URL=https://staging.atlassian.net/wiki
            CONFLUENCE_2_USERNAME=user@example.com
            CONFLUENCE_2_API_TOKEN=token2
            CONFLUENCE_2_INSTANCE_NAME=staging
            ```
        """
        configs: dict[str, ConfluenceConfig] = {}
        logger_instance = logging.getLogger("mcp-atlassian.confluence.config")

        # Reserved names that cannot be used for instances
        RESERVED_NAMES = {"jira", "confluence"}

        def validate_instance_name(name: str) -> None:
            """Validate instance name format."""
            if not name:
                return  # Empty string is valid for primary
            if name.lower() in RESERVED_NAMES:
                raise ValueError(
                    f"Reserved instance name '{name}'. Cannot use reserved names: {RESERVED_NAMES}"
                )
            # Allow alphanumeric and underscore only
            if not all(c.isalnum() or c == "_" for c in name):
                raise ValueError(
                    f"Invalid instance name '{name}'. Only alphanumeric characters and underscore allowed."
                )
            if len(name) > 30:
                raise ValueError(
                    f"Instance name '{name}' too long. Maximum 30 characters."
                )

        # Try to load primary instance
        try:
            primary_config = cls.from_env()
            validate_instance_name("")  # Validate empty string (always valid)
            configs[""] = primary_config
            logger_instance.info(
                f"Loaded primary Confluence instance: {primary_config.url}"
            )
        except ValueError as e:
            logger_instance.debug(
                f"Primary Confluence instance not configured or incomplete: {e}"
            )

        # Load secondary instances (CONFLUENCE_2_*, CONFLUENCE_3_*, etc.)
        instance_num = 2
        while instance_num <= 99:  # Reasonable limit
            prefix = f"CONFLUENCE_{instance_num}_"
            url_var = f"{prefix}URL"

            # Check if this instance number exists
            if url_var not in os.environ:
                # No more instances found
                if instance_num == 2:
                    # No secondary instances at all
                    break
                # Skip this number, keep checking (in case user skipped a number)
                instance_num += 1
                if instance_num > 10:  # Don't check beyond 10 if gaps found
                    break
                continue

            # Instance exists, try to load it
            try:
                # Build environment dict for this instance
                instance_env = {}
                for key, value in os.environ.items():
                    if key.startswith(prefix):
                        # Map CONFLUENCE_2_URL -> CONFLUENCE_URL, etc.
                        new_key = key.replace(prefix, "CONFLUENCE_")
                        instance_env[new_key] = value

                # Get instance name (custom or default)
                instance_name_var = f"{prefix}INSTANCE_NAME"
                instance_name = os.environ.get(
                    instance_name_var, f"confluence_{instance_num}"
                )

                # Validate instance name
                validate_instance_name(instance_name)

                # Check for name collision
                if instance_name in configs:
                    logger_instance.warning(
                        f"Instance name collision: '{instance_name}' already exists. Skipping CONFLUENCE_{instance_num}."
                    )
                    instance_num += 1
                    continue

                # Temporarily swap environment to load this instance
                original_env = os.environ.copy()
                try:
                    # Clear Confluence env vars and set instance-specific ones
                    for key in list(os.environ.keys()):
                        if key.startswith("CONFLUENCE_") and not key.startswith(prefix):
                            del os.environ[key]
                    os.environ.update(instance_env)

                    # Load config using from_env()
                    instance_config = cls.from_env()
                    configs[instance_name] = instance_config
                    logger_instance.info(
                        f"Loaded Confluence instance '{instance_name}': {instance_config.url}"
                    )
                finally:
                    # Restore original environment
                    os.environ.clear()
                    os.environ.update(original_env)

            except ValueError as e:
                logger_instance.warning(
                    f"Skipping CONFLUENCE_{instance_num} (incomplete or invalid config): {e}"
                )

            instance_num += 1

        logger_instance.info(f"Loaded {len(configs)} Confluence instance(s)")
        return configs

    def is_auth_configured(self) -> bool:
        """Check if the current authentication configuration is complete and valid for making API calls.

        Returns:
            bool: True if authentication is fully configured, False otherwise.
        """
        logger = logging.getLogger("mcp-atlassian.confluence.config")
        if self.auth_type == "oauth":
            # Handle different OAuth configuration types
            if self.oauth_config:
                # Full OAuth configuration (traditional mode)
                if isinstance(self.oauth_config, OAuthConfig):
                    if (
                        self.oauth_config.client_id
                        and self.oauth_config.client_secret
                        and self.oauth_config.redirect_uri
                        and self.oauth_config.scope
                        and self.oauth_config.cloud_id
                    ):
                        return True
                    # Minimal OAuth configuration (user-provided tokens mode)
                    # This is valid if we have oauth_config but missing client credentials
                    # In this case, we expect authentication to come from user-provided headers
                    elif (
                        not self.oauth_config.client_id
                        and not self.oauth_config.client_secret
                    ):
                        logger.debug(
                            "Minimal OAuth config detected - expecting user-provided tokens via headers"
                        )
                        return True
                # Bring Your Own Access Token mode
                elif isinstance(self.oauth_config, BYOAccessTokenOAuthConfig):
                    if self.oauth_config.cloud_id and self.oauth_config.access_token:
                        return True

            # Partial configuration is invalid
            logger.warning("Incomplete OAuth configuration detected")
            return False
        elif self.auth_type == "pat":
            return bool(self.personal_token)
        elif self.auth_type == "basic":
            return bool(self.username and self.api_token)
        logger.warning(
            f"Unknown or unsupported auth_type: {self.auth_type} in ConfluenceConfig"
        )
        return False
