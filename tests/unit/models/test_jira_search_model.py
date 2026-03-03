"""
Tests for the JiraSearchResult Pydantic model.
"""

from mcp_atlassian.models.jira import (
    JiraIssue,
    JiraSearchResult,
)


class TestJiraSearchResult:
    """Tests for the JiraSearchResult model."""

    def test_from_api_response_with_valid_data(self, jira_search_data):
        """Test creating a JiraSearchResult from valid API data."""
        search_result = JiraSearchResult.from_api_response(jira_search_data)
        assert search_result.total == 34
        assert search_result.start_at == 0
        assert search_result.max_results == 5
        assert len(search_result.issues) == 1

        issue = search_result.issues[0]
        assert isinstance(issue, JiraIssue)
        assert issue.key == "PROJ-123"
        assert issue.summary == "Test Issue Summary"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraSearchResult from empty data."""
        result = JiraSearchResult.from_api_response({})
        assert result.total == 0
        assert result.start_at == 0
        assert result.max_results == 0
        assert result.issues == []

    def test_from_api_response_missing_metadata(self, jira_search_data):
        """Test creating a JiraSearchResult when API is missing metadata."""
        # Remove total, startAt, maxResults from mock data
        api_data = dict(jira_search_data)
        api_data.pop("total", None)
        api_data.pop("startAt", None)
        api_data.pop("maxResults", None)

        search_result = JiraSearchResult.from_api_response(api_data)
        # Verify that -1 is used for missing metadata
        assert search_result.total == -1
        assert search_result.start_at == -1
        assert search_result.max_results == -1
        assert len(search_result.issues) == 1  # Assuming mock data has issues

    def test_to_simplified_dict(self, jira_search_data):
        """Test converting JiraSearchResult to a simplified dictionary."""
        search_result = JiraSearchResult.from_api_response(jira_search_data)
        simplified = search_result.to_simplified_dict()

        # Verify the structure and basic metadata
        assert isinstance(simplified, dict)
        assert "total" in simplified
        assert "start_at" in simplified
        assert "max_results" in simplified
        assert "issues" in simplified

        # Verify metadata values
        assert simplified["total"] == 34
        assert simplified["start_at"] == 0
        assert simplified["max_results"] == 5

        # Verify issues array
        assert isinstance(simplified["issues"], list)
        assert len(simplified["issues"]) == 1

        # Verify that each issue is a simplified dict (not a JiraIssue object)
        issue = simplified["issues"][0]
        assert isinstance(issue, dict)
        assert issue["key"] == "PROJ-123"
        assert issue["summary"] == "Test Issue Summary"

        # Verify that the issues are properly simplified (calling to_simplified_dict on each)
        # This ensures field filtering works properly
        assert "id" in issue  # ID is included in simplified version
        assert "expand" not in issue  # Should be filtered out in simplified version

        # Verify that issue contains expected fields
        assert "assignee" in issue
        assert "created" in issue
        assert "updated" in issue

    def test_to_simplified_dict_empty_result(self):
        """Test converting an empty JiraSearchResult to a simplified dictionary."""
        search_result = JiraSearchResult()
        simplified = search_result.to_simplified_dict()

        assert isinstance(simplified, dict)
        assert simplified["total"] == 0
        assert simplified["start_at"] == 0
        assert simplified["max_results"] == 0
        assert simplified["issues"] == []

    def test_to_simplified_dict_with_multiple_issues(self):
        """Test converting JiraSearchResult with multiple issues to a simplified dictionary."""
        # Create mock data with multiple issues
        mock_data = {
            "total": 2,
            "startAt": 0,
            "maxResults": 10,
            "issues": [
                {
                    "id": "12345",
                    "key": "PROJ-123",
                    "fields": {
                        "summary": "First Issue",
                        "status": {"name": "In Progress"},
                    },
                },
                {
                    "id": "12346",
                    "key": "PROJ-124",
                    "fields": {
                        "summary": "Second Issue",
                        "status": {"name": "Done"},
                    },
                },
            ],
        }

        search_result = JiraSearchResult.from_api_response(mock_data)
        simplified = search_result.to_simplified_dict()

        # Verify metadata
        assert simplified["total"] == 2
        assert simplified["start_at"] == 0
        assert simplified["max_results"] == 10

        # Verify issues
        assert len(simplified["issues"]) == 2
        assert simplified["issues"][0]["key"] == "PROJ-123"
        assert simplified["issues"][0]["summary"] == "First Issue"
        assert simplified["issues"][1]["key"] == "PROJ-124"
        assert simplified["issues"][1]["summary"] == "Second Issue"

    def test_from_api_response_with_next_page_token(self):
        """Test from_api_response extracts nextPageToken from API data."""
        mock_data = {
            "total": -1,
            "startAt": 0,
            "maxResults": 10,
            "nextPageToken": "eyJhbGciOiJIUzI1NiJ9.abc123",
            "issues": [
                {
                    "id": "12345",
                    "key": "PROJ-123",
                    "fields": {
                        "summary": "Test Issue",
                        "status": {"name": "Open"},
                    },
                }
            ],
        }

        result = JiraSearchResult.from_api_response(mock_data)
        assert result.next_page_token == "eyJhbGciOiJIUzI1NiJ9.abc123"

    def test_from_api_response_without_next_page_token(self):
        """Test from_api_response sets next_page_token to None when absent."""
        mock_data = {
            "total": 1,
            "startAt": 0,
            "maxResults": 10,
            "issues": [
                {
                    "id": "12345",
                    "key": "PROJ-123",
                    "fields": {
                        "summary": "Test Issue",
                        "status": {"name": "Open"},
                    },
                }
            ],
        }

        result = JiraSearchResult.from_api_response(mock_data)
        assert result.next_page_token is None

    def test_to_simplified_dict_includes_next_page_token_when_present(self):
        """Test to_simplified_dict includes next_page_token when not None."""
        mock_data = {
            "total": -1,
            "startAt": 0,
            "maxResults": 10,
            "nextPageToken": "token_abc_123",
            "issues": [],
        }

        result = JiraSearchResult.from_api_response(mock_data)
        simplified = result.to_simplified_dict()
        assert "next_page_token" in simplified
        assert simplified["next_page_token"] == "token_abc_123"

    def test_to_simplified_dict_excludes_next_page_token_when_none(self):
        """Test to_simplified_dict excludes next_page_token when None."""
        mock_data = {
            "total": 1,
            "startAt": 0,
            "maxResults": 10,
            "issues": [],
        }

        result = JiraSearchResult.from_api_response(mock_data)
        simplified = result.to_simplified_dict()
        assert "next_page_token" not in simplified
