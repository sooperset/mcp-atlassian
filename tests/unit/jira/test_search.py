"""Tests for the Jira Search mixin."""

from unittest.mock import ANY, MagicMock

import pytest
import requests

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.search import SearchMixin
from mcp_atlassian.models.jira import JiraIssue, JiraSearchResult


class TestSearchMixin:
    """Tests for the SearchMixin class."""

    @pytest.fixture
    def search_mixin(self, jira_fetcher: JiraFetcher) -> SearchMixin:
        """Create a SearchMixin instance with mocked dependencies."""
        mixin = jira_fetcher

        # Mock methods that are typically provided by other mixins
        mixin._clean_text = MagicMock(side_effect=lambda text: text if text else "")

        # Set config with is_cloud=False by default (Server/DC)
        mixin.config = MagicMock()
        mixin.config.is_cloud = False
        mixin.config.projects_filter = None
        mixin.config.url = "https://example.atlassian.net"

        return mixin

    @pytest.fixture
    def mock_issues_response(self) -> dict:
        """Create a mock Jira issues response for testing."""
        return {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                        "description": "Test description",
                        "created": "2024-01-01T10:00:00.000+0000",
                        "updated": "2024-01-01T11:00:00.000+0000",
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }

    def test_search_issues_calls_v3_api_for_cloud(
        self,
        search_mixin: SearchMixin,
        mock_issues_response,
    ):
        """Test that Cloud uses POST /rest/api/3/search/jql (v3 API)."""
        # Setup: Mock config.is_cloud = True
        search_mixin.config.is_cloud = True
        search_mixin.config.projects_filter = None
        search_mixin.config.url = "https://test.example.com"

        # Setup: Mock v3 API response
        search_mixin.jira.post = MagicMock(return_value=mock_issues_response)
        search_mixin.jira.jql = MagicMock(return_value=mock_issues_response)

        # Act
        jql_query = "project = TEST"
        result = search_mixin.search_issues(jql_query, limit=10, start=0)

        # Assert: Basic result verification
        assert isinstance(result, JiraSearchResult)
        assert len(result.issues) > 0

        # Assert: v3 API (POST) was called for Cloud
        search_mixin.jira.post.assert_called_once()
        call_args = search_mixin.jira.post.call_args
        assert call_args[0][0] == "rest/api/3/search/jql"
        assert call_args[1]["json"]["jql"] == jql_query

        # Assert: v2 API (jql) was NOT called
        search_mixin.jira.jql.assert_not_called()

    def test_search_issues_calls_jql_for_server(
        self,
        search_mixin: SearchMixin,
        mock_issues_response,
    ):
        """Test that Server/DC uses jql method (v2 API)."""
        # Setup: Mock config.is_cloud = False
        search_mixin.config.is_cloud = False
        search_mixin.config.projects_filter = None
        search_mixin.config.url = "https://test.example.com"

        # Setup: Mock response
        search_mixin.jira.post = MagicMock(return_value=mock_issues_response)
        search_mixin.jira.jql = MagicMock(return_value=mock_issues_response)

        # Act
        jql_query = "project = TEST"
        result = search_mixin.search_issues(jql_query, limit=10, start=0)

        # Assert: Basic result verification
        assert isinstance(result, JiraSearchResult)
        assert len(result.issues) > 0

        # Assert: jql method was called for Server/DC
        search_mixin.jira.jql.assert_called_once_with(
            jql_query, fields=ANY, start=0, limit=10, expand=None
        )

        # Assert: v3 API (POST) was NOT called
        search_mixin.jira.post.assert_not_called()

    def test_search_issues_basic(self, search_mixin: SearchMixin):
        """Test basic search functionality."""
        # Setup mock response
        mock_issues = {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                        "description": "Issue description",
                        "created": "2024-01-01T10:00:00.000+0000",
                        "updated": "2024-01-01T11:00:00.000+0000",
                        "priority": {"name": "High"},
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        search_mixin.jira.jql.return_value = mock_issues

        # Call the method
        result = search_mixin.search_issues("project = TEST")

        # Verify
        search_mixin.jira.jql.assert_called_once_with(
            "project = TEST",
            fields=ANY,
            start=0,
            limit=50,
            expand=None,
        )

        # Verify results
        assert isinstance(result, JiraSearchResult)
        assert len(result.issues) == 1
        assert all(isinstance(issue, JiraIssue) for issue in result.issues)
        assert result.total == 1
        assert result.start_at == 0
        assert result.max_results == 50

        # Check the first issue
        issue = result.issues[0]
        assert issue.key == "TEST-123"
        assert issue.summary == "Test issue"
        assert issue.description == "Issue description"
        assert issue.status is not None
        assert issue.status.name == "Open"
        assert issue.issue_type is not None
        assert issue.issue_type.name == "Bug"
        assert issue.priority is not None
        assert issue.priority.name == "High"

        # Remove backward compatibility checks
        assert "Issue description" in issue.description
        assert issue.key == "TEST-123"

    def test_search_issues_with_empty_description(self, search_mixin: SearchMixin):
        """Test search with issues that have no description."""
        # Setup mock response
        mock_issues = {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                        "description": None,
                        "created": "2024-01-01T10:00:00.000+0000",
                        "updated": "2024-01-01T11:00:00.000+0000",
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        search_mixin.jira.jql.return_value = mock_issues

        # Call the method
        result = search_mixin.search_issues("project = TEST")

        # Verify results
        assert len(result.issues) == 1
        assert isinstance(result.issues[0], JiraIssue)
        assert result.issues[0].key == "TEST-123"
        assert result.issues[0].description is None
        assert result.issues[0].summary == "Test issue"

        # Update to use direct properties instead of backward compatibility
        assert "Test issue" in result.issues[0].summary

    def test_search_issues_with_missing_fields(self, search_mixin: SearchMixin):
        """Test search with issues missing some fields."""
        # Setup mock response
        mock_issues = {
            "issues": [
                {
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        # Missing issuetype, status, etc.
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        search_mixin.jira.jql.return_value = mock_issues

        # Call the method
        result = search_mixin.search_issues("project = TEST")

        # Verify results
        assert len(result.issues) == 1
        assert isinstance(result.issues[0], JiraIssue)
        assert result.issues[0].key == "TEST-123"
        assert result.issues[0].summary == "Test issue"
        assert result.issues[0].status is None
        assert result.issues[0].issue_type is None

    def test_search_issues_with_empty_results(self, search_mixin: SearchMixin):
        """Test search with no results."""
        # Setup mock response
        search_mixin.jira.jql.return_value = {"issues": []}

        # Call the method
        result = search_mixin.search_issues("project = NONEXISTENT")

        # Verify results
        assert isinstance(result, JiraSearchResult)
        assert len(result.issues) == 0
        assert result.total == -1

    def test_search_issues_with_error(self, search_mixin: SearchMixin):
        """Test search with API error."""
        # Setup mock to raise exception
        search_mixin.jira.jql.side_effect = Exception("API Error")

        # Call the method and verify it raises the expected exception
        with pytest.raises(Exception, match="Error searching issues"):
            search_mixin.search_issues("project = TEST")

    def test_search_issues_with_projects_filter(self, search_mixin: SearchMixin):
        """Test search with projects filter."""
        # Setup mock response
        mock_issues = {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        search_mixin.jira.jql.return_value = mock_issues
        search_mixin.config.url = "https://example.atlassian.net"

        # Test with single project filter
        result = search_mixin.search_issues("text ~ 'test'", projects_filter="TEST")
        search_mixin.jira.jql.assert_called_with(
            "(text ~ 'test') AND project = \"TEST\"",
            fields=ANY,
            start=0,
            limit=50,
            expand=None,
        )
        assert len(result.issues) == 1
        assert result.total == 1

        # Test with multiple project filter
        result = search_mixin.search_issues("text ~ 'test'", projects_filter="TEST,DEV")
        search_mixin.jira.jql.assert_called_with(
            '(text ~ \'test\') AND project IN ("TEST", "DEV")',
            fields=ANY,
            start=0,
            limit=50,
            expand=None,
        )
        assert len(result.issues) == 1
        assert result.total == 1

    def test_search_issues_with_config_projects_filter(self, search_mixin: SearchMixin):
        """Test search with projects filter from config."""
        # Setup mock response
        mock_issues = {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        search_mixin.jira.jql.return_value = mock_issues
        search_mixin.config.url = "https://example.atlassian.net"
        search_mixin.config.projects_filter = "TEST,DEV"

        # Test with config filter
        result = search_mixin.search_issues("text ~ 'test'")
        search_mixin.jira.jql.assert_called_with(
            '(text ~ \'test\') AND project IN ("TEST", "DEV")',
            fields=ANY,
            start=0,
            limit=50,
            expand=None,
        )
        assert len(result.issues) == 1
        assert result.total == 1

        # Test with override
        result = search_mixin.search_issues("text ~ 'test'", projects_filter="OVERRIDE")
        search_mixin.jira.jql.assert_called_with(
            "(text ~ 'test') AND project = \"OVERRIDE\"",
            fields=ANY,
            start=0,
            limit=50,
            expand=None,
        )
        assert len(result.issues) == 1
        assert result.total == 1

        # Test with override - multiple projects
        result = search_mixin.search_issues(
            "text ~ 'test'", projects_filter="OVER1,OVER2"
        )
        search_mixin.jira.jql.assert_called_with(
            '(text ~ \'test\') AND project IN ("OVER1", "OVER2")',
            fields=ANY,
            start=0,
            limit=50,
            expand=None,
        )
        assert len(result.issues) == 1
        assert result.total == 1

    def test_search_issues_with_fields_parameter(self, search_mixin: SearchMixin):
        """Test search with specific fields parameter, including custom fields."""
        # Setup mock response with a custom field
        mock_issues = {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue with custom field",
                        "assignee": {
                            "displayName": "Test User",
                            "emailAddress": "test@example.com",
                            "active": True,
                        },
                        "customfield_10049": "Custom value",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                        "description": "Issue description",
                        "created": "2024-01-01T10:00:00.000+0000",
                        "updated": "2024-01-01T11:00:00.000+0000",
                        "priority": {"name": "High"},
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        search_mixin.jira.jql.return_value = mock_issues
        search_mixin.config.url = "https://example.atlassian.net"

        # Call the method with specific fields
        result = search_mixin.search_issues(
            "project = TEST", fields="summary,assignee,customfield_10049"
        )

        # Verify the JQL call includes the fields parameter
        search_mixin.jira.jql.assert_called_once_with(
            "project = TEST",
            fields="summary,assignee,customfield_10049",
            start=0,
            limit=50,
            expand=None,
        )

        # Verify results
        assert isinstance(result, JiraSearchResult)
        assert len(result.issues) == 1
        issue = result.issues[0]

        # Convert to simplified dict to check field filtering
        simplified = issue.to_simplified_dict()

        # These fields should be included (plus id and key which are always included)
        assert "id" in simplified
        assert "key" in simplified
        assert "summary" in simplified
        assert "assignee" in simplified
        assert "customfield_10049" in simplified

        assert simplified["customfield_10049"] == {"value": "Custom value"}
        assert "assignee" in simplified
        assert simplified["assignee"]["display_name"] == "Test User"

    def test_get_board_issues(self, search_mixin: SearchMixin):
        """Test get_board_issues method."""
        mock_issues = {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                        "description": "Issue description",
                        "created": "2024-01-01T10:00:00.000+0000",
                        "updated": "2024-01-01T11:00:00.000+0000",
                        "priority": {"name": "High"},
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        search_mixin.jira.get_issues_for_board.return_value = mock_issues

        # Call the method
        result = search_mixin.get_board_issues("1000", jql="", limit=20)

        # Verify results
        assert isinstance(result, JiraSearchResult)
        assert len(result.issues) == 1
        assert all(isinstance(issue, JiraIssue) for issue in result.issues)
        assert result.total == 1
        assert result.start_at == 0
        assert result.max_results == 50

        # Check the first issue
        issue = result.issues[0]
        assert issue.key == "TEST-123"
        assert issue.summary == "Test issue"
        assert issue.description == "Issue description"
        assert issue.status is not None
        assert issue.status.name == "Open"
        assert issue.issue_type is not None
        assert issue.issue_type.name == "Bug"
        assert issue.priority is not None
        assert issue.priority.name == "High"

        # Remove backward compatibility checks
        assert "Issue description" in issue.description
        assert issue.key == "TEST-123"

    def test_get_board_issues_exception(self, search_mixin: SearchMixin):
        search_mixin.jira.get_issues_for_board.side_effect = Exception("API Error")

        with pytest.raises(Exception) as e:
            search_mixin.get_board_issues("1000", jql="", limit=20)
        assert "API Error" in str(e.value)

    def test_get_board_issues_http_error(self, search_mixin: SearchMixin):
        search_mixin.jira.get_issues_for_board.side_effect = requests.HTTPError(
            response=MagicMock(content="API Error content")
        )

        with pytest.raises(Exception) as e:
            search_mixin.get_board_issues("1000", jql="", limit=20)
        assert "API Error content" in str(e.value)

    def test_get_sprint_issues(self, search_mixin: SearchMixin):
        """Test get_sprint_issues method."""
        mock_issues = {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-123",
                    "fields": {
                        "summary": "Test issue",
                        "issuetype": {"name": "Bug"},
                        "status": {"name": "Open"},
                        "description": "Issue description",
                        "created": "2024-01-01T10:00:00.000+0000",
                        "updated": "2024-01-01T11:00:00.000+0000",
                        "priority": {"name": "High"},
                    },
                }
            ],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        search_mixin.jira.get_sprint_issues.return_value = mock_issues

        # Call the method
        result = search_mixin.get_sprint_issues("10001")

        # Verify results
        assert isinstance(result, JiraSearchResult)
        assert len(result.issues) == 1
        assert all(isinstance(issue, JiraIssue) for issue in result.issues)
        assert result.total == 1
        assert result.start_at == 0
        assert result.max_results == 50

        # Check the first issue
        issue = result.issues[0]
        assert issue.key == "TEST-123"
        assert issue.summary == "Test issue"
        assert issue.description == "Issue description"
        assert issue.status is not None
        assert issue.status.name == "Open"
        assert issue.issue_type is not None
        assert issue.issue_type.name == "Bug"
        assert issue.priority is not None
        assert issue.priority.name == "High"

    def test_get_sprint_issues_exception(self, search_mixin: SearchMixin):
        search_mixin.jira.get_sprint_issues.side_effect = Exception("API Error")

        with pytest.raises(Exception) as e:
            search_mixin.get_sprint_issues("10001")
        assert "API Error" in str(e.value)

    def test_get_sprint_issues_http_error(self, search_mixin: SearchMixin):
        search_mixin.jira.get_sprint_issues.side_effect = requests.HTTPError(
            response=MagicMock(content="API Error content")
        )

        with pytest.raises(Exception) as e:
            search_mixin.get_sprint_issues("10001")
        assert "API Error content" in str(e.value)

    @pytest.mark.parametrize("is_cloud", [True, False])
    def test_search_issues_with_projects_filter_jql_construction(
        self, search_mixin: SearchMixin, mock_issues_response, is_cloud
    ):
        """Test that JQL string is correctly constructed when projects_filter is provided."""
        # Setup
        search_mixin.config.is_cloud = is_cloud
        search_mixin.config.projects_filter = (
            None  # Don't use config filter for this test
        )
        search_mixin.config.url = "https://test.example.com"

        # Setup mock response for both API methods
        search_mixin.jira.post = MagicMock(return_value=mock_issues_response)
        search_mixin.jira.jql = MagicMock(return_value=mock_issues_response)

        # Helper to get the JQL from the appropriate mock
        def get_jql_from_call():
            if is_cloud:
                return search_mixin.jira.post.call_args[1]["json"]["jql"]
            else:
                return search_mixin.jira.jql.call_args[0][0]

        # Act: Single project filter
        search_mixin.search_issues("text ~ 'test'", projects_filter="TEST")

        # Assert: JQL verification
        assert get_jql_from_call() == "(text ~ 'test') AND project = \"TEST\""

        # Reset mocks for next call
        search_mixin.jira.post.reset_mock()
        search_mixin.jira.jql.reset_mock()

        # Act: Multiple projects filter
        search_mixin.search_issues("text ~ 'test'", projects_filter="TEST, DEV")
        # Assert: JQL verification
        assert get_jql_from_call() == '(text ~ \'test\') AND project IN ("TEST", "DEV")'

        # Reset mocks for next call
        search_mixin.jira.post.reset_mock()
        search_mixin.jira.jql.reset_mock()

        # Act: Call with both JQL and filter
        search_mixin.search_issues("project = OTHER", projects_filter="TEST")
        # Assert: JQL verification (existing JQL has priority)
        assert get_jql_from_call() == "project = OTHER"

    @pytest.mark.parametrize("is_cloud", [True, False])
    def test_search_issues_with_config_projects_filter_jql_construction(
        self, search_mixin: SearchMixin, mock_issues_response, is_cloud
    ):
        """Test that JQL string is correctly constructed when config.projects_filter is used."""
        # Setup
        search_mixin.config.is_cloud = is_cloud
        search_mixin.config.projects_filter = "CONF1,CONF2"  # Set config filter
        search_mixin.config.url = "https://test.example.com"

        # Setup mock response for both API methods
        search_mixin.jira.post = MagicMock(return_value=mock_issues_response)
        search_mixin.jira.jql = MagicMock(return_value=mock_issues_response)

        # Helper to get the JQL from the appropriate mock
        def get_jql_from_call():
            if is_cloud:
                return search_mixin.jira.post.call_args[1]["json"]["jql"]
            else:
                return search_mixin.jira.jql.call_args[0][0]

        # Act: Use config filter
        search_mixin.search_issues("text ~ 'test'")
        # Assert: JQL verification
        assert (
            get_jql_from_call() == '(text ~ \'test\') AND project IN ("CONF1", "CONF2")'
        )

        # Reset mocks for next call
        search_mixin.jira.post.reset_mock()
        search_mixin.jira.jql.reset_mock()

        # Act: Override config filter with parameter
        search_mixin.search_issues("text ~ 'test'", projects_filter="OVERRIDE")
        # Assert: JQL verification
        assert get_jql_from_call() == "(text ~ 'test') AND project = \"OVERRIDE\""

    @pytest.mark.parametrize("is_cloud", [True, False])
    def test_search_issues_with_empty_jql_and_projects_filter(
        self, search_mixin: SearchMixin, mock_issues_response, is_cloud
    ):
        """Test that empty JQL correctly prepends project filter without AND."""
        # Setup
        search_mixin.config.is_cloud = is_cloud
        search_mixin.config.projects_filter = None
        search_mixin.config.url = "https://test.example.com"

        # Setup mock response for both API methods
        search_mixin.jira.post = MagicMock(return_value=mock_issues_response)
        search_mixin.jira.jql = MagicMock(return_value=mock_issues_response)

        # Helper to get the JQL from the appropriate mock
        def get_jql_from_call():
            if is_cloud:
                return search_mixin.jira.post.call_args[1]["json"]["jql"]
            else:
                return search_mixin.jira.jql.call_args[0][0]

        # Test 1: Empty string JQL with single project
        search_mixin.search_issues("", projects_filter="PROJ1")
        assert get_jql_from_call() == 'project = "PROJ1"'

        # Reset mocks
        search_mixin.jira.post.reset_mock()
        search_mixin.jira.jql.reset_mock()

        # Test 2: Empty string JQL with multiple projects
        search_mixin.search_issues("", projects_filter="PROJ1,PROJ2")
        assert get_jql_from_call() == 'project IN ("PROJ1", "PROJ2")'

        # Reset mocks
        search_mixin.jira.post.reset_mock()
        search_mixin.jira.jql.reset_mock()

        # Test 3: None JQL with projects filter
        result = search_mixin.search_issues(None, projects_filter="PROJ1")
        assert get_jql_from_call() == 'project = "PROJ1"'
        assert isinstance(result, JiraSearchResult)

    @pytest.mark.parametrize("is_cloud", [True, False])
    def test_search_issues_with_order_by_and_projects_filter(
        self, search_mixin: SearchMixin, mock_issues_response, is_cloud
    ):
        """Test that JQL starting with ORDER BY correctly prepends project filter."""
        # Setup
        search_mixin.config.is_cloud = is_cloud
        search_mixin.config.projects_filter = None
        search_mixin.config.url = "https://test.example.com"

        # Setup mock response for both API methods
        search_mixin.jira.post = MagicMock(return_value=mock_issues_response)
        search_mixin.jira.jql = MagicMock(return_value=mock_issues_response)

        # Helper to get the JQL from the appropriate mock
        def get_jql_from_call():
            if is_cloud:
                return search_mixin.jira.post.call_args[1]["json"]["jql"]
            else:
                return search_mixin.jira.jql.call_args[0][0]

        # Test 1: ORDER BY with single project
        search_mixin.search_issues("ORDER BY created DESC", projects_filter="PROJ1")
        assert get_jql_from_call() == 'project = "PROJ1" ORDER BY created DESC'

        # Reset mocks
        search_mixin.jira.post.reset_mock()
        search_mixin.jira.jql.reset_mock()

        # Test 2: ORDER BY with multiple projects
        search_mixin.search_issues(
            "ORDER BY created DESC", projects_filter="PROJ1,PROJ2"
        )
        assert (
            get_jql_from_call() == 'project IN ("PROJ1", "PROJ2") ORDER BY created DESC'
        )

        # Reset mocks
        search_mixin.jira.post.reset_mock()
        search_mixin.jira.jql.reset_mock()

        # Test 3: Case insensitive ORDER BY
        search_mixin.search_issues("order by updated ASC", projects_filter="PROJ1")
        assert get_jql_from_call() == 'project = "PROJ1" order by updated ASC'

        # Reset mocks
        search_mixin.jira.post.reset_mock()
        search_mixin.jira.jql.reset_mock()

        # Test 4: ORDER BY with extra spaces
        search_mixin.search_issues(
            "  ORDER BY priority DESC  ", projects_filter="PROJ1"
        )
        assert get_jql_from_call() == 'project = "PROJ1"   ORDER BY priority DESC  '
