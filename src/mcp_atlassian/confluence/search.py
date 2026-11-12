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
from ..utils.query_scope import and_scope_clause
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
        # The caller's CQL is validated as one balanced expression first, so a
        # stray `)` cannot close the wrapper and OR around the allowlist.
        cql = and_scope_clause(cql, space_query, "CQL")
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


    # ------------------------------------------------------------------
    # Custom User Profile (CUP / Linchpin) profile plugin support (DC)
    #
    # Data Center instances with the Seibert "Custom User Profile" plugin
    # expose:
    #   GET /rest/cup/1.0/fields                  -> field definitions
    #   GET /rest/cup/1.0/profile?username=<u>    -> key/value profile data
    # Both are probed gracefully: if the plugin is not installed the calls
    # fail with 404/405/406 and callers fall back to plain identity data.
    # ------------------------------------------------------------------

    def _get_cup_endpoint(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> Any | None:
        """GET a CUP profile plugin endpoint, returning None when absent.

        Args:
            endpoint: REST endpoint path, e.g. ``rest/cup/1.0/fields``.
            params: Optional query parameters.

        Returns:
            The decoded JSON response, or None if the instance does not
            expose the CUP profile plugin (HTTP 404/405/406) or the
            endpoint returns a non-JSON payload.

        Raises:
            MCPAtlassianAuthenticationError: On HTTP 401/403.
            HTTPError: On any other HTTP error.
        """
        from requests.exceptions import HTTPError

        from ..exceptions import MCPAtlassianAuthenticationError

        try:
            response = self.confluence.get(
                endpoint, params=params, headers={"Accept": "application/json"}
            )
        except HTTPError as http_err:
            status = (
                http_err.response.status_code
                if http_err.response is not None
                else None
            )
            if status in (401, 403):
                error_msg = (
                    f"Authentication failed for Confluence API ({status}). "
                    "Token may be expired or invalid. Please verify credentials."
                )
                logger.error(error_msg)
                raise MCPAtlassianAuthenticationError(error_msg) from http_err
            if status in (404, 405, 406):
                logger.info(
                    f"CUP profile plugin not available at {endpoint} "
                    f"(HTTP {status})"
                )
                return None
            raise
        if response is None:
            return None
        if isinstance(response, (dict, list)):
            return response
        logger.warning(
            f"CUP endpoint {endpoint} returned a non-JSON response; "
            "the profile plugin is likely not installed or misconfigured."
        )
        return None

    def get_profile_fields(self) -> list[dict[str, Any]] | None:
        """Fetch the CUP profile plugin field definitions.

        Returns the list of field definitions from ``/rest/cup/1.0/fields``.
        Each field carries its opaque key (``userFieldBK``/``cup.field-NN``),
        the human-readable label (``localizedLabel``), the category
        (``localizedFieldCategoryLabel``), the data source and help text.

        Returns:
            List of field definition dicts, or None when the instance does
            not expose the CUP profile plugin.
        """
        response = self._get_cup_endpoint("rest/cup/1.0/fields")
        if not isinstance(response, list):
            return None
        return [f for f in response if isinstance(f, dict)]

    def get_user_profile(self, username: str) -> dict[str, Any]:
        """Fetch the full CUP profile of a user, merged with identity data.

        Uses ``/rest/api/user?username=<u>`` for identity fields and
        ``/rest/cup/1.0/profile?username=<u>`` for profile plugin data, then
        annotates every profile field with its human-readable label and
        category from ``/rest/cup/1.0/fields``.

        Args:
            username: The username of the user.

        Returns:
            A dict with:
              ``user``: identity data (username, userKey, displayName, ...).
              ``profile``: raw key -> value map from the CUP plugin, or None
                  when the plugin is not installed.
              ``profile_fields``: label/category annotations for each profile
                  key (``cup.field-NN``), or None when unavailable.
              ``profile_available``: whether the CUP profile plugin was found.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
            ValueError: If the user cannot be found.
        """
        identity = self.confluence.get("rest/api/user", params={"username": username})
        if not isinstance(identity, dict) or not identity.get("username"):
            error = f"User '{username}' not found"
            raise ValueError(error)

        profile_raw = self._get_cup_endpoint(
            "rest/cup/1.0/profile", params={"username": username}
        )
        profile: dict[str, Any] | None = (
            profile_raw if isinstance(profile_raw, dict) else None
        )

        fields: list[dict[str, Any]] | None = None
        if profile is not None:
            fields = self.get_profile_fields()

        profile_fields: dict[str, Any] | None = None
        if profile is not None and fields:
            by_key: dict[str, dict[str, Any]] = {}
            for field in fields:
                key = field.get("userFieldBK") or field.get("xmlKey")
                if not isinstance(key, str) or not key:
                    continue
                by_key[key] = {
                    "label": (
                        field.get("localizedLabel")
                        or field.get("labelPropertyKey")
                    ),
                    "category": field.get("localizedFieldCategoryLabel")
                    or field.get("fieldCategoryPropertyKey"),
                    "field_type": field.get("fieldType") or field.get("type"),
                    "data_source": field.get("dataSourceType"),
                    "help_text": (
                        field.get("localizedHelpText")
                        or field.get("helpTextKey")
                    ),
                }
            profile_fields = {
                key: by_key.get(key, {})
                for key in profile if key in by_key
            }

        return {
            "user": identity,
            "profile": profile,
            "profile_fields": profile_fields,
            "profile_available": profile is not None,
        }
