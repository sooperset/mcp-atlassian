"""Module for Confluence search operations."""

import logging

from ..models.confluence import (
    ConfluencePage,
    ConfluenceSearchResult,
    ConfluenceUserSearchResult,
    ConfluenceUserSearchResults,
)
from ..utils.decorators import handle_atlassian_api_errors
from .client import ConfluenceClient
from .utils import quote_cql_identifier_if_needed

logger = logging.getLogger("mcp-atlassian")


class SearchMixin(ConfluenceClient):
    """Mixin for Confluence search operations."""

    @handle_atlassian_api_errors("Confluence API")
    def search(
        self, cql: str, limit: int = 10, spaces_filter: str | None = None
    ) -> list[ConfluencePage]:
        """
        Search content using Confluence Query Language (CQL).

        Args:
            cql: Confluence Query Language string
            limit: Maximum number of results to return
            spaces_filter: Optional comma-separated list of space keys to filter by,
                overrides config

        Returns:
            List of ConfluencePage models containing search results

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails with the
                Confluence API (401/403)
        """
        # Use spaces_filter parameter if provided, otherwise fall back to config
        filter_to_use = spaces_filter or self.config.spaces_filter

        # Apply spaces filter if present
        if filter_to_use:
            # Split spaces filter by commas and handle possible whitespace
            spaces = [s.strip() for s in filter_to_use.split(",")]

            # Build the space filter query part using proper quoting for each space key
            space_query = " OR ".join(
                [f"space = {quote_cql_identifier_if_needed(space)}" for space in spaces]
            )

            # Add the space filter to existing query with parentheses
            if cql and space_query:
                if "space = " not in cql:  # Only add if not already filtering by space
                    cql = f"({cql}) AND ({space_query})"
            else:
                cql = space_query

            logger.info(f"Applied spaces filter to query: {cql}")

        # Execute the CQL search query
        results = self.confluence.cql(cql=cql, limit=limit)

        # Convert the response to a search result model
        search_result = ConfluenceSearchResult.from_api_response(
            results,
            base_url=self.config.url,
            cql_query=cql,
            is_cloud=self.config.is_cloud,
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
                        _, processed_markdown = self.preprocessor.process_html_content(
                            excerpt,
                            space_key=space_key,
                            confluence_client=self.confluence,
                        )
                        # Create a new page with processed content
                        page.content = processed_markdown
                    break

            processed_pages.append(page)

        # Return the list of result pages with processed content
        return processed_pages

    @handle_atlassian_api_errors("Confluence API")
    def search_user(
        self, cql: str, limit: int = 10, group_name: str = "confluence-users"
    ) -> list[ConfluenceUserSearchResult]:
        """
        Search users using Confluence Query Language (CQL) for Cloud,
        or group member API with fuzzy matching for Server/DC.

        Args:
            cql: Confluence Query Language string for user search (Cloud),
                 or search term for fuzzy matching (Server/DC)
            limit: Maximum number of results to return
            group_name: (Server/DC only) Group name to search users from.
                       Defaults to 'confluence-users'.

        Returns:
            List of ConfluenceUserSearchResult models containing user search results

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails with the
                Confluence API (401/403)
        """
        if self.config.is_cloud:
            # Cloud: Use CQL search API
            results = self.confluence.get(
                "rest/api/search/user", params={"cql": cql, "limit": limit}
            )
            search_result = ConfluenceUserSearchResults.from_api_response(results or {})
            return search_result.results
        else:
            # Server/DC: Use group member API with fuzzy matching
            return self._search_user_server_dc(cql, limit, group_name)

    def _search_user_server_dc(
        self, search_term: str, limit: int = 10, group_name: str = "confluence-users"
    ) -> list[ConfluenceUserSearchResult]:
        """
        Search users in Confluence Server/DC using group member API.

        Args:
            search_term: Search term for fuzzy matching against username/displayName
            limit: Maximum number of results to return
            group_name: Group name to search users from

        Returns:
            List of ConfluenceUserSearchResult models
        """
        # Extract search term from CQL-like query if present
        # e.g., 'user.fullname ~ "张"' -> '张'
        import re
        match = re.search(r'~\s*["\']([^"\']+)["\']', search_term)
        if match:
            search_term = match.group(1)

        # Get all members from the specified group
        try:
            results = self.confluence.get(
                f"rest/api/group/{group_name}/member",
                params={"limit": 200}  # Get more users for local filtering
            )
        except Exception as e:
            logger.warning(f"Failed to get group members from '{group_name}': {e}")
            # Try alternative endpoint for older Confluence versions
            try:
                results = self.confluence.get(
                    "rest/api/user/list",
                    params={"limit": 200}
                )
            except Exception:
                logger.error("Failed to get user list from Server/DC")
                return []

        if not results:
            return []

        # Get the results list
        users_data = results.get("results", [])
        if not users_data:
            return []

        # Filter users based on search term (fuzzy matching)
        matched_users = []
        search_lower = search_term.lower() if search_term else ""

        for user_data in users_data:
            username = user_data.get("username", "").lower()
            display_name = user_data.get("displayName", "").lower()

            # If no search term, include all users
            if not search_term:
                matched_users.append(user_data)
            # Match against username or display name
            elif search_lower in username or search_lower in display_name:
                matched_users.append(user_data)

            # Stop if we have enough results
            if len(matched_users) >= limit:
                break

        # Convert to ConfluenceUserSearchResult models
        user_results = []
        for user_data in matched_users:
            user_result = ConfluenceUserSearchResult.from_server_dc_response(user_data)
            user_results.append(user_result)

        return user_results
