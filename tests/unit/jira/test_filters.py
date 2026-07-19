from unittest.mock import Mock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.jira.filters import FiltersMixin


class TestFiltersMixin:
    @pytest.fixture
    def mixin(self, mock_config, mock_atlassian_jira):
        m = FiltersMixin(config=mock_config)
        m.jira = mock_atlassian_jira
        return m

    # ---- get_filter ----

    def test_get_filter_success(self, mixin):
        mixin.jira.get_filter.return_value = {
            "id": "12345",
            "name": "My Filter",
            "description": "A test filter",
            "jql": "project = PROJ",
            "owner": {"displayName": "Alice", "name": "alice"},
            "viewUrl": "https://jira.example.com/filter/12345",
            "searchUrl": "https://jira.example.com/search",
            "favourite": True,
            "sharePermissions": [],
        }

        result = mixin.get_filter("12345")

        assert result["id"] == "12345"
        assert result["name"] == "My Filter"
        assert result["jql"] == "project = PROJ"
        assert result["owner"] == "Alice"
        assert result["is_favourite"] is True

    def test_get_filter_invalid_response(self, mixin):
        mixin.jira.get_filter.return_value = "not a dict"

        result = mixin.get_filter("99999")

        assert result["error"] == "Invalid response"

    def test_get_filter_auth_error(self, mixin):
        mixin.jira.get_filter.side_effect = HTTPError(response=Mock(status_code=401))
        with pytest.raises(MCPAtlassianAuthenticationError):
            mixin.get_filter("12345")

    # ---- search_filters ----

    def test_search_filters_success(self, mixin):
        mixin.jira.get.return_value = {
            "values": [
                {
                    "id": "1",
                    "name": "Sprint Filter",
                    "description": "",
                    "jql": "sprint in openSprints()",
                    "owner": {"displayName": "Bob"},
                    "favourite": False,
                },
                {
                    "id": "2",
                    "name": "Sprint Backlog",
                    "description": "Backlog items",
                    "jql": "sprint is EMPTY",
                    "owner": {"name": "charlie"},
                    "favourite": True,
                },
            ],
            "total": 2,
        }

        result = mixin.search_filters("Sprint")

        assert result["total"] == 2
        assert len(result["filters"]) == 2
        assert result["filters"][0]["name"] == "Sprint Filter"
        assert result["filters"][1]["is_favourite"] is True

    def test_search_filters_invalid_response(self, mixin):
        mixin.jira.get.return_value = "bad"

        result = mixin.search_filters("anything")

        assert result == {"filters": [], "total": 0}

    def test_search_filters_auth_error(self, mixin):
        mixin.jira.get.side_effect = HTTPError(response=Mock(status_code=403))
        with pytest.raises(MCPAtlassianAuthenticationError):
            mixin.search_filters("test")

    # ---- search_filters (Server/DC fallback) ----

    def test_search_filters_server_dc_fallback(
        self, jira_config_factory, mock_atlassian_jira
    ):
        dc_config = jira_config_factory(
            url="https://jira.example.com", auth_type="pat", personal_token="tok"
        )
        dc_mixin = FiltersMixin(config=dc_config)
        dc_mixin.jira = mock_atlassian_jira
        dc_mixin.jira.get.return_value = [
            {"id": "10", "name": "Sprint Board", "jql": "x", "owner": {}},
            {"id": "20", "name": "My Backlog", "jql": "y", "owner": {}},
        ]

        result = dc_mixin.search_filters("sprint")

        assert result["total"] == 1
        assert result["filters"][0]["name"] == "Sprint Board"
        assert result["partial"] is True
        assert "favourite" in result.get("note", "").lower()

    def test_search_filters_server_dc_no_match(
        self, jira_config_factory, mock_atlassian_jira
    ):
        dc_config = jira_config_factory(
            url="https://jira.example.com", auth_type="pat", personal_token="tok"
        )
        dc_mixin = FiltersMixin(config=dc_config)
        dc_mixin.jira = mock_atlassian_jira
        dc_mixin.jira.get.return_value = [
            {"id": "10", "name": "My Filter", "jql": "x", "owner": {}},
        ]

        result = dc_mixin.search_filters("nonexistent")

        assert result["total"] == 0
        assert result["filters"] == []

    # ---- get_favourite_filters ----

    def test_get_favourite_filters_success(self, mixin):
        mixin.jira.get.return_value = [
            {
                "id": "10",
                "name": "Fav 1",
                "description": "",
                "jql": "assignee = currentUser()",
                "owner": {"displayName": "Alice"},
            },
            {
                "id": "20",
                "name": "Fav 2",
                "description": "desc",
                "jql": "project = PROJ",
                "owner": {"name": "bob"},
            },
        ]

        result = mixin.get_favourite_filters()

        assert result["total"] == 2
        assert result["filters"][0]["name"] == "Fav 1"
        assert result["filters"][1]["owner"] == "bob"

    def test_get_favourite_filters_respects_limit(self, mixin):
        mixin.jira.get.return_value = [
            {"id": str(i), "name": f"F{i}", "jql": "x", "owner": {}} for i in range(10)
        ]

        result = mixin.get_favourite_filters(limit=3)

        assert result["total"] == 3

    def test_get_favourite_filters_invalid_response(self, mixin):
        mixin.jira.get.return_value = {"not": "a list"}

        result = mixin.get_favourite_filters()

        assert result == {"filters": [], "total": 0}

    def test_get_favourite_filters_auth_error(self, mixin):
        mixin.jira.get.side_effect = HTTPError(response=Mock(status_code=401))
        with pytest.raises(MCPAtlassianAuthenticationError):
            mixin.get_favourite_filters()
