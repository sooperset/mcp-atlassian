"""Tests for custom field options tooling."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.field_options import FieldOptionsMixin
from mcp_atlassian.models.jira.field_option import FieldContext, FieldOption

# ============================================================================
# Model Tests
# ============================================================================


class TestFieldContextModel:
    """Tests for FieldContext.from_api_response."""

    @pytest.mark.parametrize(
        "test_id, data, expected_id, expected_name, expected_global",
        [
            (
                "basic",
                {"id": "10001", "name": "Default", "description": "Global context"},
                "10001",
                "Default",
                False,
            ),
            (
                "global_context",
                {
                    "id": "10002",
                    "name": "Global",
                    "isGlobalContext": True,
                    "isAnyIssueType": True,
                },
                "10002",
                "Global",
                True,
            ),
            (
                "empty_data",
                {},
                "",
                "",
                False,
            ),
            (
                "none_data",
                None,
                "",
                "",
                False,
            ),
        ],
    )
    def test_from_api_response(
        self, test_id, data, expected_id, expected_name, expected_global
    ):
        ctx = FieldContext.from_api_response(data)
        assert ctx.id == expected_id
        assert ctx.name == expected_name
        assert ctx.is_global_context == expected_global

    def test_to_simplified_dict(self):
        ctx = FieldContext(
            id="10001",
            name="Default",
            description="Global context",
            is_global_context=True,
        )
        simplified = ctx.to_simplified_dict()
        assert simplified["id"] == "10001"
        assert simplified["name"] == "Default"
        assert simplified["description"] == "Global context"
        assert simplified["is_global_context"] is True

    def test_to_simplified_dict_no_extras(self):
        ctx = FieldContext(id="1", name="Basic")
        simplified = ctx.to_simplified_dict()
        assert "description" not in simplified
        assert "is_global_context" not in simplified


class TestFieldOptionModel:
    """Tests for FieldOption.from_api_response."""

    @pytest.mark.parametrize(
        "test_id, data, expected_id, expected_value, expected_disabled",
        [
            (
                "basic",
                {"id": "10100", "value": "High", "disabled": False},
                "10100",
                "High",
                False,
            ),
            (
                "disabled",
                {"id": "10101", "value": "Deprecated", "disabled": True},
                "10101",
                "Deprecated",
                True,
            ),
            (
                "option_id_fallback",
                {"optionId": "10102", "value": "Low"},
                "10102",
                "Low",
                False,
            ),
            (
                "name_fallback",
                {"id": "1", "name": "Highest"},
                "1",
                "Highest",
                False,
            ),
            (
                "value_over_name",
                {"id": "1", "value": "Val", "name": "Name"},
                "1",
                "Val",
                False,
            ),
            (
                "empty_data",
                {},
                "",
                "",
                False,
            ),
        ],
    )
    def test_from_api_response(
        self, test_id, data, expected_id, expected_value, expected_disabled
    ):
        opt = FieldOption.from_api_response(data)
        assert opt.id == expected_id
        assert opt.value == expected_value
        assert opt.disabled == expected_disabled

    def test_cascading_options(self):
        data = {
            "id": "10200",
            "value": "North America",
            "cascadingOptions": [
                {"id": "10201", "value": "United States"},
                {"id": "10202", "value": "Canada"},
            ],
        }
        opt = FieldOption.from_api_response(data)
        assert opt.value == "North America"
        assert len(opt.child_options) == 2
        assert opt.child_options[0].value == "United States"
        assert opt.child_options[1].value == "Canada"

    def test_to_simplified_dict_with_children(self):
        opt = FieldOption(
            id="1",
            value="Parent",
            child_options=[
                FieldOption(id="2", value="Child A"),
                FieldOption(id="3", value="Child B"),
            ],
        )
        simplified = opt.to_simplified_dict()
        assert simplified["id"] == "1"
        assert simplified["value"] == "Parent"
        assert "disabled" not in simplified
        assert len(simplified["child_options"]) == 2

    def test_to_simplified_dict_disabled(self):
        opt = FieldOption(id="1", value="Old", disabled=True)
        simplified = opt.to_simplified_dict()
        assert simplified["disabled"] is True


# ============================================================================
# Mixin Tests
# ============================================================================


class TestFieldOptionsMixin:
    """Tests for FieldOptionsMixin methods."""

    @pytest.fixture
    def mixin(self, jira_fetcher: JiraFetcher) -> FieldOptionsMixin:
        """Create a mixin instance with mocked dependencies."""
        fetcher = jira_fetcher
        fetcher.config = MagicMock()
        fetcher.config.is_cloud = True
        return fetcher

    # -- get_field_contexts -------------------------------------------------

    def test_contexts_cloud(self, mixin):
        mixin.config.is_cloud = True
        mixin.jira.get = MagicMock(
            return_value={
                "values": [
                    {
                        "id": "10001",
                        "name": "Default Configuration Scheme",
                        "isGlobalContext": True,
                        "isAnyIssueType": True,
                    },
                    {
                        "id": "10002",
                        "name": "Bug context",
                        "isGlobalContext": False,
                    },
                ],
                "startAt": 0,
                "maxResults": 50,
                "total": 2,
            }
        )

        result = mixin.get_field_contexts("customfield_10001")
        assert len(result) == 2
        assert result[0].id == "10001"
        assert result[0].is_global_context is True
        assert result[1].name == "Bug context"

    def test_contexts_server_returns_empty(self, mixin):
        mixin.config.is_cloud = False
        result = mixin.get_field_contexts("customfield_10001")
        assert result == []

    # -- get_field_options (Cloud) ------------------------------------------

    def test_options_cloud_with_context(self, mixin):
        mixin.config.is_cloud = True
        mixin.jira.get = MagicMock(
            return_value={
                "values": [
                    {"id": "10100", "value": "High", "disabled": False},
                    {"id": "10101", "value": "Medium", "disabled": False},
                    {"id": "10102", "value": "Low", "disabled": False},
                ],
                "startAt": 0,
                "maxResults": 50,
                "total": 3,
            }
        )

        result = mixin.get_field_options("customfield_10001", context_id="10001")
        assert len(result) == 3
        assert result[0].value == "High"
        assert result[2].value == "Low"

    def test_options_cloud_auto_context(self, mixin):
        """When context_id is None, auto-resolve via get_field_contexts."""
        mixin.config.is_cloud = True
        # First call returns contexts, second returns options
        mixin.jira.get = MagicMock(
            side_effect=[
                # get_field_contexts response
                {
                    "values": [
                        {"id": "10001", "name": "Global", "isGlobalContext": True},
                    ],
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 1,
                },
                # get_field_options response
                {
                    "values": [{"id": "1", "value": "Option A"}],
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 1,
                },
            ]
        )

        result = mixin.get_field_options("customfield_10001")
        assert len(result) == 1
        assert result[0].value == "Option A"

    def test_options_cloud_disabled(self, mixin):
        mixin.config.is_cloud = True
        mixin.jira.get = MagicMock(
            return_value={
                "values": [
                    {"id": "1", "value": "Active", "disabled": False},
                    {"id": "2", "value": "Deprecated", "disabled": True},
                ],
                "startAt": 0,
                "maxResults": 50,
                "total": 2,
            }
        )

        result = mixin.get_field_options("customfield_10001", context_id="10001")
        assert result[1].disabled is True

    def test_options_cloud_pagination(self, mixin):
        """Pagination: two pages of results."""
        mixin.config.is_cloud = True
        mixin.jira.get = MagicMock(
            side_effect=[
                {
                    "values": [
                        {"id": "1", "value": "A"},
                        {"id": "2", "value": "B"},
                    ],
                    "startAt": 0,
                    "maxResults": 2,
                    "total": 3,
                },
                {
                    "values": [{"id": "3", "value": "C"}],
                    "startAt": 2,
                    "maxResults": 2,
                    "total": 3,
                },
            ]
        )

        result = mixin.get_field_options("customfield_10001", context_id="10001")
        assert len(result) == 3
        assert [o.value for o in result] == ["A", "B", "C"]

    def test_options_cloud_empty(self, mixin):
        mixin.config.is_cloud = True
        mixin.jira.get = MagicMock(
            return_value={
                "values": [],
                "startAt": 0,
                "maxResults": 50,
                "total": 0,
            }
        )

        result = mixin.get_field_options("customfield_10001", context_id="10001")
        assert result == []

    def test_options_cloud_cascading(self, mixin):
        mixin.config.is_cloud = True
        mixin.jira.get = MagicMock(
            return_value={
                "values": [
                    {
                        "id": "10200",
                        "value": "Americas",
                        "cascadingOptions": [
                            {"id": "10201", "value": "US"},
                            {"id": "10202", "value": "Canada"},
                        ],
                    }
                ],
                "startAt": 0,
                "maxResults": 50,
                "total": 1,
            }
        )

        result = mixin.get_field_options("customfield_10020", context_id="10001")
        assert len(result) == 1
        assert result[0].value == "Americas"
        assert len(result[0].child_options) == 2

    # -- get_field_options (Server/DC) --------------------------------------

    def test_options_server_with_params(self, mixin):
        """New createmeta endpoint: resolve issue type, extract allowedValues."""
        mixin.config.is_cloud = False
        mixin.get_project_issue_types = MagicMock(
            return_value=[{"id": "10001", "name": "Bug"}]
        )
        mixin.jira.issue_createmeta_fieldtypes = MagicMock(
            return_value={
                "maxResults": 50,
                "startAt": 0,
                "total": 2,
                "isLast": True,
                "values": [
                    {
                        "fieldId": "summary",
                        "required": True,
                        "name": "Summary",
                    },
                    {
                        "fieldId": "customfield_10001",
                        "required": False,
                        "name": "Priority",
                        "allowedValues": [
                            {"id": "1", "value": "High"},
                            {"id": "2", "value": "Low"},
                        ],
                    },
                ],
            }
        )

        result = mixin.get_field_options(
            "customfield_10001", project_key="TEST", issue_type="Bug"
        )
        assert len(result) == 2
        assert result[0].value == "High"
        mixin.jira.issue_createmeta_fieldtypes.assert_called_once_with(
            project="TEST", issue_type_id="10001", start=0, limit=50
        )

    def test_options_server_missing_params(self, mixin):
        mixin.config.is_cloud = False
        with pytest.raises(ValueError, match="project_key.*issue_type"):
            mixin.get_field_options("customfield_10001")

    def test_options_server_field_not_found(self, mixin):
        """Field not in createmeta response → empty list."""
        mixin.config.is_cloud = False
        mixin.get_project_issue_types = MagicMock(
            return_value=[{"id": "10001", "name": "Bug"}]
        )
        mixin.jira.issue_createmeta_fieldtypes = MagicMock(
            return_value={
                "maxResults": 50,
                "startAt": 0,
                "total": 1,
                "isLast": True,
                "values": [
                    {
                        "fieldId": "customfield_99999",
                        "allowedValues": [{"id": "1", "value": "X"}],
                    },
                ],
            }
        )

        result = mixin.get_field_options(
            "customfield_10001", project_key="TEST", issue_type="Bug"
        )
        assert result == []

    def test_options_server_issue_type_not_found(self, mixin):
        """Issue type name not in project → empty list."""
        mixin.config.is_cloud = False
        mixin.get_project_issue_types = MagicMock(
            return_value=[{"id": "10001", "name": "Task"}]
        )

        result = mixin.get_field_options(
            "customfield_10001", project_key="TEST", issue_type="Bug"
        )
        assert result == []

    def test_options_server_pagination(self, mixin):
        """Field on second page of createmeta results."""
        mixin.config.is_cloud = False
        mixin.get_project_issue_types = MagicMock(
            return_value=[{"id": "10001", "name": "Bug"}]
        )
        mixin.jira.issue_createmeta_fieldtypes = MagicMock(
            side_effect=[
                # Page 1: field not here
                {
                    "maxResults": 2,
                    "startAt": 0,
                    "total": 3,
                    "isLast": False,
                    "values": [
                        {"fieldId": "summary", "required": True},
                        {"fieldId": "description", "required": False},
                    ],
                },
                # Page 2: target field here
                {
                    "maxResults": 2,
                    "startAt": 2,
                    "total": 3,
                    "isLast": True,
                    "values": [
                        {
                            "fieldId": "customfield_10001",
                            "allowedValues": [
                                {"id": "1", "value": "Option A"},
                            ],
                        },
                    ],
                },
            ]
        )

        result = mixin.get_field_options(
            "customfield_10001", project_key="TEST", issue_type="Bug"
        )
        assert len(result) == 1
        assert result[0].value == "Option A"

    def test_options_server_case_insensitive_issue_type(self, mixin):
        """Issue type name matching is case-insensitive."""
        mixin.config.is_cloud = False
        mixin.get_project_issue_types = MagicMock(
            return_value=[{"id": "10001", "name": "Bug"}]
        )
        mixin.jira.issue_createmeta_fieldtypes = MagicMock(
            return_value={
                "maxResults": 50,
                "startAt": 0,
                "total": 1,
                "isLast": True,
                "values": [
                    {
                        "fieldId": "customfield_10001",
                        "allowedValues": [{"id": "1", "value": "Yes"}],
                    },
                ],
            }
        )

        result = mixin.get_field_options(
            "customfield_10001", project_key="TEST", issue_type="bug"
        )
        assert len(result) == 1
        assert result[0].value == "Yes"
