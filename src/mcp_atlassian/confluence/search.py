"""Module for Confluence search operations."""

import logging

import requests
from requests.exceptions import HTTPError

from ..exceptions import MCPAtlassianAuthenticationError
from ..models.confluence import ConfluencePage, ConfluenceSearchResult
from .client import ConfluenceClient
from .utils import quote_cql_identifier_if_needed

logger = logging.getLogger("mcp-atlassian")


class SearchMixin(ConfluenceClient):
    """Mixin for Confluence search operations."""

    def search(
        self, cql: str, limit: int = 10, spaces_filter: str | None = None
    ) -> list[ConfluencePage]:
        """
        Search content using Confluence Query Language (CQL).

        Args:
            cql: Confluence Query Language string
            limit: Maximum number of results to return
            spaces_filter: Optional comma-separated list of space keys to filter by, overrides config

        Returns:
            List of ConfluencePage models containing search results

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails with the Confluence API (401/403)
        """
        try:
            # Use spaces_filter parameter if provided, otherwise fall back to config
            filter_to_use = spaces_filter or self.config.spaces_filter

            # Apply spaces filter if present
            if filter_to_use:
                # Split spaces filter by commas and handle possible whitespace
                spaces = [s.strip() for s in filter_to_use.split(",")]

                # Build the space filter query part using proper quoting for each space key
                space_query = " OR ".join(
                    [
                        f"space = {quote_cql_identifier_if_needed(space)}"
                        for space in spaces
                    ]
                )

                # Add the space filter to existing query with parentheses
                if cql and space_query:
                    if (
                        "space = " not in cql
                    ):  # Only add if not already filtering by space
                        cql = f"({cql}) AND ({space_query})"
                else:
                    cql = space_query

                logger.info(f"Applied spaces filter to query: {cql}")

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
        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code in [
                401,
                403,
            ]:
                error_msg = (
                    f"Authentication failed for Confluence API ({http_err.response.status_code}). "
                    "Token may be expired or invalid. Please verify credentials."
                )
                logger.error(error_msg)
                raise MCPAtlassianAuthenticationError(error_msg) from http_err
            else:
                logger.error(f"HTTP error during API call: {http_err}", exc_info=False)
                raise http_err
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
