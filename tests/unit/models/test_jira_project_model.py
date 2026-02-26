"""
Tests for the JiraProject Pydantic model.
"""

from mcp_atlassian.models.constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_PROJECT,
    UNKNOWN,
)
from mcp_atlassian.models.jira import (
    JiraProject,
)


class TestJiraProject:
    """Tests for the JiraProject model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraProject from valid API data."""
        project_data = {
            "id": "10000",
            "key": "TEST",
            "name": "Test Project",
            "description": "This is a test project",
            "lead": {
                "accountId": "5b10a2844c20165700ede21g",
                "displayName": "John Doe",
                "active": True,
            },
            "self": "https://example.atlassian.net/rest/api/3/project/10000",
            "projectCategory": {
                "id": "10100",
                "name": "Software Projects",
                "description": "Software development projects",
            },
            "avatarUrls": {
                "48x48": "https://example.atlassian.net/secure/projectavatar?pid=10000&avatarId=10011",
                "24x24": "https://example.atlassian.net/secure/projectavatar?pid=10000&size=small&avatarId=10011",
            },
        }
        project = JiraProject.from_api_response(project_data)
        assert project.id == "10000"
        assert project.key == "TEST"
        assert project.name == "Test Project"
        assert project.description == "This is a test project"
        assert project.lead is not None
        assert project.lead.display_name == "John Doe"
        assert project.url == "https://example.atlassian.net/rest/api/3/project/10000"
        assert project.category_name == "Software Projects"
        assert (
            project.avatar_url
            == "https://example.atlassian.net/secure/projectavatar?pid=10000&avatarId=10011"
        )

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraProject from empty data."""
        project = JiraProject.from_api_response({})
        assert project.id == JIRA_DEFAULT_PROJECT
        assert project.key == EMPTY_STRING
        assert project.name == UNKNOWN
        assert project.description is None
        assert project.lead is None
        assert project.url is None
        assert project.category_name is None
        assert project.avatar_url is None

    def test_to_simplified_dict(self):
        """Test converting a JiraProject to a simplified dictionary."""
        project_data = {
            "id": "10000",
            "key": "TEST",
            "name": "Test Project",
            "description": "This is a test project",
            "lead": {
                "accountId": "5b10a2844c20165700ede21g",
                "displayName": "John Doe",
                "active": True,
            },
            "self": "https://example.atlassian.net/rest/api/3/project/10000",
            "projectCategory": {
                "name": "Software Projects",
            },
        }
        project = JiraProject.from_api_response(project_data)
        simplified = project.to_simplified_dict()
        assert simplified["key"] == "TEST"
        assert simplified["name"] == "Test Project"
        assert simplified["description"] == "This is a test project"
        assert simplified["lead"] is not None
        assert simplified["lead"]["display_name"] == "John Doe"
        assert simplified["category"] == "Software Projects"
        assert "id" not in simplified
        assert "url" not in simplified
        assert "avatar_url" not in simplified
