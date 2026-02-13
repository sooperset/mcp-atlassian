"""Base client module for Zephyr Scale API interactions."""

import logging
from typing import Any

import requests
from requests import Session

from ..exceptions import MCPAtlassianAuthenticationError
from ..utils.logging import get_masked_session_headers, mask_sensitive
from ..utils.oauth import configure_oauth_session
from ..utils.ssl import configure_ssl_verification
from .config import ZephyrConfig

logger = logging.getLogger("mcp-zephyr")


class ZephyrClient:
    """Base client for Zephyr Scale API interactions."""

    config: ZephyrConfig
    session: Session

    def __init__(self, config: ZephyrConfig | None = None) -> None:
        """Initialize the Zephyr Scale client with configuration options.

        Args:
            config: Optional configuration object (will use env vars if not provided)

        Raises:
            ValueError: If configuration is invalid or required credentials are missing
            MCPAtlassianAuthenticationError: If OAuth authentication fails
        """
        self.config = config or ZephyrConfig.from_env()
        self.session = Session()

        # Configure authentication based on auth type
        if self.config.auth_type == "oauth":
            if not self.config.oauth_config or not self.config.oauth_config.cloud_id:
                error_msg = "OAuth authentication requires a valid cloud_id"
                raise ValueError(error_msg)

            if not configure_oauth_session(self.session, self.config.oauth_config):
                error_msg = "Failed to configure OAuth session"
                raise MCPAtlassianAuthenticationError(error_msg)

            # Zephyr Scale Cloud API base URL
            self.base_url = f"https://api.atlassian.com/ex/zephyr/{self.config.oauth_config.cloud_id}/v2"
        elif self.config.auth_type == "bearer":
            logger.debug(
                f"Initializing Zephyr client with Bearer token auth. "
                f"URL: {self.config.url}, "
                f"Token (masked): {mask_sensitive(str(self.config.api_token))}"
            )
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.config.api_token}",
                    "Content-Type": "application/json",
                }
            )
            self.base_url = self.config.url.rstrip("/")
        elif self.config.auth_type == "pat":
            logger.debug(
                f"Initializing Zephyr client with Token (PAT) auth. "
                f"URL: {self.config.url}, "
                f"Token (masked): {mask_sensitive(str(self.config.personal_token))}"
            )
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.config.personal_token}",
                    "Content-Type": "application/json",
                }
            )
            self.base_url = self.config.url.rstrip("/")
        else:  # basic auth
            logger.debug(
                f"Initializing Zephyr client with Basic auth. "
                f"URL: {self.config.url}, Username: {self.config.username}"
            )
            self.session.auth = (self.config.username, self.config.password)
            self.session.headers.update({"Content-Type": "application/json"})
            self.base_url = self.config.url.rstrip("/")

        logger.debug(
            f"Zephyr client initialized. "
            f"Session headers (Authorization masked): "
            f"{get_masked_session_headers(dict(self.session.headers))}"
        )

        # Configure SSL verification
        configure_ssl_verification(
            service_name="Zephyr",
            url=self.config.url,
            session=self.session,
            ssl_verify=self.config.ssl_verify,
            client_cert=self.config.client_cert,
            client_key=self.config.client_key,
            client_key_password=self.config.client_key_password,
        )

        # Configure proxies if provided
        if self.config.http_proxy or self.config.https_proxy:
            proxies = {}
            if self.config.http_proxy:
                proxies["http"] = self.config.http_proxy
            if self.config.https_proxy:
                proxies["https"] = self.config.https_proxy
            self.session.proxies.update(proxies)

        # Add custom headers if provided
        if self.config.custom_headers:
            self.session.headers.update(self.config.custom_headers)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: Any | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make an HTTP request to the Zephyr Scale API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (will be appended to base_url)
            params: Query parameters
            json: JSON body
            data: Request body data

        Returns:
            Response JSON data

        Raises:
            requests.HTTPError: If the request fails
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"Making {method} request to {url}")

        response = self.session.request(
            method=method, url=url, params=params, json=json, data=data
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            logger.error(f"HTTP error: {e}, Response: {response.text}")
            raise

        if response.status_code == 204:  # No content
            return {}

        return response.json()

    def get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        """Make a GET request."""
        return self._make_request("GET", endpoint, params=params)

    def post(
        self, endpoint: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        """Make a POST request."""
        return self._make_request("POST", endpoint, json=json)

    def put(
        self, endpoint: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        """Make a PUT request."""
        return self._make_request("PUT", endpoint, json=json)

    def delete(self, endpoint: str) -> dict[str, Any] | list[Any]:
        """Make a DELETE request."""
        return self._make_request("DELETE", endpoint)
