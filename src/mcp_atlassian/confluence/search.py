"""Module for Confluence search operations."""

import logging
import re
from typing import Any
from urllib.parse import quote

from ..models.confluence import (
    ConfluencePage,
    ConfluenceSearchResult,
    ConfluenceUserSearchResult,
    ConfluenceUserSearchResults,
)
from ..models.confluence.common import ConfluenceUser
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
        self,
        cql: str,
        limit: int = 10,
        group_name: str = "confluence-users",
    ) -> list[ConfluenceUserSearchResult]:
        """
        Search users using CQL (Cloud) or group member API (Server/DC).

        Args:
            cql: Confluence Query Language string for user search
            limit: Maximum number of results to return
            group_name: Group to search within on Server/DC
                (default: "confluence-users")

        Returns:
            List of ConfluenceUserSearchResult models containing
            user search results

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails
                with the Confluence API (401/403)
        """
        if self.config.is_cloud:
            # Cloud: use CQL search endpoint
            results = self.confluence.get(
                "rest/api/search/user",
                params={"cql": cql, "limit": limit},
            )
            search_result = ConfluenceUserSearchResults.from_api_response(results or {})
            return search_result.results

        # Server/DC: fall back to group member API
        return self._search_user_server_dc(cql, group_name, limit)

    def _search_user_server_dc(
        self,
        cql: str,
        group_name: str,
        limit: int,
    ) -> list[ConfluenceUserSearchResult]:
        """Search users on Server/DC via group member API with pagination.

        Args:
            cql: CQL string or plain search term to fuzzy match.
            group_name: Group to search within.
            limit: Max results to return.

        Returns:
            List of matching ConfluenceUserSearchResult models.
        """
        # Extract search term from CQL if possible
        match = re.search(r'user\.fullname\s*~\s*"([^"]*)"', cql)
        search_term = match.group(1) if match else cql
        search_lower = search_term.lower()

        matches: list[ConfluenceUserSearchResult] = []
        start = 0
        page_size = 200
        encoded_group = quote(group_name, safe="")

        while len(matches) < limit:
            response: dict[str, Any] = self.confluence.get(
                f"rest/api/group/{encoded_group}/member",
                params={"start": start, "limit": page_size},
            )
            members = response.get("results", [])

            for member in members:
                display = member.get("displayName", "")
                username = member.get("username", "")
                if search_lower in display.lower() or search_lower in username.lower():
                    user = ConfluenceUser.from_api_response(member)
                    # Server/DC responses lack accountStatus;
                    # default to active for group members
                    if member.get("accountStatus") is None:
                        user.is_active = True
                    result = ConfluenceUserSearchResult(
                        user=user,
                        title=display,
                        entity_type="user",
                    )
                    matches.append(result)
                    if len(matches) >= limit:
                        break

            # Stop when no more pages available
            has_next = "_links" in response and "next" in response.get("_links", {})
            if not has_next or not members:
                break
            start += len(members)

        return matches[:limit]
