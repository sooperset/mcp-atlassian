"""Unit tests for the SearchMixin class."""

from unittest.mock import patch

import pytest
import requests

from mcp_atlassian.confluence.search import SearchMixin
from mcp_atlassian.confluence.utils import quote_cql_identifier_if_needed


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
        """Test search with successful results."""
        # Prepare the mock
        search_mixin.confluence.cql.return_value = {
            "results": [
                {
                    "content": {
                        "id": "123456789",
                        "title": "Test Page",
                        "type": "page",
                        "space": {"key": "SPACE", "name": "Test Space"},
                        "version": {"number": 1},
                    },
                    "excerpt": "Test content excerpt",
                    "url": "https://confluence.example.com/pages/123456789",
                }
            ]
        }

        # Mock the preprocessor to return processed content
        search_mixin.preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed content",
        )

        # Call the method
        result = search_mixin.search("test query")

        # Verify API call
        search_mixin.confluence.cql.assert_called_once_with(cql="test query", limit=10)

        # Verify result
        assert len(result) == 1
        assert result[0].id == "123456789"
        assert result[0].title == "Test Page"
        assert result[0].content == "Processed content"

    def test_search_with_empty_results(self, search_mixin):
        """Test handling of empty search results."""
        # Mock an empty result set
        search_mixin.confluence.cql.return_value = {"results": []}

        # Act
        results = search_mixin.search("empty query")

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_with_non_page_content(self, search_mixin):
        """Test handling of non-page content in search results."""
        # Mock search results with non-page content
        search_mixin.confluence.cql.return_value = {
            "results": [
                {
                    "content": {"type": "blogpost", "id": "12345"},
                    "title": "Blog Post",
                    "excerpt": "This is a blog post",
                    "url": "/pages/12345",
                    "resultGlobalContainer": {"title": "TEST"},
                }
            ]
        }

        # Act
        results = search_mixin.search("blogpost query")

        # Assert
        assert isinstance(results, list)
        # The method should still handle them as pages since we're using models
        assert len(results) > 0

    def test_search_key_error(self, search_mixin):
        """Test handling of KeyError in search results."""
        # Mock a response missing required keys
        search_mixin.confluence.cql.return_value = {"incomplete": "data"}

        # Act
        results = search_mixin.search("invalid query")

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_request_exception(self, search_mixin):
        """Test handling of RequestException during search."""
        # Mock a network error
        search_mixin.confluence.cql.side_effect = requests.RequestException("API error")

        # Act
        results = search_mixin.search("error query")

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_value_error(self, search_mixin):
        """Test handling of ValueError during search."""
        # Mock a value error
        search_mixin.confluence.cql.side_effect = ValueError("Value error")

        # Act
        results = search_mixin.search("error query")

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_type_error(self, search_mixin):
        """Test handling of TypeError during search."""
        # Mock a type error
        search_mixin.confluence.cql.side_effect = TypeError("Type error")

        # Act
        results = search_mixin.search("error query")

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_with_spaces_filter(self, search_mixin):
        """Test searching with spaces filter from parameter."""
        # Prepare the mock
        search_mixin.confluence.cql.return_value = {
            "results": [
                {
                    "content": {
                        "id": "123456789",
                        "title": "Test Page",
                        "type": "page",
                        "space": {"key": "SPACE", "name": "Test Space"},
                        "version": {"number": 1},
                    },
                    "excerpt": "Test content excerpt",
                    "url": "https://confluence.example.com/pages/123456789",
                }
            ]
        }

        # Mock the preprocessor
        search_mixin.preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed content",
        )

        # Test with single space filter
        result = search_mixin.search("test query", spaces_filter="DEV")

        # Verify space was properly quoted in the CQL query
        quoted_dev = quote_cql_identifier_if_needed("DEV")
        search_mixin.confluence.cql.assert_called_with(
            cql=f"(test query) AND (space = {quoted_dev})",
            limit=10,
        )
        assert len(result) == 1

        # Test with multiple spaces filter
        result = search_mixin.search("test query", spaces_filter="DEV,TEAM")

        # Verify spaces were properly quoted in the CQL query
        quoted_dev = quote_cql_identifier_if_needed("DEV")
        quoted_team = quote_cql_identifier_if_needed("TEAM")
        search_mixin.confluence.cql.assert_called_with(
            cql=f"(test query) AND (space = {quoted_dev} OR space = {quoted_team})",
            limit=10,
        )
        assert len(result) == 1

        # Test with filter when query already has space
        result = search_mixin.search('space = "EXISTING"', spaces_filter="DEV")
        search_mixin.confluence.cql.assert_called_with(
            cql='space = "EXISTING"',  # Should not add filter when space already exists
            limit=10,
        )
        assert len(result) == 1

    def test_search_with_config_spaces_filter(self, search_mixin):
        """Test search using spaces filter from config."""
        # Prepare the mock
        search_mixin.confluence.cql.return_value = {
            "results": [
                {
                    "content": {
                        "id": "123456789",
                        "title": "Test Page",
                        "type": "page",
                        "space": {"key": "SPACE", "name": "Test Space"},
                        "version": {"number": 1},
                    },
                    "excerpt": "Test content excerpt",
                    "url": "https://confluence.example.com/pages/123456789",
                }
            ]
        }

        # Mock the preprocessor
        search_mixin.preprocessor.process_html_content.return_value = (
            "<p>Processed HTML</p>",
            "Processed content",
        )

        # Set config filter
        search_mixin.config.spaces_filter = "DEV,TEAM"

        # Test with config filter
        result = search_mixin.search("test query")

        # Verify spaces were properly quoted in the CQL query
        quoted_dev = quote_cql_identifier_if_needed("DEV")
        quoted_team = quote_cql_identifier_if_needed("TEAM")
        search_mixin.confluence.cql.assert_called_with(
            cql=f"(test query) AND (space = {quoted_dev} OR space = {quoted_team})",
            limit=10,
        )
        assert len(result) == 1

        # Test that explicit filter overrides config filter
        result = search_mixin.search("test query", spaces_filter="OVERRIDE")

        # Verify space was properly quoted in the CQL query
        quoted_override = quote_cql_identifier_if_needed("OVERRIDE")
        search_mixin.confluence.cql.assert_called_with(
            cql=f"(test query) AND (space = {quoted_override})",
            limit=10,
        )
        assert len(result) == 1

    def test_search_general_exception(self, search_mixin):
        """Test handling of general exceptions during search."""
        # Mock a general exception
        search_mixin.confluence.cql.side_effect = Exception("General error")

        # Act
        results = search_mixin.search("error query")

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0
