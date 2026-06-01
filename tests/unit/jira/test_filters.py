"""Tests for the Jira FilterMixin."""

from unittest.mock import MagicMock, Mock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.jira.filters import FilterMixin


@pytest.fixture
def filter_mixin(jira_fetcher) -> FilterMixin:
    """Create a FilterMixin instance with mocked dependencies."""
    return jira_fetcher


def test_get_filter_success(filter_mixin: FilterMixin) -> None:
    """get_filter returns a well-formed dict for a valid filter ID."""
    filter_mixin.jira.get = MagicMock(
        return_value={
            "id": "12345",
            "name": "My Open Issues",
            "jql": "assignee = currentUser() AND statusCategory != Done",
            "description": "All my open issues",
            "favourite": True,
            "owner": {
                "name": "jdoe",
                "displayName": "Jane Doe",
                "emailAddress": "jane@example.com",
            },
            "sharePermissions": [
                {"type": "project", "project": {"name": "ORB"}, "role": None, "group": None}
            ],
        }
    )

    result = filter_mixin.get_filter("12345")

    assert result["id"] == "12345"
    assert result["name"] == "My Open Issues"
    assert "assignee = currentUser()" in result["jql"]
    assert result["favourite"] is True
    assert result["owner"]["displayName"] == "Jane Doe"
    assert result["owner"]["emailAddress"] == "jane@example.com"
    assert len(result["shared_with"]) == 1
    assert result["shared_with"][0]["type"] == "project"


def test_get_filter_not_found(filter_mixin: FilterMixin) -> None:
    """get_filter returns an error dict on 404 without raising."""
    filter_mixin.jira.get = MagicMock(
        side_effect=HTTPError(response=Mock(status_code=404))
    )

    result = filter_mixin.get_filter("99999")

    assert "error" in result
    assert "99999" in result["error"]


def test_get_filter_non_dict_response(filter_mixin: FilterMixin) -> None:
    """get_filter returns an error dict when API returns non-dict data."""
    filter_mixin.jira.get = MagicMock(return_value=None)

    result = filter_mixin.get_filter("12345")

    assert "error" in result


def test_get_filter_non_404_http_error_propagates(filter_mixin: FilterMixin) -> None:
    """get_filter re-raises non-404 HTTPErrors."""
    filter_mixin.jira.get = MagicMock(
        side_effect=HTTPError(response=Mock(status_code=500))
    )

    with pytest.raises(HTTPError):
        filter_mixin.get_filter("12345")


def test_search_filters_success(filter_mixin: FilterMixin) -> None:
    """search_filters returns simplified filter list from /filter/search."""
    filter_mixin.jira.get = MagicMock(
        return_value={
            "values": [
                {
                    "id": "1",
                    "name": "ORB Sprint Filter",
                    "jql": "project = ORB",
                    "owner": {"displayName": "Alice"},
                },
                {
                    "id": "2",
                    "name": "ORB Bugs",
                    "jql": "project = ORB AND issuetype = Bug",
                    "owner": {"displayName": "Bob"},
                },
            ]
        }
    )

    results = filter_mixin.search_filters(query="ORB", limit=10)

    assert len(results) == 2
    assert results[0]["id"] == "1"
    assert results[0]["name"] == "ORB Sprint Filter"
    assert results[0]["owner_display_name"] == "Alice"
    assert "project = ORB" in results[0]["jql"]


def test_search_filters_fallback_on_404(filter_mixin: FilterMixin) -> None:
    """search_filters falls back to GET /filter when /filter/search returns 404."""
    call_count = 0

    def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        path = kwargs.get("path") or (args[0] if args else "")
        if "filter/search" in path:
            raise HTTPError(response=Mock(status_code=404))
        # Fallback endpoint returns a list
        return [
            {"id": "10", "name": "ORB Filter", "jql": "project = ORB", "owner": {"name": "alice"}},
            {"id": "11", "name": "Unrelated", "jql": "project = OTHER", "owner": {"name": "bob"}},
        ]

    filter_mixin.jira.get = MagicMock(side_effect=get_side_effect)

    results = filter_mixin.search_filters(query="ORB", limit=25)

    assert call_count == 2  # first /filter/search, then /filter
    assert len(results) == 1
    assert results[0]["name"] == "ORB Filter"


def test_search_filters_fallback_no_query(filter_mixin: FilterMixin) -> None:
    """search_filters fallback without a query returns all accessible filters up to limit."""

    def get_side_effect(*args, **kwargs):
        path = kwargs.get("path") or (args[0] if args else "")
        if "filter/search" in path:
            raise HTTPError(response=Mock(status_code=404))
        return [
            {"id": str(i), "name": f"Filter {i}", "jql": f"project = P{i}", "owner": {}}
            for i in range(10)
        ]

    filter_mixin.jira.get = MagicMock(side_effect=get_side_effect)

    results = filter_mixin.search_filters(query=None, limit=5)

    assert len(results) == 5


def test_search_filters_limit_clamped(filter_mixin: FilterMixin) -> None:
    """search_filters clamps limit to 1–50 range."""
    filter_mixin.jira.get = MagicMock(return_value={"values": []})

    # limit=0 should be clamped to 1
    filter_mixin.search_filters(query=None, limit=0)
    call_args = filter_mixin.jira.get.call_args
    assert call_args.kwargs["params"]["maxResults"] == 1

    # limit=100 should be clamped to 50
    filter_mixin.search_filters(query=None, limit=100)
    call_args = filter_mixin.jira.get.call_args
    assert call_args.kwargs["params"]["maxResults"] == 50
