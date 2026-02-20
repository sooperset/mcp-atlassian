"""Tests for custom field options functionality."""

from unittest.mock import Mock, patch

import pytest

from mcp_atlassian.models.jira.field_option import (
    JiraFieldContext,
    JiraFieldContextOptionsResponse,
    JiraFieldContextsResponse,
    JiraFieldOption,
    JiraFieldOptionsResponse,
)
from mcp_atlassian.servers.jira import (
    _apply_option_filters,
    _json_dumps_compact,
    _to_values_only_payload,
)


class TestFieldOptionModels:
    """Test the field option data models."""

    def test_jira_field_option_creation(self):
        """Test creating a JiraFieldOption."""
        option_data = {
            "id": "10001",
            "value": "High Priority",
            "disabled": False,
            "config": {"color": "red"},
        }

        option = JiraFieldOption(**option_data)

        assert option.id == "10001"
        assert option.value == "High Priority"
        assert option.disabled is False
        assert option.config == {"color": "red"}

    def test_jira_field_context_creation(self):
        """Test creating a JiraFieldContext."""
        context_data = {
            "id": "10020",
            "name": "Default context",
            "description": "Default field context",
            "isGlobalContext": True,
            "isAnyIssueType": True,
        }

        context = JiraFieldContext(**context_data)

        assert context.id == "10020"
        assert context.name == "Default context"
        assert context.description == "Default field context"
        assert context.is_global_context is True
        assert context.is_any_issue_type is True

    def test_jira_field_options_response_creation(self):
        """Test creating a JiraFieldOptionsResponse."""
        response_data = {
            "maxResults": 50,
            "startAt": 0,
            "total": 3,
            "isLast": True,
            "values": [
                {"id": "10001", "value": "High", "disabled": False},
                {"id": "10002", "value": "Medium", "disabled": False},
                {"id": "10003", "value": "Low", "disabled": False},
            ],
        }

        response = JiraFieldOptionsResponse(**response_data)

        assert response.max_results == 50
        assert response.start_at == 0
        assert response.total == 3
        assert response.is_last is True
        assert len(response.values) == 3
        assert response.values[0].value == "High"

    def test_jira_field_options_response_to_simplified_dict(self):
        """Test converting JiraFieldOptionsResponse to simplified dict."""
        response_data = {
            "maxResults": 50,
            "startAt": 0,
            "total": 2,
            "isLast": True,
            "values": [
                {"id": "10001", "value": "High", "disabled": False},
                {"id": "10002", "value": "Low", "disabled": True},
            ],
        }

        response = JiraFieldOptionsResponse(**response_data)
        simplified = response.to_simplified_dict()

        expected = {
            "pagination": {
                "start_at": 0,
                "max_results": 50,
                "total": 2,
                "is_last": True,
            },
            "options": [
                {"id": "10001", "value": "High", "disabled": False, "config": None},
                {"id": "10002", "value": "Low", "disabled": True, "config": None},
            ],
        }

        assert simplified == expected

    def test_jira_field_contexts_response_creation(self):
        """Test creating a JiraFieldContextsResponse."""
        response_data = {
            "maxResults": 50,
            "startAt": 0,
            "total": 1,
            "isLast": True,
            "values": [
                {
                    "id": "10020",
                    "name": "Default context",
                    "description": "Default field context",
                    "isGlobalContext": True,
                    "isAnyIssueType": True,
                }
            ],
        }

        response = JiraFieldContextsResponse(**response_data)

        assert response.max_results == 50
        assert response.start_at == 0
        assert response.total == 1
        assert response.is_last is True
        assert len(response.values) == 1
        assert response.values[0].name == "Default context"

    def test_jira_field_context_options_response_creation(self):
        """Test creating a JiraFieldContextOptionsResponse."""
        response_data = {
            "maxResults": 50,
            "startAt": 0,
            "total": 2,
            "isLast": True,
            "values": [
                {"id": "10001", "value": "Option 1", "disabled": False},
                {"id": "10002", "value": "Option 2", "disabled": False},
            ],
            "context": {
                "id": "10020",
                "name": "Test context",
                "description": "Test context description",
                "isGlobalContext": False,
                "isAnyIssueType": False,
            },
        }

        response = JiraFieldContextOptionsResponse(**response_data)

        assert response.max_results == 50
        assert response.start_at == 0
        assert response.total == 2
        assert response.is_last is True
        assert len(response.values) == 2
        assert response.context is not None
        assert response.context.name == "Test context"

    def test_jira_field_context_options_response_to_simplified_dict(self):
        """Test converting JiraFieldContextOptionsResponse to simplified dict."""
        response_data = {
            "maxResults": 50,
            "startAt": 0,
            "total": 1,
            "isLast": True,
            "values": [{"id": "10001", "value": "Context Option", "disabled": False}],
            "context": {
                "id": "10020",
                "name": "Test context",
                "description": "Test context description",
                "isGlobalContext": False,
                "isAnyIssueType": True,
            },
        }

        response = JiraFieldContextOptionsResponse(**response_data)
        simplified = response.to_simplified_dict()

        expected = {
            "pagination": {
                "start_at": 0,
                "max_results": 50,
                "total": 1,
                "is_last": True,
            },
            "options": [
                {
                    "id": "10001",
                    "value": "Context Option",
                    "disabled": False,
                    "config": None,
                }
            ],
            "context": {
                "id": "10020",
                "name": "Test context",
                "description": "Test context description",
                "is_global_context": False,
                "is_any_issue_type": True,
            },
        }

        assert simplified == expected


class TestFieldOptionMethods:
    """Test the field option methods in FieldsMixin."""

    @patch("mcp_atlassian.jira.fields.logger")
    def test_get_field_options_validation(self, mock_logger):
        """Test field options validation."""
        from mcp_atlassian.jira.fields import FieldsMixin

        # Create a mock mixin instance
        mixin = Mock(spec=FieldsMixin)
        mixin.config = Mock()
        mixin.config.is_cloud = True

        # Test empty field_id
        with pytest.raises(ValueError, match="Field ID is required"):
            FieldsMixin.get_customfield_options(mixin, "")

        # Test invalid field_id (not a custom field)
        with pytest.raises(ValueError, match="Field ID must be a custom field"):
            FieldsMixin.get_customfield_options(mixin, "summary")

    @patch("mcp_atlassian.jira.fields.logger")
    def test_get_field_contexts_validation(self, mock_logger):
        """Test field contexts validation."""
        from mcp_atlassian.jira.fields import FieldsMixin

        # Create a mock mixin instance
        mixin = Mock(spec=FieldsMixin)
        mixin.config = Mock()
        mixin.config.is_cloud = True

        # Test empty field_id
        with pytest.raises(ValueError, match="Field ID is required"):
            FieldsMixin.get_customfield_contexts(mixin, "")

        # Test invalid field_id (not a custom field)
        with pytest.raises(ValueError, match="Field ID must be a custom field"):
            FieldsMixin.get_customfield_contexts(mixin, "priority")

    @patch("mcp_atlassian.jira.fields.logger")
    def test_get_field_context_options_validation(self, mock_logger):
        """Test field context options validation."""
        from mcp_atlassian.jira.fields import FieldsMixin

        # Create a mock mixin instance
        mixin = Mock(spec=FieldsMixin)
        mixin.config = Mock()
        mixin.config.is_cloud = True

        # Test empty field_id
        with pytest.raises(ValueError, match="Field ID is required"):
            FieldsMixin.get_customfield_context_options(mixin, "", "10020")

        # Test empty context_id
        with pytest.raises(ValueError, match="Context ID is required"):
            FieldsMixin.get_customfield_context_options(mixin, "customfield_10001", "")

        # Test invalid field_id (not a custom field)
        with pytest.raises(ValueError, match="Field ID must be a custom field"):
            FieldsMixin.get_customfield_context_options(mixin, "status", "10020")

    def test_api_version_selection(self):
        """Test that the correct API version is selected based on deployment type."""
        from mcp_atlassian.jira.fields import FieldsMixin

        # Create mock mixin instances
        cloud_mixin = Mock(spec=FieldsMixin)
        cloud_mixin.config = Mock()
        cloud_mixin.config.is_cloud = True
        cloud_mixin.jira = Mock()

        server_mixin = Mock(spec=FieldsMixin)
        server_mixin.config = Mock()
        server_mixin.config.is_cloud = False
        server_mixin.jira = Mock()

        # Mock successful API responses
        mock_response = {
            "maxResults": 50,
            "startAt": 0,
            "total": 1,
            "isLast": True,
            "values": [{"id": "10001", "value": "Test Option", "disabled": False}],
        }

        cloud_mixin.jira.get.return_value = mock_response
        server_mixin.jira.get.return_value = mock_response

        # Test Cloud API version (3)
        FieldsMixin.get_customfield_options(cloud_mixin, "customfield_10001")
        cloud_mixin.jira.get.assert_called_with(
            path="/rest/api/3/field/customfield_10001/option",
            params={"startAt": 0, "maxResults": 10000},
        )

        # Test Server API version (2)
        FieldsMixin.get_customfield_options(server_mixin, "customfield_10001")
        server_mixin.jira.get.assert_called_with(
            path="/rest/api/2/customFields/10001/options",
            params={"startAt": 0, "maxResults": 10000},
        )


class TestCustomfieldPayloadHelpers:
    """Test helper functions used by customfield tools."""

    def test_to_values_only_payload(self):
        """Convert full options payload into values-only representation."""
        payload = {
            "pagination": {
                "start_at": 0,
                "max_results": 2,
                "total": 2,
                "is_last": True,
            },
            "options": [
                {"id": "1", "value": "Alpha", "disabled": False, "config": None},
                {"id": "2", "value": "Beta", "disabled": False, "config": None},
            ],
        }

        result = _to_values_only_payload(payload)
        assert result == {
            "pagination": {
                "start_at": 0,
                "max_results": 2,
                "total": 2,
                "is_last": True,
            },
            "values": ["Alpha", "Beta"],
        }

    def test_json_dumps_compact(self):
        """Serialize without pretty-print whitespace."""
        data = {"a": 1, "b": ["x", "y"]}
        assert _json_dumps_compact(data) == '{"a":1,"b":["x","y"]}'

    def test_apply_option_filters_contains_and_limit(self):
        """Filter by substring and cap number of returned options."""
        payload = {
            "pagination": {
                "start_at": 0,
                "max_results": 4,
                "total": 4,
                "is_last": True,
            },
            "options": [
                {"id": "1", "value": "Mobile iOS"},
                {"id": "2", "value": "Backend"},
                {"id": "3", "value": "Mobile Android"},
                {"id": "4", "value": "Web"},
            ],
        }

        result = _apply_option_filters(payload, contains="mobile", return_limit=1)

        assert result["filter"] == {
            "contains": "mobile",
            "matched": 2,
            "returned": 1,
        }
        assert result["options"] == [{"id": "1", "value": "Mobile iOS"}]
