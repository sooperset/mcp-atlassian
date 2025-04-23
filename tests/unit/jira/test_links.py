from unittest.mock import MagicMock, patch

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
        mock_response = {
            "issueLinkTypes": [
                {
                    "id": "1",
                    "name": "Blocks",
                    "inward": "is blocked by",
                    "outward": "blocks",
                },
                {
                    "id": "2",
                    "name": "Relates",
                    "inward": "relates to",
                    "outward": "is related to",
                },
            ]
        }
        links_mixin.jira.get.return_value = mock_response

        with patch.object(
            JiraIssueLinkType, "from_api_response", side_effect=lambda x: x
        ):
            result = links_mixin.get_issue_link_types()

        assert len(result) == 2
        assert result[0]["name"] == "Blocks"
        assert result[1]["name"] == "Relates"

    def test_get_issue_link_types_authentication_error(self, links_mixin):
        links_mixin.jira.get.side_effect = HTTPError(
            response=MagicMock(status_code=401)
        )

        with pytest.raises(MCPAtlassianAuthenticationError):
            links_mixin.get_issue_link_types()

    def test_get_issue_link_types_generic_error(self, links_mixin):
        links_mixin.jira.get.side_effect = Exception("Unexpected error")

        with pytest.raises(Exception, match="Unexpected error"):
            links_mixin.get_issue_link_types()

    def test_create_issue_link_success(self, links_mixin):
        data = {
            "type": {"name": "Relates"},
            "inwardIssue": {"key": "ISSUE-1"},
            "outwardIssue": {"key": "ISSUE-2"},
        }

        response = links_mixin.create_issue_link(data)

        links_mixin.jira.create_issue_link.assert_called_once_with(data)
        assert response["success"] is True
        assert response["message"] == ("Link created between ISSUE-1 and ISSUE-2")

    def test_create_issue_link_missing_type(self, links_mixin):
        data = {
            "inwardIssue": {"key": "ISSUE-1"},
            "outwardIssue": {"key": "ISSUE-2"},
        }

        with pytest.raises(ValueError, match="Link type is required"):
            links_mixin.create_issue_link(data)

    def test_create_issue_link_authentication_error(self, links_mixin):
        data = {
            "type": {"name": "Relates"},
            "inwardIssue": {"key": "ISSUE-1"},
            "outwardIssue": {"key": "ISSUE-2"},
        }
        links_mixin.jira.create_issue_link.side_effect = HTTPError(
            response=MagicMock(status_code=403)
        )

        with pytest.raises(MCPAtlassianAuthenticationError):
            links_mixin.create_issue_link(data)

    def test_remove_issue_link_success(self, links_mixin):
        link_id = "12345"

        response = links_mixin.remove_issue_link(link_id)

        links_mixin.jira.remove_issue_link.assert_called_once_with(link_id)
        assert response["success"] is True
        assert response["message"] == (f"Link with ID {link_id} has been removed")

    def test_remove_issue_link_missing_id(self, links_mixin):
        with pytest.raises(ValueError, match="Link ID is required"):
            links_mixin.remove_issue_link("")

    def test_remove_issue_link_authentication_error(self, links_mixin):
        link_id = "12345"
        links_mixin.jira.remove_issue_link.side_effect = HTTPError(
            response=MagicMock(status_code=401)
        )

        with pytest.raises(MCPAtlassianAuthenticationError):
            links_mixin.remove_issue_link(link_id)
