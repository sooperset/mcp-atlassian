"""Tests for the get_project_fields method in FieldsMixin."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira.fields import FieldsMixin


class TestGetProjectFields:
    """Tests for the get_project_fields method."""

    @pytest.fixture
    def fields_mixin(self, jira_client):
        """Create a FieldsMixin instance with mocked dependencies."""
        mixin = FieldsMixin(config=jira_client.config)
        mixin.jira = jira_client.jira
        return mixin

    @pytest.fixture
    def mock_fields(self):
        """Return mock field data."""
        return [
            {"id": "summary", "name": "Summary", "schema": {"type": "string"}},
            {"id": "description", "name": "Description", "schema": {"type": "string"}},
            {"id": "status", "name": "Status", "schema": {"type": "status"}},
            {"id": "assignee", "name": "Assignee", "schema": {"type": "user"}},
            {
                "id": "customfield_10010",
                "name": "Epic Link",
                "schema": {
                    "type": "string",
                    "custom": "com.pyxis.greenhopper.jira:gh-epic-link",
                },
            },
        ]

    def test_get_project_fields_success(self, fields_mixin, mock_fields):
        """Test get_project_fields successfully retrieves and processes fields."""
        # Mock the get_fields method
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)
        
        # Mock the get_issue_type_id method
        fields_mixin.get_issue_type_id = MagicMock(return_value="10001")
        
        # Mock the issue_createmeta_fieldtypes response
        mock_meta = {
            "fields": {
                "summary": {"required": True, "name": "Summary"},
                "description": {"required": False, "name": "Description"},
                "customfield_10010": {"required": True, "name": "Epic Link", "allowedValues": ["PROJ-1", "PROJ-2"]},
            }
        }
        fields_mixin.jira.issue_createmeta_fieldtypes = MagicMock(return_value=mock_meta)
        
        # Call the method
        result = fields_mixin.get_project_fields("PROJ", "Story")
        
        # Verify the result
        assert len(result) == 3
        
        # Check that fields were correctly processed
        summary_field = next(field for field in result if field["id"] == "summary")
        assert summary_field["required"] is True
        assert summary_field["project_meta"]["required"] is True
        
        # Check custom field
        epic_field = next(field for field in result if field["id"] == "customfield_10010")
        assert epic_field["required"] is True
        assert epic_field["project_meta"]["allowed_values"] == ["PROJ-1", "PROJ-2"]

    def test_get_project_fields_no_issue_type(self, fields_mixin):
        """Test get_project_fields handles missing issue type."""
        # Mock the get_issue_type_id method to return empty string
        fields_mixin.get_issue_type_id = MagicMock(return_value="")
        
        # Call the method
        result = fields_mixin.get_project_fields("PROJ", "NonExistentType")
        
        # Verify empty list is returned
        assert result == []
        
        # Verify API was not called
        fields_mixin.jira.issue_createmeta_fieldtypes.assert_not_called()

    def test_get_project_fields_api_error(self, fields_mixin, mock_fields):
        """Test get_project_fields handles API errors gracefully."""
        # Mock the get_fields method
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)
        
        # Mock the get_issue_type_id method
        fields_mixin.get_issue_type_id = MagicMock(return_value="10001")
        
        # Mock API error
        fields_mixin.jira.issue_createmeta_fieldtypes = MagicMock(
            side_effect=Exception("API error")
        )
        
        # Call the method
        result = fields_mixin.get_project_fields("PROJ", "Story")
        
        # Verify empty list is returned on error
        assert result == []

    def test_get_project_fields_no_fields_in_response(self, fields_mixin, mock_fields):
        """Test get_project_fields handles response with no fields."""
        # Mock the get_fields method
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)
        
        # Mock the get_issue_type_id method
        fields_mixin.get_issue_type_id = MagicMock(return_value="10001")
        
        # Mock empty response
        fields_mixin.jira.issue_createmeta_fieldtypes = MagicMock(return_value={})
        
        # Call the method
        result = fields_mixin.get_project_fields("PROJ", "Story")
        
        # Verify empty list is returned
        assert result == []
        
    def test_get_project_fields_with_list_fields(self, fields_mixin, mock_fields):
        """Test get_project_fields handles fields as a list instead of a dictionary."""
        # Mock the get_fields method
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)
        
        # Mock the get_issue_type_id method
        fields_mixin.get_issue_type_id = MagicMock(return_value="10001")
        
        # Mock the issue_createmeta_fieldtypes response with fields as a list
        mock_meta = {
            "startAt": 0,
            "maxResults": 50,
            "total": 3,
            "fields": [
                {
                    "required": True,
                    "schema": {"type": "string"},
                    "name": "Summary",
                    "key": "summary",
                    "fieldId": "summary"
                },
                {
                    "required": False,
                    "schema": {"type": "string"},
                    "name": "Description",
                    "key": "description",
                    "fieldId": "description"
                },
                {
                    "required": True,
                    "schema": {"type": "string", "custom": "com.pyxis.greenhopper.jira:gh-epic-link"},
                    "name": "Epic Link",
                    "key": "customfield_10010",
                    "fieldId": "customfield_10010",
                    "allowedValues": ["PROJ-1", "PROJ-2"]
                }
            ]
        }
        fields_mixin.jira.issue_createmeta_fieldtypes = MagicMock(return_value=mock_meta)
        
        # Call the method
        result = fields_mixin.get_project_fields("PROJ", "Story")
        
        # Verify the result
        assert len(result) == 3
        
        # Check that fields were correctly processed
        summary_field = next(field for field in result if field["id"] == "summary")
        assert summary_field["required"] is True
        assert summary_field["project_meta"]["required"] is True
        
        # Check custom field
        epic_field = next(field for field in result if field["id"] == "customfield_10010")
        assert epic_field["required"] is True
        assert epic_field["project_meta"]["allowed_values"] == ["PROJ-1", "PROJ-2"]