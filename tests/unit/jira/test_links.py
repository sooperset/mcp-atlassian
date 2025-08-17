from unittest.mock import MagicMock, Mock, patch

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.jira.links import LinksMixin
from mcp_atlassian.models.jira import JiraIssueLinkType


class TestLinksMixin:
    @pytest.fixture
    def links_mixin(self, mock_config, mock_atlassian_jira):
        mixin = LinksMixin(config=mock_config)
        mixin.jira = mock_atlassian_jira
        return mixin

    def test_get_issue_link_types_success(self, links_mixin):
        """Test successful retrieval of issue link types."""
        mock_response = {
            "issueLinkTypes": [
                {
                    "id": "10000",
                    "name": "Blocks",
                    "inward": "is blocked by",
                    "outward": "blocks",
                },
                {
                    "id": "10001",
                    "name": "Duplicate",
                    "inward": "is duplicated by",
                    "outward": "duplicates",
                },
            ]
        }
        links_mixin.jira.get.return_value = mock_response

        def fake_from_api_response(data):
            mock = MagicMock()
            mock.name = data["name"]
            return mock

        with patch.object(
            JiraIssueLinkType, "from_api_response", side_effect=fake_from_api_response
        ):
            result = links_mixin.get_issue_link_types()

        assert len(result) == 2
        assert result[0].name == "Blocks"
        assert result[1].name == "Duplicate"
        links_mixin.jira.get.assert_called_once_with("rest/api/2/issueLinkType")

    def test_get_issue_link_types_authentication_error(self, links_mixin):
        links_mixin.jira.get.side_effect = HTTPError(response=Mock(status_code=401))

        with pytest.raises(MCPAtlassianAuthenticationError):
            links_mixin.get_issue_link_types()

    def test_get_issue_link_types_generic_error(self, links_mixin):
        links_mixin.jira.get.side_effect = Exception("Unexpected error")

        with pytest.raises(Exception, match="Unexpected error"):
            links_mixin.get_issue_link_types()

    def test_create_issue_link_success(self, links_mixin):
        data = {
            "type": {"name": "Blocks"},
            "inwardIssue": {"key": "PROJ-123"},
            "outwardIssue": {"key": "PROJ-456"},
        }

        response = links_mixin.create_issue_link(data)

        assert response["success"] is True
        assert "Link created between PROJ-123 and PROJ-456" in response["message"]
        links_mixin.jira.create_issue_link.assert_called_once_with(data)

    def test_create_issue_link_missing_type(self, links_mixin):
        data = {
            "inwardIssue": {"key": "PROJ-123"},
            "outwardIssue": {"key": "PROJ-456"},
        }

        with pytest.raises(ValueError, match="Link type is required"):
            links_mixin.create_issue_link(data)

    def test_create_issue_link_authentication_error(self, links_mixin):
        data = {
            "type": {"name": "Blocks"},
            "inwardIssue": {"key": "PROJ-123"},
            "outwardIssue": {"key": "PROJ-456"},
        }
        links_mixin.jira.create_issue_link.side_effect = HTTPError(
            response=Mock(status_code=401)
        )

        with pytest.raises(MCPAtlassianAuthenticationError):
            links_mixin.create_issue_link(data)

    def test_create_remote_issue_link_success(self, links_mixin):
        issue_key = "PROJ-123"
        link_data = {
            "object": {
                "url": "https://example.com/page",
                "title": "Example Page",
                "summary": "A test page",
            },
            "relationship": "documentation",
        }

        response = links_mixin.create_remote_issue_link(issue_key, link_data)

        assert response["success"] is True
        assert response["issue_key"] == issue_key
        assert response["link_title"] == "Example Page"
        assert response["link_url"] == "https://example.com/page"
        assert response["relationship"] == "documentation"
        links_mixin.jira.post.assert_called_once_with(
            "rest/api/3/issue/PROJ-123/remotelink", json=link_data
        )

    def test_create_remote_issue_link_missing_issue_key(self, links_mixin):
        link_data = {
            "object": {"url": "https://example.com/page", "title": "Example Page"}
        }

        with pytest.raises(ValueError, match="Issue key is required"):
            links_mixin.create_remote_issue_link("", link_data)

    def test_create_remote_issue_link_missing_object(self, links_mixin):
        issue_key = "PROJ-123"
        link_data = {"relationship": "documentation"}

        with pytest.raises(ValueError, match="Link object is required"):
            links_mixin.create_remote_issue_link(issue_key, link_data)

    def test_create_remote_issue_link_missing_url(self, links_mixin):
        issue_key = "PROJ-123"
        link_data = {"object": {"title": "Example Page"}}

        with pytest.raises(ValueError, match="URL is required in link object"):
            links_mixin.create_remote_issue_link(issue_key, link_data)

    def test_create_remote_issue_link_missing_title(self, links_mixin):
        issue_key = "PROJ-123"
        link_data = {"object": {"url": "https://example.com/page"}}

        with pytest.raises(ValueError, match="Title is required in link object"):
            links_mixin.create_remote_issue_link(issue_key, link_data)

    def test_create_remote_issue_link_authentication_error(self, links_mixin):
        issue_key = "PROJ-123"
        link_data = {
            "object": {"url": "https://example.com/page", "title": "Example Page"}
        }
        links_mixin.jira.post.side_effect = HTTPError(response=Mock(status_code=401))

        with pytest.raises(MCPAtlassianAuthenticationError):
            links_mixin.create_remote_issue_link(issue_key, link_data)

    def test_remove_issue_link_success(self, links_mixin):
        link_id = "10000"

        response = links_mixin.remove_issue_link(link_id)

        assert response["success"] is True
        assert f"Link with ID {link_id} has been removed" in response["message"]
        links_mixin.jira.remove_issue_link.assert_called_once_with(link_id)

    def test_remove_issue_link_empty_id(self, links_mixin):
        with pytest.raises(ValueError, match="Link ID is required"):
            links_mixin.remove_issue_link("")

    def test_remove_issue_link_authentication_error(self, links_mixin):
        link_id = "10000"
        links_mixin.jira.remove_issue_link.side_effect = HTTPError(
            response=Mock(status_code=401)
        )

        with pytest.raises(MCPAtlassianAuthenticationError):
            links_mixin.remove_issue_link(link_id)
