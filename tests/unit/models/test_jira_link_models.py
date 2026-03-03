"""
Tests for Jira issue link Pydantic models.

Tests for JiraIssueLinkType, JiraLinkedIssueFields, JiraLinkedIssue,
and JiraIssueLink models.
"""

from mcp_atlassian.models.constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
    UNKNOWN,
)
from mcp_atlassian.models.jira import (
    JiraIssueLink,
    JiraIssueLinkType,
    JiraIssueType,
    JiraLinkedIssue,
    JiraLinkedIssueFields,
    JiraPriority,
    JiraStatus,
)


class TestJiraIssueLinkType:
    """Tests for the JiraIssueLinkType model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraIssueLinkType from valid API data."""
        data = {
            "id": "10001",
            "name": "Blocks",
            "inward": "is blocked by",
            "outward": "blocks",
            "self": "https://example.atlassian.net/rest/api/3/issueLinkType/10001",
        }
        link_type = JiraIssueLinkType.from_api_response(data)
        assert link_type.id == "10001"
        assert link_type.name == "Blocks"
        assert link_type.inward == "is blocked by"
        assert link_type.outward == "blocks"
        assert (
            link_type.self_url
            == "https://example.atlassian.net/rest/api/3/issueLinkType/10001"
        )

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraIssueLinkType from empty data."""
        link_type = JiraIssueLinkType.from_api_response({})
        assert link_type.id == JIRA_DEFAULT_ID
        assert link_type.name == UNKNOWN
        assert link_type.inward == EMPTY_STRING
        assert link_type.outward == EMPTY_STRING
        assert link_type.self_url is None

    def test_from_api_response_with_none_data(self):
        """Test creating a JiraIssueLinkType from None data."""
        link_type = JiraIssueLinkType.from_api_response(None)
        assert link_type.id == JIRA_DEFAULT_ID
        assert link_type.name == UNKNOWN
        assert link_type.inward == EMPTY_STRING
        assert link_type.outward == EMPTY_STRING
        assert link_type.self_url is None

    def test_to_simplified_dict(self):
        """Test converting JiraIssueLinkType to a simplified dictionary."""
        link_type = JiraIssueLinkType(
            id="10001",
            name="Blocks",
            inward="is blocked by",
            outward="blocks",
            self_url="https://example.atlassian.net/rest/api/3/issueLinkType/10001",
        )
        simplified = link_type.to_simplified_dict()
        assert isinstance(simplified, dict)
        assert simplified["id"] == "10001"
        assert simplified["name"] == "Blocks"
        assert simplified["inward"] == "is blocked by"
        assert simplified["outward"] == "blocks"
        assert "self" in simplified
        assert (
            simplified["self"]
            == "https://example.atlassian.net/rest/api/3/issueLinkType/10001"
        )


class TestJiraLinkedIssueFields:
    """Tests for the JiraLinkedIssueFields model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraLinkedIssueFields from valid API data."""
        data = {
            "summary": "Linked Issue Summary",
            "status": {
                "id": "10000",
                "name": "In Progress",
                "statusCategory": {
                    "id": 4,
                    "key": "indeterminate",
                    "name": "In Progress",
                    "colorName": "yellow",
                },
            },
            "priority": {
                "id": "3",
                "name": "Medium",
                "description": "Medium priority",
                "iconUrl": "https://example.com/medium-priority.png",
            },
            "issuetype": {
                "id": "10000",
                "name": "Task",
                "description": "A task that needs to be done.",
                "iconUrl": "https://example.com/task-icon.png",
            },
        }
        fields = JiraLinkedIssueFields.from_api_response(data)
        assert fields.summary == "Linked Issue Summary"
        assert fields.status is not None
        assert fields.status.name == "In Progress"
        assert fields.priority is not None
        assert fields.priority.name == "Medium"
        assert fields.issuetype is not None
        assert fields.issuetype.name == "Task"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraLinkedIssueFields from empty data."""
        fields = JiraLinkedIssueFields.from_api_response({})
        assert fields.summary == EMPTY_STRING
        assert fields.status is None
        assert fields.priority is None
        assert fields.issuetype is None

    def test_to_simplified_dict(self):
        """Test converting JiraLinkedIssueFields to a simplified dictionary."""
        fields = JiraLinkedIssueFields(
            summary="Linked Issue Summary",
            status=JiraStatus(name="In Progress"),
            priority=JiraPriority(name="Medium"),
            issuetype=JiraIssueType(name="Task"),
        )
        simplified = fields.to_simplified_dict()
        assert simplified["summary"] == "Linked Issue Summary"
        assert simplified["status"]["name"] == "In Progress"
        assert simplified["priority"]["name"] == "Medium"
        assert simplified["issuetype"]["name"] == "Task"


class TestJiraLinkedIssue:
    """Tests for the JiraLinkedIssue model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraLinkedIssue from valid API data."""
        data = {
            "id": "10001",
            "key": "PROJ-456",
            "self": "https://example.atlassian.net/rest/api/2/issue/10001",
            "fields": {
                "summary": "Linked Issue Summary",
                "status": {
                    "id": "10000",
                    "name": "In Progress",
                },
                "priority": {
                    "id": "3",
                    "name": "Medium",
                },
                "issuetype": {
                    "id": "10000",
                    "name": "Task",
                },
            },
        }
        linked_issue = JiraLinkedIssue.from_api_response(data)
        assert linked_issue.id == "10001"
        assert linked_issue.key == "PROJ-456"
        assert (
            linked_issue.self_url
            == "https://example.atlassian.net/rest/api/2/issue/10001"
        )
        assert linked_issue.fields is not None
        assert linked_issue.fields.summary == "Linked Issue Summary"
        assert linked_issue.fields.status is not None
        assert linked_issue.fields.status.name == "In Progress"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraLinkedIssue from empty data."""
        linked_issue = JiraLinkedIssue.from_api_response({})
        assert linked_issue.id == JIRA_DEFAULT_ID
        assert linked_issue.key == EMPTY_STRING
        assert linked_issue.self_url is None
        assert linked_issue.fields is None

    def test_to_simplified_dict(self):
        """Test converting JiraLinkedIssue to a simplified dictionary."""
        linked_issue = JiraLinkedIssue(
            id="10001",
            key="PROJ-456",
            self_url="https://example.atlassian.net/rest/api/2/issue/10001",
            fields=JiraLinkedIssueFields(
                summary="Linked Issue Summary",
                status=JiraStatus(name="In Progress"),
                priority=JiraPriority(name="Medium"),
                issuetype=JiraIssueType(name="Task"),
            ),
        )
        simplified = linked_issue.to_simplified_dict()
        assert simplified["id"] == "10001"
        assert simplified["key"] == "PROJ-456"
        assert (
            simplified["self"] == "https://example.atlassian.net/rest/api/2/issue/10001"
        )
        assert simplified["fields"]["summary"] == "Linked Issue Summary"
        assert simplified["fields"]["status"]["name"] == "In Progress"


class TestJiraIssueLink:
    """Tests for the JiraIssueLink model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a JiraIssueLink from valid API data."""
        data = {
            "id": "10001",
            "type": {
                "id": "10000",
                "name": "Blocks",
                "inward": "is blocked by",
                "outward": "blocks",
                "self": "https://example.atlassian.net/rest/api/2/issueLinkType/10000",
            },
            "inwardIssue": {
                "id": "10002",
                "key": "PROJ-789",
                "self": "https://example.atlassian.net/rest/api/2/issue/10002",
                "fields": {
                    "summary": "Inward Issue Summary",
                    "status": {
                        "id": "10000",
                        "name": "In Progress",
                    },
                },
            },
        }
        issue_link = JiraIssueLink.from_api_response(data)
        assert issue_link.id == "10001"
        assert issue_link.type is not None
        assert issue_link.type.name == "Blocks"
        assert issue_link.inward_issue is not None
        assert issue_link.inward_issue.key == "PROJ-789"
        assert issue_link.outward_issue is None

    def test_from_api_response_with_outward_issue(self):
        """Test creating a JiraIssueLink with an outward issue."""
        data = {
            "id": "10001",
            "type": {
                "id": "10000",
                "name": "Blocks",
                "inward": "is blocked by",
                "outward": "blocks",
            },
            "outwardIssue": {
                "id": "10003",
                "key": "PROJ-101",
                "fields": {
                    "summary": "Outward Issue Summary",
                    "status": {
                        "id": "10000",
                        "name": "In Progress",
                    },
                },
            },
        }
        issue_link = JiraIssueLink.from_api_response(data)
        assert issue_link.id == "10001"
        assert issue_link.type is not None
        assert issue_link.type.name == "Blocks"
        assert issue_link.inward_issue is None
        assert issue_link.outward_issue is not None
        assert issue_link.outward_issue.key == "PROJ-101"

    def test_from_api_response_with_empty_data(self):
        """Test creating a JiraIssueLink from empty data."""
        issue_link = JiraIssueLink.from_api_response({})
        assert issue_link.id == JIRA_DEFAULT_ID
        assert issue_link.type is None
        assert issue_link.inward_issue is None
        assert issue_link.outward_issue is None

    def test_to_simplified_dict(self):
        """Test converting JiraIssueLink to a simplified dictionary."""
        issue_link = JiraIssueLink(
            id="10001",
            type=JiraIssueLinkType(
                id="10000",
                name="Blocks",
                inward="is blocked by",
                outward="blocks",
            ),
            inward_issue=JiraLinkedIssue(
                id="10002",
                key="PROJ-789",
                fields=JiraLinkedIssueFields(
                    summary="Inward Issue Summary",
                    status=JiraStatus(name="In Progress"),
                ),
            ),
        )
        simplified = issue_link.to_simplified_dict()
        assert simplified["id"] == "10001"
        assert simplified["type"]["name"] == "Blocks"
        assert simplified["inward_issue"]["key"] == "PROJ-789"
        assert "outward_issue" not in simplified
