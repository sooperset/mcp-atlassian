"""Base client module for Jira API interactions."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from atlassian import Jira

from mcp_atlassian.preprocessing import JiraPreprocessor
from mcp_atlassian.utils import (
    ApiCache,
    configure_ssl_verification,
    run_parallel,
    with_timeout,
)

from .config import JiraConfig

# Configure logging
logger = logging.getLogger("mcp-jira")

T = TypeVar("T")


class JiraClient:
    """Base client for Jira API interactions."""

    def __init__(
        self, config: JiraConfig | None = None, lazy_init: bool = False
    ) -> None:
        """Initialize the Jira client with configuration options.

        Args:
            config: Optional configuration object (will use env vars if not provided)
            lazy_init: If True, delay initialization of the API client until first use

        Raises:
            ValueError: If configuration is invalid or required credentials are missing
        """
        # Load configuration from environment variables if not provided
        self.config = config or JiraConfig.from_env()

        # Cache for frequently used data
        self._field_ids: dict[str, str] | None = None
        self._current_user_account_id: str | None = None

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
        self._jira = None
        self._preprocessor = None

        # Initialize the client immediately if not lazy
        if not lazy_init:
            self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the Jira client and preprocessor."""
        if self._is_initialized:
            return

        logger.debug("Initializing Jira client")

        # Initialize the Jira client based on auth type
        if self.config.auth_type == "token":
            self._jira = Jira(
                url=self.config.url,
                token=self.config.personal_token,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )
        else:  # basic auth
            self._jira = Jira(
                url=self.config.url,
                username=self.config.username,
                password=self.config.api_token,
                cloud=self.config.is_cloud,
                verify_ssl=self.config.ssl_verify,
            )

        # Configure SSL verification using the shared utility
        if self._jira and hasattr(self._jira, "_session"):
            configure_ssl_verification(
                service_name="Jira",
                url=self.config.url,
                session=self._jira._session,
                ssl_verify=self.config.ssl_verify,
            )

        # Initialize the text preprocessor for text processing capabilities
        self._preprocessor = JiraPreprocessor(base_url=self.config.url)

        self._is_initialized = True

    @property
    def jira(self) -> Jira:
        """Get the Jira API client, initializing it if necessary.

        Returns:
            Initialized Jira API client
        """
        if not self._is_initialized:
            self._initialize_client()
        return self._jira

    @property
    def preprocessor(self) -> JiraPreprocessor:
        """Get the Jira text preprocessor, initializing it if necessary.

        Returns:
            Initialized JiraPreprocessor
        """
        if not self._is_initialized:
            self._initialize_client()
        return self._preprocessor

    def clear_cache(self) -> None:
        """Clear all cached data."""
        if hasattr(self, "_api_cache"):
            self._api_cache.clear()

        # Reset any instance cache
        self._field_ids = None
        self._current_user_account_id = None

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
            func: Jira API function to execute
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

    def _clean_text(self, text: str) -> str:
        """Clean text content by:
        1. Processing user mentions and links
        2. Converting HTML/wiki markup to markdown

        Args:
            text: Text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Make sure preprocessor is initialized
        if not self._is_initialized:
            self._initialize_client()

        return self.preprocessor.clean_jira_text(text)

    def _markdown_to_jira(self, markdown_text: str) -> str:
        """
        Convert Markdown syntax to Jira markup syntax.

        Args:
            markdown_text: Text in Markdown format

        Returns:
            Text in Jira markup format
        """
        if not markdown_text:
            return ""

        # Make sure preprocessor is initialized
        if not self._is_initialized:
            self._initialize_client()

        return self.preprocessor.markdown_to_jira(markdown_text)
