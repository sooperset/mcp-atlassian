"""Module for Jira filter operations."""

import logging
from typing import Any

from ..utils.decorators import handle_auth_errors
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class FiltersMixin(JiraClient):
    """Mixin for Jira filter operations."""

    @handle_auth_errors("Jira API")
    def get_filter(self, filter_id: str | int) -> dict[str, Any]:
        """Get a Jira saved filter by ID.

        Args:
            filter_id: The ID of the filter.

        Returns:
            Dictionary with filter details including JQL.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
        """
        result = self.jira.get_filter(filter_id)

        if not isinstance(result, dict):
            logger.error(
                "Unexpected response type from get_filter: %s",
                type(result),
            )
            return {"filter_id": str(filter_id), "error": "Invalid response"}

        owner = result.get("owner", {})
        return {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description", ""),
            "jql": result.get("jql"),
            "owner": owner.get("displayName", owner.get("name")),
            "view_url": result.get("viewUrl"),
            "search_url": result.get("searchUrl"),
            "is_favourite": result.get("favourite", False),
            "share_permissions": result.get("sharePermissions", []),
        }

    @handle_auth_errors("Jira API")
    def search_filters(
        self,
        filter_name: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search for Jira saved filters by name.

        Note: The /rest/api/2/filter/search endpoint is Cloud-only.
        On Server/DC this falls back to searching favourite filters.

        Args:
            filter_name: Filter name to search for.
            limit: Maximum number of results.

        Returns:
            Dictionary with list of matching filters.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
        """
        if not self.config.is_cloud:
            return self._search_filters_server_fallback(filter_name, limit)

        result = self.jira.get(
            "rest/api/2/filter/search",
            params={"filterName": filter_name, "maxResults": limit, "expand": "jql"},
        )

        if not isinstance(result, dict):
            return {"filters": [], "total": 0}

        filters = []
        for f in result.get("values", []):
            owner = f.get("owner", {})
            filters.append(
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "description": f.get("description", ""),
                    "jql": f.get("jql"),
                    "owner": owner.get("displayName", owner.get("name")),
                    "is_favourite": f.get("favourite", False),
                }
            )

        return {
            "filters": filters,
            "total": result.get("total", len(filters)),
        }

    @handle_auth_errors("Jira API")
    def get_favourite_filters(self, limit: int = 50) -> dict[str, Any]:
        """Get the current user's favourite/starred filters.

        Args:
            limit: Maximum number of filters to return.

        Returns:
            Dictionary with list of favourite filters.

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails.
        """
        result = self.jira.get("rest/api/2/filter/favourite")

        if not isinstance(result, list):
            return {"filters": [], "total": 0}

        filters = []
        for f in result[:limit]:
            owner = f.get("owner", {})
            filters.append(
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "description": f.get("description", ""),
                    "jql": f.get("jql"),
                    "owner": owner.get("displayName", owner.get("name")),
                }
            )

        return {"filters": filters, "total": len(filters)}

    def _search_filters_server_fallback(
        self, filter_name: str, limit: int
    ) -> dict[str, Any]:
        """Search filters on Server/DC by fetching favourites and filtering by name.

        The filter search API (``/rest/api/2/filter/search``) is
        Cloud-only.  On Server/DC we fall back to the user's favourite
        filters and substring-match locally.  The result is explicitly
        marked ``partial=True`` so callers know this is not an
        exhaustive search — shared or private filters the user can
        access but has not starred will not appear.
        """
        favourites = self.get_favourite_filters(limit=1000)
        needle = filter_name.lower()
        matched = [
            f
            for f in favourites.get("filters", [])
            if needle in f.get("name", "").lower()
        ][:limit]
        return {
            "filters": matched,
            "total": len(matched),
            "partial": True,
            "note": (
                "Server/DC: searched favourite filters only — "
                "filter search API is Cloud-only. Non-starred filters "
                "the user can access are not included."
            ),
        }
