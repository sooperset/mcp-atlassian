"""Module for Confluence search operations."""

import logging

import requests

from ..models.confluence import ConfluencePage, ConfluenceSearchResult
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
