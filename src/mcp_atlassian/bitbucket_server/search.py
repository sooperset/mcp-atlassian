"""Module for searching Bitbucket Server repositories."""

import json
import logging
from typing import Any

from ..exceptions import BitbucketServerApiError as BitbucketServerError
from .client import BitbucketServerClient
from .config import BitbucketServerConfig

logger = logging.getLogger("mcp-atlassian.bitbucket_server")


class BitbucketServerSearch:
    """Class for searching code and repositories in Bitbucket Server."""

    def __init__(
        self, client: BitbucketServerClient, config: BitbucketServerConfig
    ) -> None:
        """Initialize the BitbucketServerSearch class.

        Args:
            client: A BitbucketServerClient instance for making API calls
            config: A BitbucketServerConfig instance for configuration
        """
        self.client = client
        self.config = config

    def search_code(
        self,
        query: str,
        project_key: str | None = None,
        repository_slug: str | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search code content in Bitbucket Server repositories.

        Args:
            query: The search query
            project_key: Optional project key to limit search to a specific project
            repository_slug: Optional repository slug to limit search to a specific repository
            page: Page number to start from (1-based indexing)
            limit: Maximum number of results to return per page

        Returns:
            Search results as a dictionary

        Raises:
            BitbucketServerError: If the request fails or returns an error
        """
        search_query = query

        # Add project filter if provided
        if project_key:
            search_query = f"project:{project_key} {search_query}"

        # Add repository filter if provided
        if repository_slug:
            search_query = f"repo:{repository_slug} {search_query}"

        # Prepare request data
        data = {
            "query": search_query,
            "entities": {"code": {"start": page, "limit": limit}},
        }

        # Make the API call
        url = f"{self.client.root_url}/rest/search/latest/search"
        try:
            response = self.client.post_url(url, data=json.dumps(data))
            return response
        except Exception as e:
            logger.error(f"Error searching Bitbucket Server code: {str(e)}")
            raise BitbucketServerError(f"Failed to search code: {str(e)}") from e

    def search_repositories(
        self,
        query: str,
        project_key: str | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search for repositories in Bitbucket Server.

        Args:
            query: The search query
            project_key: Optional project key to limit search to a specific project
            page: Page number to start from (1-based indexing)
            limit: Maximum number of results to return per page

        Returns:
            Search results as a dictionary

        Raises:
            BitbucketServerError: If the request fails or returns an error
        """
        # For repository search, the query seems to work best when kept simple
        # If project_key is provided, use it as the main query, otherwise use the provided query
        search_query = project_key if project_key else query

        # Prepare request data
        data = {
            "query": search_query,
            "entities": {"repositories": {"start": page, "limit": limit}},
        }

        # Make the API call
        url = f"{self.client.root_url}/rest/search/latest/search"
        try:
            response = self.client.post_url(url, data=json.dumps(data))
            return response
        except Exception as e:
            logger.error(f"Error searching Bitbucket Server repositories: {str(e)}")
            raise BitbucketServerError(
                f"Failed to search repositories: {str(e)}"
            ) from e
