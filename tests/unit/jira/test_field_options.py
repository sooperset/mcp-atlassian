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

    def test_children_key_server_dc(self):
        """Server/DC createmeta uses 'children' instead of 'cascadingOptions'."""
        data = {
            "id": "10200",
            "value": "North America",
            "children": [
                {"id": "10201", "value": "United States"},
                {"id": "10202", "value": "Canada"},
            ],
        }
        opt = FieldOption.from_api_response(data)
        assert opt.value == "North America"
        assert len(opt.child_options) == 2
        assert opt.child_options[0].value == "United States"
        assert opt.child_options[1].value == "Canada"

    def test_cascading_options_empty_list_not_shadowed_by_children(self):
        """An explicit empty cascadingOptions is not overridden by children."""
        data = {
            "id": "10200",
            "value": "Parent",
            "cascadingOptions": [],
            "children": [{"id": "1", "value": "Should not appear"}],
        }
        opt = FieldOption.from_api_response(data)
        assert opt.child_options == []

    def test_cascading_options_key_takes_precedence_over_children(self):
        """cascadingOptions wins when both keys are present."""
        data = {
            "id": "10200",
            "value": "Parent",
            "cascadingOptions": [{"id": "1", "value": "Cascade Child"}],
            "children": [{"id": "2", "value": "Regular Child"}],
        }
        opt = FieldOption.from_api_response(data)
        assert len(opt.child_options) == 1
        assert opt.child_options[0].value == "Cascade Child"

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
        # Cloud main endpoint returns a flat list; children reference
        # their parent via "optionId" or are available via the
        # cascade-specific endpoint. Mock the main list followed by
        # the cascade endpoint response for the parent.
        mixin.jira.get = MagicMock(
            side_effect=[
                # main options list (parent only)
                {
                    "values": [
                        {"id": "10200", "value": "Americas"},
                    ],
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 1,
                },
                # cascade-specific endpoint for parent 10200
                {
                    "values": [
                        {"id": "10201", "value": "US"},
                        {"id": "10202", "value": "Canada"},
                    ]
                },
            ]
        )

        result = mixin.get_field_options("customfield_10020", context_id="10001")
        assert len(result) == 1
        assert result[0].value == "Americas"
        assert len(result[0].child_options) == 2

    def test_options_cloud_cascading_cascade_pagination(self, mixin):
        """Cascade endpoint paginates across multiple pages."""
        mixin.config.is_cloud = True
        mixin.jira.get = MagicMock(
            side_effect=[
                # main options list (one parent)
                {
                    "values": [{"id": "10200", "value": "Americas"}],
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 1,
                },
                # cascade endpoint page 1
                {
                    "values": [
                        {"id": "10201", "value": "US"},
                        {"id": "10202", "value": "Canada"},
                    ],
                    "startAt": 0,
                    "maxResults": 2,
                    "total": 3,
                },
                # cascade endpoint page 2
                {
                    "values": [{"id": "10203", "value": "Mexico"}],
                    "startAt": 2,
                    "maxResults": 2,
                    "total": 3,
                },
            ]
        )

        result = mixin.get_field_options("customfield_10020", context_id="10001")
        assert len(result) == 1
        assert result[0].value == "Americas"
        assert len(result[0].child_options) == 3
        assert result[0].child_options[2].value == "Mexico"

    def test_options_cloud_cascading_flat_list_fallback(self, mixin):
        """When cascade endpoint is unreachable, fall back to optionId grouping."""
        mixin.config.is_cloud = True
        mixin.jira.get = MagicMock(
            side_effect=[
                # main options: parent + children as flat list with optionId
                {
                    "values": [
                        {"id": "10200", "value": "Americas"},
                        {"id": "10201", "value": "US", "optionId": "10200"},
                        {"id": "10202", "value": "Canada", "optionId": "10200"},
                    ],
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 3,
                },
                # cascade endpoint unavailable
                Exception("404 Not Found"),
            ]
        )

        result = mixin.get_field_options("customfield_10020", context_id="10001")
        assert len(result) == 1
        assert result[0].value == "Americas"
        assert len(result[0].child_options) == 2
        assert {c.value for c in result[0].child_options} == {"US", "Canada"}

    def test_options_cloud_cascading_empty_cascade_no_fallback(self, mixin):
        """Empty cascade response is trusted; optionId fallback must not trigger."""
        mixin.config.is_cloud = True
        mixin.jira.get = MagicMock(
            side_effect=[
                # main options: parent + flat-list child (optionId present)
                {
                    "values": [
                        {"id": "10200", "value": "Americas"},
                        {"id": "10201", "value": "US", "optionId": "10200"},
                    ],
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 2,
                },
                # cascade endpoint responds but says no children
                {"values": [], "total": 0},
            ]
        )

        result = mixin.get_field_options("customfield_10020", context_id="10001")
        assert len(result) == 1
        assert result[0].value == "Americas"
        assert result[0].child_options == []

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

    def test_options_server_cascading_children_key(self, mixin):
        """Server/DC allowedValues with 'children' key for cascading select."""
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
                        "fieldId": "customfield_10020",
                        "required": False,
                        "name": "Region",
                        "allowedValues": [
                            {
                                "id": "10200",
                                "value": "Americas",
                                "children": [
                                    {"id": "10201", "value": "US"},
                                    {"id": "10202", "value": "Canada"},
                                ],
                            }
                        ],
                    }
                ],
            }
        )

        result = mixin.get_field_options(
            "customfield_10020", project_key="TEST", issue_type="Bug"
        )
        assert len(result) == 1
        assert result[0].value == "Americas"
        assert len(result[0].child_options) == 2
        assert result[0].child_options[0].value == "US"
        assert result[0].child_options[1].value == "Canada"


# ============================================================================
# Regression Tests — upstream #673
# ============================================================================


class TestGetFieldOptionsRegression673:
    """Regression for https://github.com/sooperset/mcp-atlassian/issues/673.

    Issue: "Get Jira custom field available values"
    Status: RESOLVED — get_field_options MCP tool already exists and the
    fetcher method returns option values with id, value, and disabled fields.

    These tests prove the end-to-end data contract: the fetcher returns
    FieldOption objects with the fields users need to inspect available values.
    """

    @pytest.fixture
    def mixin(self, jira_fetcher: JiraFetcher) -> FieldOptionsMixin:
        """Create a FieldOptionsMixin configured for Cloud."""
        fetcher = jira_fetcher
        fetcher.config = MagicMock()
        fetcher.config.is_cloud = True
        return fetcher

    def test_get_field_options_returns_option_values(self, mixin):
        """get_field_options returns a list of FieldOption with value populated.

        Regression: the core ask in #673 was to retrieve the available values
        (strings) for a custom field so callers know what to submit.
        """
        mixin.jira.get = MagicMock(
            side_effect=[
                # main options list (flat, no children)
                {
                    "values": [
                        {"id": "10100", "value": "Blocker", "disabled": False},
                        {"id": "10101", "value": "Critical", "disabled": False},
                        {"id": "10102", "value": "Major", "disabled": False},
                    ],
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 3,
                },
                # cascade endpoint for each parent (empty — no children)
                {"values": []},
                {"values": []},
                {"values": []},
            ]
        )

        result = mixin.get_field_options("customfield_10016", context_id="10001")

        assert isinstance(result, list)
        assert len(result) == 3
        values = [opt.value for opt in result]
        assert "Blocker" in values
        assert "Critical" in values
        assert "Major" in values

    def test_get_field_options_returns_field_option_objects(self, mixin):
        """Each returned item is a FieldOption with id, value, disabled attrs."""
        mixin.jira.get = MagicMock(
            side_effect=[
                {
                    "values": [{"id": "10200", "value": "Yes", "disabled": False}],
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 1,
                },
                # cascade endpoint (empty)
                {"values": []},
            ]
        )

        result = mixin.get_field_options("customfield_10020", context_id="10001")

        assert len(result) == 1
        opt = result[0]
        assert isinstance(opt, FieldOption)
        assert opt.id == "10200"
        assert opt.value == "Yes"
        assert opt.disabled is False

    def test_get_field_options_to_simplified_dict_contract(self, mixin):
        """to_simplified_dict() provides the serialisable form consumers need."""
        mixin.jira.get = MagicMock(
            side_effect=[
                {
                    "values": [
                        {"id": "10300", "value": "Done", "disabled": False},
                        {"id": "10301", "value": "Won't Do", "disabled": True},
                    ],
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 2,
                },
                # cascade endpoint for each parent (empty)
                {"values": []},
                {"values": []},
            ]
        )

        result = mixin.get_field_options("customfield_10030", context_id="10001")

        active = next(o for o in result if o.value == "Done")
        deprecated = next(o for o in result if o.value == "Won't Do")

        active_dict = active.to_simplified_dict()
        assert active_dict["id"] == "10300"
        assert active_dict["value"] == "Done"
        assert "disabled" not in active_dict  # omitted when False

        deprecated_dict = deprecated.to_simplified_dict()
        assert deprecated_dict["disabled"] is True

    def test_get_field_options_server_returns_allowed_values(self, mixin):
        """Server/DC path: allowedValues from createmeta are returned as options.

        Confirms the feature works on Jira Server/DC as well as Cloud.
        """
        mixin.config.is_cloud = False
        mixin.get_project_issue_types = MagicMock(
            return_value=[{"id": "10001", "name": "Story"}]
        )
        mixin.jira.issue_createmeta_fieldtypes = MagicMock(
            return_value={
                "maxResults": 50,
                "startAt": 0,
                "total": 1,
                "isLast": True,
                "values": [
                    {
                        "fieldId": "customfield_10016",
                        "required": False,
                        "name": "Sprint",
                        "allowedValues": [
                            {"id": "1", "value": "Sprint 1"},
                            {"id": "2", "value": "Sprint 2"},
                        ],
                    },
                ],
            }
        )

        result = mixin.get_field_options(
            "customfield_10016", project_key="PROJ", issue_type="Story"
        )

        assert len(result) == 2
        assert result[0].value == "Sprint 1"
        assert result[1].value == "Sprint 2"
