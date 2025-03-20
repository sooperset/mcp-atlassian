"""Base client module for Confluence API interactions."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from atlassian import Confluence

from ..preprocessing.confluence import ConfluencePreprocessor
from ..utils import (
    ApiCache,
    configure_ssl_verification,
    run_parallel,
    with_timeout,
)
from .config import ConfluenceConfig

# Configure logging
logger = logging.getLogger("mcp-atlassian")

T = TypeVar("T")


class ConfluenceClient:
    """Base client for Confluence API interactions."""

    def __init__(
        self, config: ConfluenceConfig | None = None, lazy_init: bool = False
    ) -> None:
        """Initialize the Confluence client with given or environment config.

        Args:
            config: Configuration for Confluence client. If None, will load from
                environment.
            lazy_init: If True, delay initialization of the API client until first use

        Raises:
            ValueError: If configuration is invalid or environment variables are missing
        """
        self.config = config or ConfluenceConfig.from_env()

        # Initialize API cache with default TTL from config or 5 minutes
        self._api_cache = ApiCache(
            default_ttl=getattr(self.config, "cache_ttl_seconds", 300)
        )

        # Timeout settings for asynchronous operations
        self.default_timeout = getattr(self.config, "default_timeout_seconds", 30)
        self.max_concurrent_requests = getattr(
            self.config, "max_concurrent_requests", 5
        )

        # For lazy initialization
        self._is_initialized = False
        self._confluence = None
        self._preprocessor = None

        # Initialize the client immediately if not lazy
        if not lazy_init:
            self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the Confluence client and preprocessor."""
        if self._is_initialized:
            return

        logger.debug("Initializing Confluence client")

        # Initialize the Confluence client based on auth type
        if self.config.auth_type == "token":
            self._confluence = Confluence(
                url=self.config.url,
                token=self.config.personal_token,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )
        else:  # basic auth
            self._confluence = Confluence(
                url=self.config.url,
                username=self.config.username,
                password=self.config.api_token,  # API token is used as password
                cloud=self.config.is_cloud,
            )

        # Configure SSL verification using the shared utility
        if self._confluence and hasattr(self._confluence, "_session"):
            configure_ssl_verification(
                service_name="Confluence",
                url=self.config.url,
                session=self._confluence._session,
                ssl_verify=self.config.ssl_verify,
            )

        # Import here to avoid circular imports
        from ..preprocessing.confluence import ConfluencePreprocessor

        self._preprocessor = ConfluencePreprocessor(
            base_url=self.config.url, confluence_client=self._confluence
        )

        self._is_initialized = True

    @property
    def confluence(self) -> Confluence:
        """Safely access the Confluence API client, initializing if needed.

        Returns:
            The Confluence API client instance
        """
        if not self._is_initialized:
            self._initialize_client()

        if self._confluence is None:
            raise ValueError("Failed to initialize Confluence client")

        return self._confluence

    @property
    def preprocessor(self) -> "ConfluencePreprocessor":
        """Get the Confluence text preprocessor, initializing it if necessary.

        Returns:
            Initialized ConfluencePreprocessor
        """
        if not self._is_initialized:
            self._initialize_client()
        return self._preprocessor

    def clear_cache(self) -> None:
        """Clear all cached data."""
        if hasattr(self, "_api_cache"):
            self._api_cache.clear()

    def invalidate_cache_by_prefix(self, prefix: str) -> None:
        """Invalidate cache entries that start with the given prefix.

        Args:
            prefix: Prefix to match cache keys against
        """
        if hasattr(self, "_api_cache"):
            self._api_cache.invalidate_by_prefix(prefix)

    async def async_request(
        self, func: Callable[..., T], *args: Any, **kwargs: Any
    ) -> Any:
        """Execute an asynchronous request.

        Args:
            func: Confluence API function to execute
            *args: Positional arguments for the function
            **kwargs: Named arguments for the function

        Returns:
            Result of the function

        Raises:
            TimeoutError: If the operation exceeds the configured timeout
            Exception: If an error occurs in the request
        """
        # Guarantee initialization
        if not self._is_initialized:
            self._initialize_client()

        timeout = kwargs.pop("timeout", self.default_timeout)

        @with_timeout(timeout)
        async def _execute() -> T:
            # Execute the function in a separate thread
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

        try:
            return await _execute()
        except TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Error in asynchronous request for {func.__name__}: {str(e)}")
            raise

    def parallel_requests(
        self, requests_data: list[tuple[Callable[..., Any], list, dict]]
    ) -> list[Any]:
        """Execute multiple requests in parallel.

        Args:
            requests_data: List of tuples containing (function, args, kwargs)

        Returns:
            List with the results of the requests in the same order
        """
        # Guarantee initialization
        if not self._is_initialized:
            self._initialize_client()

        return run_parallel(requests_data, max_workers=self.max_concurrent_requests)

    def get_user_details_by_accountid(
        self, account_id: str, expand: str = None
    ) -> dict[str, Any]:
        """Get user details by account ID.

        Args:
            account_id: The account ID of the user
            expand: OPTIONAL expand for get status of user.
                Possible param is "status". Results are "Active, Deactivated"

        Returns:
            User details as a dictionary

        Raises:
            Various exceptions from the Atlassian API if user doesn't exist or
            if there are permission issues
        """
        # Make sure client is initialized
        if not self._is_initialized:
            self._initialize_client()

        return self.confluence.get_user_details_by_accountid(account_id, expand)

    def _process_html_content(
        self, html_content: str, space_key: str
    ) -> tuple[str, str]:
        """Process HTML content into both HTML and markdown formats.

        Args:
            html_content: Raw HTML content from Confluence
            space_key: The key of the space containing the content

        Returns:
            Tuple of (processed_html, processed_markdown)
        """
        # Make sure preprocessor is initialized
        if not self._is_initialized:
            self._initialize_client()

        return self.preprocessor.process_html_content(html_content, space_key)
