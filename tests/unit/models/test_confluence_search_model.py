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

    def test_from_api_response_with_space_type_results(self):
        """Space-type CQL results (``type=space``) carry their data under a
        ``space`` key instead of ``content`` and must not be dropped.

        Regression for https://github.com/sooperset/mcp-atlassian/issues/907
        """
        data = {
            "results": [
                {
                    "space": {"id": 98765, "key": "DEV", "name": "Development"},
                    "title": "Development",
                    "excerpt": "",
                }
            ],
            "totalSize": 1,
            "start": 0,
            "limit": 25,
        }

        search_result = ConfluenceSearchResult.from_api_response(data)

        assert search_result.total_size == 1
        assert len(search_result.results) == 1

        page = search_result.results[0]
        assert isinstance(page, ConfluencePage)
        # Space id is mapped onto the page id so excerpt matching can resolve it
        assert page.id == "98765"
        assert page.title == "Development"

    def test_from_api_response_with_server_dc_space_without_id(self):
        """Preserve the key and UI URL from a Server/DC space result.

        Regression for https://github.com/sooperset/mcp-atlassian/issues/907
        """
        data = {
            "results": [
                {
                    "space": {
                        "key": "ANONKEY1",
                        "name": "Anonymized Space 1",
                        "type": "global",
                        "_links": {
                            "self": "https://anonymized.wiki.net/rest/api/space/ANONKEY1"
                        },
                    },
                    "title": "Anonymized Space 1",
                    "excerpt": "",
                    "url": "/spaces/ANONKEY1/overview",
                    "resultGlobalContainer": {
                        "displayUrl": "/spaces/ANONKEY1/overview"
                    },
                    "entityType": "space",
                }
            ],
            "totalSize": 1,
        }

        search_result = ConfluenceSearchResult.from_api_response(
            data,
            base_url="https://anonymized.wiki.net",
            is_cloud=False,
        )

        page = search_result.results[0]
        assert page.id == "ANONKEY1"
        assert page.title == "Anonymized Space 1"
        assert page.space is not None
        assert page.space.key == "ANONKEY1"
        assert page.url == "https://anonymized.wiki.net/spaces/ANONKEY1/overview"
