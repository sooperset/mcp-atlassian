"""Configuration module for Jira API interactions."""

import logging
import os
import re
from dataclasses import dataclass, field
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

logger = logging.getLogger("mcp-atlassian.jira.config")

_PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# str.strip() does not remove zero-width characters or a BOM, so a key pasted
# from a browser or spreadsheet can carry one invisibly. That matters more here
# than in most settings: an unmatched key silently leaves the project
# unprotected, and this guard exists to keep automation off a customer-facing
# portal, so it has to normalize them away rather than fail open.
_INVISIBLE_CHARS = dict.fromkeys(
    map(ord, "​‌‍⁠﻿")  # ZWSP, ZWNJ, ZWJ, word-joiner, BOM
)


def normalize_project_key(raw: str) -> str:
    """Normalize a project key for internal-only comparisons."""
    return raw.translate(_INVISIBLE_CHARS).strip().upper()


def _parse_internal_only_projects(raw: str | None) -> frozenset[str]:
    """Parse JIRA_INTERNAL_ONLY_PROJECTS into a set of normalized project keys.

    Tolerant of malformed input: extra whitespace, invisible characters, blank
    entries from double/trailing commas, and mixed case are all normalized away.
    An unset or empty value returns an empty set, which is the semantic
    "guard disabled" state used throughout the internal-only-projects
    feature — this keeps the feature strictly opt-in and a no-op for
    every other deployment of this server.

    An entry that still does not look like a project key after normalization is
    kept (it simply never matches) but logged as a warning: silently discarding
    it would leave an operator believing a project is guarded when it is not.

    Args:
        raw: Raw comma-separated project keys from the environment
            (e.g. "CC" or "CC, HELP ,, support").

    Returns:
        A frozenset of normalized project keys. Empty when raw is None,
        empty, or contains only blank entries.
    """
    if not raw:
        return frozenset()

    keys = set()
    for entry in raw.split(","):
        key = normalize_project_key(entry)
        if not key:
            continue
        if not _PROJECT_KEY_RE.match(key):
            logger.warning(
                "JIRA_INTERNAL_ONLY_PROJECTS entry %r is not a valid project key; "
                "it will never match an issue, so that project is NOT guarded.",
                entry,
            )
        keys.add(key)
    return frozenset(keys)


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
    auth_type: Literal[
        "basic", "pat", "oauth", "cert", "external"
    ]  # Authentication type
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
    proxy_wpad_enable: bool = False  # Whether to load PAC/WPAD configuration
    proxy_wpad_url: str | None = None  # PAC URL used when WPAD is enabled
    custom_headers: dict[str, str] | None = None  # Custom HTTP headers
    passthrough_headers: list[str] | None = None  # Request headers to pass through
    disable_jira_markup_translation: bool = (
        False  # Disable automatic markup translation between formats
    )
    client_cert: str | None = None  # Client certificate file path (.pem)
    client_key: str | None = None  # Client private key file path (.pem)
    client_key_password: str | None = None  # Password for encrypted private key
    sla_config: SLAConfig | None = None  # Optional SLA configuration
    timeout: int = 75  # Connection timeout in seconds
    internal_only_projects: frozenset[str] = field(
        default_factory=frozenset
    )  # Project keys where jira_add_comment/jira_edit_comment enforce
    # internal-only (non-customer-visible) comments. See
    # JIRA_INTERNAL_ONLY_PROJECTS. Empty by default (guard disabled).

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
    def from_env(cls) -> "JiraConfig":
        """Create configuration from environment variables.

        Returns:
            JiraConfig with values from environment variables

        Raises:
            ValueError: If required environment variables are missing or invalid
        """
        url = os.getenv("JIRA_URL")
        if (
            not url
            and not os.getenv("ATLASSIAN_OAUTH_ENABLE")
            and not is_env_truthy("ATLASSIAN_EXTERNAL_AUTH_ENABLE")
        ):
            error_msg = (
                "Missing required JIRA_URL environment variable. "
                "Set JIRA_URL to your Jira base URL, for example "
                "https://your-company.atlassian.net"
            )
            raise ValueError(error_msg)

        # Determine authentication type based on available environment variables
        username = os.getenv("JIRA_USERNAME")
        api_token = os.getenv("JIRA_API_TOKEN")
        personal_token = os.getenv("JIRA_PERSONAL_TOKEN")
        client_cert_env = os.getenv("JIRA_CLIENT_CERT")

        # Check for OAuth configuration (pass service info for DC detection)
        oauth_config = get_oauth_config_from_env(service_url=url, service_type="jira")
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
                    missing_fields.append("JIRA_USERNAME")
                if not api_token:
                    missing_fields.append("JIRA_API_TOKEN")
                missing_fields_text = ", ".join(missing_fields)
                error_msg = (
                    "Cloud authentication requires JIRA_USERNAME and "
                    "JIRA_API_TOKEN, or OAuth configuration "
                    "(set ATLASSIAN_OAUTH_ENABLE=true for user-provided tokens). "
                    "Jira Cloud authentication is incomplete. Missing: "
                    f"{missing_fields_text}. "
                    "Set JIRA_USERNAME and JIRA_API_TOKEN, or enable OAuth with "
                    "ATLASSIAN_OAUTH_ENABLE=true."
                )
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
            elif client_cert_env:
                auth_type = "cert"
            else:
                error_msg = (
                    "Server/Data Center authentication requires "
                    "JIRA_PERSONAL_TOKEN, JIRA_USERNAME and JIRA_API_TOKEN, "
                    "or JIRA_CLIENT_CERT for mTLS authentication. "
                    "Jira Server/Data Center authentication is incomplete. "
                    "Set JIRA_PERSONAL_TOKEN, set both JIRA_USERNAME and "
                    "JIRA_API_TOKEN, or set JIRA_CLIENT_CERT."
                )
                raise ValueError(error_msg)

        # SSL verification (for Server/DC)
        ssl_verify = is_env_ssl_verify("JIRA_SSL_VERIFY")

        # Get the projects filter if provided
        projects_filter = os.getenv("JIRA_PROJECTS_FILTER")

        # Internal-only projects: server-side guard forcing
        # jira_add_comment/jira_edit_comment to internal (non-customer-visible)
        # comments for these JSM project keys. Unset/empty = no-op.
        internal_only_projects = _parse_internal_only_projects(
            os.getenv("JIRA_INTERNAL_ONLY_PROJECTS")
        )

        # Proxy settings
        proxy_settings = get_proxy_settings_from_env("JIRA")

        # Custom headers - service-specific only
        custom_headers = get_custom_headers("JIRA_CUSTOM_HEADERS")
        passthrough_headers = get_header_names("JIRA_PASSTHROUGH_HEADERS")

        # Markup translation setting
        disable_jira_markup_translation = (
            os.getenv("DISABLE_JIRA_MARKUP_TRANSLATION", "false").lower() == "true"
        )

        # Client certificate settings
        client_cert = os.getenv("JIRA_CLIENT_CERT")
        client_key = os.getenv("JIRA_CLIENT_KEY")
        client_key_password = os.getenv("JIRA_CLIENT_KEY_PASSWORD")

        # Timeout setting
        timeout = 75  # Default timeout
        if os.getenv("JIRA_TIMEOUT") and os.getenv("JIRA_TIMEOUT", "").isdigit():
            timeout = int(os.getenv("JIRA_TIMEOUT", "75"))

        return cls(
            url=url or "",
            auth_type=auth_type,
            username=username,
            api_token=api_token,
            personal_token=personal_token,
            oauth_config=oauth_config,
            ssl_verify=ssl_verify,
            projects_filter=projects_filter,
            http_proxy=proxy_settings["http_proxy"],
            https_proxy=proxy_settings["https_proxy"],
            no_proxy=proxy_settings["no_proxy"],
            socks_proxy=proxy_settings["socks_proxy"],
            proxy_wpad_enable=bool(proxy_settings["proxy_wpad_enable"]),
            proxy_wpad_url=proxy_settings["proxy_wpad_url"],
            custom_headers=custom_headers,
            passthrough_headers=passthrough_headers,
            disable_jira_markup_translation=disable_jira_markup_translation,
            client_cert=client_cert,
            client_key=client_key,
            client_key_password=client_key_password,
            timeout=timeout,
            internal_only_projects=internal_only_projects,
        )

    def is_auth_configured(self) -> bool:
        """Check if the current authentication configuration is complete and valid for making API calls.

        Returns:
            bool: True if authentication is fully configured, False otherwise.
        """
        logger = logging.getLogger("mcp-atlassian.jira.config")
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
            f"Unknown or unsupported auth_type: {self.auth_type} in JiraConfig"
        )
        return False
