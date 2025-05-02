"""Bitbucket Server API client."""

import logging
from typing import Any

import httpx

from ..exceptions import BitbucketServerApiError
from .config import BitbucketServerConfig
from .constants import API_BASE_PATH

logger = logging.getLogger("mcp-atlassian.bitbucket_server")


class BitbucketServerClient:
    """Client for Bitbucket Server REST API."""

    def __init__(self, config: BitbucketServerConfig) -> None:
        """Initialize Bitbucket Server client.

        Args:
            config: Bitbucket Server configuration
        """
        self.config = config
        self.base_url = f"{config.url}{API_BASE_PATH}"
        self.session = self._create_session()

    def _create_session(self) -> httpx.Client:
        """Create HTTP session with authentication.

        Returns:
            Authenticated HTTP session
        """
        session = httpx.Client(verify=self.config.ssl_verify)

        if self.config.auth_type == "basic":
            session.auth = self.config.get_auth()
        else:
            # For personal access token, add Authorization header
            headers = self.config.get_auth()
            session.headers.update(headers)

        return session

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send GET request to Bitbucket Server API.

        Args:
            path: API endpoint path (without base URL)
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            BitbucketServerApiError: If the request fails
        """
        url = f"{self.base_url}{path}"
        logger.debug(f"Sending GET request to {url}")

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error {e.response.status_code} for {url}: {e.response.text}"
            )
            raise BitbucketServerApiError(
                f"HTTP error: {e.response.status_code} - {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"Request error for {url}: {str(e)}")
            raise BitbucketServerApiError(f"Request error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error for {url}: {str(e)}")
            raise BitbucketServerApiError(f"Unexpected error: {str(e)}")

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send POST request to Bitbucket Server API.

        Args:
            path: API endpoint path (without base URL)
            json: JSON request body
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            BitbucketServerApiError: If the request fails
        """
        url = f"{self.base_url}{path}"
        logger.debug(f"Sending POST request to {url}")

        try:
            response = self.session.post(url, json=json, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error {e.response.status_code} for {url}: {e.response.text}"
            )
            raise BitbucketServerApiError(
                f"HTTP error: {e.response.status_code} - {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"Request error for {url}: {str(e)}")
            raise BitbucketServerApiError(f"Request error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error for {url}: {str(e)}")
            raise BitbucketServerApiError(f"Unexpected error: {str(e)}")

    def close(self) -> None:
        """Close HTTP session."""
        self.session.close()
