"""Utility functions for the MCP Atlassian integration."""

import asyncio
import functools
import logging
import re
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import (
    Any,
    Generic,
    TypeVar,
)
from urllib.parse import urlparse

from requests.adapters import HTTPAdapter
from requests.sessions import Session

# Configure logging
logger = logging.getLogger("mcp-atlassian")

T = TypeVar("T")


class CacheItem(Generic[T]):
    """Cache item with timestamp for expiration checks."""

    def __init__(self, value: T, ttl_seconds: int = 300) -> None:
        """Initialize cache item with value and expiration time.

        Args:
            value: The value to store in cache
            ttl_seconds: Time to live in seconds (default: 5 minutes)
        """
        self.value = value
        self.timestamp = datetime.now(timezone.utc)
        self.ttl_seconds = ttl_seconds

    def is_expired(self) -> bool:
        """Check if the item has expired.

        Returns:
            True if the item has expired, False otherwise
        """
        return datetime.now(timezone.utc) > self.timestamp + timedelta(
            seconds=self.ttl_seconds
        )


class ApiCache:
    """Generic cache for API responses with TTL-based invalidation."""

    def __init__(self, default_ttl: int = 300) -> None:
        """Initialize the cache.

        Args:
            default_ttl: Default time to live in seconds (default: 5 minutes)
        """
        self._cache: dict[str, CacheItem] = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        """Get a value from the cache if it exists and is not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        item = self._cache.get(key)
        if item is None or item.is_expired():
            if item is not None:
                # Clear expired item
                del self._cache[key]
            return None
        return item.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value in the cache with specified TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default: None, uses instance default)
        """
        self._cache[key] = CacheItem(value, ttl or self.default_ttl)

    def delete(self, key: str) -> None:
        """Delete a value from the cache.

        Args:
            key: Cache key to delete
        """
        if key in self._cache:
            del self._cache[key]

    def invalidate_by_prefix(self, prefix: str) -> None:
        """Invalidate all keys that start with the given prefix.

        Args:
            prefix: Key prefix to match
        """
        keys_to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
        for key in keys_to_delete:
            del self._cache[key]

    def clear(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()

    def size(self) -> int:
        """Get the current size of the cache.

        Returns:
            Number of cached items
        """
        return len(self._cache)


def cached(
    key_prefix: str, ttl_seconds: int | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for caching function results.

    Example usage:
        @cached("projects", 3600)
        def get_all_projects(self):
            # Function implementation

    Args:
        key_prefix: Prefix for cache key
        ttl_seconds: Time to live in seconds

    Returns:
        Decorator function
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            # Generate a unique cache key based on function args
            arg_string = "_".join([str(arg) for arg in args])
            kwarg_string = "_".join([f"{k}={v}" for k, v in sorted(kwargs.items())])
            cache_key = f"{key_prefix}_{func.__name__}_{arg_string}_{kwarg_string}"

            # Try to get from cache first
            # Access the instance cache from the instance self
            cache = getattr(self, "_api_cache", None)
            if cache:
                cached_value = cache.get(cache_key)
                if cached_value is not None:
                    return cached_value

            # If not in cache or no cache available, execute function
            result = func(self, *args, **kwargs)

            # Store in cache if cache is available
            if cache:
                ttl = ttl_seconds if ttl_seconds is not None else cache.default_ttl
                cache.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


class SSLIgnoreAdapter(HTTPAdapter):
    """HTTP adapter that ignores SSL verification.

    A custom transport adapter that disables SSL certificate verification for specific domains.

    The adapter overrides the cert_verify method to force verify=False, ensuring SSL verification
    is bypassed regardless of the verify parameter passed to the request. This only affects
    domains where the adapter is explicitly mounted.

    Example:
        session = requests.Session()
        adapter = SSLIgnoreAdapter()
        session.mount('https://example.com', adapter)  # Disable SSL verification for example.com

    Warning:
        Only use this adapter when SSL verification must be disabled for specific use cases.
        Disabling SSL verification reduces security by making the connection vulnerable to
        man-in-the-middle attacks.
    """

    def cert_verify(self, conn: Any, url: str, verify: bool, cert: Any | None) -> None:
        """Override cert verification to disable SSL verification.

        Args:
            conn: The connection
            url: The URL being requested
            verify: The original verify parameter (ignored)
            cert: Client certificate path
        """
        super().cert_verify(conn, url, verify=False, cert=cert)


def configure_ssl_verification(
    service_name: str, url: str, session: Session, ssl_verify: bool
) -> None:
    """Configure SSL verification for a specific service.

    If SSL verification is disabled, this function will configure the session
    to use a custom SSL adapter that bypasses certificate validation for the
    service's domain.

    Args:
        service_name: Name of the service for logging (e.g., "Confluence", "Jira")
        url: The base URL of the service
        session: The requests session to configure
        ssl_verify: Whether SSL verification should be enabled
    """
    if not ssl_verify:
        logger.warning(
            f"SSL verification is disabled for {service_name}. This may be insecure."
        )

        # Get the domain from the configured URL
        domain = urlparse(url).netloc

        # Mount the adapter to handle requests to this domain
        adapter = SSLIgnoreAdapter()
        session.mount(f"https://{domain}", adapter)
        session.mount(f"http://{domain}", adapter)


def paginated_iterator(
    fetch_function: Callable[[int, int], tuple[list[Any], int]],
    start_at: int = 0,
    max_per_page: int = 50,
    max_total: int = None,
) -> Generator[Any, None, None]:
    """
    Create a generator that handles pagination automatically for API results.

    Args:
        fetch_function: Function that takes (start_at, max_results) parameters and returns (items, total)
        start_at: Starting index for pagination
        max_per_page: Maximum number of items to fetch per page
        max_total: Maximum total number of items to return (None for all)

    Yields:
        Individual items from the paginated results
    """
    total_items_seen = 0
    current_start = start_at
    total_available = None

    while True:
        # Check if we've reached the requested maximum
        if max_total is not None and total_items_seen >= max_total:
            break

        # Adjust max_results for the final page if needed
        if max_total is not None:
            remaining = max_total - total_items_seen
            current_max = min(max_per_page, remaining)
        else:
            current_max = max_per_page

        # Fetch the current page
        items, total_available = fetch_function(current_start, current_max)

        # If no items returned or empty response, we're done
        if not items:
            break

        # Yield each item
        for item in items:
            yield item
            total_items_seen += 1

            # Check again if we've hit the maximum
            if max_total is not None and total_items_seen >= max_total:
                break

        # If we've seen all available items, we're done
        if (
            total_available is not None
            and current_start + len(items) >= total_available
        ):
            break

        # Move to the next page
        current_start += len(items)

        # If no items were returned but we haven't reached the total,
        # something is wrong - prevent infinite loop
        if len(items) == 0:
            break


def chunked_request(
    items: list[Any], chunk_size: int = 50
) -> Generator[list[Any], None, None]:
    """
    Split a large list into chunks for processing in batches.

    Args:
        items: List of items to chunk
        chunk_size: Maximum size of each chunk

    Yields:
        Lists of items, each with at most chunk_size items
    """
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]


def run_async(func: Callable, *args: Any, **kwargs: Any) -> Any:
    """
    Execute a function asynchronously in an event loop.

    Args:
        func: Function to be executed
        *args: Positional arguments for the function
        **kwargs: Named arguments for the function

    Returns:
        Result of the function
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        if asyncio.iscoroutinefunction(func):
            return loop.run_until_complete(func(*args, **kwargs))
        else:
            return loop.run_until_complete(asyncio.to_thread(func, *args, **kwargs))
    finally:
        loop.close()


async def gather_with_concurrency(limit: int, *tasks: Any) -> list[Any]:
    """
    Execute asynchronous tasks with concurrency limit.

    Args:
        limit: Maximum number of concurrent tasks
        *tasks: Asynchronous tasks (coroutines)

    Returns:
        List with the results of the tasks
    """
    semaphore = asyncio.Semaphore(limit)

    async def sem_task(task: Any) -> Any:
        async with semaphore:
            return await task

    return await asyncio.gather(*(sem_task(task) for task in tasks))


def run_parallel(
    funcs_with_args: list[tuple[Callable, list, dict]], max_workers: int = None
) -> list[Any]:
    """
    Execute multiple functions in parallel using ThreadPoolExecutor.

    Args:
        funcs_with_args: List of tuples containing (function, args, kwargs)
        max_workers: Maximum number of workers

    Returns:
        List with the results of the functions in the same order
    """
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for func, args, kwargs in funcs_with_args:
            if not args:
                args = []
            if not kwargs:
                kwargs = {}
            futures.append(executor.submit(func, *args, **kwargs))

        return [future.result() for future in futures]


def with_timeout(
    timeout_seconds: int,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to add timeout to an asynchronous function.

    Args:
        timeout_seconds: Maximum execution time in seconds

    Returns:
        Decorator
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Function {func.__name__} exceeded timeout of {timeout_seconds}s"
                )
                raise TimeoutError(
                    f"Operation exceeded the limit of {timeout_seconds} seconds"
                )

        return wrapper

    return decorator


class TextChunker:
    """Utility for incremental processing of large text blocks."""

    def __init__(self, chunk_size: int = 5000, overlap: int = 200) -> None:
        """
        Initialize the text chunker.

        Args:
            chunk_size: Maximum size of each chunk in characters
            overlap: Overlap between chunks to avoid breaking entities
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def _find_break_point(self, text: str, position: int) -> int:
        """
        Find a suitable point to break the text near the position.
        Looks for line breaks, paragraphs, or sentences.

        Args:
            text: Text to be divided
            position: Approximate position for the break

        Returns:
            Exact position for the break
        """
        # Preference 1: paragraph break
        for i in range(min(200, position), 0, -1):
            check_pos = position - i
            if check_pos >= 0 and text[check_pos : check_pos + 2] == "\n\n":
                return check_pos + 2

        # Preference 2: line break
        for i in range(min(200, position), 0, -1):
            check_pos = position - i
            if check_pos >= 0 and text[check_pos] == "\n":
                return check_pos + 1

        # Preference 3: end of sentence
        for i in range(min(200, position), 0, -1):
            check_pos = position - i
            if (
                check_pos >= 0
                and text[check_pos] in ".!?"
                and (check_pos + 1 >= len(text) or text[check_pos + 1] == " ")
            ):
                return check_pos + 1

        # If no ideal break point was found, return the original position
        return position

    def chunk_text(self, text: str, preserve_newlines: bool = False) -> list[str]:
        """
        Divides the text into chunks while maintaining semantic structures.

        Args:
            text: Text to be divided
            preserve_newlines: If True, preserves line breaks in the text

        Returns:
            List of text chunks
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            # Determine the end of the current chunk
            end = min(start + self.chunk_size, len(text))

            # Find a suitable point to break the text
            if end < len(text):
                end = self._find_break_point(text, end)

            # Add the current chunk
            chunks.append(text[start:end])

            # Update the start position for the next chunk
            # Subtract the overlap to maintain context between chunks
            start = end - min(self.overlap, end - start)

            # Avoid infinite loops
            if start >= end:
                start = end

        return chunks

    def process_text_in_chunks(self, text: str, processor: Callable[[str], str]) -> str:
        """
        Process text in chunks and recombine the result.

        Args:
            text: Text to be processed
            processor: Function that processes each chunk

        Returns:
            Combined processed text
        """
        # For small texts, process directly
        if len(text) <= self.chunk_size:
            return processor(text)

        # Divide into chunks
        chunks = self.chunk_text(text)

        # Process each chunk
        processed_chunks = []
        for chunk in chunks:
            processed_chunks.append(processor(chunk))

        # Combine the results
        return "".join(processed_chunks)


class HTMLProcessor:
    """Utility for efficient processing of HTML content."""

    @staticmethod
    def strip_tags(html: str) -> str:
        """
        Remove all HTML tags while keeping the text.
        More efficient than using BeautifulSoup for large text blocks.

        Args:
            html: HTML to clean

        Returns:
            Text without HTML tags
        """
        # Pattern to detect HTML tags
        tag_pattern = re.compile(r"<[^>]*>")
        return tag_pattern.sub("", html)

    @staticmethod
    def extract_text_from_html(html: str) -> str:
        """
        Extracts text from HTML preserving line breaks for paragraphs, lists, etc.

        Args:
            html: HTML to process

        Returns:
            Extracted text with semantic line breaks
        """
        # Replace block tags with line breaks
        block_tags = re.compile(
            r"</(p|div|h\d|ul|ol|li|blockquote|pre)[^>]*>", re.IGNORECASE
        )
        html = block_tags.sub("\n", html)

        # Remove all other tags
        html = HTMLProcessor.strip_tags(html)

        # Clean multiple line breaks
        html = re.sub(r"\n\s*\n", "\n\n", html)

        # Decode common HTML entities
        html = html.replace("&nbsp;", " ")
        html = html.replace("&lt;", "<")
        html = html.replace("&gt;", ">")
        html = html.replace("&amp;", "&")
        html = html.replace("&quot;", '"')
        html = html.replace("&#39;", "'")

        return html.strip()

    @staticmethod
    def generate_excerpt(html: str, max_length: int = 200) -> str:
        """
        Generates a summary of the HTML content.

        Args:
            html: HTML to process
            max_length: Maximum length of the summary

        Returns:
            Text summary
        """
        text = HTMLProcessor.extract_text_from_html(html)

        # Truncate at maximum length, trying to preserve complete words
        if len(text) <= max_length:
            return text

        # Truncate at the last complete word
        truncated = text[:max_length]
        last_space = truncated.rfind(" ")

        if (
            last_space > max_length * 0.7
        ):  # Only truncate at space if it's at least 70% of the desired length
            truncated = truncated[:last_space]

        return truncated + "..."


class MarkdownOptimizer:
    """Utility for optimizing Markdown operations."""

    # Cache for frequent conversions
    _md_to_html_cache = {}
    _html_to_md_cache = {}

    @staticmethod
    def optimize_markdown_tables(markdown: str) -> str:
        """
        Optimizes tables in Markdown by adjusting alignment.

        Args:
            markdown: Markdown text

        Returns:
            Markdown with optimized tables
        """
        # Identifies table lines
        lines = markdown.split("\n")
        in_table = False
        table_start = 0
        tables = []

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Detects start of table
            if not in_table and stripped.startswith("|") and stripped.endswith("|"):
                in_table = True
                table_start = i

            # Detects end of table
            elif in_table and (
                not stripped.startswith("|") or not stripped.endswith("|")
            ):
                in_table = False
                tables.append((table_start, i - 1))

        # Finalizes the last table if it's at the end of the text
        if in_table:
            tables.append((table_start, len(lines) - 1))

        # Processes each table
        for start, end in tables:
            if end - start < 2:  # Table needs to have at least header and separator
                continue

            table_lines = lines[start : end + 1]

            # Process only if it has a separator line with hyphens
            if not re.match(r"\s*\|(\s*[-:]+\s*\|)+\s*$", table_lines[1]):
                continue

            # Optimizes each table
            optimized_table = MarkdownOptimizer._optimize_table_format(table_lines)

            # Replaces original table with optimized one
            lines[start : end + 1] = optimized_table

        return "\n".join(lines)

    @staticmethod
    def _optimize_table_format(table_lines: list[str]) -> list[str]:
        """
        Optimizes the format of a single Markdown table.

        Args:
            table_lines: Table lines

        Returns:
            Optimized table lines
        """
        # Splits the cells
        cells = []
        for line in table_lines:
            # Removes first and last pipe and splits
            parts = [cell.strip() for cell in line.strip()[1:-1].split("|")]
            cells.append(parts)

        # Determines maximum size of each column
        col_sizes = []
        for row in cells:
            for i, cell in enumerate(row):
                if i >= len(col_sizes):
                    col_sizes.append(len(cell))
                else:
                    col_sizes[i] = max(col_sizes[i], len(cell))

        # Rebuilds the table with uniform column sizes
        result = []
        for i, row in enumerate(cells):
            line_parts = []

            # For each cell in the row
            for j, cell in enumerate(row):
                # Separator header
                if i == 1:
                    # Preserves alignment
                    if cell.startswith(":") and cell.endswith(":"):
                        formatted = ":" + "-" * (col_sizes[j] - 2) + ":"
                    elif cell.startswith(":"):
                        formatted = ":" + "-" * (col_sizes[j] - 1)
                    elif cell.endswith(":"):
                        formatted = "-" * (col_sizes[j] - 1) + ":"
                    else:
                        formatted = "-" * col_sizes[j]
                else:
                    # Uses column size for padding
                    formatted = cell.ljust(col_sizes[j])

                line_parts.append(formatted)

            result.append("| " + " | ".join(line_parts) + " |")

        return result

    @staticmethod
    def remove_empty_markdown_links(markdown: str) -> str:
        """
        Remove empty or broken links from Markdown.

        Args:
            markdown: Markdown text

        Returns:
            Markdown without empty links
        """
        # Remove links with empty URLs
        markdown = re.sub(r"\[([^\]]*)\]\(\s*\)", r"\1", markdown)

        # Remove links with identical text and URL (redundant)
        markdown = re.sub(r"\[([^\]]+)\]\(\1\)", r"\1", markdown)

        return markdown
