"""Tests for the Jira Filters mixin."""

from unittest.mock import MagicMock

import pytest
import requests

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.filters import FiltersMixin
from mcp_atlassian.models.jira.filter import JiraFilter

MOCK_FILTER_RESPONSE = {
    "id": "10001",
    "name": "My Open Bugs",
    "description": "All open bugs assigned to me",
    "jql": "assignee = currentUser() AND type = Bug AND statusCategory != Done",
    "owner": {
        "accountId": "test-account-id",
        "displayName": "Test User",
        "emailAddress": "test@example.com",
        "active": True,
    },
    "self": "https://example.atlassian.net/rest/api/2/filter/10001",
    "favourite": True,
}

MOCK_FILTER_RESPONSE_2 = {
    "id": "10002",
    "name": "Sprint Backlog",
    "description": None,
    "jql": "project = TEST AND sprint in openSprints()",
    "owner": {
        "accountId": "test-account-id",
        "displayName": "Test User",
    },
    "self": "https://example.atlassian.net/rest/api/2/filter/10002",
    "favourite": False,
}


class TestFiltersMixin:
    """Tests for the FiltersMixin class."""

    @pytest.fixture
    def filters_mixin(self, jira_fetcher: JiraFetcher) -> FiltersMixin:
        """Create a FiltersMixin instance with mocked dependencies."""
        mixin = jira_fetcher
        mixin.config = MagicMock()
        mixin.config.is_cloud = True
        mixin.config.url = "https://example.atlassian.net"
        return mixin

    def test_get_my_filters_returns_list(self, filters_mixin: FiltersMixin):
        """Test that get_my_filters returns a list of JiraFilter objects."""
        filters_mixin.jira.get = MagicMock(
            return_value=[MOCK_FILTER_RESPONSE, MOCK_FILTER_RESPONSE_2]
        )

        result = filters_mixin.get_my_filters()

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(f, JiraFilter) for f in result)

    def test_get_my_filters_calls_correct_endpoint(self, filters_mixin: FiltersMixin):
        """Test that get_my_filters calls the correct REST API endpoint."""
        filters_mixin.jira.get = MagicMock(return_value=[])

        filters_mixin.get_my_filters()

        filters_mixin.jira.get.assert_called_once_with("rest/api/2/filter/my")

    def test_get_my_filters_parses_fields_correctly(self, filters_mixin: FiltersMixin):
        """Test that filter fields are correctly parsed."""
        filters_mixin.jira.get = MagicMock(return_value=[MOCK_FILTER_RESPONSE])

        result = filters_mixin.get_my_filters()

        f = result[0]
        assert f.id == "10001"
        assert f.name == "My Open Bugs"
        assert f.description == "All open bugs assigned to me"
        assert (
            f.jql
            == "assignee = currentUser() AND type = Bug AND statusCategory != Done"
        )
        assert f.favourite is True
        assert f.owner is not None
        assert f.owner.display_name == "Test User"

    def test_get_my_filters_empty_response(self, filters_mixin: FiltersMixin):
        """Test that get_my_filters handles empty response."""
        filters_mixin.jira.get = MagicMock(return_value=[])

        result = filters_mixin.get_my_filters()

        assert result == []

    def test_get_my_filters_unexpected_response_type(self, filters_mixin: FiltersMixin):
        """Test that get_my_filters raises TypeError for non-list response."""
        filters_mixin.jira.get = MagicMock(return_value="unexpected")

        with pytest.raises(TypeError):
            filters_mixin.get_my_filters()

    def test_get_favourite_filters_returns_list(self, filters_mixin: FiltersMixin):
        """Test that get_favourite_filters returns a list of JiraFilter objects."""
        filters_mixin.jira.get = MagicMock(return_value=[MOCK_FILTER_RESPONSE])

        result = filters_mixin.get_favourite_filters()

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].favourite is True

    def test_get_favourite_filters_calls_correct_endpoint(
        self, filters_mixin: FiltersMixin
    ):
        """Test that get_favourite_filters calls the correct REST API endpoint."""
        filters_mixin.jira.get = MagicMock(return_value=[])

        filters_mixin.get_favourite_filters()

        filters_mixin.jira.get.assert_called_once_with("rest/api/2/filter/favourite")

    def test_get_filter_by_id_returns_filter(self, filters_mixin: FiltersMixin):
        """Test that get_filter_by_id returns a JiraFilter object."""
        filters_mixin.jira.get = MagicMock(return_value=MOCK_FILTER_RESPONSE)

        result = filters_mixin.get_filter_by_id("10001")

        assert isinstance(result, JiraFilter)
        assert result.id == "10001"
        assert result.name == "My Open Bugs"

    def test_get_filter_by_id_calls_correct_endpoint(self, filters_mixin: FiltersMixin):
        """Test that get_filter_by_id calls the correct REST API endpoint."""
        filters_mixin.jira.get = MagicMock(return_value=MOCK_FILTER_RESPONSE)

        filters_mixin.get_filter_by_id("10001")

        filters_mixin.jira.get.assert_called_once_with("rest/api/2/filter/10001")

    def test_get_filter_by_id_not_found(self, filters_mixin: FiltersMixin):
        """Test that get_filter_by_id raises ValueError for 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = requests.exceptions.HTTPError(response=mock_response)
        filters_mixin.jira.get = MagicMock(side_effect=http_error)

        with pytest.raises(ValueError, match="not found"):
            filters_mixin.get_filter_by_id("99999")

    def test_get_filter_by_id_unexpected_response_type(
        self, filters_mixin: FiltersMixin
    ):
        """Test that get_filter_by_id raises TypeError for non-dict response."""
        filters_mixin.jira.get = MagicMock(return_value="unexpected")

        with pytest.raises(TypeError):
            filters_mixin.get_filter_by_id("10001")


class TestJiraFilterModel:
    """Tests for the JiraFilter model."""

    def test_from_api_response_full(self):
        """Test creating a JiraFilter from a full API response."""
        f = JiraFilter.from_api_response(MOCK_FILTER_RESPONSE)

        assert f.id == "10001"
        assert f.name == "My Open Bugs"
        assert f.description == "All open bugs assigned to me"
        assert f.favourite is True
        assert f.owner is not None
        assert f.owner.display_name == "Test User"

    def test_from_api_response_minimal(self):
        """Test creating a JiraFilter from a minimal API response."""
        data = {"id": "10003", "name": "Simple Filter", "jql": "project = TEST"}
        f = JiraFilter.from_api_response(data)

        assert f.id == "10003"
        assert f.name == "Simple Filter"
        assert f.jql == "project = TEST"
        assert f.description is None
        assert f.owner is None
        assert f.favourite is False

    def test_from_api_response_empty(self):
        """Test creating a JiraFilter from an empty dict."""
        f = JiraFilter.from_api_response({})
        assert f.id == ""
        assert f.name == ""

    def test_from_api_response_none(self):
        """Test creating a JiraFilter from None."""
        f = JiraFilter.from_api_response(None)
        assert f.id == ""
        assert f.name == ""

    def test_from_api_response_non_dict(self):
        """Test creating a JiraFilter from non-dict data."""
        f = JiraFilter.from_api_response("not a dict")
        assert f.id == ""
        assert f.name == ""

    def test_to_simplified_dict(self):
        """Test converting a JiraFilter to a simplified dict."""
        f = JiraFilter.from_api_response(MOCK_FILTER_RESPONSE)
        d = f.to_simplified_dict()

        assert d["id"] == "10001"
        assert d["name"] == "My Open Bugs"
        assert (
            d["jql"]
            == "assignee = currentUser() AND type = Bug AND statusCategory != Done"
        )
        assert d["favourite"] is True
        assert "description" in d
        assert "owner" in d

    def test_to_simplified_dict_no_optional_fields(self):
        """Test that optional fields are excluded when not present."""
        data = {"id": "10003", "name": "Simple", "jql": "project = TEST"}
        f = JiraFilter.from_api_response(data)
        d = f.to_simplified_dict()

        assert "description" not in d
        assert "owner" not in d
