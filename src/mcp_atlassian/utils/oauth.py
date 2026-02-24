"""OAuth 2.0 utilities for Atlassian Cloud and Data Center authentication.

This module provides utilities for OAuth 2.0 (3LO) authentication with Atlassian.
It handles:
- OAuth configuration for both Cloud and Data Center
- Token acquisition, storage, and refresh
- Session configuration for API clients
"""

import hashlib
import json
import logging
import os
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import keyring
import requests

from .urls import is_atlassian_cloud_url

# Configure logging
logger = logging.getLogger("mcp-atlassian.oauth")

# Cloud OAuth endpoints
CLOUD_TOKEN_URL = "https://auth.atlassian.com/oauth/token"  # noqa: S105 - This is a public API endpoint URL, not a password
CLOUD_AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
CLOUD_ID_URL = "https://api.atlassian.com/oauth/token/accessible-resources"

# Legacy aliases for backward compatibility
TOKEN_URL = CLOUD_TOKEN_URL  # noqa: S105
AUTHORIZE_URL = CLOUD_AUTHORIZE_URL

# Data Center OAuth endpoint paths (appended to base_url)
DC_TOKEN_PATH = "/rest/oauth2/latest/token"  # noqa: S105
DC_AUTHORIZE_PATH = "/rest/oauth2/latest/authorize"

TOKEN_EXPIRY_MARGIN = 300  # 5 minutes in seconds

# HTTP request timeouts (in seconds)
# Connection timeout: Time to establish TCP connection
# Read timeout: Time to receive response after connection established
HTTP_CONNECT_TIMEOUT = 5
HTTP_READ_TIMEOUT = 20
HTTP_TIMEOUT = (HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT)
KEYRING_SERVICE_NAME = "mcp-atlassian-oauth"


@dataclass
class OAuthConfig:
    """OAuth 2.0 configuration for Atlassian Cloud and Data Center.

    This class manages the OAuth configuration and tokens. It handles:
    - Authentication configuration (client credentials)
    - Token acquisition and refreshing
    - Token storage and retrieval
    - Cloud ID identification (Cloud) or base URL routing (Data Center)
    """

    client_id: str
    client_secret: str
    redirect_uri: str
    scope: str
    cloud_id: str | None = None
    base_url: str | None = None
    refresh_token: str | None = None
    access_token: str | None = None
    expires_at: float | None = None

    def __post_init__(self) -> None:
        """Validate mutual exclusivity of cloud_id and base_url."""
        if self.cloud_id and self.base_url:
            # Check if base_url is a Cloud URL — if so, cloud_id takes precedence
            if is_atlassian_cloud_url(self.base_url):
                self.base_url = None
            else:
                raise ValueError(
                    "OAuthConfig cannot have both cloud_id and base_url set. "
                    "Use cloud_id for Cloud or base_url for Data Center."
                )

    @property
    def is_data_center(self) -> bool:
        """Check if this is a Data Center OAuth configuration.

        Returns:
            True if base_url is set and is not a Cloud URL.
        """
        if not self.base_url:
            return False
        return not is_atlassian_cloud_url(self.base_url)

    @property
    def token_url(self) -> str:
        """Get the token endpoint URL for the configured environment.

        Returns:
            Cloud token URL or Data Center instance-specific token URL.
        """
        if self.is_data_center and self.base_url:
            return f"{self.base_url.rstrip('/')}{DC_TOKEN_PATH}"
        return CLOUD_TOKEN_URL

    @property
    def authorize_url(self) -> str:
        """Get the authorization endpoint URL for the configured environment.

        Returns:
            Cloud authorize URL or Data Center instance-specific authorize URL.
        """
        if self.is_data_center and self.base_url:
            return f"{self.base_url.rstrip('/')}{DC_AUTHORIZE_PATH}"
        return CLOUD_AUTHORIZE_URL

    @property
    def is_token_expired(self) -> bool:
        """Check if the access token is expired or will expire soon.

        Returns:
            True if the token is expired or will expire soon, False otherwise.
        """
        # If we don't have a token or expiry time, consider it expired
        if not self.access_token or not self.expires_at:
            return True

        # Consider the token expired if it will expire within the margin
        return time.time() + TOKEN_EXPIRY_MARGIN >= self.expires_at

    def get_authorization_url(self, state: str) -> str:
        """Get the authorization URL for the OAuth 2.0 flow.

        Args:
            state: Random state string for CSRF protection

        Returns:
            The authorization URL to redirect the user to.
        """
        params: dict[str, str] = {
            "client_id": self.client_id,
            "scope": self.scope,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": state,
        }
        # Cloud-specific params (DC doesn't use audience or prompt)
        if not self.is_data_center:
            params["audience"] = "api.atlassian.com"
            params["prompt"] = "consent"

        return f"{self.authorize_url}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> bool:
        """Exchange the authorization code for access and refresh tokens.

        Args:
            code: The authorization code from the callback

        Returns:
            True if tokens were successfully acquired, False otherwise.
        """
        try:
            payload = {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
            }

            token_endpoint = self.token_url
            logger.info(f"Exchanging authorization code for tokens at {token_endpoint}")
            logger.debug("Sending token exchange request")

            response = requests.post(token_endpoint, data=payload, timeout=HTTP_TIMEOUT)

            # Log more details about the response
            logger.debug(f"Token exchange response status: {response.status_code}")

            if not response.ok:
                logger.error(
                    f"Token exchange failed with status {response.status_code}. "
                    f"Response: {response.text}"
                )
                return False

            # Parse the response
            token_data = response.json()

            # Check if required tokens are present
            if "access_token" not in token_data:
                logger.error(
                    f"Access token not found in response. "
                    f"Keys found: {list(token_data.keys())}"
                )
                return False

            # DC does NOT require refresh_token (no offline_access scope needed)
            if "refresh_token" not in token_data:
                if self.is_data_center:
                    logger.warning(
                        "No refresh_token in DC response — token cannot be refreshed. "
                        "Re-authenticate when the token expires."
                    )
                else:
                    logger.error(
                        "Refresh token not found in response. "
                        "Ensure 'offline_access' scope is included. "
                        f"Keys found: {list(token_data.keys())}"
                    )
                    return False

            self.access_token = token_data["access_token"]
            self.refresh_token = token_data.get("refresh_token")
            self.expires_at = time.time() + token_data.get("expires_in", 3600)

            # Only get cloud ID for Cloud OAuth
            if not self.is_data_center:
                self._get_cloud_id()

            # Save the tokens
            self._save_tokens()

            # Log success message with token details
            logger.info(
                f"OAuth token exchange successful! "
                f"Access token expires in {token_data.get('expires_in', 3600)}s."
            )
            logger.info("Access token obtained successfully.")
            logger.info("Refresh token obtained successfully.")
            if self.cloud_id:
                logger.info(f"Cloud ID successfully retrieved: {self.cloud_id}")
            elif not self.is_data_center:
                logger.warning(
                    "Cloud ID was not retrieved after token exchange. "
                    "Check accessible resources."
                )
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during token exchange: {e}", exc_info=True)
            return False
        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to decode JSON response from token endpoint: {e}",
                exc_info=True,
            )
            logger.error(
                f"Response text that failed to parse: "
                f"{response.text if 'response' in locals() else 'Response object not available'}"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {e}")
            return False

    def refresh_access_token(self) -> bool:
        """Refresh the access token using the refresh token.

        Returns:
            True if the token was successfully refreshed, False otherwise.
        """
        if not self.refresh_token:
            logger.error("No refresh token available")
            return False

        try:
            payload = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            }

            logger.debug(f"Refreshing access token at {self.token_url}...")
            response = requests.post(self.token_url, data=payload, timeout=HTTP_TIMEOUT)
            response.raise_for_status()

            # Parse the response
            token_data = response.json()
            self.access_token = token_data["access_token"]
            # Refresh token might also be rotated
            if "refresh_token" in token_data:
                self.refresh_token = token_data["refresh_token"]
            self.expires_at = time.time() + token_data.get("expires_in", 3600)

            # Save the tokens
            self._save_tokens()

            return True
        except Exception as e:
            logger.error(f"Failed to refresh access token: {e}")
            return False

    def ensure_valid_token(self) -> bool:
        """Ensure the access token is valid, refreshing if necessary.

        Returns:
            True if the token is valid (or was refreshed successfully), False otherwise.
        """
        if not self.is_token_expired:
            return True
        return self.refresh_access_token()

    def _get_cloud_id(self) -> None:
        """Get the cloud ID for the Atlassian instance.

        This method queries the accessible resources endpoint to get the cloud ID.
        The cloud ID is needed for API calls with Cloud OAuth.
        Data Center does not use cloud IDs.
        """
        if self.is_data_center:
            return

        if not self.access_token:
            logger.debug("No access token available to get cloud ID")
            return

        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(CLOUD_ID_URL, headers=headers, timeout=HTTP_TIMEOUT)
            response.raise_for_status()

            resources = response.json()
            if resources and len(resources) > 0:
                # Use the first cloud site (most users have only one)
                self.cloud_id = resources[0]["id"]
                logger.debug(f"Found cloud ID: {self.cloud_id}")
            else:
                logger.warning("No Atlassian sites found in the response")
        except Exception as e:
            logger.error(f"Failed to get cloud ID: {e}")

    def _get_keyring_username(self) -> str:
        """Get the keyring username for storing tokens.

        Includes context (cloud_id or base_url hash) to prevent collisions
        when the same client_id is used across Cloud and Data Center.

        Returns:
            A username string for keyring
        """
        if self.is_data_center and self.base_url:
            url_hash = hashlib.sha256(self.base_url.encode()).hexdigest()[:8]
            return f"oauth-{self.client_id}-dc-{url_hash}"
        if self.cloud_id:
            return f"oauth-{self.client_id}-cloud-{self.cloud_id}"
        return f"oauth-{self.client_id}"

    def _save_tokens(self) -> None:
        """Save the tokens securely using keyring for later use.

        This allows the tokens to be reused between runs without requiring
        the user to go through the authorization flow again.
        """
        try:
            username = self._get_keyring_username()
            base_username = f"oauth-{self.client_id}"

            # Store token data as JSON string in keyring
            token_data = {
                "refresh_token": self.refresh_token,
                "access_token": self.access_token,
                "expires_at": self.expires_at,
                "cloud_id": self.cloud_id,
                "base_url": self.base_url,
            }

            token_json = json.dumps(token_data)

            # Store the token data in the system keyring using context-specific key
            keyring.set_password(KEYRING_SERVICE_NAME, username, token_json)
            logger.debug(f"Saved OAuth tokens to keyring for {username}")

            # Also save to base username for compatibility with load_tokens()
            # which uses the simpler oauth-{client_id} pattern.
            # Note: If the same client_id is used for both Cloud and DC (rare),
            # the base key will be overwritten by whichever saves last.
            if username != base_username:
                keyring.set_password(KEYRING_SERVICE_NAME, base_username, token_json)
                logger.debug(f"Saved OAuth tokens to keyring for {base_username}")

            # Also maintain backwards compatibility with file storage
            # for environments where keyring might not work
            self._save_tokens_to_file(token_data)

        except Exception as e:
            logger.error(f"Failed to save tokens to keyring: {e}")
            # Fall back to file storage if keyring fails
            self._save_tokens_to_file()

    def _save_tokens_to_file(self, token_data: dict | None = None) -> None:
        """Save the tokens to a file as fallback storage.

        Args:
            token_data: Optional dict with token data. If not provided,
                        will use the current object attributes.
        """
        try:
            # Create the directory if it doesn't exist
            token_dir = Path.home() / ".mcp-atlassian"
            token_dir.mkdir(exist_ok=True)

            # Save the tokens to a file
            token_path = token_dir / f"oauth-{self.client_id}.json"

            if token_data is None:
                token_data = {
                    "refresh_token": self.refresh_token,
                    "access_token": self.access_token,
                    "expires_at": self.expires_at,
                    "cloud_id": self.cloud_id,
                    "base_url": self.base_url,
                }

            with open(token_path, "w") as f:
                json.dump(token_data, f)

            logger.debug(f"Saved OAuth tokens to file {token_path} (fallback storage)")
        except Exception as e:
            logger.error(f"Failed to save tokens to file: {e}")

    @staticmethod
    def load_tokens(client_id: str) -> dict[str, Any]:
        """Load tokens securely from keyring.

        Args:
            client_id: The OAuth client ID

        Returns:
            Dict with the token data or empty dict if no tokens found
        """
        username = f"oauth-{client_id}"

        # Try to load tokens from keyring first
        try:
            token_json = keyring.get_password(KEYRING_SERVICE_NAME, username)
            if token_json:
                logger.debug(f"Loaded OAuth tokens from keyring for {username}")
                return json.loads(token_json)
        except Exception as e:
            logger.warning(
                f"Failed to load tokens from keyring: {e}. Trying file fallback."
            )

        # Fall back to loading from file if keyring fails or returns None
        return OAuthConfig._load_tokens_from_file(client_id)

    @staticmethod
    def _load_tokens_from_file(client_id: str) -> dict[str, Any]:
        """Load tokens from a file as fallback.

        Args:
            client_id: The OAuth client ID

        Returns:
            Dict with the token data or empty dict if no tokens found
        """
        token_path = Path.home() / ".mcp-atlassian" / f"oauth-{client_id}.json"

        if not token_path.exists():
            return {}

        try:
            with open(token_path) as f:
                token_data = json.load(f)
                logger.debug(
                    f"Loaded OAuth tokens from file {token_path} (fallback storage)"
                )
                return token_data
        except Exception as e:
            logger.error(f"Failed to load tokens from file: {e}")
            return {}

    @classmethod
    def from_env(
        cls,
        service_url: str | None = None,
        service_type: str | None = None,
    ) -> Optional["OAuthConfig"]:
        """Create an OAuth configuration from environment variables.

        Args:
            service_url: The service URL (e.g., JIRA_URL value) for DC detection.
            service_type: Service type ('jira' or 'confluence') for service-specific
                env vars.

        Returns:
            OAuthConfig instance or None if OAuth is not enabled
        """
        # Check if OAuth is explicitly enabled (allows minimal config)
        oauth_enabled = os.getenv("ATLASSIAN_OAUTH_ENABLE", "").lower() in (
            "true",
            "1",
            "yes",
        )

        # Service-specific env vars take precedence over shared ones
        prefix = service_type.upper() if service_type else None
        client_id = (
            os.getenv(f"{prefix}_OAUTH_CLIENT_ID") if prefix else None
        ) or os.getenv("ATLASSIAN_OAUTH_CLIENT_ID")
        client_secret = (
            os.getenv(f"{prefix}_OAUTH_CLIENT_SECRET") if prefix else None
        ) or os.getenv("ATLASSIAN_OAUTH_CLIENT_SECRET")
        redirect_uri = (
            os.getenv(f"{prefix}_OAUTH_REDIRECT_URI") if prefix else None
        ) or os.getenv("ATLASSIAN_OAUTH_REDIRECT_URI")
        scope = (os.getenv(f"{prefix}_OAUTH_SCOPE") if prefix else None) or os.getenv(
            "ATLASSIAN_OAUTH_SCOPE"
        )

        # Determine if this is a DC instance
        is_dc = bool(service_url) and not is_atlassian_cloud_url(service_url)

        # For DC, redirect_uri and scope can have defaults
        if is_dc:
            if not redirect_uri:
                redirect_uri = "http://localhost:8080/callback"
            if not scope:
                scope = "WRITE"

        # Full OAuth configuration (traditional mode)
        if all([client_id, client_secret]):
            # Need redirect_uri + scope for Cloud, but DC has defaults above
            if not all([redirect_uri, scope]) and not is_dc:
                return None

            cloud_id = os.getenv("ATLASSIAN_OAUTH_CLOUD_ID") if not is_dc else None
            base_url = service_url if is_dc else None

            config = cls(
                client_id=client_id or "",
                client_secret=client_secret or "",
                redirect_uri=redirect_uri or "",
                scope=scope or "",
                cloud_id=cloud_id,
                base_url=base_url,
            )

            # Try to load existing tokens
            token_data = cls.load_tokens(client_id or "")
            if token_data:
                config.refresh_token = token_data.get("refresh_token")
                config.access_token = token_data.get("access_token")
                config.expires_at = token_data.get("expires_at")
                if not config.cloud_id and "cloud_id" in token_data:
                    config.cloud_id = token_data["cloud_id"]
                if not config.base_url and "base_url" in token_data:
                    config.base_url = token_data["base_url"]

            return config

        # Minimal OAuth configuration (user-provided tokens mode)
        elif oauth_enabled:
            # Create minimal config that works with user-provided tokens
            logger.info(
                "Creating minimal OAuth config for user-provided tokens "
                "(ATLASSIAN_OAUTH_ENABLE=true)"
            )
            cloud_id = os.getenv("ATLASSIAN_OAUTH_CLOUD_ID") if not is_dc else None
            base_url = service_url if is_dc else None

            return cls(
                client_id="",  # Will be provided by user tokens
                client_secret="",  # Not needed for user tokens
                redirect_uri="",  # Not needed for user tokens
                scope="",  # Will be determined by user token permissions
                cloud_id=cloud_id,
                base_url=base_url,
            )

        # No OAuth configuration
        return None


@dataclass
class BYOAccessTokenOAuthConfig:
    """OAuth configuration when providing a pre-existing access token.

    This class is used when the user provides their own access token directly,
    bypassing the full OAuth 2.0 (3LO) flow. Works for both Cloud (with cloud_id)
    and Data Center (with base_url).

    This configuration does not support token refreshing.
    """

    access_token: str
    cloud_id: str | None = None
    base_url: str | None = None
    refresh_token: None = field(default=None, repr=False)
    expires_at: None = field(default=None, repr=False)

    @property
    def is_data_center(self) -> bool:
        """Check if this is a Data Center configuration."""
        if not self.base_url:
            return False
        return not is_atlassian_cloud_url(self.base_url)

    @classmethod
    def from_env(
        cls,
        service_url: str | None = None,
        service_type: str | None = None,
    ) -> Optional["BYOAccessTokenOAuthConfig"]:
        """Create a BYOAccessTokenOAuthConfig from environment variables.

        Args:
            service_url: The service URL for DC detection.
            service_type: Service type ('jira' or 'confluence') for service-specific
                env vars.

        Returns:
            BYOAccessTokenOAuthConfig instance or None if required
            environment variables are missing.
        """
        cloud_id = os.getenv("ATLASSIAN_OAUTH_CLOUD_ID")

        # Service-specific access token takes precedence
        prefix = service_type.upper() if service_type else None
        access_token = (
            os.getenv(f"{prefix}_OAUTH_ACCESS_TOKEN") if prefix else None
        ) or os.getenv("ATLASSIAN_OAUTH_ACCESS_TOKEN")

        if not access_token:
            return None

        # Determine if DC
        is_dc = bool(service_url) and not is_atlassian_cloud_url(service_url)
        base_url = service_url if is_dc else None

        # Need either cloud_id (Cloud) or base_url (DC) to be useful
        if not cloud_id and not base_url:
            return None

        return cls(
            access_token=access_token,
            cloud_id=cloud_id if not is_dc else None,
            base_url=base_url,
        )


def get_oauth_config_from_env(
    service_url: str | None = None,
    service_type: str | None = None,
) -> OAuthConfig | BYOAccessTokenOAuthConfig | None:
    """Get the appropriate OAuth configuration from environment variables.

    This function attempts to load standard OAuth configuration first (OAuthConfig).
    If that's not available, it tries to load a "Bring Your Own Access Token"
    configuration (BYOAccessTokenOAuthConfig).

    Args:
        service_url: The service URL for DC detection.
        service_type: Service type ('jira' or 'confluence') for service-specific
            env vars.

    Returns:
        An instance of OAuthConfig or BYOAccessTokenOAuthConfig if environment
        variables are set for either, otherwise None.
    """
    return BYOAccessTokenOAuthConfig.from_env(
        service_url=service_url, service_type=service_type
    ) or OAuthConfig.from_env(service_url=service_url, service_type=service_type)


def configure_oauth_session(
    session: requests.Session, oauth_config: OAuthConfig | BYOAccessTokenOAuthConfig
) -> bool:
    """Configure a requests session with OAuth 2.0 authentication.

    This function ensures the access token is valid and adds it to the session headers.

    Args:
        session: The requests session to configure
        oauth_config: The OAuth configuration to use

    Returns:
        True if the session was successfully configured, False otherwise
    """
    logger.debug(
        f"configure_oauth_session: Received OAuthConfig with "
        f"access_token_present={bool(oauth_config.access_token)}, "
        f"refresh_token_present={bool(oauth_config.refresh_token)}, "
        f"cloud_id='{oauth_config.cloud_id}'"
    )

    # Early return when no tokens are available at all (#858)
    if not oauth_config.access_token and not oauth_config.refresh_token:
        logger.warning(
            "configure_oauth_session: No access_token or refresh_token available. "
            "Cannot configure OAuth session. If using per-request auth, "
            "the token should come from the request header."
        )
        return False

    # If user provided only an access token (no refresh_token), use it directly
    if oauth_config.access_token and not oauth_config.refresh_token:
        logger.info(
            "configure_oauth_session: Using provided OAuth access token directly "
            "(no refresh_token)."
        )
        session.headers["Authorization"] = f"Bearer {oauth_config.access_token}"
        return True
    logger.debug("configure_oauth_session: Proceeding to ensure_valid_token.")
    # Otherwise, ensure we have a valid token (refresh if needed)
    if isinstance(oauth_config, BYOAccessTokenOAuthConfig):
        logger.error(
            "configure_oauth_session: oauth access token configuration "
            "provided as empty string."
        )
        return False
    if not oauth_config.ensure_valid_token():
        logger.error(
            f"configure_oauth_session: ensure_valid_token returned False. "
            f"Token was expired: {oauth_config.is_token_expired}, "
            f"Refresh token present for attempt: {bool(oauth_config.refresh_token)}"
        )
        return False
    session.headers["Authorization"] = f"Bearer {oauth_config.access_token}"
    logger.info("Successfully configured OAuth session for Atlassian API")
    return True
