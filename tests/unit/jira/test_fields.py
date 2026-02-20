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

    def test_format_field_value_user_field_cloud(
        self, fields_mixin: FieldsMixin, mock_fields
    ):
        """Test format_field_value formats user fields correctly for Cloud."""
        # Set up the mocks
        fields_mixin.get_field_by_id = MagicMock(
            return_value=mock_fields[3]
        )  # The Assignee field
        fields_mixin._get_account_id = MagicMock(return_value="account123")
        fields_mixin.config = MagicMock()
        fields_mixin.config.is_cloud = True

        # Call the method with a user field and string value
        result = fields_mixin.format_field_value("assignee", "johndoe")

        # Verify the result — Cloud uses accountId
        assert result == {"accountId": "account123"}
        fields_mixin._get_account_id.assert_called_once_with("johndoe")

    def test_format_field_value_user_field_server(
        self, fields_mixin: FieldsMixin, mock_fields
    ):
        """Test format_field_value formats user fields correctly for Server/DC."""
        # Set up the mocks
        fields_mixin.get_field_by_id = MagicMock(
            return_value=mock_fields[3]
        )  # The Assignee field
        fields_mixin._get_account_id = MagicMock(return_value="jdoe")
        fields_mixin.config = MagicMock()
        fields_mixin.config.is_cloud = False

        # Call the method with a user field and string value
        result = fields_mixin.format_field_value("assignee", "johndoe")

        # Verify the result — Server/DC uses name
        assert result == {"name": "jdoe"}
        fields_mixin._get_account_id.assert_called_once_with("johndoe")

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

    def test_format_field_value_priority_field(self, fields_mixin: FieldsMixin):
        """Test format_field_value formats priority correctly with {name: ...}."""
        mock_priority_field = {
            "id": "priority",
            "name": "Priority",
            "schema": {"type": "priority"},
        }
        fields_mixin.get_field_by_id = MagicMock(return_value=mock_priority_field)

        result = fields_mixin.format_field_value("priority", "High")
        assert result == {"name": "High"}

        already_formatted = {"name": "Medium"}
        result = fields_mixin.format_field_value("priority", already_formatted)
        assert result == already_formatted

    def test_format_field_value_option_field(self, fields_mixin: FieldsMixin):
        """Test format_field_value formats option fields with {value: ...}."""
        mock_option_field = {
            "id": "customfield_10024",
            "name": "Severity",
            "schema": {"type": "option", "custom": "radiobuttons"},
        }
        fields_mixin.get_field_by_id = MagicMock(return_value=mock_option_field)

        result = fields_mixin.format_field_value("customfield_10024", "Critical")
        assert result == {"value": "Critical"}

        already_formatted = {"value": "Medium"}
        result = fields_mixin.format_field_value("customfield_10024", already_formatted)
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


class TestFormatFieldValueForWrite:
    """Tests for _format_field_value_for_write on FieldsMixin."""

    @pytest.fixture
    def mixin(self, jira_fetcher: JiraFetcher) -> FieldsMixin:
        """Create a FieldsMixin instance with mocked dependencies."""
        fetcher = jira_fetcher
        fetcher._get_account_id = MagicMock(return_value="resolved-id")
        fetcher.config = MagicMock()
        fetcher.config.is_cloud = True
        return fetcher

    # -- Priority --------------------------------------------------------

    @pytest.mark.parametrize(
        "test_id, field_id, value, field_definition, expected",
        [
            (
                "priority_string",
                "priority",
                "High",
                {"name": "Priority", "schema": {"type": "priority"}},
                {"name": "High"},
            ),
            (
                "priority_dict",
                "priority",
                {"name": "High"},
                {"name": "Priority", "schema": {"type": "priority"}},
                {"name": "High"},
            ),
        ],
    )
    def test_priority(
        self, mixin, test_id, field_id, value, field_definition, expected
    ):
        result = mixin._format_field_value_for_write(field_id, value, field_definition)
        assert result == expected

    # -- Labels ----------------------------------------------------------

    @pytest.mark.parametrize(
        "test_id, field_id, value, field_definition, expected",
        [
            (
                "labels_list",
                "labels",
                ["a", "b"],
                {"name": "Labels", "schema": {"type": "array", "items": "string"}},
                ["a", "b"],
            ),
            (
                "labels_csv",
                "labels",
                "a,b",
                {"name": "Labels", "schema": {"type": "array", "items": "string"}},
                ["a", "b"],
            ),
        ],
    )
    def test_labels(self, mixin, test_id, field_id, value, field_definition, expected):
        result = mixin._format_field_value_for_write(field_id, value, field_definition)
        assert result == expected

    # -- Components / fixVersions ----------------------------------------

    @pytest.mark.parametrize(
        "test_id, field_id, value, field_definition, expected",
        [
            (
                "components_strings",
                "components",
                ["UI", "API"],
                {
                    "name": "Component/s",
                    "schema": {"type": "array", "items": "component"},
                },
                [{"name": "UI"}, {"name": "API"}],
            ),
            (
                "components_dicts",
                "components",
                [{"name": "UI"}],
                {
                    "name": "Component/s",
                    "schema": {"type": "array", "items": "component"},
                },
                [{"name": "UI"}],
            ),
            (
                "fixversions",
                "fixVersions",
                ["1.0"],
                {
                    "name": "Fix Version/s",
                    "schema": {"type": "array", "items": "version"},
                },
                [{"name": "1.0"}],
            ),
        ],
    )
    def test_name_wrapped_arrays(
        self, mixin, test_id, field_id, value, field_definition, expected
    ):
        result = mixin._format_field_value_for_write(field_id, value, field_definition)
        assert result == expected

    # -- Reporter (Cloud vs Server) --------------------------------------

    def test_reporter_cloud(self, mixin):
        mixin.config.is_cloud = True
        mixin._get_account_id = MagicMock(return_value="cloud-acc-id")
        result = mixin._format_field_value_for_write(
            "reporter",
            "user@ex.com",
            {"name": "Reporter", "schema": {"type": "user"}},
        )
        assert result == {"accountId": "cloud-acc-id"}
        mixin._get_account_id.assert_called_once_with("user@ex.com")

    def test_reporter_server(self, mixin):
        mixin.config.is_cloud = False
        mixin._get_account_id = MagicMock(return_value="jdoe")
        result = mixin._format_field_value_for_write(
            "reporter",
            "jdoe",
            {"name": "Reporter", "schema": {"type": "user"}},
        )
        assert result == {"name": "jdoe"}
        mixin._get_account_id.assert_called_once_with("jdoe")

    # -- Duedate ---------------------------------------------------------

    def test_duedate_valid(self, mixin):
        result = mixin._format_field_value_for_write("duedate", "2026-03-01", None)
        assert result == "2026-03-01"

    def test_duedate_invalid(self, mixin):
        result = mixin._format_field_value_for_write("duedate", 12345, None)
        assert result is None

    # -- Cascading select ------------------------------------------------

    @pytest.mark.parametrize(
        "test_id, value, expected",
        [
            (
                "cascading_tuple",
                ("NA", "US"),
                {"value": "NA", "child": {"value": "US"}},
            ),
            (
                "cascading_dict",
                {"value": "NA", "child": {"value": "US"}},
                {"value": "NA", "child": {"value": "US"}},
            ),
            (
                "cascading_string",
                "NA",
                {"value": "NA"},
            ),
        ],
    )
    def test_cascading_select(self, mixin, test_id, value, expected):
        field_def = {
            "name": "Region",
            "schema": {"type": "option-with-child", "custom": "cascadingselect"},
        }
        result = mixin._format_field_value_for_write(
            "customfield_10020", value, field_def
        )
        assert result == expected

    # -- Multi-select ----------------------------------------------------

    @pytest.mark.parametrize(
        "test_id, value, expected",
        [
            (
                "multiselect_strings",
                ["opt1", "opt2"],
                [{"value": "opt1"}, {"value": "opt2"}],
            ),
            (
                "multiselect_dicts",
                [{"value": "opt1"}],
                [{"value": "opt1"}],
            ),
            (
                "multiselect_csv",
                "opt1,opt2",
                [{"value": "opt1"}, {"value": "opt2"}],
            ),
        ],
    )
    def test_multiselect(self, mixin, test_id, value, expected):
        field_def = {
            "name": "Categories",
            "schema": {"type": "array", "items": "option", "custom": "multiselect"},
        }
        result = mixin._format_field_value_for_write(
            "customfield_10021", value, field_def
        )
        assert result == expected

    # -- Custom user field -----------------------------------------------

    def test_custom_user_cloud(self, mixin):
        mixin.config.is_cloud = True
        mixin._get_account_id = MagicMock(return_value="cloud-acc-id")
        field_def = {
            "name": "Reviewer",
            "schema": {"type": "user", "custom": "userpicker"},
        }
        result = mixin._format_field_value_for_write(
            "customfield_10022", "user@ex.com", field_def
        )
        assert result == {"accountId": "cloud-acc-id"}

    def test_custom_user_server(self, mixin):
        mixin.config.is_cloud = False
        mixin._get_account_id = MagicMock(return_value="jdoe")
        field_def = {
            "name": "Reviewer",
            "schema": {"type": "user", "custom": "userpicker"},
        }
        result = mixin._format_field_value_for_write(
            "customfield_10022", "jdoe", field_def
        )
        assert result == {"name": "jdoe"}

    def test_custom_user_unresolvable(self, mixin):
        """Unresolvable custom user field returns None instead of raising."""
        mixin._get_account_id = MagicMock(side_effect=ValueError("User not found"))
        field_def = {
            "name": "Reviewer",
            "schema": {"type": "user", "custom": "userpicker"},
        }
        result = mixin._format_field_value_for_write(
            "customfield_10022", "nobody@ex.com", field_def
        )
        assert result is None

    # -- Custom date field -----------------------------------------------

    def test_custom_date_valid(self, mixin):
        field_def = {"name": "Target Date", "schema": {"type": "date"}}
        result = mixin._format_field_value_for_write(
            "customfield_10023", "2026-03-01", field_def
        )
        assert result == "2026-03-01"

    def test_custom_date_invalid(self, mixin):
        field_def = {"name": "Target Date", "schema": {"type": "date"}}
        result = mixin._format_field_value_for_write(
            "customfield_10023", 12345, field_def
        )
        assert result is None

    # -- Generic option (radio/select) -----------------------------------

    @pytest.mark.parametrize(
        "test_id, value, expected",
        [
            ("option_string", "Critical", {"value": "Critical"}),
            ("option_dict", {"value": "Critical"}, {"value": "Critical"}),
        ],
    )
    def test_option_field(self, mixin, test_id, value, expected):
        field_def = {
            "name": "Severity",
            "schema": {"type": "option", "custom": "radiobuttons"},
        }
        result = mixin._format_field_value_for_write(
            "customfield_10024", value, field_def
        )
        assert result == expected

    # -- Unknown field passthrough ---------------------------------------

    def test_unknown_passthrough(self, mixin):
        result = mixin._format_field_value_for_write(
            "customfield_99999", "anything", None
        )
        assert result == "anything"


class TestDatetimeTimezoneFormat:
    """Test datetime field formatting produces Jira-compatible tz offsets."""

    @pytest.fixture
    def fields_mixin(self, jira_fetcher: "JiraFetcher") -> FieldsMixin:
        """Create a FieldsMixin instance with mocked dependencies."""
        mixin = jira_fetcher
        mixin._field_ids_cache = None
        return mixin

    @pytest.mark.parametrize(
        "input_value,expected",
        [
            pytest.param(
                "2026-01-21T15:00:00.000+0000",
                "2026-01-21T15:00:00.000+0000",
                id="already-basic-format",
            ),
            pytest.param(
                "2026-01-21T15:00:00+00:00",
                "2026-01-21T15:00:00.000+0000",
                id="extended-to-basic",
            ),
            pytest.param(
                "2026-01-21T15:00:00.000+0530",
                "2026-01-21T15:00:00.000+0530",
                id="non-utc-preserved",
            ),
            pytest.param(
                "2026-01-21T15:00:00-0800",
                "2026-01-21T15:00:00.000-0800",
                id="negative-offset-basic",
            ),
            pytest.param(
                "2026-01-21T15:00:00",
                "2026-01-21T15:00:00.000",
                id="naive-no-tz",
            ),
            pytest.param(
                "2026-01-21",
                "2026-01-21T00:00:00.000",
                id="date-only-to-midnight",
            ),
            pytest.param(
                "invalid-date",
                "invalid-date",
                id="unparseable-passthrough",
            ),
            pytest.param(
                "",
                "",
                id="empty-string",
            ),
        ],
    )
    def test_datetime_timezone_format(
        self, fields_mixin: FieldsMixin, input_value: str, expected: str
    ):
        """Datetime fields must use ±HHMM (basic) format, not ±HH:MM."""
        mock_datetime_field = {
            "id": "customfield_10050",
            "name": "Due DateTime",
            "schema": {"type": "datetime"},
        }
        fields_mixin.get_field_by_id = MagicMock(return_value=mock_datetime_field)

        result = fields_mixin.format_field_value("customfield_10050", input_value)
        assert result == expected


class TestChecklistFieldFormatting:
    """Tests for checklist field formatting in _format_field_value_for_write."""

    CHECKLIST_FIELD_DEF = {
        "id": "customfield_11003",
        "name": "Definition of Done",
        "schema": {
            "type": "string",
            "custom": "com.okapya.jira.checklist:checklist",
            "customId": 11003,
        },
    }

    @pytest.fixture
    def mixin(self, jira_fetcher: "JiraFetcher") -> FieldsMixin:
        """Create a FieldsMixin instance with mocked dependencies."""
        fetcher = jira_fetcher
        fetcher.config = MagicMock()
        fetcher.config.is_cloud = True
        return fetcher

    @pytest.mark.parametrize(
        "test_id, value, expected",
        [
            pytest.param(
                "list_to_markdown",
                ["Task A", "Task B"],
                "* Task A\n* Task B",
                id="list_to_markdown",
            ),
            pytest.param(
                "list_with_checked_tuples",
                [("Task A", True), ("Task B", False)],
                "* [x] Task A\n* Task B",
                id="list_with_checked_tuples",
            ),
            pytest.param(
                "dict_list",
                [{"name": "Task A", "checked": True}],
                "* [x] Task A",
                id="dict_list",
            ),
            pytest.param(
                "string_passthrough",
                "* [x] done\n* todo",
                "* [x] done\n* todo",
                id="string_passthrough",
            ),
            pytest.param(
                "empty_list",
                [],
                "",
                id="empty_list",
            ),
        ],
    )
    def test_checklist_formatting(self, mixin, test_id, value, expected):
        """Checklist fields should be converted to markdown string format."""
        result = mixin._format_field_value_for_write(
            "customfield_11003", value, self.CHECKLIST_FIELD_DEF
        )
        assert result == expected

    def test_non_checklist_string_field_unaffected(self, mixin):
        """Non-checklist string fields should not be affected by checklist logic."""
        non_checklist_def = {
            "id": "customfield_99999",
            "name": "Some Text Field",
            "schema": {"type": "string"},
        }
        value = ["a", "b"]
        result = mixin._format_field_value_for_write(
            "customfield_99999", value, non_checklist_def
        )
        # Should pass through unchanged (no checklist conversion)
        assert result == ["a", "b"]
