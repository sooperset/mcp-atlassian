"""
Tests for the ConfluenceSearchResult Pydantic model.
"""

from mcp_atlassian.models import (
    ConfluencePage,
    ConfluenceSearchResult,
)


class TestConfluenceSearchResult:
    """Tests for the ConfluenceSearchResult model."""

    def test_from_api_response_with_valid_data(self, confluence_search_data):
        """Test creating a ConfluenceSearchResult from valid API data."""
        search_result = ConfluenceSearchResult.from_api_response(confluence_search_data)

        assert search_result.total_size == 1
        assert search_result.start == 0
        assert search_result.limit == 50
        assert search_result.cql_query == "parent = 123456789"
        assert search_result.search_duration == 156

        assert len(search_result.results) == 1

        # Verify that results are properly converted to ConfluencePage objects
        page = search_result.results[0]
        assert isinstance(page, ConfluencePage)
        assert page.id == "123456789"
        assert page.title == "2024-01-01: Team Progress Meeting 01"

    def test_from_api_response_with_empty_data(self):
        """Test creating a ConfluenceSearchResult from empty data."""
        search_result = ConfluenceSearchResult.from_api_response({})

        # Should use default values
        assert search_result.total_size == 0
        assert search_result.start == 0
        assert search_result.limit == 0
        assert search_result.cql_query is None
        assert search_result.search_duration is None
        assert len(search_result.results) == 0
