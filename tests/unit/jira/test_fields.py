"""Tests for the Jira Fields mixin."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.fields import FieldsMixin


class TestFieldsMixin:
    """Tests for the FieldsMixin class."""

    @pytest.fixture
    def fields_mixin(self, jira_fetcher: JiraFetcher) -> FieldsMixin:
        """Create a FieldsMixin instance with mocked dependencies."""
        mixin = jira_fetcher
        mixin._field_ids_cache = None
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
            {
                "id": "customfield_10011",
                "name": "Epic Name",
                "schema": {
                    "type": "string",
                    "custom": "com.pyxis.greenhopper.jira:gh-epic-label",
                },
            },
            {
                "id": "customfield_10012",
                "name": "Story Points",
                "schema": {"type": "number"},
            },
        ]

    def test_get_field_ids_cache(self, fields_mixin: FieldsMixin, mock_fields):
        """Test get_fields uses cache when available."""
        # Set up the cache
        fields_mixin._field_ids_cache = mock_fields

        # Call the method
        result = fields_mixin.get_fields()

        # Verify cache was used
        assert result == mock_fields
        fields_mixin.jira.get_all_fields.assert_not_called()

    def test_get_fields_refresh(self, fields_mixin: FieldsMixin, mock_fields):
        """Test get_fields refreshes data when requested."""
        # Set up the cache
        fields_mixin._field_ids_cache = [{"id": "old_data", "name": "old data"}]

        # Mock the API response
        fields_mixin.jira.get_all_fields.return_value = mock_fields

        # Call the method with refresh=True
        result = fields_mixin.get_fields(refresh=True)

        # Verify API was called
        fields_mixin.jira.get_all_fields.assert_called_once()
        assert result == mock_fields
        # Verify cache was updated
        assert fields_mixin._field_ids_cache == mock_fields

    def test_get_fields_from_api(
        self, fields_mixin: FieldsMixin, mock_fields: list[dict[str, Any]]
    ):
        """Test get_fields fetches from API when no cache exists."""
        # Mock the API response
        fields_mixin.jira.get_all_fields.return_value = mock_fields

        # Call the method
        result = fields_mixin.get_fields()

        # Verify API was called
        fields_mixin.jira.get_all_fields.assert_called_once()
        assert result == mock_fields
        # Verify cache was created
        assert fields_mixin._field_ids_cache == mock_fields

    def test_get_fields_error(self, fields_mixin: FieldsMixin):
        """Test get_fields handles errors gracefully."""

        # Mock API error
        fields_mixin.jira.get_all_fields.side_effect = Exception("API error")

        # Call the method
        result = fields_mixin.get_fields()

        # Verify empty list is returned on error
        assert result == []

    def test_get_field_id_by_exact_match(self, fields_mixin: FieldsMixin, mock_fields):
        """Test get_field_id finds field by exact name match."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method
        result = fields_mixin.get_field_id("Summary")

        # Verify the result
        assert result == "summary"

    def test_get_field_id_case_insensitive(
        self, fields_mixin: FieldsMixin, mock_fields
    ):
        """Test get_field_id is case-insensitive."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method with different case
        result = fields_mixin.get_field_id("summary")

        # Verify the result
        assert result == "summary"

    def test_get_field_id_exact_match_case_insensitive(
        self, fields_mixin: FieldsMixin, mock_fields
    ):
        """Test get_field_id finds field by exact match (case-insensitive) using the map."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)
        # Ensure the map is generated based on the mock fields for this test
        fields_mixin._generate_field_map(force_regenerate=True)

        # Call the method with exact name (case-insensitive)
        result = fields_mixin.get_field_id("epic link")

        # Verify the result (should find Epic Link as first match)
        assert result == "customfield_10010"

    def test_get_field_id_not_found(self, fields_mixin: FieldsMixin, mock_fields):
        """Test get_field_id returns None when field not found."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method with non-existent field
        result = fields_mixin.get_field_id("NonExistent")

        # Verify the result
        assert result is None

    def test_get_field_id_error(self, fields_mixin: FieldsMixin):
        """Test get_field_id handles errors gracefully."""
        # Make get_fields raise an exception
        fields_mixin.get_fields = MagicMock(
            side_effect=Exception("Error getting fields")
        )

        # Call the method
        result = fields_mixin.get_field_id("Summary")

        # Verify None is returned on error
        assert result is None

    def test_get_field_by_id(self, fields_mixin: FieldsMixin, mock_fields):
        """Test get_field_by_id retrieves field definition correctly."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method
        result = fields_mixin.get_field_by_id("customfield_10012")

        # Verify the result
        assert result == mock_fields[6]  # The Story Points field
        assert result["name"] == "Story Points"

    def test_get_field_by_id_not_found(self, fields_mixin: FieldsMixin, mock_fields):
        """Test get_field_by_id returns None when field not found."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method with non-existent ID
        result = fields_mixin.get_field_by_id("customfield_99999")

        # Verify the result
        assert result is None

    def test_get_custom_fields(self, fields_mixin: FieldsMixin, mock_fields):
        """Test get_custom_fields returns only custom fields."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method
        result = fields_mixin.get_custom_fields()

        # Verify the result
        assert len(result) == 3
        assert all(field["id"].startswith("customfield_") for field in result)
        assert result[0]["name"] == "Epic Link"
        assert result[1]["name"] == "Epic Name"
        assert result[2]["name"] == "Story Points"

    def test_get_required_fields(self, fields_mixin: FieldsMixin):
        """Test get_required_fields retrieves required fields correctly."""
        # Mock the response for get_project_issue_types
        mock_issue_types = [
            {"id": "10001", "name": "Bug"},
            {"id": "10002", "name": "Task"},
        ]
        fields_mixin.get_project_issue_types = MagicMock(return_value=mock_issue_types)

        # Mock the response for issue_createmeta_fieldtypes based on API docs
        mock_field_meta = {
            "fields": [
                {
                    "required": True,
                    "schema": {"type": "string", "system": "summary"},
                    "name": "Summary",
                    "fieldId": "summary",
                    "autoCompleteUrl": "",
                    "hasDefaultValue": False,
                    "operations": ["set"],
                    "allowedValues": [],
                },
                {
                    "required": False,
                    "schema": {"type": "string", "system": "description"},
                    "name": "Description",
                    "fieldId": "description",
                },
                {
                    "required": True,
                    "schema": {"type": "string", "custom": "some.custom.type"},
                    "name": "Epic Link",
                    "fieldId": "customfield_10010",
                },
            ]
        }
        fields_mixin.jira.issue_createmeta_fieldtypes.return_value = mock_field_meta

        # Call the method
        result = fields_mixin.get_required_fields("Bug", "TEST")

        # Verify the result
        assert len(result) == 2
        assert "summary" in result
        assert result["summary"]["required"] is True
        assert "customfield_10010" in result
        assert result["customfield_10010"]["required"] is True
        assert "description" not in result
        # Verify the correct API was called
        fields_mixin.get_project_issue_types.assert_called_once_with("TEST")
        fields_mixin.jira.issue_createmeta_fieldtypes.assert_called_once_with(
            project="TEST", issue_type_id="10001"
        )

    def test_get_required_fields_not_found(self, fields_mixin: FieldsMixin):
        """Test get_required_fields handles project/issue type not found."""
        # Scenario 1: Issue type not found in project
        mock_issue_types = [{"id": "10002", "name": "Task"}]  # "Bug" is missing
        fields_mixin.get_project_issue_types = MagicMock(return_value=mock_issue_types)
        fields_mixin.jira.issue_createmeta_fieldtypes = MagicMock()

        # Call the method
        result = fields_mixin.get_required_fields("Bug", "TEST")
        # Verify issue type lookup was attempted, but field meta was not called
        fields_mixin.get_project_issue_types.assert_called_once_with("TEST")
        fields_mixin.jira.issue_createmeta_fieldtypes.assert_not_called()

        # Verify the result
        assert result == {}

    def test_get_required_fields_error(self, fields_mixin: FieldsMixin):
        """Test get_required_fields handles errors gracefully."""
        # Mock the response for get_project_issue_types
        mock_issue_types = [
            {"id": "10001", "name": "Bug"},
        ]
        fields_mixin.get_project_issue_types = MagicMock(return_value=mock_issue_types)
        # Mock issue_createmeta_fieldtypes to raise an error
        fields_mixin.jira.issue_createmeta_fieldtypes.side_effect = Exception(
            "API error"
        )

        # Call the method
        result = fields_mixin.get_required_fields("Bug", "TEST")

        # Verify the result
        assert result == {}
        # Verify the correct API was called (which then raised the error)
        fields_mixin.jira.issue_createmeta_fieldtypes.assert_called_once_with(
            project="TEST", issue_type_id="10001"
        )

    def test_get_jira_field_ids_cached(self, fields_mixin: FieldsMixin):
        """Test get_field_ids_to_epic returns cached field IDs."""
        # Set up the cache
        fields_mixin._field_ids_cache = [
            {"id": "summary", "name": "Summary"},
            {"id": "description", "name": "Description"},
        ]

        # Call the method
        result = fields_mixin.get_field_ids_to_epic()

        # Verify the result
        assert result == {
            "Summary": "summary",
            "Description": "description",
        }

    def test_get_jira_field_ids_from_fields(
        self, fields_mixin: FieldsMixin, mock_fields: list[dict]
    ):
        """Test get_field_ids_to_epic extracts field IDs from field definitions."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)
        # Ensure field map is generated
        fields_mixin._generate_field_map(force_regenerate=True)

        # Call the method
        result = fields_mixin.get_field_ids_to_epic()

        # Verify that epic-specific fields are properly identified
        assert "epic_link" in result
        assert "Epic Link" in result
        assert result["epic_link"] == "customfield_10010"
        assert "epic_name" in result
        assert "Epic Name" in result
        assert result["epic_name"] == "customfield_10011"

    def test_get_jira_field_ids_error(self, fields_mixin: FieldsMixin):
        """Test get_field_ids_to_epic handles errors gracefully."""
        # Ensure no cache exists
        fields_mixin._field_ids_cache = None

        # Make get_fields raise an exception
        fields_mixin.get_fields = MagicMock(
            side_effect=Exception("Error getting fields")
        )

        # Call the method
        result = fields_mixin.get_field_ids_to_epic()

        # Verify the result
        assert result == {}

    def test_is_custom_field(self, fields_mixin: FieldsMixin):
        """Test is_custom_field correctly identifies custom fields."""
        # Test with custom field
        assert fields_mixin.is_custom_field("customfield_10010") is True

        # Test with standard field
        assert fields_mixin.is_custom_field("summary") is False

    def test_format_field_value_user_field(
        self, fields_mixin: FieldsMixin, mock_fields
    ):
        """Test format_field_value formats user fields correctly."""
        # Set up the mocks
        fields_mixin.get_field_by_id = MagicMock(
            return_value=mock_fields[3]
        )  # The Assignee field
        fields_mixin._get_account_id = MagicMock(return_value="account123")

        # Call the method with a user field and string value
        result = fields_mixin.format_field_value("assignee", "johndoe")

        # Verify the result
        assert result == {"accountId": "account123"}
        fields_mixin._get_account_id.assert_called_once_with("johndoe")

    # FIXME: The test covers impossible case.
    #
    # This test is failing because it assumes that the `_get_account_id`
    # method is unavailable. As default, `format_field_value` will return
    # `{"name": value}` for server/DC.
    #
    # However, in any case `JiraFetcher` always inherits from `UsersMixin`
    # and will therefore have the `_get_account_id` method available.
    #
    # That is to say, the `format_field_value` method will never return in
    # format `{"name": value}`.
    #
    # Further fixes are needed in the `FieldsMixin` class to support the case
    # for server/DC.
    #
    # See also:
    # https://github.com/sooperset/mcp-atlassian/blob/651c271e8aa76b469e9c67535669d93267ad5da6/src/mcp_atlassian/jira/fields.py#L279-L297

    # def test_format_field_value_user_field_no_account_id(
    #     self, fields_mixin: FieldsMixin, mock_fields
    # ):
    #     """Test format_field_value handles user fields without _get_account_id."""
    #     # Set up the mocks
    #     fields_mixin.get_field_by_id = MagicMock(
    #         return_value=mock_fields[3]
    #     )  # The Assignee field

    #     # Call the method with a user field and string value
    #     result = fields_mixin.format_field_value("assignee", "johndoe")

    #     # Verify the result - should use name for server/DC
    #     assert result == {"name": "johndoe"}

    def test_format_field_value_array_field(self, fields_mixin: FieldsMixin):
        """Test format_field_value formats array fields correctly."""
        # Set up the mocks
        mock_array_field = {
            "id": "labels",
            "name": "Labels",
            "schema": {"type": "array"},
        }
        fields_mixin.get_field_by_id = MagicMock(return_value=mock_array_field)

        # Test with single value (should convert to list)
        result = fields_mixin.format_field_value("labels", "bug")
        assert result == ["bug"]

        # Test with list value (should keep as list)
        result = fields_mixin.format_field_value("labels", ["bug", "feature"])
        assert result == ["bug", "feature"]

    def test_format_field_value_option_field(self, fields_mixin: FieldsMixin):
        """Test format_field_value formats option fields correctly."""
        # Set up the mocks
        mock_option_field = {
            "id": "priority",
            "name": "Priority",
            "schema": {"type": "option"},
        }
        fields_mixin.get_field_by_id = MagicMock(return_value=mock_option_field)

        # Test with string value
        result = fields_mixin.format_field_value("priority", "High")
        assert result == {"value": "High"}

        # Test with already formatted value
        already_formatted = {"value": "Medium"}
        result = fields_mixin.format_field_value("priority", already_formatted)
        assert result == already_formatted

    def test_format_field_value_unknown_field(self, fields_mixin: FieldsMixin):
        """Test format_field_value returns value as-is for unknown fields."""
        # Set up the mocks
        fields_mixin.get_field_by_id = MagicMock(return_value=None)

        # Call the method with unknown field
        test_value = "test value"
        result = fields_mixin.format_field_value("unknown", test_value)

        # Verify the value is returned as-is
        assert result == test_value

    def test_search_fields_empty_keyword(self, fields_mixin: FieldsMixin, mock_fields):
        """Test search_fields returns first N fields when keyword is empty."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call with empty keyword and limit=3
        result = fields_mixin.search_fields("", limit=3)

        # Verify first 3 fields are returned
        assert len(result) == 3
        assert result == mock_fields[:3]

    def test_search_fields_exact_match(self, fields_mixin: FieldsMixin, mock_fields):
        """Test search_fields finds exact matches with high relevance."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Search for "Story Points"
        result = fields_mixin.search_fields("Story Points")

        # Verify Story Points field is first result
        assert len(result) > 0
        assert result[0]["name"] == "Story Points"
        assert result[0]["id"] == "customfield_10012"

    def test_search_fields_partial_match(self, fields_mixin: FieldsMixin, mock_fields):
        """Test search_fields finds partial matches."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Search for "Epic"
        result = fields_mixin.search_fields("Epic")

        # Verify Epic-related fields are in results
        epic_fields = [field["name"] for field in result[:2]]  # Top 2 results
        assert "Epic Link" in epic_fields
        assert "Epic Name" in epic_fields

    def test_search_fields_case_insensitive(
        self, fields_mixin: FieldsMixin, mock_fields
    ):
        """Test search_fields is case insensitive."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Search with different cases
        result_lower = fields_mixin.search_fields("story points")
        result_upper = fields_mixin.search_fields("STORY POINTS")
        result_mixed = fields_mixin.search_fields("Story Points")

        # Verify all searches find the same field
        assert len(result_lower) > 0
        assert len(result_upper) > 0
        assert len(result_mixed) > 0
        assert result_lower[0]["id"] == result_upper[0]["id"] == result_mixed[0]["id"]
        assert result_lower[0]["name"] == "Story Points"

    def test_search_fields_with_limit(self, fields_mixin: FieldsMixin, mock_fields):
        """Test search_fields respects the limit parameter."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Search with limit=2
        result = fields_mixin.search_fields("field", limit=2)

        # Verify only 2 results are returned
        assert len(result) == 2

    def test_search_fields_error(self, fields_mixin: FieldsMixin):
        """Test search_fields handles errors gracefully."""
        # Make get_fields raise an exception
        fields_mixin.get_fields = MagicMock(
            side_effect=Exception("Error getting fields")
        )

        # Call the method
        result = fields_mixin.search_fields("test")

        # Verify empty list is returned on error
        assert result == []
