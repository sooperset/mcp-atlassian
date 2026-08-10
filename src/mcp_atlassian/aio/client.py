"""Base client module for AIO Tests API interactions."""

import logging
import os
from typing import Any
from urllib.parse import quote

import requests
from requests import Response, Session

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.utils.logging import log_config_param, mask_sensitive
from mcp_atlassian.utils.ssl import configure_ssl_verification

from .config import AIOConfig

logger = logging.getLogger("mcp-aio")

# Requests that take longer than this are aborted, in seconds.
DEFAULT_TIMEOUT = 60


class AIOApiError(Exception):
    """Raised when the AIO Tests API returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Initialize the error.

        Args:
            message: Human-readable error message.
            status_code: HTTP status code returned by the API, if any.
        """
        super().__init__(message)
        self.status_code = status_code


class AIOClient:
    """Base client for AIO Tests API interactions.

    AIO Tests is not covered by ``atlassian-python-api``, so this client speaks
    to the REST API directly over a configured :class:`requests.Session`.
    """

    config: AIOConfig

    def __init__(self, config: AIOConfig | None = None) -> None:
        """Initialize the AIO Tests client.

        Args:
            config: Optional configuration object (loaded from env vars if omitted).

        Raises:
            ValueError: If the configuration is invalid or credentials are missing.
        """
        self.config = config or AIOConfig.from_env()
        self.session = Session()

        if self.config.auth_type == "token":
            logger.debug(
                "Initializing AIO Tests client with AioAuth token. "
                f"URL: {self.config.url}, "
                f"Token (masked): {mask_sensitive(str(self.config.api_token))}"
            )
            self.session.headers["Authorization"] = f"AioAuth {self.config.api_token}"
        elif self.config.auth_type == "pat":
            logger.debug(
                "Initializing AIO Tests client with Token (PAT) auth. "
                f"URL: {self.config.url}, "
                f"Token (masked): {mask_sensitive(str(self.config.personal_token))}"
            )
            self.session.headers["Authorization"] = (
                f"Bearer {self.config.personal_token}"
            )
        else:  # basic auth
            logger.debug(
                "Initializing AIO Tests client with Basic auth. "
                f"URL: {self.config.url}, Username: {self.config.username}"
            )
            self.session.auth = (
                str(self.config.username),
                str(self.config.password),
            )

        self.session.headers["Accept"] = "application/json"

        configure_ssl_verification(
            service_name="AIO Tests",
            url=self.config.url,
            session=self.session,
            ssl_verify=self.config.ssl_verify,
            client_cert=self.config.client_cert,
            client_key=self.config.client_key,
            client_key_password=self.config.client_key_password,
        )

        proxies = {}
        if self.config.http_proxy:
            proxies["http"] = self.config.http_proxy
        if self.config.https_proxy:
            proxies["https"] = self.config.https_proxy
        if self.config.socks_proxy:
            proxies["socks"] = self.config.socks_proxy
        if proxies:
            self.session.proxies.update(proxies)
            for key, value in proxies.items():
                log_config_param(
                    logger, "AIO Tests", f"{key.upper()}_PROXY", value, sensitive=True
                )
        if self.config.no_proxy and isinstance(self.config.no_proxy, str):
            os.environ["NO_PROXY"] = self.config.no_proxy
            log_config_param(logger, "AIO Tests", "NO_PROXY", self.config.no_proxy)

        if self.config.custom_headers:
            logger.debug(
                f"Applying {len(self.config.custom_headers)} custom headers to "
                "AIO Tests session"
            )
            self.session.headers.update(self.config.custom_headers)

    @staticmethod
    def project_path(project_key: str, *segments: str | int) -> str:
        """Build a project-scoped API path with URL-escaped segments.

        Args:
            project_key: Jira project key or numeric ID.
            *segments: Additional path segments appended after the project.

        Returns:
            A relative API path such as ``/project/PROJ/testcase/detail``.

        Raises:
            ValueError: If the project key is empty.
        """
        if not str(project_key).strip():
            raise ValueError("Project key or ID is required")
        parts = [quote(str(project_key).strip(), safe="")]
        parts.extend(quote(str(segment), safe="") for segment in segments)
        return "/project/" + "/".join(parts)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        """Send a request to the AIO Tests API and return the decoded body.

        Args:
            method: HTTP method (``GET``, ``POST``, ``PUT``, ...).
            path: API path relative to the configured base URL.
            params: Optional query parameters; ``None`` values are dropped.
            json: Optional JSON request body.

        Returns:
            The decoded JSON response, or the raw text when the body is not JSON.

        Raises:
            MCPAtlassianAuthenticationError: If the API rejects the credentials.
            AIOApiError: If the API returns any other error response.
        """
        url = f"{self.config.url}{path}"
        query = (
            {key: value for key, value in params.items() if value is not None}
            if params
            else None
        )
        logger.debug(f"AIO Tests request: {method} {url} params={query}")

        try:
            response = self.session.request(
                method,
                url,
                params=query,
                json=json,
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AIOApiError(f"Network error calling AIO Tests API: {exc}") from exc

        if not response.ok:
            self._raise_for_response(method, path, response)

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _raise_for_response(method: str, path: str, response: Response) -> None:
        """Translate an error response into the matching exception.

        Args:
            method: HTTP method of the failed request.
            path: API path of the failed request.
            response: The error response.

        Raises:
            MCPAtlassianAuthenticationError: For 401 and 403 responses.
            AIOApiError: For every other error status.
        """
        detail = response.text.strip()
        if len(detail) > 500:
            detail = f"{detail[:500]}..."
        message = (
            f"AIO Tests API error {response.status_code} for {method} {path}"
            f"{f': {detail}' if detail else ''}"
        )
        if response.status_code in (401, 403):
            logger.error(message)
            raise MCPAtlassianAuthenticationError(
                f"Authentication failed for AIO Tests ({response.status_code}). "
                "Verify AIO_API_TOKEN (Cloud) or the Jira credentials (Server/DC), "
                "and that the user has access to the project."
            )
        logger.error(message)
        raise AIOApiError(message, status_code=response.status_code)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Send a GET request.

        Args:
            path: API path relative to the configured base URL.
            params: Optional query parameters.

        Returns:
            The decoded JSON response.
        """
        return self.request("GET", path, params=params)

    def post(
        self,
        path: str,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send a POST request.

        Args:
            path: API path relative to the configured base URL.
            json: Optional JSON request body.
            params: Optional query parameters.

        Returns:
            The decoded JSON response.
        """
        return self.request("POST", path, params=params, json=json)

    def put(
        self,
        path: str,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send a PUT request.

        Args:
            path: API path relative to the configured base URL.
            json: Optional JSON request body.
            params: Optional query parameters.

        Returns:
            The decoded JSON response.
        """
        return self.request("PUT", path, params=params, json=json)
