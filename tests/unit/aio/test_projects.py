"""Tests for AIO Tests project and schema operations."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.aio.client import AIOApiError
from tests.fixtures.aio_mocks import MOCK_AIO_PROJECT_CONFIG


@pytest.fixture
def fetcher(aio_fetcher):
    """Provide a fetcher whose configuration call returns the mock config."""
    aio_fetcher.get = MagicMock(return_value=MOCK_AIO_PROJECT_CONFIG)
    return aio_fetcher


class TestGetProject:
    """Tests for get_project."""

    def test_returns_enabled_project(self, fetcher):
        """A successful configuration call proves AIO Tests is enabled."""
        project = fetcher.get_project("PROJ")

        assert project.aio_enabled is True
        assert project.key == "PROJ"
        assert project.id == 10010
        assert project.adhoc_cycle_key == "AT-CY-1"
        fetcher.get.assert_called_once_with("/project/PROJ/config")

    def test_reports_disabled_project(self, aio_fetcher):
        """An API error means AIO Tests is unavailable for the project."""
        aio_fetcher.get = MagicMock(
            side_effect=AIOApiError("AIO Tests API error 404", status_code=404)
        )

        project = aio_fetcher.get_project("NOPE")

        assert project.aio_enabled is False
        assert project.key == "NOPE"
        assert "404" in (project.error or "")
        assert project.to_simplified_dict()["aio_enabled"] is False

    def test_configuration_is_cached(self, fetcher):
        """The configuration is fetched once per project."""
        fetcher.get_project("PROJ")
        fetcher.get_project("PROJ")

        assert fetcher.get.call_count == 1

    def test_refresh_bypasses_cache(self, fetcher):
        """An explicit refresh re-fetches the configuration."""
        fetcher.get_project_configuration("PROJ")
        fetcher.get_project_configuration("PROJ", refresh=True)

        assert fetcher.get.call_count == 2

    def test_unexpected_response_raises(self, aio_fetcher):
        """A non-object configuration response is an error."""
        aio_fetcher.get = MagicMock(return_value=["not", "a", "dict"])

        with pytest.raises(AIOApiError, match="Unexpected AIO Tests configuration"):
            aio_fetcher.get_project_configuration("PROJ")


class TestGetTestCaseSchema:
    """Tests for get_test_case_schema."""

    def test_includes_builtin_fields_and_allowed_values(self, fetcher):
        """The schema merges the built-in field catalog with project values."""
        schema = fetcher.get_test_case_schema("PROJ").to_simplified_dict()

        assert schema["project_key"] == "PROJ"
        assert schema["project_id"] == 10010
        field_names = {field["name"] for field in schema["fields"]}
        assert {"title", "steps", "priority", "folder"} <= field_names
        assert schema["allowed_values"]["priorities"] == [
            {"id": 10, "name": "Critical"},
            {"id": 11, "name": "Medium", "is_default": True},
        ]
        assert [status["name"] for status in schema["allowed_values"]["statuses"]] == [
            "Draft",
            "Published",
        ]

    def test_marks_read_only_fields(self, fetcher):
        """Read-only fields are flagged so they are never sent on writes."""
        schema = fetcher.get_test_case_schema("PROJ").to_simplified_dict()

        read_only = {
            field["name"] for field in schema["fields"] if field.get("read_only")
        }
        assert {"key", "version", "createdDate", "isArchived"} <= read_only

    def test_lists_required_fields(self, fetcher):
        """Required built-in and custom fields are listed together."""
        schema = fetcher.get_test_case_schema("PROJ").to_simplified_dict()

        assert schema["required_fields"] == ["title", "Environment"]

    def test_only_case_custom_fields_are_included(self, fetcher):
        """Custom fields not associated with cases are filtered out."""
        schema = fetcher.get_test_case_schema("PROJ").to_simplified_dict()

        names = {field["name"] for field in schema["custom_fields"]}
        assert names == {"Environment", "Reviewer", "Notes"}

    def test_custom_field_allowed_values(self, fetcher):
        """Select-list custom fields expose their allowed values."""
        schema = fetcher.get_test_case_schema("PROJ").to_simplified_dict()

        environment = next(
            field for field in schema["custom_fields"] if field["name"] == "Environment"
        )
        assert environment["required"] is True
        assert environment["type"] == "SINGLE_SELECT_LIST"
        assert environment["allowed_values"] == [
            {"id": 1, "value": "Staging"},
            {"id": 2, "value": "Production"},
        ]


class TestResolveLookupId:
    """Tests for resolve_lookup_id."""

    def test_resolves_name_case_insensitively(self, fetcher):
        """Names are matched without regard to case."""
        assert fetcher.resolve_lookup_id("PROJ", "casePriorities", "critical") == 10

    def test_passes_through_integer(self, fetcher):
        """An integer is already an ID."""
        assert fetcher.resolve_lookup_id("PROJ", "casePriorities", 99) == 99
        fetcher.get.assert_not_called()

    def test_passes_through_numeric_string(self, fetcher):
        """A numeric string is treated as an ID."""
        assert fetcher.resolve_lookup_id("PROJ", "caseStatuses", "21") == 21

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_values_return_none(self, fetcher, value):
        """Empty values resolve to nothing."""
        assert fetcher.resolve_lookup_id("PROJ", "caseStatuses", value) is None

    def test_unknown_name_lists_available_values(self, fetcher):
        """An unknown name reports what the project does accept."""
        with pytest.raises(ValueError, match="Available values: Draft, Published"):
            fetcher.resolve_lookup_id("PROJ", "caseStatuses", "Retired")

    def test_boolean_is_rejected(self, fetcher):
        """A boolean is never a valid lookup value."""
        value = True
        with pytest.raises(ValueError, match="Invalid value"):
            fetcher.resolve_lookup_id("PROJ", "caseStatuses", value)
