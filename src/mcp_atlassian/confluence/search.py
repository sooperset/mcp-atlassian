"""Module for Confluence search operations."""

import logging
from collections.abc import Iterator
from typing import Any

import requests

from ..models.confluence import ConfluencePage, ConfluenceSearchResult
from ..utils import cached, paginated_iterator
from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class SearchMixin(ConfluenceClient):
    """Mixin for Confluence search operations."""

    def search(self, cql: str, limit: int = 10) -> list[ConfluencePage]:
        """
        Search content using Confluence Query Language (CQL).

        Args:
            cql: Confluence Query Language string
            limit: Maximum number of results to return

        Returns:
            List of ConfluencePage models containing search results
        """
        try:
            # Execute the CQL search query
            results = self.confluence.cql(cql=cql, limit=limit)

            # Convert the response to a search result model
            search_result = ConfluenceSearchResult.from_api_response(
                results, base_url=self.config.url, cql_query=cql
            )

            # Process result excerpts as content
            processed_pages = []
            for page in search_result.results:
                # Get the excerpt from the original search results
                for result_item in results.get("results", []):
                    if result_item.get("content", {}).get("id") == page.id:
                        excerpt = result_item.get("excerpt", "")
                        if excerpt:
                            # Process the excerpt as HTML content
                            space_key = page.space.key if page.space else ""
                            processed_html, processed_markdown = (
                                self.preprocessor.process_html_content(
                                    excerpt, space_key=space_key
                                )
                            )
                            # Create a new page with processed content
                            page.content = processed_markdown
                        break

                processed_pages.append(page)

            # Return the list of result pages with processed content
            return processed_pages
        except KeyError as e:
            logger.error(f"Missing key in search results: {str(e)}")
            return []
        except requests.RequestException as e:
            logger.error(f"Network error during search: {str(e)}")
            return []
        except (ValueError, TypeError) as e:
            logger.error(f"Error processing search results: {str(e)}")
            return []
        except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
            logger.error(f"Unexpected error during search: {str(e)}")
            logger.debug("Full exception details for search:", exc_info=True)
            return []

    @cached("confluence_cql_search", 300)  # Cache for 5 minutes
    def cql_search(
        self, cql: str, start: int = 0, limit: int = 25, expand: str | None = None
    ) -> dict[str, Any]:
        """
        Search Confluence using CQL (Confluence Query Language).

        Args:
            cql: CQL query string
            start: The start point of the results
            limit: Maximum number of results to return
            expand: Expand parameters for the results

        Returns:
            Dictionary with search results
        """
        try:
            results = self.confluence.cql(
                cql=cql, start=start, limit=limit, expand=expand
            )
            return results if isinstance(results, dict) else {}
        except Exception as e:
            logger.warning(f"Error executing CQL search: {e}")
            logger.debug(f"Failed CQL query: {cql}")
            return {}

    @cached("confluence_text_search", 300)  # Cache for 5 minutes
    def search_content(
        self,
        text: str,
        space_key: str | None = None,
        start: int = 0,
        limit: int = 25,
    ) -> dict[str, Any]:
        """
        Search Confluence content by text.

        Args:
            text: Text to search for
            space_key: Optional space key to limit the search
            start: The start point of the results
            limit: Maximum number of results to return

        Returns:
            Dictionary with search results
        """
        try:
            if space_key:
                query = f'"{text}" AND space = "{space_key}"'
            else:
                query = f'"{text}"'

            results = self.confluence.search(
                query, start=start, limit=limit, expand="body.view,history"
            )
            return results if isinstance(results, dict) else {}
        except Exception as e:
            logger.warning(f"Error searching Confluence content: {e}")
            return {}

    def cql_search_iter(
        self,
        cql: str,
        start: int = 0,
        max_results: int = 1000,
        page_size: int = 25,
        expand: str | None = None,
    ) -> Iterator[ConfluencePage]:
        """
        Search Confluence using CQL and iterate through all results.
        This uses efficient pagination to avoid loading all results at once.

        Args:
            cql: CQL query string
            start: The starting index
            max_results: Maximum total number of results to return (None for all)
            page_size: Number of results to fetch per page
            expand: Expand parameters for the results

        Yields:
            ConfluencePage objects one at a time
        """

        def fetch_page(
            page_start: int, page_limit: int
        ) -> tuple[list[ConfluencePage], int]:
            """Internal function to fetch a page of results."""
            results = self.cql_search(
                cql=cql, start=page_start, limit=page_limit, expand=expand
            )

            pages = []
            search_results = results.get("results", [])

            for result in search_results:
                try:
                    # Extract content from result
                    content = result.get("content", {})

                    # Skip if we don't have valid content
                    if not content or not isinstance(content, dict):
                        continue

                    # Create ConfluencePage object
                    page = ConfluencePage.from_api_response(
                        content, base_url=self.config.url
                    )

                    # Try to extract excerpt if available
                    if "excerpt" in result:
                        excerpt = result.get("excerpt", "")
                        if excerpt:
                            # Process excerpt as HTML content
                            space_key = page.space.key if page.space else ""
                            _, processed_markdown = (
                                self.preprocessor.process_html_content(
                                    excerpt, space_key=space_key
                                )
                            )
                            # Add excerpt as content
                            page.content = processed_markdown

                    pages.append(page)

                except Exception as e:
                    logger.warning(f"Error processing search result: {e}")
                    continue

            # Get the total size if available
            total = results.get("size", len(pages))

            return pages, total

        # Use the paginated iterator
        return paginated_iterator(
            fetch_function=fetch_page,
            start_at=start,
            max_per_page=page_size,
            max_total=max_results,
        )
