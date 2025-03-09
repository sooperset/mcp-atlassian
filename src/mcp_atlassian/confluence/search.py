"""Module for Confluence search operations."""

import logging

import requests

from ..document_types import Document
from .client import ConfluenceClient

logger = logging.getLogger("mcp-atlassian")


class SearchMixin(ConfluenceClient):
    """Mixin for Confluence search operations."""

    def search(self, cql: str, limit: int = 10) -> list[Document]:
        """
        Search content using Confluence Query Language (CQL).

        Args:
            cql: Confluence Query Language string
            limit: Maximum number of results to return

        Returns:
            List of Document objects containing search results
        """
        try:
            results = self.confluence.cql(cql=cql, limit=limit)
            documents = []

            for result in results.get("results", []):
                content = result.get("content", {})
                if content.get("type") == "page":
                    metadata = {
                        "page_id": content["id"],
                        "title": result["title"],
                        "space": result.get("resultGlobalContainer", {}).get("title"),
                        "url": f"{self.config.url}{result['url']}",
                        "last_modified": result.get("lastModified"),
                        "type": content["type"],
                    }

                    # Use the excerpt as page_content since it's already a good summary
                    documents.append(
                        Document(
                            page_content=result.get("excerpt", ""), metadata=metadata
                        )
                    )

            return documents
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
