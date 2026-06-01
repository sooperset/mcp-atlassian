"""Tests for the Jira DashboardMixin."""

from unittest.mock import MagicMock, Mock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.jira.dashboards import DashboardMixin, _GADGET_HINT


@pytest.fixture
def dashboard_mixin(jira_fetcher) -> DashboardMixin:
    """Create a DashboardMixin instance with mocked dependencies."""
    return jira_fetcher


_SENTINEL = object()


def _make_dashboard(gadgets: list[dict] | object = _SENTINEL) -> dict:
    """Build a mock dashboard response. Pass gadgets=None to omit the key."""
    base: dict = {
        "id": "14207",
        "name": "Sprint Overview",
        "description": "Team sprint board",
        "owner": {"displayName": "Alice"},
        "view": "https://jira.example.com/secure/Dashboard.jspa?selectPageId=14207",
    }
    if gadgets is not _SENTINEL:
        base["gadgets"] = gadgets  # type: ignore[assignment]
    else:
        base["gadgets"] = []
    return base


def _make_dashboard_no_gadgets_key() -> dict:
    """Build a mock dashboard response without the gadgets key (DC unsupported)."""
    return {
        "id": "14207",
        "name": "Sprint Overview",
        "description": "Team sprint board",
        "owner": {"displayName": "Alice"},
        "view": "https://jira.example.com/secure/Dashboard.jspa?selectPageId=14207",
    }


def _make_gadget(gadget_id: str, title: str = "Gadget", row: int = 0, col: int = 0) -> dict:
    return {
        "id": gadget_id,
        "title": title,
        "color": "blue",
        "position": {"row": row, "column": col},
    }


def test_get_dashboard_success_with_filter_resolution(
    dashboard_mixin: DashboardMixin,
) -> None:
    """Dashboard with 3 gadgets returns resolved filter_name and jql for all."""
    gadgets = [
        _make_gadget("g1", "Sprint Health", 0, 0),
        _make_gadget("g2", "Backlog Status", 0, 1),
        _make_gadget("g3", "Velocity Chart", 1, 0),
    ]

    filter_responses = {
        "f100": {
            "id": "f100",
            "name": "Sprint Health Filter",
            "jql": "project = ORB AND sprint in openSprints()",
            "description": None,
            "favourite": False,
            "owner": {"name": "alice", "displayName": "Alice", "emailAddress": None},
            "shared_with": [],
        },
        "f101": {
            "id": "f101",
            "name": "Backlog Filter",
            "jql": "project = ORB AND sprint is EMPTY",
            "description": None,
            "favourite": False,
            "owner": {"name": "alice", "displayName": "Alice", "emailAddress": None},
            "shared_with": [],
        },
        "f102": {
            "id": "f102",
            "name": "Velocity Filter",
            "jql": "project = ORB AND sprint in closedSprints()",
            "description": None,
            "favourite": False,
            "owner": {"name": "alice", "displayName": "Alice", "emailAddress": None},
            "shared_with": [],
        },
    }

    gadget_configs = {
        "g1": {"filterId": "f100"},
        "g2": {"filterId": "f101"},
        "g3": {"filterId": "f102"},
    }

    def get_side_effect(*args, **kwargs):
        path = kwargs.get("path") or (args[0] if args else "")
        if path == "rest/api/2/dashboard/14207":
            return _make_dashboard(gadgets)
        for gid, config in gadget_configs.items():
            if f"items/{gid}/properties/config" in path:
                return {"value": config}
        for fid, fdata in filter_responses.items():
            if path == f"rest/api/2/filter/{fid}":
                return {
                    "id": fid,
                    "name": fdata["name"],
                    "jql": fdata["jql"],
                    "description": fdata["description"],
                    "favourite": fdata["favourite"],
                    "owner": {"name": "alice", "displayName": "Alice"},
                    "sharePermissions": [],
                }
        return {}

    dashboard_mixin.jira.get = MagicMock(side_effect=get_side_effect)

    result = dashboard_mixin.get_dashboard("14207", resolve_filters=True)

    assert result["id"] == "14207"
    assert result["name"] == "Sprint Overview"
    assert result["owner"] == "Alice"
    assert len(result["gadgets"]) == 3
    assert result["gadget_resolution_warnings"] == []
    assert result["gadgets_supported"] is True
    assert result["next_step_hint"] is None

    g1 = result["gadgets"][0]
    assert g1["filter_id"] == "f100"
    assert g1["filter_name"] == "Sprint Health Filter"
    assert "openSprints" in g1["jql"]

    g2 = result["gadgets"][1]
    assert g2["filter_id"] == "f101"
    assert g2["filter_name"] == "Backlog Filter"

    g3 = result["gadgets"][2]
    assert g3["filter_id"] == "f102"
    assert g3["filter_name"] == "Velocity Filter"


def test_get_dashboard_gadget_config_404(
    dashboard_mixin: DashboardMixin,
) -> None:
    """A gadget whose config returns 404 is added to gadget_resolution_warnings."""
    gadgets = [
        _make_gadget("g1", "Resolved Gadget"),
        _make_gadget("g2", "Unresolvable Gadget"),
    ]

    def get_side_effect(*args, **kwargs):
        path = kwargs.get("path") or (args[0] if args else "")
        if path == "rest/api/2/dashboard/14207":
            return _make_dashboard(gadgets)
        if "items/g1/properties/config" in path:
            return {"value": {"filterId": "f50"}}
        if "items/g2/properties/config" in path:
            raise HTTPError(response=Mock(status_code=404))
        if path == "rest/api/2/filter/f50":
            return {
                "id": "f50",
                "name": "Good Filter",
                "jql": "project = ORB",
                "sharePermissions": [],
                "owner": {"displayName": "Alice"},
            }
        return {}

    dashboard_mixin.jira.get = MagicMock(side_effect=get_side_effect)

    result = dashboard_mixin.get_dashboard("14207", resolve_filters=True)

    assert len(result["gadgets"]) == 2
    assert "g2" in result["gadget_resolution_warnings"]
    assert "g1" not in result["gadget_resolution_warnings"]
    assert result["gadgets_supported"] is True
    assert result["next_step_hint"] is None

    g1 = next(g for g in result["gadgets"] if g["id"] == "g1")
    assert g1["filter_name"] == "Good Filter"

    g2 = next(g for g in result["gadgets"] if g["id"] == "g2")
    assert g2["filter_id"] is None
    assert g2["filter_name"] is None


def test_get_dashboard_resolve_filters_false(
    dashboard_mixin: DashboardMixin,
) -> None:
    """With resolve_filters=False, filter_id is extracted but filter_name/jql stay None."""
    gadgets = [_make_gadget("g1", "Sprint Board")]

    def get_side_effect(*args, **kwargs):
        path = kwargs.get("path") or (args[0] if args else "")
        if path == "rest/api/2/dashboard/14207":
            return _make_dashboard(gadgets)
        if "items/g1/properties/config" in path:
            return {"value": {"filterId": "f77"}}
        return {}

    dashboard_mixin.jira.get = MagicMock(side_effect=get_side_effect)

    result = dashboard_mixin.get_dashboard("14207", resolve_filters=False)

    assert len(result["gadgets"]) == 1
    assert result["gadgets_supported"] is True
    assert result["next_step_hint"] is None
    g = result["gadgets"][0]
    assert g["filter_id"] == "f77"
    assert g["filter_name"] is None
    assert g["jql"] is None

    # Ensure no /rest/api/2/filter/ call was made
    for call_args in dashboard_mixin.jira.get.call_args_list:
        path = call_args.kwargs.get("path") or (call_args.args[0] if call_args.args else "")
        assert "rest/api/2/filter/" not in path


def test_get_dashboard_not_found(
    dashboard_mixin: DashboardMixin,
) -> None:
    """get_dashboard returns an error dict on 404 without raising."""
    dashboard_mixin.jira.get = MagicMock(
        side_effect=HTTPError(response=Mock(status_code=404))
    )

    result = dashboard_mixin.get_dashboard("99999")

    assert "error" in result
    assert "99999" in result["error"]


def test_get_dashboard_non_dict_response(
    dashboard_mixin: DashboardMixin,
) -> None:
    """get_dashboard returns an error dict when API returns non-dict data."""
    dashboard_mixin.jira.get = MagicMock(return_value=None)

    result = dashboard_mixin.get_dashboard("14207")

    assert "error" in result


def test_get_dashboard_gadget_position(
    dashboard_mixin: DashboardMixin,
) -> None:
    """Gadget position row/column is correctly extracted."""
    gadgets = [_make_gadget("g1", "Gadget", row=2, col=1)]

    dashboard_mixin.jira.get = MagicMock(
        side_effect=lambda *a, **kw: (
            _make_dashboard(gadgets)
            if "rest/api/2/dashboard/14207" in (kw.get("path") or "")
            else {}
        )
    )

    result = dashboard_mixin.get_dashboard("14207", resolve_filters=False)

    g = result["gadgets"][0]
    assert g["position"]["row"] == 2
    assert g["position"]["column"] == 1


def test_get_dashboard_gadgets_supported_true_when_empty_list(
    dashboard_mixin: DashboardMixin,
) -> None:
    """gadgets_supported is True when the API returns an explicit empty gadgets list."""
    dashboard_mixin.jira.get = MagicMock(return_value=_make_dashboard(gadgets=[]))

    result = dashboard_mixin.get_dashboard("14207", resolve_filters=False)

    assert result["gadgets"] == []
    assert result["gadgets_supported"] is True
    assert result["next_step_hint"] is None


def test_get_dashboard_gadgets_supported_false_when_key_absent(
    dashboard_mixin: DashboardMixin,
) -> None:
    """gadgets_supported is False when the API response has no gadgets key (DC unsupported)."""
    dashboard_mixin.jira.get = MagicMock(return_value=_make_dashboard_no_gadgets_key())

    result = dashboard_mixin.get_dashboard("14207", resolve_filters=False)

    assert result["gadgets"] == []
    assert result["gadgets_supported"] is False


def test_get_dashboard_next_step_hint_set_when_unsupported(
    dashboard_mixin: DashboardMixin,
) -> None:
    """next_step_hint is populated with the guidance string when gadgets_supported is False."""
    dashboard_mixin.jira.get = MagicMock(return_value=_make_dashboard_no_gadgets_key())

    result = dashboard_mixin.get_dashboard("14207")

    assert result["next_step_hint"] == _GADGET_HINT
    assert "filter IDs" in result["next_step_hint"]


def test_get_dashboard_next_step_hint_none_when_supported(
    dashboard_mixin: DashboardMixin,
) -> None:
    """next_step_hint is None when gadgets_supported is True."""
    dashboard_mixin.jira.get = MagicMock(
        side_effect=lambda *a, **kw: (
            _make_dashboard([_make_gadget("g1")])
            if "rest/api/2/dashboard/14207" in (kw.get("path") or "")
            else {}
        )
    )

    result = dashboard_mixin.get_dashboard("14207", resolve_filters=False)

    assert result["gadgets_supported"] is True
    assert result["next_step_hint"] is None
