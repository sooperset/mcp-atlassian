"""Module for Jira dashboard read operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from .client import JiraClient

logger = logging.getLogger("mcp-jira")

_GADGET_HINT = (
    "Gadget enumeration is not supported on this Jira instance. Open the "
    "dashboard in your browser, click each gadget's title, and share the "
    "filter IDs from the resulting URLs (?filter=NNNNN) so the assistant "
    "can proceed."
)


class DashboardMixin(JiraClient):
    """Mixin for reading Jira dashboard metadata and gadget configuration.

    Gadget filter resolution is best-effort on Data Center. Some gadgets store
    JQL inline rather than via a saved filterId; those cannot be resolved through
    the properties/config endpoint. Unresolvable gadgets are listed in
    gadget_resolution_warnings without raising an error.
    """

    def get_dashboard(
        self,
        dashboard_id: str,
        resolve_filters: bool = True,
    ) -> dict[str, Any]:
        """Fetch dashboard metadata and resolve gadget filter details.

        Args:
            dashboard_id: The numeric ID of the Jira dashboard.
            resolve_filters: When True, attempt to resolve filter name and JQL
                for each gadget that exposes a filterId via its config property.

        Returns:
            A dict with keys id, name, description, owner, view_url, gadgets,
            gadget_resolution_warnings, gadgets_supported, and next_step_hint.
            Returns an error dict on 404.

            gadgets_supported is False when the Jira instance does not expose
            gadget data (common on Data Center). In that case next_step_hint
            contains a human-readable instruction for the user.

            On Jira Data Center, gadget enumeration may not be supported.
            In that case, gadgets will be empty and gadgets_supported will
            be False. The caller should prompt the user for filter IDs and
            resolve them via jira_get_filter.
        """
        try:
            dashboard = self.jira.get(path=f"rest/api/2/dashboard/{dashboard_id}")
        except HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                return {"error": f"Dashboard {dashboard_id} not found"}
            logger.error("Error fetching dashboard %s: %s", dashboard_id, error)
            raise

        if not isinstance(dashboard, dict):
            return {"error": f"Dashboard {dashboard_id} not found"}

        # Distinguish supported (key present, even if []) from unsupported (key absent).
        gadgets_raw_value = dashboard.get("gadgets")
        gadgets_supported = gadgets_raw_value is not None
        gadgets_raw: list[Any] = gadgets_raw_value if isinstance(gadgets_raw_value, list) else []

        gadgets: list[dict[str, Any]] = []
        warnings: list[str] = []

        for gadget in gadgets_raw:
            if not isinstance(gadget, dict):
                continue
            processed = self._process_gadget(
                dashboard_id=dashboard_id,
                gadget=gadget,
                resolve_filters=resolve_filters,
                warnings=warnings,
            )
            gadgets.append(processed)

        owner_raw = dashboard.get("owner") or {}
        if isinstance(owner_raw, dict):
            owner = owner_raw.get("displayName") or owner_raw.get("name")
        else:
            owner = str(owner_raw) if owner_raw else None

        return {
            "id": str(dashboard.get("id", dashboard_id)),
            "name": str(dashboard.get("name", "")),
            "description": dashboard.get("description"),
            "owner": owner,
            "view_url": str(dashboard.get("view", "")),
            "gadgets": gadgets,
            "gadget_resolution_warnings": warnings,
            "gadgets_supported": gadgets_supported,
            "next_step_hint": None if gadgets_supported else _GADGET_HINT,
        }

    def _process_gadget(
        self,
        dashboard_id: str,
        gadget: dict[str, Any],
        resolve_filters: bool,
        warnings: list[str],
    ) -> dict[str, Any]:
        """Build a processed gadget dict, attempting filter resolution."""
        gadget_id = str(gadget.get("id", ""))
        position = gadget.get("position") or {}

        result: dict[str, Any] = {
            "id": gadget_id,
            "title": str(gadget.get("title", "")),
            "color": gadget.get("color"),
            "position": {
                "row": int(position.get("row", 0)) if isinstance(position, dict) else 0,
                "column": int(position.get("column", 0)) if isinstance(position, dict) else 0,
            },
            "filter_id": None,
            "filter_name": None,
            "jql": None,
        }

        config = self._fetch_gadget_config(
            dashboard_id=dashboard_id,
            gadget_id=gadget_id,
            warnings=warnings,
        )
        if config is None:
            return result

        filter_id = _extract_filter_id_from_config(config)
        result["filter_id"] = filter_id

        if filter_id and resolve_filters:
            filter_data = self.get_filter(filter_id)  # type: ignore[attr-defined]
            if isinstance(filter_data, dict) and "error" not in filter_data:
                result["filter_name"] = filter_data.get("name")
                result["jql"] = filter_data.get("jql")

        return result

    def _fetch_gadget_config(
        self,
        dashboard_id: str,
        gadget_id: str,
        warnings: list[str],
    ) -> dict[str, Any] | None:
        """Fetch gadget config property; returns None and appends to warnings on failure."""
        if not gadget_id:
            return None
        try:
            response = self.jira.get(
                path=(
                    f"rest/api/2/dashboard/{dashboard_id}"
                    f"/items/{gadget_id}/properties/config"
                )
            )
            if isinstance(response, dict):
                return response.get("value") if "value" in response else response
            return None
        except HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                warnings.append(gadget_id)
                return None
            logger.warning(
                "Unexpected error fetching config for gadget %s on dashboard %s: %s",
                gadget_id,
                dashboard_id,
                error,
            )
            warnings.append(gadget_id)
            return None


def _extract_filter_id_from_config(config: dict[str, Any]) -> str | None:
    """Extract a filter ID string from a gadget config dict."""
    for key in ("filterId", "filter_id", "filterid"):
        value = config.get(key)
        if value is not None:
            return str(value)
    return None
