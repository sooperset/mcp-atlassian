"""Tests for the Jira Fields mixin."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira.fields import FieldsMixin


class TestFieldsMixin:
    """Tests for the FieldsMixin class."""

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

    def test_get_fields_cache(self, fields_mixin, mock_fields):
        """Test get_fields uses cache when available."""
        # Set up the cache
        fields_mixin._fields_cache = mock_fields

        # Call the method
        result = fields_mixin.get_fields()

        # Verify cache was used
        assert result == mock_fields
        fields_mixin.jira.get_all_fields.assert_not_called()

    def test_get_fields_refresh(self, fields_mixin, mock_fields):
        """Test get_fields refreshes data when requested."""
        # Set up the cache
        fields_mixin._fields_cache = ["old data"]

        # Mock the API response
        fields_mixin.jira.get_all_fields.return_value = mock_fields

        # Call the method with refresh=True
        result = fields_mixin.get_fields(refresh=True)

        # Verify API was called
        fields_mixin.jira.get_all_fields.assert_called_once()
        assert result == mock_fields
        # Verify cache was updated
        assert fields_mixin._fields_cache == mock_fields

    def test_get_fields_from_api(self, fields_mixin, mock_fields):
        """Test get_fields fetches from API when no cache exists."""
        # Ensure no cache exists
        if hasattr(fields_mixin, "_fields_cache"):
            delattr(fields_mixin, "_fields_cache")

        # Mock the API response
        fields_mixin.jira.get_all_fields.return_value = mock_fields

        # Call the method
        result = fields_mixin.get_fields()

        # Verify API was called
        fields_mixin.jira.get_all_fields.assert_called_once()
        assert result == mock_fields
        # Verify cache was created
        assert fields_mixin._fields_cache == mock_fields

    def test_get_fields_error(self, fields_mixin):
        """Test get_fields handles errors gracefully."""
        # Ensure no cache exists
        if hasattr(fields_mixin, "_fields_cache"):
            delattr(fields_mixin, "_fields_cache")

        # Mock API error
        fields_mixin.jira.get_all_fields.side_effect = Exception("API error")

        # Call the method
        result = fields_mixin.get_fields()

        # Verify empty list is returned on error
        assert result == []

    def test_get_field_id_by_exact_match(self, fields_mixin, mock_fields):
        """Test get_field_id finds field by exact name match."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method
        result = fields_mixin.get_field_id("Summary")

        # Verify the result
        assert result == "summary"

    def test_get_field_id_case_insensitive(self, fields_mixin, mock_fields):
        """Test get_field_id is case-insensitive."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method with different case
        result = fields_mixin.get_field_id("summary")

        # Verify the result
        assert result == "summary"

    def test_get_field_id_partial_match(self, fields_mixin, mock_fields):
        """Test get_field_id finds field by partial match."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method with partial name
        result = fields_mixin.get_field_id("Epic")

        # Verify the result (should find Epic Link as first match)
        assert result == "customfield_10010"

    def test_get_field_id_not_found(self, fields_mixin, mock_fields):
        """Test get_field_id returns None when field not found."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method with non-existent field
        result = fields_mixin.get_field_id("NonExistent")

        # Verify the result
        assert result is None

    def test_get_field_id_error(self, fields_mixin):
        """Test get_field_id handles errors gracefully."""
        # Make get_fields raise an exception
        fields_mixin.get_fields = MagicMock(
            side_effect=Exception("Error getting fields")
        )

        # Call the method
        result = fields_mixin.get_field_id("Summary")

        # Verify None is returned on error
        assert result is None

    def test_get_field_by_id(self, fields_mixin, mock_fields):
        """Test get_field_by_id retrieves field definition correctly."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method
        result = fields_mixin.get_field_by_id("customfield_10012")

        # Verify the result
        assert result == mock_fields[6]  # The Story Points field
        assert result["name"] == "Story Points"

    def test_get_field_by_id_not_found(self, fields_mixin, mock_fields):
        """Test get_field_by_id returns None when field not found."""
        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method with non-existent ID
        result = fields_mixin.get_field_by_id("customfield_99999")

        # Verify the result
        assert result is None

    def test_get_custom_fields(self, fields_mixin, mock_fields):
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

    def test_get_required_fields(self, fields_mixin):
        """Test get_required_fields retrieves required fields correctly."""
        # Mock the createmeta response
        mock_meta = {
            "projects": [
                {
                    "key": "TEST",
                    "issuetypes": [
                        {
                            "name": "Bug",
                            "fields": {
                                "summary": {"required": True, "name": "Summary"},
                                "description": {
                                    "required": False,
                                    "name": "Description",
                                },
                                "customfield_10010": {
                                    "required": True,
                                    "name": "Epic Link",
                                },
                            },
                        }
                    ],
                }
            ]
        }
        fields_mixin.jira.createmeta.return_value = mock_meta

        # Call the method
        result = fields_mixin.get_required_fields("Bug", "TEST")

        # Verify the result
        assert len(result) == 2
        assert "summary" in result
        assert "customfield_10010" in result
        assert "description" not in result

    def test_get_required_fields_not_found(self, fields_mixin):
        """Test get_required_fields handles project/issue type not found."""
        # Mock empty createmeta response
        fields_mixin.jira.createmeta.return_value = {"projects": []}

        # Call the method
        result = fields_mixin.get_required_fields("Bug", "TEST")

        # Verify the result
        assert result == {}

    def test_get_required_fields_error(self, fields_mixin):
        """Test get_required_fields handles errors gracefully."""
        # Mock API error
        fields_mixin.jira.createmeta.side_effect = Exception("API error")

        # Call the method
        result = fields_mixin.get_required_fields("Bug", "TEST")

        # Verify the result
        assert result == {}

    def test_get_jira_field_ids_cached(self, fields_mixin):
        """Test get_jira_field_ids returns cached field IDs."""
        # Set up the cache
        fields_mixin._field_ids_cache = {
            "Summary": "summary",
            "Description": "description",
        }

        # Call the method
        result = fields_mixin.get_jira_field_ids()

        # Verify the result
        assert result == fields_mixin._field_ids_cache

    def test_get_jira_field_ids_from_fields(self, fields_mixin, mock_fields):
        """Test get_jira_field_ids extracts field IDs from field definitions."""
        # Ensure no cache exists
        if hasattr(fields_mixin, "_field_ids_cache"):
            delattr(fields_mixin, "_field_ids_cache")

        # Set up the fields
        fields_mixin.get_fields = MagicMock(return_value=mock_fields)

        # Call the method
        result = fields_mixin.get_jira_field_ids()

        # Verify the result
        assert len(result) == 7
        assert result["Summary"] == "summary"
        assert result["Epic Name"] == "customfield_10011"
        assert result["Story Points"] == "customfield_10012"

    def test_get_jira_field_ids_error(self, fields_mixin):
        """Test get_jira_field_ids handles errors gracefully."""
        # Ensure no cache exists
        if hasattr(fields_mixin, "_field_ids_cache"):
            delattr(fields_mixin, "_field_ids_cache")

        # Make get_fields raise an exception
        fields_mixin.get_fields = MagicMock(
            side_effect=Exception("Error getting fields")
        )

        # Call the method
        result = fields_mixin.get_jira_field_ids()

        # Verify the result
        assert result == {}

    def test_is_custom_field(self, fields_mixin):
        """Test is_custom_field correctly identifies custom fields."""
        # Test with custom field
        assert fields_mixin.is_custom_field("customfield_10010") is True

        # Test with standard field
        assert fields_mixin.is_custom_field("summary") is False

    def test_format_field_value_user_field(self, fields_mixin, mock_fields):
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

    def test_format_field_value_user_field_no_account_id(
        self, fields_mixin, mock_fields
    ):
        """Test format_field_value handles user fields without _get_account_id."""
        # Set up the mocks
        fields_mixin.get_field_by_id = MagicMock(
            return_value=mock_fields[3]
        )  # The Assignee field
        # No _get_account_id method available

        # Call the method with a user field and string value
        result = fields_mixin.format_field_value("assignee", "johndoe")

        # Verify the result - should use name for server/DC
        assert result == {"name": "johndoe"}

    def test_format_field_value_array_field(self, fields_mixin):
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

    def test_format_field_value_option_field(self, fields_mixin):
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

    def test_format_field_value_unknown_field(self, fields_mixin):
        """Test format_field_value returns value as-is for unknown fields."""
        # Set up the mocks
        fields_mixin.get_field_by_id = MagicMock(return_value=None)

        # Call the method with unknown field
        test_value = "test value"
        result = fields_mixin.format_field_value("unknown", test_value)

        # Verify the value is returned as-is
        assert result == test_value
