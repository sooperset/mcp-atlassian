"""Unit tests for the SearchMixin class."""

from unittest.mock import patch

import pytest
import requests

from mcp_atlassian.confluence.search import SearchMixin
from mcp_atlassian.document_types import Document


class TestSearchMixin:
    """Tests for the SearchMixin class."""

    @pytest.fixture
    def search_mixin(self, confluence_client):
        """Create a SearchMixin instance for testing."""
        # SearchMixin inherits from ConfluenceClient, so we need to create it properly
        with patch(
            "mcp_atlassian.confluence.search.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = SearchMixin()
            # Copy the necessary attributes from our mocked client
            mixin.confluence = confluence_client.confluence
            mixin.config = confluence_client.config
            mixin.preprocessor = confluence_client.preprocessor
            return mixin

    def test_search_success(self, search_mixin):
        """Test that search returns properly formatted results."""
        # Arrange
        cql = 'space = "TEST" and type = "page"'
        limit = 15
        search_mixin.config.url = "https://example.atlassian.net/wiki"

        # Act
        results = search_mixin.search(cql, limit=limit)

        # Assert
        search_mixin.confluence.cql.assert_called_once_with(cql=cql, limit=limit)

        # Verify the results
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(doc, Document) for doc in results)

        # Check the first result
        doc = results[0]
        assert (
            doc.page_content
            == "📅 Date\n2024-01-01\n👥 Participants\nJohn Smith\nJane Doe\nBob Wilson\n!-@123456"
        )
        assert doc.metadata["page_id"] == "123456789"
        assert doc.metadata["title"] == "2024-01-01: Team Progress Meeting 01"
        assert "url" in doc.metadata
        assert "space" in doc.metadata
        assert doc.metadata["type"] == "page"

    def test_search_with_empty_results(self, search_mixin):
        """Test search when no results are found."""
        # Arrange
        search_mixin.confluence.cql.return_value = {"results": []}

        # Act
        results = search_mixin.search("query")

        # Assert
        assert results == []

    def test_search_with_non_page_content(self, search_mixin):
        """Test search with results that aren't pages."""
        # Arrange
        mock_response = {
            "results": [
                {
                    "content": {"id": "123", "type": "comment"},  # Not a page
                    "title": "Test Comment",
                    "url": "/spaces/TEST/comments/123",
                    "resultGlobalContainer": {"title": "Test Space"},
                }
            ]
        }
        search_mixin.confluence.cql.return_value = mock_response

        # Act
        results = search_mixin.search("query")

        # Assert
        assert results == []  # Should filter out non-page content

    def test_search_key_error(self, search_mixin):
        """Test handling of KeyError when processing results."""
        # Arrange - Missing required keys
        search_mixin.confluence.cql.return_value = {"results": [{"incomplete": "data"}]}

        # Act
        results = search_mixin.search("query")

        # Assert
        assert results == []

    def test_search_request_exception(self, search_mixin):
        """Test handling of request exceptions."""
        # Arrange
        search_mixin.confluence.cql.side_effect = requests.RequestException("API Error")

        # Act
        results = search_mixin.search("query")

        # Assert
        assert results == []

    def test_search_value_error(self, search_mixin):
        """Test handling of ValueError."""
        # Arrange
        search_mixin.confluence.cql.side_effect = ValueError("Invalid query")

        # Act
        results = search_mixin.search("query")

        # Assert
        assert results == []

    def test_search_type_error(self, search_mixin):
        """Test handling of TypeError."""
        # Arrange
        search_mixin.confluence.cql.side_effect = TypeError("Invalid data type")

        # Act
        results = search_mixin.search("query")

        # Assert
        assert results == []

    def test_search_general_exception(self, search_mixin):
        """Test handling of general exceptions."""
        # Arrange
        search_mixin.confluence.cql.side_effect = Exception("Unexpected error")

        # Act
        results = search_mixin.search("query")

        # Assert
        assert results == []
