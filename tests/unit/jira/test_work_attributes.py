"""Unit tests for Tempo Core Work Attributes functionality."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira.work_attributes import WorkAttributeMixin
from mcp_atlassian.models.jira import JiraWorkAttribute, JiraWorkAttributeValue
from mcp_atlassian.models.jira.worklog import JiraWorklog


class TestJiraWorkAttribute:
    """Tests for JiraWorkAttribute model."""

    def test_from_api_response_valid(self):
        """Test creating a JiraWorkAttribute from valid API response."""
        data = {
            "id": 45,
            "name": "Work Mode",
            "type": "singleselect",
            "description": "Where the work was performed",
            "isRequired": False,
        }
        attr = JiraWorkAttribute.from_api_response(data)

        assert attr.id == 45
        assert attr.name == "Work Mode"
        assert attr.type == "singleselect"
        assert attr.description == "Where the work was performed"
        assert attr.is_required is False

    def test_from_api_response_required(self):
        """Test parsing isRequired as string."""
        data = {
            "id": 46,
            "name": "Cost Category",
            "type": "multiselect",
            "isRequired": "true",
        }
        attr = JiraWorkAttribute.from_api_response(data)

        assert attr.is_required is True

    def test_from_api_response_empty(self):
        """Test creating empty JiraWorkAttribute."""
        attr = JiraWorkAttribute.from_api_response(None)
        assert attr.id == 0
        assert attr.name == ""

    def test_from_api_response_non_dict(self):
        """Test handling non-dict input."""
        attr = JiraWorkAttribute.from_api_response("invalid")
        assert attr.id == 0

    def test_to_simplified_dict(self):
        """Test converting to simplified dictionary."""
        attr = JiraWorkAttribute(
            id=45,
            name="Work Mode",
            type="singleselect",
            description="Where the work was performed",
            is_required=False,
        )
        result = attr.to_simplified_dict()

        assert result == {
            "id": 45,
            "name": "Work Mode",
            "type": "singleselect",
            "description": "Where the work was performed",
            "is_required": False,
        }


class TestJiraWorkAttributeValue:
    """Tests for JiraWorkAttributeValue model."""

    def test_from_api_response_valid(self):
        """Test creating a JiraWorkAttributeValue from valid API response."""
        data = {
            "id": 123,
            "name": "Office",
            "color": "#36B37E",
            "workAttributeId": 45,
        }
        value = JiraWorkAttributeValue.from_api_response(data)

        assert value.id == 123
        assert value.name == "Office"
        assert value.color == "#36B37E"
        assert value.work_attribute_id == 45

    def test_from_api_response_empty(self):
        """Test creating empty JiraWorkAttributeValue."""
        value = JiraWorkAttributeValue.from_api_response(None)
        assert value.id == 0
        assert value.name == ""

    def test_from_api_response_non_dict(self):
        """Test handling non-dict input."""
        value = JiraWorkAttributeValue.from_api_response("invalid")
        assert value.id == 0

    def test_to_simplified_dict(self):
        """Test converting to simplified dictionary."""
        value = JiraWorkAttributeValue(
            id=123,
            name="Office",
            color="#36B37E",
            work_attribute_id=45,
        )
        result = value.to_simplified_dict()

        assert result == {
            "id": 123,
            "name": "Office",
            "color": "#36B37E",
            "work_attribute_id": 45,
        }


class TestJiraWorklogWithAttributes:
    """Tests for JiraWorklog with worklog attributes support."""

    def test_from_api_response_with_attributes(self):
        """Test parsing worklog with attributes."""
        data = {
            "id": "10001",
            "author": {
                "displayName": "John Doe",
                "emailAddress": "john@example.com",
            },
            "comment": "Fixed the bug",
            "created": "2024-01-15T10:00:00.000+0000",
            "updated": "2024-01-15T10:00:00.000+0000",
            "started": "2024-01-15T09:00:00.000+0000",
            "timeSpent": "2 hours",
            "timeSpentSeconds": 7200,
            "attributes": {"45": "123"},
        }
        worklog = JiraWorklog.from_api_response(data)

        assert worklog.attributes is not None
        assert worklog.attributes == {"45": "123"}
        assert "attributes" in worklog.to_simplified_dict()

    def test_from_api_response_without_attributes(self):
        """Test parsing worklog without attributes."""
        data = {
            "id": "10002",
            "author": {
                "displayName": "Jane Doe",
                "emailAddress": "jane@example.com",
            },
            "comment": "Working on feature",
            "timeSpent": "1 day",
            "timeSpentSeconds": 28800,
        }
        worklog = JiraWorklog.from_api_response(data)

        assert worklog.attributes is None


class TestWorkAttributeMixin:
    """Tests for WorkAttributeMixin."""

    @pytest.fixture
    def mixin(self):
        """Create a WorkAttributeMixin with mocked Jira client."""
        mock_config = MagicMock()
        mock_config.is_cloud = False

        mock_jira = MagicMock()
        mock_jira.get = MagicMock()

        mixin = MagicMock(spec=WorkAttributeMixin)
        mixin.config = mock_config
        mixin.jira = mock_jira

        return mixin

    def test_get_work_attributes_success(self, mixin):
        """Test successful retrieval of work attributes."""
        # Mock the API response
        mixin.jira.get.return_value = [
            {"id": 45, "name": "Work Mode", "type": "singleselect"},
            {"id": 46, "name": "Cost Category", "type": "multiselect"},
        ]

        # Call the actual method on the real mixin class
        # We need to properly set up the mixin
        from mcp_atlassian.jira.work_attributes import WorkAttributeMixin

        # Create a partial instance for testing
        class TestMixin(WorkAttributeMixin):
            def __init__(self):
                self.config = MagicMock()
                self.config.is_cloud = False
                self.jira = MagicMock()

        test_mixin = TestMixin()
        test_mixin.jira.get.return_value = [
            {"id": 45, "name": "Work Mode", "type": "singleselect"},
        ]

        result = test_mixin.get_work_attributes()

        assert len(result) == 1
        assert isinstance(result[0], JiraWorkAttribute)
        assert result[0].id == 45
        assert result[0].name == "Work Mode"

    def test_get_work_attributes_empty(self, mixin):
        """Test handling empty work attributes response."""
        from mcp_atlassian.jira.work_attributes import WorkAttributeMixin

        class TestMixin(WorkAttributeMixin):
            def __init__(self):
                self.config = MagicMock()
                self.config.is_cloud = False
                self.jira = MagicMock()

        test_mixin = TestMixin()
        test_mixin.jira.get.return_value = []

        result = test_mixin.get_work_attributes()

        assert result == []

    def test_get_work_attributes_invalid_response(self, mixin):
        """Test handling invalid response type."""
        from mcp_atlassian.jira.work_attributes import WorkAttributeMixin

        class TestMixin(WorkAttributeMixin):
            def __init__(self):
                self.config = MagicMock()
                self.config.is_cloud = False
                self.jira = MagicMock()

        test_mixin = TestMixin()
        test_mixin.jira.get.return_value = "invalid"

        result = test_mixin.get_work_attributes()

        assert result == []

    def test_get_work_attribute_values_success(self, mixin):
        """Test successful retrieval of work attribute values."""
        from mcp_atlassian.jira.work_attributes import WorkAttributeMixin

        class TestMixin(WorkAttributeMixin):
            def __init__(self):
                self.config = MagicMock()
                self.config.is_cloud = False
                self.jira = MagicMock()

        test_mixin = TestMixin()
        test_mixin.jira.get.return_value = [
            {"id": 123, "name": "Office", "color": "#36B37E", "workAttributeId": 45},
            {"id": 124, "name": "Remote", "color": "#579DFF", "workAttributeId": 45},
        ]

        result = test_mixin.get_work_attribute_values(attribute_id=45)

        assert len(result) == 2
        assert isinstance(result[0], JiraWorkAttributeValue)
        assert result[0].id == 123
        assert result[0].name == "Office"
        assert result[1].name == "Remote"

    def test_get_work_attribute_values_empty(self, mixin):
        """Test handling empty attribute values response."""
        from mcp_atlassian.jira.work_attributes import WorkAttributeMixin

        class TestMixin(WorkAttributeMixin):
            def __init__(self):
                self.config = MagicMock()
                self.config.is_cloud = False
                self.jira = MagicMock()

        test_mixin = TestMixin()
        test_mixin.jira.get.return_value = []

        result = test_mixin.get_work_attribute_values(attribute_id=45)

        assert result == []


class TestAddWorklogWithAttributes:
    """Tests for add_worklog with worklog_attributes parameter."""

    def test_add_worklog_data_with_attributes(self):
        """Test that worklog_data includes worklogAttributes when provided."""
        from mcp_atlassian.jira.worklog import WorklogMixin

        class TestMixin(WorklogMixin):
            def __init__(self):
                self.config = MagicMock()
                self.config.is_cloud = False
                self.jira = MagicMock()

        test_mixin = TestMixin()
        test_mixin.jira.resource_url.return_value = (
            "https://jira.example.com/rest/api/2/issue"
        )
        test_mixin.jira.post.return_value = {
            "id": "10001",
            "timeSpent": "2 hours",
            "timeSpentSeconds": 7200,
            "author": {"displayName": "Test User"},
        }

        result = test_mixin.add_worklog(
            issue_key="PROJ-123",
            time_spent="2h",
            worklog_attributes={"45": "123"},
        )

        # Check that post was called with attributes in data
        call_args = test_mixin.jira.post.call_args
        assert call_args is not None
        data_arg = call_args[1]["data"] if "data" in call_args[1] else call_args[0][1]
        assert "worklogAttributes" in data_arg
        assert data_arg["worklogAttributes"] == {"45": "123"}
