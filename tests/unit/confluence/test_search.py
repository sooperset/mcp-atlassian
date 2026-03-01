"""Unit tests for the SearchMixin class."""

import re
from unittest.mock import MagicMock, call, patch

import pytest
import requests
from requests import HTTPError

from mcp_atlassian.confluence.search import SearchMixin
from mcp_atlassian.confluence.utils import quote_cql_identifier_if_needed
from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError


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
                        "email": "first.last@example.com",
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
        assert result[0].user.email == "first.last@example.com"
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

    @pytest.mark.parametrize(
        "exception_type,exception_args,expected_result",
        [
            (requests.RequestException, ("Network error",), []),
            (ValueError, ("Value error",), []),
            (TypeError, ("Type error",), []),
            (Exception, ("General error",), []),
            (KeyError, ("Missing key",), []),
        ],
    )
    def test_search_user_exception_handling(
        self, search_mixin, exception_type, exception_args, expected_result
    ):
        """Test search_user handling of various exceptions that return empty list."""
        # Mock the exception
        search_mixin.confluence.get.side_effect = exception_type(*exception_args)

        # Act
        results = search_mixin.search_user('user.fullname ~ "Test"')

        # Assert
        assert isinstance(results, list)
        assert results == expected_result

    @pytest.mark.parametrize(
        "status_code,exception_type",
        [
            (401, MCPAtlassianAuthenticationError),
            (403, MCPAtlassianAuthenticationError),
        ],
    )
    def test_search_user_http_auth_errors(
        self, search_mixin, status_code, exception_type
    ):
        """Test search_user handling of HTTP authentication errors."""
        # Mock HTTP error
        mock_response = MagicMock()
        mock_response.status_code = status_code
        http_error = HTTPError(f"HTTP {status_code}")
        http_error.response = mock_response
        search_mixin.confluence.get.side_effect = http_error

        # Act and assert
        with pytest.raises(exception_type):
            search_mixin.search_user('user.fullname ~ "Test"')

    def test_search_user_http_other_error(self, search_mixin):
        """Test search_user handling of other HTTP errors."""
        # Mock HTTP 500 error
        mock_response = MagicMock()
        mock_response.status_code = 500
        http_error = HTTPError("Internal Server Error")
        http_error.response = mock_response
        search_mixin.confluence.get.side_effect = http_error

        # Act and assert - should re-raise the HTTPError
        with pytest.raises(HTTPError):
            search_mixin.search_user('user.fullname ~ "Test"')

    @pytest.mark.parametrize(
        "mock_response,expected_length",
        [
            ({"incomplete": "data"}, 0),  # KeyError case
            (None, 0),  # None response case
            ({"results": []}, 0),  # Empty results case
        ],
    )
    def test_search_user_edge_cases(self, search_mixin, mock_response, expected_length):
        """Test search_user handling of edge cases in API responses."""
        search_mixin.confluence.get.return_value = mock_response

        # Act
        results = search_mixin.search_user('user.fullname ~ "Test"')

        # Assert
        assert isinstance(results, list)
        assert len(results) == expected_length

    # You can also parametrize the regular search method exception tests:
    @pytest.mark.parametrize(
        "exception_type,exception_args,expected_result",
        [
            (requests.RequestException, ("API error",), []),
            (ValueError, ("Value error",), []),
            (TypeError, ("Type error",), []),
            (Exception, ("General error",), []),
            (KeyError, ("Missing key",), []),
        ],
    )
    def test_search_exception_handling(
        self, search_mixin, exception_type, exception_args, expected_result
    ):
        """Test search handling of various exceptions that return empty list."""
        # Mock the exception
        search_mixin.confluence.cql.side_effect = exception_type(*exception_args)

        # Act
        results = search_mixin.search("error query")

        # Assert
        assert isinstance(results, list)
        assert results == expected_result

    # Parametrize CQL query tests:
    @pytest.mark.parametrize(
        "query,limit,expected_params",
        [
            (
                'user.fullname ~ "Test"',
                10,
                {"cql": 'user.fullname ~ "Test"', "limit": 10},
            ),
            (
                'user.email ~ "test@example.com"',
                5,
                {"cql": 'user.email ~ "test@example.com"', "limit": 5},
            ),
            (
                'user.fullname ~ "John" AND user.email ~ "@company.com"',
                15,
                {
                    "cql": 'user.fullname ~ "John" AND user.email ~ "@company.com"',
                    "limit": 15,
                },
            ),
        ],
    )
    def test_search_user_api_parameters(
        self, search_mixin, query, limit, expected_params
    ):
        """Test that search_user calls the API with correct parameters."""
        # Mock successful response
        search_mixin.confluence.get.return_value = {
            "results": [],
            "start": 0,
            "limit": limit,
            "totalSize": 0,
        }

        # Act
        search_mixin.search_user(query, limit=limit)

        # Assert API was called with correct parameters
        search_mixin.confluence.get.assert_called_once_with(
            "rest/api/search/user", params=expected_params
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


class TestSearchUserServerDC:
    """Tests for Server/DC user search via group member API fallback."""

    @pytest.fixture
    def server_search_mixin(self, confluence_client):
        """Create a SearchMixin configured as Server/DC."""
        with patch(
            "mcp_atlassian.confluence.search.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = SearchMixin()
            mixin.confluence = confluence_client.confluence
            mixin.config = MagicMock()
            mixin.config.is_cloud = False
            mixin.preprocessor = confluence_client.preprocessor
            return mixin

    @pytest.fixture
    def cloud_search_mixin(self, confluence_client):
        """Create a SearchMixin configured as Cloud."""
        with patch(
            "mcp_atlassian.confluence.search.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = SearchMixin()
            mixin.confluence = confluence_client.confluence
            mixin.config = MagicMock()
            mixin.config.is_cloud = True
            mixin.preprocessor = confluence_client.preprocessor
            return mixin

    def test_cloud_path_uses_cql_endpoint(self, cloud_search_mixin):
        """Cloud path should still use CQL rest/api/search/user."""
        cloud_search_mixin.confluence.get.return_value = {
            "results": [],
            "start": 0,
            "limit": 10,
            "size": 0,
            "totalSize": 0,
        }

        cloud_search_mixin.search_user('user.fullname ~ "Test"')

        cloud_search_mixin.confluence.get.assert_called_once_with(
            "rest/api/search/user",
            params={"cql": 'user.fullname ~ "Test"', "limit": 10},
        )

    def test_server_dc_calls_group_member_api(self, server_search_mixin):
        """Server/DC should call group member API instead of CQL."""
        server_search_mixin.confluence.get.return_value = {
            "results": [
                {
                    "type": "known",
                    "username": "jdoe",
                    "displayName": "John Doe",
                    "userKey": "abc123",
                }
            ],
            "start": 0,
            "limit": 200,
            "size": 1,
        }

        results = server_search_mixin.search_user('user.fullname ~ "John"')

        # Should have called the group member API
        server_search_mixin.confluence.get.assert_called_with(
            "rest/api/group/confluence-users/member",
            params={"start": 0, "limit": 200},
        )
        assert len(results) == 1
        assert results[0].user is not None
        assert results[0].user.display_name == "John Doe"

    def test_server_dc_fuzzy_match_case_insensitive(self, server_search_mixin):
        """Fuzzy matching should be case-insensitive substring match."""
        server_search_mixin.confluence.get.return_value = {
            "results": [
                {
                    "type": "known",
                    "username": "jdoe",
                    "displayName": "John Doe",
                    "userKey": "abc123",
                },
                {
                    "type": "known",
                    "username": "asmith",
                    "displayName": "Alice Smith",
                    "userKey": "def456",
                },
                {
                    "type": "known",
                    "username": "bjohnson",
                    "displayName": "Bob Johnson",
                    "userKey": "ghi789",
                },
            ],
            "start": 0,
            "limit": 200,
            "size": 3,
        }

        results = server_search_mixin.search_user('user.fullname ~ "john"')

        # Should match "John Doe" (displayName) and "bjohnson" (username)
        assert len(results) == 2
        display_names = {r.user.display_name for r in results}
        assert "John Doe" in display_names
        assert "Bob Johnson" in display_names

    def test_server_dc_pagination(self, server_search_mixin):
        """Should paginate through group members when _links.next is present."""
        # First page: 200 results with _links.next indicating more pages
        page1_members = [
            {
                "type": "known",
                "username": f"user{i}",
                "displayName": f"User {i}",
                "userKey": f"key{i}",
            }
            for i in range(200)
        ]
        # Second page: no _links.next (last page), contains a match
        page2_members = [
            {
                "type": "known",
                "username": "targetuser",
                "displayName": "Target User",
                "userKey": "targetkey",
            }
        ]

        server_search_mixin.confluence.get.side_effect = [
            {
                "results": page1_members,
                "start": 0,
                "limit": 200,
                "size": 200,
                "_links": {"next": "/rest/api/group/confluence-users/member?start=200"},
            },
            {
                "results": page2_members,
                "start": 200,
                "limit": 200,
                "size": 1,
            },
        ]

        results = server_search_mixin.search_user('user.fullname ~ "Target"')

        # Should have called twice for pagination
        assert server_search_mixin.confluence.get.call_count == 2
        calls = server_search_mixin.confluence.get.call_args_list
        assert calls[0] == call(
            "rest/api/group/confluence-users/member",
            params={"start": 0, "limit": 200},
        )
        assert calls[1] == call(
            "rest/api/group/confluence-users/member",
            params={"start": 200, "limit": 200},
        )
        assert len(results) == 1
        assert results[0].user.display_name == "Target User"

    @pytest.mark.parametrize(
        "cql,expected_term",
        [
            ('user.fullname ~ "John Doe"', "John Doe"),
            ('user.fullname~"Jane"', "Jane"),
            ('user.fullname ~ "Test"', "Test"),
            ("plain search term", "plain search term"),
            ("", ""),
        ],
    )
    def test_cql_term_extraction(self, cql, expected_term):
        """CQL term extraction regex should work correctly."""
        match = re.search(r'user\.fullname\s*~\s*"([^"]*)"', cql)
        extracted = match.group(1) if match else cql
        assert extracted == expected_term

    def test_server_dc_no_matches(self, server_search_mixin):
        """Should return empty list when no users match."""
        server_search_mixin.confluence.get.return_value = {
            "results": [
                {
                    "type": "known",
                    "username": "asmith",
                    "displayName": "Alice Smith",
                    "userKey": "def456",
                }
            ],
            "start": 0,
            "limit": 200,
            "size": 1,
        }

        results = server_search_mixin.search_user('user.fullname ~ "Nonexistent"')

        assert len(results) == 0

    def test_server_dc_custom_group_name(self, server_search_mixin):
        """Should use the provided group_name parameter."""
        server_search_mixin.confluence.get.return_value = {
            "results": [
                {
                    "type": "known",
                    "username": "jdoe",
                    "displayName": "John Doe",
                    "userKey": "abc123",
                }
            ],
            "start": 0,
            "limit": 200,
            "size": 1,
        }

        server_search_mixin.search_user(
            'user.fullname ~ "John"',
            group_name="custom-group",
        )

        server_search_mixin.confluence.get.assert_called_with(
            "rest/api/group/custom-group/member",
            params={"start": 0, "limit": 200},
        )

    def test_server_dc_respects_limit(self, server_search_mixin):
        """Should return at most `limit` results."""
        members = [
            {
                "type": "known",
                "username": f"john{i}",
                "displayName": f"John User {i}",
                "userKey": f"key{i}",
            }
            for i in range(10)
        ]
        server_search_mixin.confluence.get.return_value = {
            "results": members,
            "start": 0,
            "limit": 200,
            "size": 10,
        }

        results = server_search_mixin.search_user('user.fullname ~ "John"', limit=3)

        assert len(results) == 3

    def test_server_dc_stops_pagination_when_limit_reached(self, server_search_mixin):
        """Should stop paginating once enough matches are found."""
        # All 200 members match, limit is 5 -> should not fetch page 2
        page1_members = [
            {
                "type": "known",
                "username": f"john{i}",
                "displayName": f"John {i}",
                "userKey": f"key{i}",
            }
            for i in range(200)
        ]

        server_search_mixin.confluence.get.return_value = {
            "results": page1_members,
            "start": 0,
            "limit": 200,
            "size": 200,
            "_links": {"next": "/rest/api/group/confluence-users/member?start=200"},
        }

        results = server_search_mixin.search_user('user.fullname ~ "John"', limit=5)

        # Should only call once since we have enough matches
        assert server_search_mixin.confluence.get.call_count == 1
        assert len(results) == 5

    def test_server_dc_matches_on_username(self, server_search_mixin):
        """Should match on username field too, not just displayName."""
        server_search_mixin.confluence.get.return_value = {
            "results": [
                {
                    "type": "known",
                    "username": "john.doe",
                    "displayName": "J. Doe",
                    "userKey": "abc123",
                }
            ],
            "start": 0,
            "limit": 200,
            "size": 1,
        }

        results = server_search_mixin.search_user('user.fullname ~ "john"')

        # Should match because "john" is in the username "john.doe"
        assert len(results) == 1
        assert results[0].user.display_name == "J. Doe"

    def test_server_dc_result_model_structure(self, server_search_mixin):
        """Results should be valid ConfluenceUserSearchResult models."""
        server_search_mixin.confluence.get.return_value = {
            "results": [
                {
                    "type": "known",
                    "username": "jdoe",
                    "displayName": "John Doe",
                    "userKey": "abc123",
                    "profilePicture": {
                        "path": "/avatar/jdoe",
                        "width": 48,
                        "height": 48,
                        "isDefault": False,
                    },
                }
            ],
            "start": 0,
            "limit": 200,
            "size": 1,
        }

        results = server_search_mixin.search_user('user.fullname ~ "John"')

        assert len(results) == 1
        result = results[0]
        assert result.user is not None
        assert result.user.display_name == "John Doe"
        assert result.title == "John Doe"
        assert result.entity_type == "user"
        # to_simplified_dict should work
        simplified = result.to_simplified_dict()
        assert simplified["title"] == "John Doe"
        assert simplified["user"]["display_name"] == "John Doe"

    def test_server_dc_user_is_active_defaults_true(self, server_search_mixin):
        """Server/DC users without accountStatus should default to active."""
        server_search_mixin.confluence.get.return_value = {
            "results": [
                {
                    "type": "known",
                    "username": "jdoe",
                    "displayName": "John Doe",
                    "userKey": "abc123",
                }
            ],
            "start": 0,
            "limit": 200,
            "size": 1,
        }

        results = server_search_mixin.search_user('user.fullname ~ "John"')

        assert len(results) == 1
        assert results[0].user.is_active is True

    def test_server_dc_url_encodes_group_name(self, server_search_mixin):
        """Group names with special characters should be URL-encoded."""
        server_search_mixin.confluence.get.return_value = {
            "results": [],
            "start": 0,
            "limit": 200,
            "size": 0,
        }

        server_search_mixin.search_user(
            'user.fullname ~ "John"',
            group_name="my group/team",
        )

        server_search_mixin.confluence.get.assert_called_with(
            "rest/api/group/my%20group%2Fteam/member",
            params={"start": 0, "limit": 200},
        )

    def test_server_dc_stops_without_links_next(self, server_search_mixin):
        """Should stop pagination when response lacks _links.next."""
        # Even with exactly page_size results, stop if no _links.next
        members = [
            {
                "type": "known",
                "username": f"user{i}",
                "displayName": f"User {i}",
                "userKey": f"key{i}",
            }
            for i in range(200)
        ]

        server_search_mixin.confluence.get.return_value = {
            "results": members,
            "start": 0,
            "limit": 200,
            "size": 200,
            # No _links.next -> last page
        }

        server_search_mixin.search_user('user.fullname ~ "User"', limit=300)

        # Should only call once since there's no _links.next
        assert server_search_mixin.confluence.get.call_count == 1
