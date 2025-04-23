"""Tests for the Jira Links mixin."""

from unittest.mock import MagicMock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.jira.links import LinksMixin
from mcp_atlassian.models.jira import JiraIssueLinkType


class TestLinksMixin:
    """Tests for the LinksMixin class."""

    @pytest.fixture
    def links_mixin(self, jira_client):
        """Create a LinksMixin instance with mocked dependencies."""
        mixin = LinksMixin(config=jira_client.config)
        mixin.jira = jira_client.jira
        return mixin

    def test_create_issue_link_basic(self, links_mixin):
        """Test basic functionality of create_issue_link."""
        # Setup mock
        links_mixin.jira.create_issue_link.return_value = {"id": "12345"}

        # Test data
        link_data = {
            "type": {"name": "Duplicate"},
            "inwardIssue": {"key": "HSP-1"},
            "outwardIssue": {"key": "MKY-1"},
            "comment": {
                "body": "Linked related issue!",
                "visibility": {"type": "group", "value": "jira-software-users"},
            },
        }

        # Call the method
        result = links_mixin.create_issue_link(link_data)

        # Verify API calls
        links_mixin.jira.create_issue_link.assert_called_once_with(link_data)

        # Verify result structure
        assert result["success"] is True
        assert "message" in result
        assert result["link_type"] == "Duplicate"
        assert result["inward_issue"] == "HSP-1"
        assert result["outward_issue"] == "MKY-1"

    def test_create_issue_link_missing_type(self, links_mixin):
        """Test create_issue_link with missing type."""
        # Test data with missing type
        link_data = {"inwardIssue": {"key": "HSP-1"}, "outwardIssue": {"key": "MKY-1"}}

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception, match="Error creating issue link: Link type is required"
        ):
            links_mixin.create_issue_link(link_data)

    def test_create_issue_link_missing_inward_issue(self, links_mixin):
        """Test create_issue_link with missing inward issue."""
        # Test data with missing inward issue
        link_data = {"type": {"name": "Duplicate"}, "outwardIssue": {"key": "MKY-1"}}

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception, match="Error creating issue link: Inward issue key is required"
        ):
            links_mixin.create_issue_link(link_data)

    def test_create_issue_link_missing_outward_issue(self, links_mixin):
        """Test create_issue_link with missing outward issue."""
        # Test data with missing outward issue
        link_data = {"type": {"name": "Duplicate"}, "inwardIssue": {"key": "HSP-1"}}

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception, match="Error creating issue link: Outward issue key is required"
        ):
            links_mixin.create_issue_link(link_data)

    def test_create_issue_link_api_error(self, links_mixin):
        """Test error handling when creating an issue link."""
        # Test data
        link_data = {
            "type": {"name": "Duplicate"},
            "inwardIssue": {"key": "HSP-1"},
            "outwardIssue": {"key": "MKY-1"},
        }

        # Make the API call raise an exception
        links_mixin.jira.create_issue_link.side_effect = Exception("API error")

        # Call the method and verify it raises the expected exception
        with pytest.raises(Exception, match="Error creating issue link: API error"):
            links_mixin.create_issue_link(link_data)

    def test_create_issue_link_http_error(self, links_mixin):
        """Test HTTP error handling when creating an issue link."""
        # Test data
        link_data = {
            "type": {"name": "Duplicate"},
            "inwardIssue": {"key": "HSP-1"},
            "outwardIssue": {"key": "MKY-1"},
        }

        # Create a mock HTTP error with a 401 status code
        mock_response = MagicMock()
        mock_response.status_code = 401
        http_error = HTTPError("Unauthorized")
        http_error.response = mock_response

        # Make the API call raise the HTTP error
        links_mixin.jira.create_issue_link.side_effect = http_error

        # Call the method and verify it raises the expected exception
        with pytest.raises(Exception, match="Authentication failed for Jira API"):
            links_mixin.create_issue_link(link_data)

    def test_remove_issue_link_basic(self, links_mixin):
        """Test basic functionality of remove_issue_link."""
        # Setup mock
        links_mixin.jira.remove_issue_link.return_value = (
            None  # This method typically returns None
        )

        # Call the method
        result = links_mixin.remove_issue_link("12345")

        # Verify API calls
        links_mixin.jira.remove_issue_link.assert_called_once_with("12345")

        # Verify result structure
        assert result["success"] is True
        assert "message" in result
        assert result["link_id"] == "12345"

    def test_remove_issue_link_missing_id(self, links_mixin):
        """Test remove_issue_link with missing link ID."""
        # Call the method with empty link_id and verify it raises the expected exception
        with pytest.raises(
            Exception, match="Error removing issue link: Link ID is required"
        ):
            links_mixin.remove_issue_link("")

        # Call the method with None link_id and verify it raises the expected exception
        with pytest.raises(
            Exception, match="Error removing issue link: Link ID is required"
        ):
            links_mixin.remove_issue_link(None)

    def test_remove_issue_link_api_error(self, links_mixin):
        """Test error handling when removing an issue link."""
        # Make the API call raise an exception
        links_mixin.jira.remove_issue_link.side_effect = Exception("API error")

        # Call the method and verify it raises the expected exception
        with pytest.raises(Exception, match="Error removing issue link: API error"):
            links_mixin.remove_issue_link("12345")

    def test_remove_issue_link_http_error(self, links_mixin):
        """Test HTTP error handling when removing an issue link."""
        # Create a mock HTTP error with a 401 status code
        mock_response = MagicMock()
        mock_response.status_code = 401
        http_error = HTTPError("Unauthorized")
        http_error.response = mock_response

        # Make the API call raise the HTTP error
        links_mixin.jira.remove_issue_link.side_effect = http_error

        # Call the method and verify it raises the expected exception
        with pytest.raises(Exception, match="Authentication failed for Jira API"):
            links_mixin.remove_issue_link("12345")

    def test_get_issue_link_types_basic(self, links_mixin, monkeypatch):
        """Test basic functionality of get_issue_link_types."""
        # Setup mock response
        mock_response = {
            "issueLinkTypes": [
                {
                    "id": "10000",
                    "name": "Blocks",
                    "inward": "is blocked by",
                    "outward": "blocks",
                    "self": "https://example.atlassian.net/rest/api/3/issueLinkType/10000",
                },
                {
                    "id": "10001",
                    "name": "Duplicate",
                    "inward": "is duplicated by",
                    "outward": "duplicates",
                    "self": "https://example.atlassian.net/rest/api/3/issueLinkType/10001",
                },
            ]
        }

        # Create a mock method to replace the internal _get_json method
        def mock_get_json(endpoint):
            if endpoint == "issueLinkType":
                return mock_response
            return {}

        # Patch the internal method
        monkeypatch.setattr(links_mixin.jira, "_get_json", mock_get_json)

        # Call the method
        result = links_mixin.get_issue_link_types()

        # Verify result structure
        assert len(result) == 2
        assert isinstance(result[0], JiraIssueLinkType)
        assert result[0].id == "10000"
        assert result[0].name == "Blocks"
        assert result[0].inward == "is blocked by"
        assert result[0].outward == "blocks"
        assert (
            result[0].self_url
            == "https://example.atlassian.net/rest/api/3/issueLinkType/10000"
        )

        assert isinstance(result[1], JiraIssueLinkType)
        assert result[1].id == "10001"
        assert result[1].name == "Duplicate"
        assert result[1].inward == "is duplicated by"
        assert result[1].outward == "duplicates"
        assert (
            result[1].self_url
            == "https://example.atlassian.net/rest/api/3/issueLinkType/10001"
        )

    def test_get_issue_link_types_empty_response(self, links_mixin, monkeypatch):
        """Test get_issue_link_types with empty response."""
        # Setup mock with empty response
        mock_response = {"issueLinkTypes": []}

        # Create a mock method to replace the internal _get_json method
        def mock_get_json(endpoint):
            if endpoint == "issueLinkType":
                return mock_response
            return {}

        # Patch the internal method
        monkeypatch.setattr(links_mixin.jira, "_get_json", mock_get_json)

        # Call the method
        result = links_mixin.get_issue_link_types()

        # Verify result is an empty list
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_issue_link_types_http_error(self, links_mixin, monkeypatch):
        """Test HTTP error handling when getting issue link types."""
        # Create a mock HTTP error with a 401 status code
        mock_response = MagicMock()
        mock_response.status_code = 401
        http_error = HTTPError("Unauthorized")
        http_error.response = mock_response

        # Create a mock method that raises an HTTP error
        def mock_get_json_error(endpoint):
            raise http_error

        # Patch the internal method
        monkeypatch.setattr(links_mixin.jira, "_get_json", mock_get_json_error)

        # Call the method and verify it raises the expected exception
        with pytest.raises(Exception, match="Authentication failed for Jira API"):
            links_mixin.get_issue_link_types()

    def test_get_issue_link_types_api_error(self, links_mixin, monkeypatch):
        """Test error handling when getting issue link types."""

        # Create a mock method that raises a general exception
        def mock_get_json_error(endpoint):
            raise Exception("API error")

        # Patch the internal method
        monkeypatch.setattr(links_mixin.jira, "_get_json", mock_get_json_error)

        # Call the method and verify it raises the expected exception
        with pytest.raises(
            Exception, match="Error getting issue link types: API error"
        ):
            links_mixin.get_issue_link_types()
