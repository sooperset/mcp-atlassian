"""Module for Jira saved filter read operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class FilterMixin(JiraClient):
    """Mixin for reading Jira saved filters."""

    def get_filter(self, filter_id: str) -> dict[str, Any]:
        """Fetch a single saved filter by ID.

        Args:
            filter_id: The numeric ID of the Jira filter.

        Returns:
            A dict with keys id, name, jql, owner, description, favourite,
            shared_with, or an error dict if the filter is not found.
        """
        try:
            response = self.jira.get(path=f"rest/api/2/filter/{filter_id}")
        except HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                return {"error": f"Filter {filter_id} not found"}
            logger.error("Error fetching filter %s: %s", filter_id, error)
            raise

        if not isinstance(response, dict):
            return {"error": f"Filter {filter_id} not found"}

        owner = response.get("owner") or {}
        share_permissions = response.get("sharePermissions") or []
        shared_with = [
            {
                "type": perm.get("type"),
                "project": (perm.get("project") or {}).get("name"),
                "role": (perm.get("role") or {}).get("name"),
                "group": (perm.get("group") or {}).get("name"),
            }
            for perm in share_permissions
            if isinstance(perm, dict)
        ]

        return {
            "id": str(response.get("id", filter_id)),
            "name": str(response.get("name", "")),
            "jql": str(response.get("jql", "")),
            "description": response.get("description"),
            "favourite": bool(response.get("favourite", False)),
            "owner": {
                "name": owner.get("name"),
                "displayName": owner.get("displayName"),
                "emailAddress": owner.get("emailAddress"),
            },
            "shared_with": shared_with,
        }

    def search_filters(
        self,
        query: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Search for saved filters accessible to the current user.

        Args:
            query: Optional substring to match against filter names.
                If omitted, returns the user's accessible filters.
            limit: Maximum number of results to return (1–50).

        Returns:
            A list of dicts with keys id, name, jql, owner_display_name.
        """
        limit = max(1, min(50, limit))

        params: dict[str, Any] = {"maxResults": limit}
        if query:
            params["filterName"] = query

        try:
            response = self.jira.get(
                path="rest/api/2/filter/search",
                params=params,
            )
            filters = _extract_filter_list(response)
        except HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                logger.debug(
                    "GET /rest/api/2/filter/search returned 404 — "
                    "falling back to GET /rest/api/2/filter"
                )
                filters = self._search_filters_fallback(query=query, limit=limit)
            else:
                logger.error("Error searching filters: %s", error)
                raise

        return [_simplify_filter(f) for f in filters]

    def _search_filters_fallback(
        self,
        query: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fallback for older DC instances that lack /filter/search."""
        response = self.jira.get(path="rest/api/2/filter")
        all_filters = _extract_filter_list(response)

        if query:
            q = query.lower()
            all_filters = [
                f
                for f in all_filters
                if isinstance(f, dict) and q in str(f.get("name", "")).lower()
            ]

        return all_filters[:limit]


def _extract_filter_list(response: Any) -> list[dict[str, Any]]:
    """Extract a list of filter dicts from a /filter/search or /filter response."""
    if isinstance(response, list):
        return [f for f in response if isinstance(f, dict)]
    if isinstance(response, dict):
        values = response.get("values") or response.get("filters") or []
        return [f for f in values if isinstance(f, dict)]
    return []


def _simplify_filter(f: dict[str, Any]) -> dict[str, Any]:
    """Return a compact filter summary dict."""
    owner = f.get("owner") or {}
    return {
        "id": str(f.get("id", "")),
        "name": str(f.get("name", "")),
        "jql": str(f.get("jql", "")),
        "owner_display_name": str(
            owner.get("displayName") or owner.get("name") or ""
        ),
    }
