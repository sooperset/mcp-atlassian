"""Configuration module for Jira API interactions."""

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
class SLAConfig:
    """SLA calculation configuration.

    Configures how SLA metrics are calculated, including working hours settings.
    """

    default_metrics: list[str]  # Default metrics to calculate
    working_hours_only: bool = False  # Exclude non-working hours
    working_hours_start: str = "09:00"  # Start of working day (24h format)
    working_hours_end: str = "17:00"  # End of working day (24h format)
    working_days: list[int] | None = None  # Working days (1=Mon, 7=Sun)
    timezone: str = "UTC"  # IANA timezone for calculations

    def __post_init__(self) -> None:
        """Set defaults and validate after initialization."""
        if self.working_days is None:
            self.working_days = [1, 2, 3, 4, 5]  # Monday-Friday
        else:
            # Validate working_days values are in range 1-7
            invalid_days = [d for d in self.working_days if d < 1 or d > 7]
            if invalid_days:
                raise ValueError(
                    f"Invalid working days: {invalid_days}. Must be 1-7 (Mon-Sun)"
                )

    @classmethod
    def from_env(cls) -> "SLAConfig":
        """Create SLA configuration from environment variables.

        Returns:
            SLAConfig with values from environment variables

        Raises:
            ValueError: If working_days contains invalid values
        """
        # Default metrics
        metrics_str = os.getenv("JIRA_SLA_METRICS", "cycle_time,time_in_status")
        default_metrics = [m.strip() for m in metrics_str.split(",")]

        # Working hours settings
        working_hours_only = os.getenv(
            "JIRA_SLA_WORKING_HOURS_ONLY", "false"
        ).lower() in ("true", "1", "yes")

        working_hours_start = os.getenv("JIRA_SLA_WORKING_HOURS_START", "09:00")
        working_hours_end = os.getenv("JIRA_SLA_WORKING_HOURS_END", "17:00")

        # Working days (1=Monday, 7=Sunday)
        working_days_str = os.getenv("JIRA_SLA_WORKING_DAYS", "1,2,3,4,5")
        working_days = [int(d.strip()) for d in working_days_str.split(",")]

        # Validate working_days
        invalid_days = [d for d in working_days if d < 1 or d > 7]
        if invalid_days:
            raise ValueError(
                f"Invalid JIRA_SLA_WORKING_DAYS: {invalid_days}. Must be 1-7 (Mon-Sun)"
            )

        # Timezone
        timezone = os.getenv("JIRA_SLA_TIMEZONE", "UTC")

        return cls(
            default_metrics=default_metrics,
            working_hours_only=working_hours_only,
            working_hours_start=working_hours_start,
            working_hours_end=working_hours_end,
            working_days=working_days,
            timezone=timezone,
        )


@dataclass
class JiraConfig:
    """Jira API configuration.

    Handles authentication for Jira Cloud and Server/Data Center:
    - Cloud: username/API token (basic auth) or OAuth 2.0 (3LO)
    - Server/DC: personal access token or basic auth
    """

    url: str  # Base URL for Jira
    auth_type: Literal["basic", "pat", "oauth"]  # Authentication type
    username: str | None = None  # Email or username (Cloud)
    api_token: str | None = None  # API token (Cloud)
    personal_token: str | None = None  # Personal access token (Server/DC)
    oauth_config: OAuthConfig | BYOAccessTokenOAuthConfig | None = None
    ssl_verify: bool = True  # Whether to verify SSL certificates
    projects_filter: str | None = None  # List of project keys to filter searches
    http_proxy: str | None = None  # HTTP proxy URL
    https_proxy: str | None = None  # HTTPS proxy URL
    no_proxy: str | None = None  # Comma-separated list of hosts to bypass proxy
    socks_proxy: str | None = None  # SOCKS proxy URL (optional)
    custom_headers: dict[str, str] | None = None  # Custom HTTP headers
    disable_jira_markup_translation: bool = (
        False  # Disable automatic markup translation between formats
    )
    client_cert: str | None = None  # Client certificate file path (.pem)
    client_key: str | None = None  # Client private key file path (.pem)
    client_key_password: str | None = None  # Password for encrypted private key
    sla_config: SLAConfig | None = None  # Optional SLA configuration

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
    def from_env(cls) -> "JiraConfig":
        """Create configuration from environment variables.

        Returns:
            JiraConfig with values from environment variables

        Raises:
            ValueError: If required environment variables are missing or invalid
        """
        url = os.getenv("JIRA_URL")
        if not url and not os.getenv("ATLASSIAN_OAUTH_ENABLE"):
            error_msg = "Missing required JIRA_URL environment variable"
            raise ValueError(error_msg)

        # Determine authentication type based on available environment variables
        username = os.getenv("JIRA_USERNAME")
        api_token = os.getenv("JIRA_API_TOKEN")
        personal_token = os.getenv("JIRA_PERSONAL_TOKEN")

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
                error_msg = "Cloud authentication requires JIRA_USERNAME and JIRA_API_TOKEN, or OAuth configuration (set ATLASSIAN_OAUTH_ENABLE=true for user-provided tokens)"
                raise ValueError(error_msg)
        else:  # Server/Data Center
            # Server/DC: PAT takes priority over OAuth (fixes #824)
            if personal_token:
                if oauth_config:
                    logger = logging.getLogger("mcp-atlassian.jira.config")
                    logger.warning(
                        "Both PAT and OAuth configured for Server/DC. Using PAT."
                    )
                auth_type = "pat"
            elif oauth_config:
                auth_type = "oauth"
            elif username and api_token:
                auth_type = "basic"
            else:
                error_msg = "Server/Data Center authentication requires JIRA_PERSONAL_TOKEN or JIRA_USERNAME and JIRA_API_TOKEN"
                raise ValueError(error_msg)

        # SSL verification (for Server/DC)
        ssl_verify = is_env_ssl_verify("JIRA_SSL_VERIFY")

        # Get the projects filter if provided
        projects_filter = os.getenv("JIRA_PROJECTS_FILTER")

        # Proxy settings
        http_proxy = os.getenv("JIRA_HTTP_PROXY", os.getenv("HTTP_PROXY"))
        https_proxy = os.getenv("JIRA_HTTPS_PROXY", os.getenv("HTTPS_PROXY"))
        no_proxy = os.getenv("JIRA_NO_PROXY", os.getenv("NO_PROXY"))
        socks_proxy = os.getenv("JIRA_SOCKS_PROXY", os.getenv("SOCKS_PROXY"))

        # Custom headers - service-specific only
        custom_headers = get_custom_headers("JIRA_CUSTOM_HEADERS")

        # Markup translation setting
        disable_jira_markup_translation = (
            os.getenv("DISABLE_JIRA_MARKUP_TRANSLATION", "false").lower() == "true"
        )

        # Client certificate settings
        client_cert = os.getenv("JIRA_CLIENT_CERT")
        client_key = os.getenv("JIRA_CLIENT_KEY")
        client_key_password = os.getenv("JIRA_CLIENT_KEY_PASSWORD")

        return cls(
            url=url,
            auth_type=auth_type,
            username=username,
            api_token=api_token,
            personal_token=personal_token,
            oauth_config=oauth_config,
            ssl_verify=ssl_verify,
            projects_filter=projects_filter,
            http_proxy=http_proxy,
            https_proxy=https_proxy,
            no_proxy=no_proxy,
            socks_proxy=socks_proxy,
            custom_headers=custom_headers,
            disable_jira_markup_translation=disable_jira_markup_translation,
            client_cert=client_cert,
            client_key=client_key,
            client_key_password=client_key_password,
        )

    @classmethod
    def from_env_multi(cls) -> dict[str, "JiraConfig"]:
        """Load multiple Jira instances from environment variables.

        Supports primary instance (JIRA_*) and numbered secondary instances (JIRA_2_*, JIRA_3_*, etc.).

        Returns:
            dict[str, JiraConfig]: Dictionary mapping instance names to configurations.
                - Primary instance uses empty string "" as key
                - Secondary instances use JIRA_{N}_INSTANCE_NAME or default "jira_{N}"

        Raises:
            ValueError: If instance name is invalid or reserved.

        Example:
            ```bash
            JIRA_URL=https://prod.atlassian.net
            JIRA_USERNAME=user@example.com
            JIRA_API_TOKEN=token1

            JIRA_2_URL=https://staging.atlassian.net
            JIRA_2_USERNAME=user@example.com
            JIRA_2_API_TOKEN=token2
            JIRA_2_INSTANCE_NAME=staging
            ```
        """
        configs: dict[str, JiraConfig] = {}
        logger_instance = logging.getLogger("mcp-atlassian.jira.config")

        # Reserved names that cannot be used for instances
        reserved_names = {"jira", "confluence"}

        def validate_instance_name(name: str) -> None:
            """Validate instance name format."""
            if not name:
                return  # Empty string is valid for primary
            if name.lower() in reserved_names:
                raise ValueError(
                    f"Reserved instance name '{name}'. Cannot use reserved names: {reserved_names}"
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
            logger_instance.info(f"Loaded primary Jira instance: {primary_config.url}")
        except ValueError as e:
            logger_instance.debug(
                f"Primary Jira instance not configured or incomplete: {e}"
            )

        # Load secondary instances (JIRA_2_*, JIRA_3_*, etc.)
        instance_num = 2
        while instance_num <= 99:  # Reasonable limit
            prefix = f"JIRA_{instance_num}_"
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
                        # Map JIRA_2_URL -> JIRA_URL, etc.
                        new_key = key.replace(prefix, "JIRA_")
                        instance_env[new_key] = value

                # Get instance name (custom or default)
                instance_name_var = f"{prefix}INSTANCE_NAME"
                instance_name = os.environ.get(
                    instance_name_var, f"jira_{instance_num}"
                )

                # Validate instance name
                validate_instance_name(instance_name)

                # Check for name collision
                if instance_name in configs:
                    logger_instance.warning(
                        f"Instance name collision: '{instance_name}' already exists. Skipping JIRA_{instance_num}."
                    )
                    instance_num += 1
                    continue

                # Temporarily swap environment to load this instance
                original_env = os.environ.copy()
                try:
                    # Clear Jira env vars and set instance-specific ones
                    for key in list(os.environ.keys()):
                        if key.startswith("JIRA_") and not key.startswith(prefix):
                            del os.environ[key]
                    os.environ.update(instance_env)

                    # Load config using from_env()
                    instance_config = cls.from_env()
                    configs[instance_name] = instance_config
                    logger_instance.info(
                        f"Loaded Jira instance '{instance_name}': {instance_config.url}"
                    )
                finally:
                    # Restore original environment
                    os.environ.clear()
                    os.environ.update(original_env)

            except ValueError as e:
                logger_instance.warning(
                    f"Skipping JIRA_{instance_num} (incomplete or invalid config): {e}"
                )

            instance_num += 1

        logger_instance.info(f"Loaded {len(configs)} Jira instance(s)")
        return configs

    def is_auth_configured(self) -> bool:
        """Check if the current authentication configuration is complete and valid for making API calls.

        Returns:
            bool: True if authentication is fully configured, False otherwise.
        """
        logger = logging.getLogger("mcp-atlassian.jira.config")
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
            f"Unknown or unsupported auth_type: {self.auth_type} in JiraConfig"
        )
        return False
