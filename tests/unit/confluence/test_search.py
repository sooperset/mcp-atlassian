"""Unit tests for the SearchMixin class."""

from unittest.mock import MagicMock, patch

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

    def test_search_user_success(self, search_mixin):
        """Test search_user with successful results."""
        # Prepare the mock response
        search_mixin.confluence.get.return_value = {
            "results": [
                {
                    "user": {
                        "type": "known",
                        "accountId": "1234asdf",
                        "accountType": "atlassian",
                        "email": "first.last@invitae.com",
                        "publicName": "First Last",
                        "displayName": "First Last",
                        "isExternalCollaborator": False,
                        "profilePicture": {
                            "path": "/wiki/aa-avatar/1234asdf",
                            "width": 48,
                            "height": 48,
                            "isDefault": False,
                        },
                    },
                    "title": "First Last",
                    "excerpt": "",
                    "url": "/people/1234asdf",
                    "entityType": "user",
                    "lastModified": "2025-06-02T13:35:59.680Z",
                    "score": 0.0,
                }
            ],
            "start": 0,
            "limit": 25,
            "size": 1,
            "totalSize": 1,
            "cqlQuery": "( user.fullname ~ 'First Last' )",
            "searchDuration": 115,
        }

        # Call the method
        result = search_mixin.search_user('user.fullname ~ "First Last"')

        # Verify API call
        search_mixin.confluence.get.assert_called_once_with(
            "rest/api/search/user",
            params={"cql": 'user.fullname ~ "First Last"', "limit": 10},
        )

        # Verify result
        assert len(result) == 1
        assert result[0].user.account_id == "1234asdf"
        assert result[0].user.display_name == "First Last"
        assert result[0].user.email == "first.last@invitae.com"
        assert result[0].title == "First Last"
        assert result[0].entity_type == "user"

    def test_search_user_with_empty_results(self, search_mixin):
        """Test search_user with empty results."""
        # Mock an empty result set
        search_mixin.confluence.get.return_value = {
            "results": [],
            "start": 0,
            "limit": 25,
            "size": 0,
            "totalSize": 0,
            "cqlQuery": 'user.fullname ~ "Nonexistent"',
            "searchDuration": 50,
        }

        # Act
        results = search_mixin.search_user('user.fullname ~ "Nonexistent"')

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_user_with_custom_limit(self, search_mixin):
        """Test search_user with custom limit."""
        # Prepare the mock response
        search_mixin.confluence.get.return_value = {
            "results": [],
            "start": 0,
            "limit": 5,
            "size": 0,
            "totalSize": 0,
            "cqlQuery": 'user.fullname ~ "Test"',
            "searchDuration": 30,
        }

        # Call with custom limit
        search_mixin.search_user('user.fullname ~ "Test"', limit=5)

        # Verify API call with correct limit
        search_mixin.confluence.get.assert_called_once_with(
            "rest/api/search/user", params={"cql": 'user.fullname ~ "Test"', "limit": 5}
        )

    def test_search_user_http_401_error(self, search_mixin):
        """Test search_user handling of HTTP 401 authentication error."""
        from requests.exceptions import HTTPError

        from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError

        # Mock HTTP 401 error
        mock_response = MagicMock()
        mock_response.status_code = 401
        http_error = HTTPError("Unauthorized")
        http_error.response = mock_response
        search_mixin.confluence.get.side_effect = http_error

        # Act and assert
        with pytest.raises(MCPAtlassianAuthenticationError):
            search_mixin.search_user('user.fullname ~ "Test"')

    def test_search_user_http_403_error(self, search_mixin):
        """Test search_user handling of HTTP 403 authentication error."""
        from requests.exceptions import HTTPError

        from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError

        # Mock HTTP 403 error
        mock_response = MagicMock()
        mock_response.status_code = 403
        http_error = HTTPError("Forbidden")
        http_error.response = mock_response
        search_mixin.confluence.get.side_effect = http_error

        # Act and assert
        with pytest.raises(MCPAtlassianAuthenticationError):
            search_mixin.search_user('user.fullname ~ "Test"')

    def test_search_user_http_other_error(self, search_mixin):
        """Test search_user handling of other HTTP errors."""
        from requests.exceptions import HTTPError

        # Mock HTTP 500 error
        mock_response = MagicMock()
        mock_response.status_code = 500
        http_error = HTTPError("Internal Server Error")
        http_error.response = mock_response
        search_mixin.confluence.get.side_effect = http_error

        # Act and assert - should re-raise the HTTPError
        with pytest.raises(HTTPError):
            search_mixin.search_user('user.fullname ~ "Test"')

    def test_search_user_key_error(self, search_mixin):
        """Test search_user handling of KeyError in results."""
        # Mock a response missing required keys
        search_mixin.confluence.get.return_value = {"incomplete": "data"}

        # Act
        results = search_mixin.search_user('user.fullname ~ "Test"')

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_user_request_exception(self, search_mixin):
        """Test search_user handling of RequestException."""
        # Mock a network error
        search_mixin.confluence.get.side_effect = requests.RequestException(
            "Network error"
        )

        # Act
        results = search_mixin.search_user('user.fullname ~ "Test"')

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_user_value_error(self, search_mixin):
        """Test search_user handling of ValueError."""
        # Mock a value error
        search_mixin.confluence.get.side_effect = ValueError("Value error")

        # Act
        results = search_mixin.search_user('user.fullname ~ "Test"')

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_user_type_error(self, search_mixin):
        """Test search_user handling of TypeError."""
        # Mock a type error
        search_mixin.confluence.get.side_effect = TypeError("Type error")

        # Act
        results = search_mixin.search_user('user.fullname ~ "Test"')

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_user_general_exception(self, search_mixin):
        """Test search_user handling of general exceptions."""
        # Mock a general exception
        search_mixin.confluence.get.side_effect = Exception("General error")

        # Act
        results = search_mixin.search_user('user.fullname ~ "Test"')

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_user_with_none_response(self, search_mixin):
        """Test search_user handling of None response from API."""
        # Mock None response
        search_mixin.confluence.get.return_value = None

        # Act
        results = search_mixin.search_user('user.fullname ~ "Test"')

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_user_api_call_parameters(self, search_mixin):
        """Test that search_user calls the API with correct parameters."""
        # Mock successful response
        search_mixin.confluence.get.return_value = {
            "results": [],
            "start": 0,
            "limit": 5,
            "totalSize": 0,
        }

        # Act with custom limit
        search_mixin.search_user('user.email ~ "test@example.com"', limit=5)

        # Assert API was called with correct parameters
        search_mixin.confluence.get.assert_called_once_with(
            "rest/api/search/user",
            params={"cql": 'user.email ~ "test@example.com"', "limit": 5},
        )

    def test_search_user_with_complex_cql_query(self, search_mixin):
        """Test search_user with complex CQL query containing operators."""
        # Mock successful response
        search_mixin.confluence.get.return_value = {
            "results": [],
            "start": 0,
            "limit": 10,
            "totalSize": 0,
        }

        complex_query = 'user.fullname ~ "John" AND user.email ~ "@company.com" OR user.displayName ~ "JD"'

        # Act
        search_mixin.search_user(complex_query)

        # Assert API was called with the exact query
        search_mixin.confluence.get.assert_called_once_with(
            "rest/api/search/user", params={"cql": complex_query, "limit": 10}
        )

    def test_search_user_result_processing(self, search_mixin):
        """Test that search_user properly processes and returns user search result objects."""
        # Mock response with user data
        search_mixin.confluence.get.return_value = {
            "results": [
                {
                    "user": {
                        "accountId": "test-account-id",
                        "displayName": "Test User",
                        "email": "test@example.com",
                        "isExternalCollaborator": False,
                    },
                    "title": "Test User",
                    "entityType": "user",
                    "score": 1.5,
                }
            ],
            "start": 0,
            "limit": 10,
            "totalSize": 1,
        }

        # Act
        results = search_mixin.search_user('user.fullname ~ "Test User"')

        # Assert result structure
        assert len(results) == 1
        assert hasattr(results[0], "user")
        assert hasattr(results[0], "title")
        assert hasattr(results[0], "entity_type")
        assert results[0].user.account_id == "test-account-id"
        assert results[0].user.display_name == "Test User"
        assert results[0].title == "Test User"
        assert results[0].entity_type == "user"
