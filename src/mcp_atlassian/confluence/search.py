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
from ..models.confluence.search import get_search_result_identifier
from ..utils.decorators import handle_atlassian_api_errors
from ..utils.pagination import clamp_limit
from .client import ConfluenceClient
from .utils import quote_cql_identifier_if_needed

logger = logging.getLogger("mcp-atlassian")


class SearchMixin(ConfluenceClient):
    """Mixin for Confluence search operations."""

    def _and_spaces_filter(self, cql: str, filter_to_use: str) -> str:
        """AND a single comma-separated spaces allowlist into ``cql``.

        Always ANDs the allowlist, even when the caller's CQL already names a
        space, so a caller-supplied ``space = X`` cannot escape it.
        """
        spaces = [s.strip() for s in filter_to_use.split(",")]
        space_query = " OR ".join(
            [f"space = {quote_cql_identifier_if_needed(space)}" for space in spaces]
        )
        if not cql:
            return space_query
        # Extract a trailing ORDER BY so the AND does not produce invalid CQL.
        order_match = re.search(r"\s+(ORDER\s+BY\s+.*)$", cql, re.IGNORECASE)
        if order_match:
            order_clause = order_match.group(1)
            cql_without_order = cql[: order_match.start()]
            cql = f"({cql_without_order}) AND ({space_query}) {order_clause}"
        else:
            cql = f"({cql}) AND ({space_query})"
        logger.info(f"Applied spaces filter to query: {cql}")
        return cql

    @staticmethod
    def _validate_search_response(response: Any, operation: str) -> dict[str, Any]:
        """Ensure a search API response has a list of results.

        A well-formed Confluence search response always includes a "results"
        field containing a list (which may legitimately be empty). A response
        missing it or containing a different type indicates an API, network, or
        processing failure that must surface as an error rather than be
        silently treated as an empty result set.

        Args:
            response: The raw response returned by the Confluence API.
            operation: Human-readable operation name for the error message
                (e.g. "search", "user search").

        Returns:
            The validated response dictionary.

        Raises:
            ValueError: If the response is not a dict or "results" is not a
                list.
        """
        if not isinstance(response, dict) or "results" not in response:
            error = (
                f"Confluence {operation} returned a malformed response "
                "missing the 'results' field"
            )
            raise ValueError(error)
        if not isinstance(response["results"], list):
            error = (
                f"Confluence {operation} returned a malformed response "
                "where 'results' is not a list"
            )
            raise ValueError(error)
        return response

    @handle_atlassian_api_errors("Confluence API")
    def search(
        self, cql: str, limit: int = 10, spaces_filter: str | None = None
    ) -> list[ConfluencePage]:
        """
        Search content using Confluence Query Language (CQL).

        Args:
            cql: Confluence Query Language string
            limit: Maximum number of results to return
            spaces_filter: Optional comma-separated list of space keys to narrow
                results within the configured allowlist (ANDed with config,
                never replaces it)

        Returns:
            List of ConfluencePage models containing search results

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails with the
                Confluence API (401/403)
        """
        limit = clamp_limit(limit, context="confluence.search")

        # config.spaces_filter is a hard boundary and is always applied; a
        # caller-supplied spaces_filter may only *narrow* within it (both ANDed),
        # never replace it — otherwise the tool argument would defeat the
        # operator's allowlist in shared-credential deployments.
        for filter_str in (self.config.spaces_filter, spaces_filter):
            if filter_str:
                cql = self._and_spaces_filter(cql, filter_str)

        # Execute the CQL search query. Expand content.history and
        # content.version so each result carries created/updated/author and
        # version metadata; on the /rest/api/search endpoint these nested
        # properties require the "content." prefix (a bare "history,version"
        # is silently ignored).
        results = self.confluence.cql(
            cql=cql, limit=limit, expand="content.history,content.version"
        )

        # Surface malformed responses (missing "results") as errors while
        # allowing a genuine "results": [] to return an empty list.
        self._validate_search_response(results, "search")

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
                if get_search_result_identifier(result_item) == page.id:
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
        limit = clamp_limit(limit, context="confluence.search_user")

        if self.config.is_cloud:
            # Cloud: use CQL search endpoint
            results = self.confluence.get(
                "rest/api/search/user",
                params={"cql": cql, "limit": limit},
            )
            # Surface malformed responses (missing "results") as errors while
            # allowing a genuine "results": [] to return an empty list.
            self._validate_search_response(results, "user search")
            search_result = ConfluenceUserSearchResults.from_api_response(results)
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
            # Surface malformed responses (missing "results") as errors while
            # allowing a genuine "results": [] to end pagination cleanly.
            self._validate_search_response(response, "user search")
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
