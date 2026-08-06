"""Unit tests for Tempo Core work attribute support."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira.work_attributes import WorkAttributeMixin
from mcp_atlassian.jira.worklog import WorklogMixin
from mcp_atlassian.models.jira import (
    JiraWorkAttribute,
    JiraWorkAttributeType,
    JiraWorkAttributeValue,
)
from mcp_atlassian.models.jira.worklog import JiraWorklog


class TestJiraWorkAttribute:
    """Tests for Tempo work attribute models."""

    def test_from_api_response(self):
        """Parse the nested type and static-list values from Tempo."""
        attribute = JiraWorkAttribute.from_api_response(
            {
                "id": 45,
                "key": "_WorkMode_",
                "name": "Work Mode",
                "type": {
                    "name": "STATIC_LIST",
                    "value": "STATIC_LIST",
                    "systemType": False,
                },
                "externalUrl": "",
                "required": False,
                "sequence": 1,
                "staticListValues": [
                    {
                        "id": 123,
                        "name": "Office",
                        "value": "office",
                        "removed": False,
                        "sequence": 1,
                        "workAttributeId": 45,
                    }
                ],
            }
        )

        assert attribute.id == 45
        assert attribute.key == "_WorkMode_"
        assert attribute.type == JiraWorkAttributeType(
            name="STATIC_LIST", value="STATIC_LIST", system_type=False
        )
        assert attribute.static_list_values[0] == JiraWorkAttributeValue(
            id=123,
            name="Office",
            value="office",
            removed=False,
            sequence=1,
            work_attribute_id=45,
        )

    def test_to_simplified_dict(self):
        """Serialize an attribute using the repository's response names."""
        attribute = JiraWorkAttribute(
            id=45,
            key="_WorkMode_",
            name="Work Mode",
            type=JiraWorkAttributeType(
                name="STATIC_LIST", value="STATIC_LIST", system_type=False
            ),
            required=False,
        )

        assert attribute.to_simplified_dict() == {
            "id": 45,
            "key": "_WorkMode_",
            "name": "Work Mode",
            "type": {
                "name": "STATIC_LIST",
                "value": "STATIC_LIST",
                "system_type": False,
            },
            "external_url": "",
            "required": False,
            "sequence": 0,
            "static_list_values": [],
        }

    @pytest.mark.parametrize("data", [None, "invalid"])
    def test_from_api_response_invalid(self, data):
        """Return an empty model for malformed response items."""
        attribute = JiraWorkAttribute.from_api_response(data)

        assert attribute == JiraWorkAttribute()


class TestJiraWorkAttributeValue:
    """Tests for static-list values."""

    def test_from_api_response(self):
        """Parse the static-list value response shape."""
        value = JiraWorkAttributeValue.from_api_response(
            {
                "id": 123,
                "name": "Office",
                "value": "office",
                "removed": False,
                "sequence": 1,
                "workAttributeId": 45,
            }
        )

        assert value.to_simplified_dict() == {
            "id": 123,
            "name": "Office",
            "value": "office",
            "removed": False,
            "sequence": 1,
            "work_attribute_id": 45,
        }


class TestJiraWorklogWithAttributes:
    """Tests for attributes returned on Jira worklogs."""

    def test_from_api_response_with_attributes(self):
        """Preserve Tempo's worklog attributes map."""
        worklog = JiraWorklog.from_api_response(
            {
                "id": "10001",
                "timeSpent": "2 hours",
                "timeSpentSeconds": 7200,
                "attributes": {
                    "_WorkMode_": {"value": "office"},
                },
            }
        )

        assert worklog.attributes == {
            "_WorkMode_": {"value": "office"},
        }
        assert worklog.to_simplified_dict()["attributes"] == worklog.attributes

    def test_from_api_response_without_attributes(self):
        """Keep attributes optional for ordinary Jira worklogs."""
        worklog = JiraWorklog.from_api_response(
            {
                "id": "10002",
                "timeSpent": "1 day",
                "timeSpentSeconds": 28800,
            }
        )

        assert worklog.attributes is None


class TestWorkAttributeMixin:
    """Tests for Tempo Core REST calls."""

    @staticmethod
    def _mixin(*, is_cloud: bool = False) -> WorkAttributeMixin:
        """Create a mixin with a mocked Jira client."""
        mixin = WorkAttributeMixin.__new__(WorkAttributeMixin)
        mixin.config = MagicMock(is_cloud=is_cloud)
        mixin.jira = MagicMock()
        return mixin

    def test_get_work_attributes_success(self):
        """Fetch work attributes from the documented Tempo endpoint."""
        mixin = self._mixin()
        mixin.jira.get.return_value = [
            {"id": 45, "key": "_WorkMode_", "name": "Work Mode"}
        ]

        result = mixin.get_work_attributes()

        mixin.jira.get.assert_called_once_with("rest/tempo-core/1/work-attribute")
        assert result[0].id == 45
        assert result[0].key == "_WorkMode_"

    def test_get_work_attribute_values_success(self):
        """Fetch static-list values from the documented Tempo endpoint."""
        mixin = self._mixin()
        mixin.jira.get.return_value = [
            {
                "id": 123,
                "name": "Office",
                "value": "office",
                "workAttributeId": 45,
            }
        ]

        result = mixin.get_work_attribute_values(attribute_id=45)

        mixin.jira.get.assert_called_once_with(
            "rest/tempo-core/1/work-attribute/45/static-list-value"
        )
        assert result[0].value == "office"

    @pytest.mark.parametrize(
        ("method_name", "args"),
        [("get_work_attributes", ()), ("get_work_attribute_values", (45,))],
    )
    def test_cloud_endpoints_are_rejected(self, method_name, args):
        """Tempo Core work attribute endpoints must not run on Cloud."""
        mixin = self._mixin(is_cloud=True)

        with pytest.raises(NotImplementedError):
            getattr(mixin, method_name)(*args)

        mixin.jira.get.assert_not_called()

    def test_get_work_attributes_propagates_request_errors(self):
        """Tempo request failures must not be reported as an empty catalog."""
        mixin = self._mixin()
        mixin.jira.get.side_effect = RuntimeError("Tempo unavailable")

        with pytest.raises(RuntimeError, match="Tempo unavailable"):
            mixin.get_work_attributes()

    def test_get_work_attribute_values_propagates_request_errors(self):
        """Static-list request failures must remain visible to callers."""
        mixin = self._mixin()
        mixin.jira.get.side_effect = RuntimeError("Tempo unavailable")

        with pytest.raises(RuntimeError, match="Tempo unavailable"):
            mixin.get_work_attribute_values(attribute_id=45)

    def test_empty_responses_return_empty_lists(self):
        """Successful empty Tempo responses remain valid empty results."""
        mixin = self._mixin()
        mixin.jira.get.return_value = []

        assert mixin.get_work_attributes() == []
        assert mixin.get_work_attribute_values(attribute_id=45) == []

    def test_get_work_attribute_catalog_includes_static_list_values(self):
        """The consolidated lookup includes values for static-list attributes."""
        mixin = self._mixin()
        mixin.jira.get.side_effect = [
            [
                {
                    "id": 45,
                    "key": "_WorkMode_",
                    "name": "Work Mode",
                    "type": {"value": "STATIC_LIST"},
                }
            ],
            [{"id": 123, "name": "Office", "value": "office"}],
        ]

        result = mixin.get_work_attribute_catalog()

        assert result[0].static_list_values[0].value == "office"
        assert mixin.jira.get.call_args_list[1].args == (
            "rest/tempo-core/1/work-attribute/45/static-list-value",
        )

    def test_invalid_attribute_id_is_rejected(self):
        """Reject invalid path parameters before making a request."""
        mixin = self._mixin()

        with pytest.raises(ValueError, match="greater than zero"):
            mixin.get_work_attribute_values(attribute_id=0)

        mixin.jira.get.assert_not_called()


class TestAddWorklogWithAttributes:
    """Tests for creating Tempo worklogs with attributes."""

    @staticmethod
    def _mixin(*, is_cloud: bool = False) -> WorklogMixin:
        """Create a worklog mixin with a mocked Jira client."""
        mixin = WorklogMixin.__new__(WorklogMixin)
        mixin.config = MagicMock(is_cloud=is_cloud)
        mixin.jira = MagicMock()
        return mixin

    def test_add_worklog_uses_tempo_endpoint(self):
        """Send attributes using Tempo's payload and endpoint contract."""
        mixin = self._mixin()
        mixin.jira.post.return_value = [
            {
                "tempoWorklogId": 10001,
                "jiraWorklogId": 20001,
                "timeSpent": "2 hours",
                "timeSpentSeconds": 7200,
                "dateCreated": "2024-01-15T10:00:00.000+0000",
                "dateUpdated": "2024-01-15T10:00:00.000+0000",
                "startDate": "2024-01-15T09:00:00.000+0000",
                "workerKey": "jdoe",
                "attributes": {"_WorkMode_": {"value": "office"}},
            }
        ]

        result = mixin.add_worklog(
            issue_key="PROJ-123",
            time_spent="2h",
            started="2024-01-15T09:00:00.000+0000",
            worklog_attributes={"_WorkMode_": {"value": "office"}},
        )

        mixin.jira.post.assert_called_once_with(
            "rest/tempo-timesheets/4/worklogs",
            data={
                "originTaskId": "PROJ-123",
                "timeSpentSeconds": 7200,
                "started": "2024-01-15T09:00:00.000+0000",
                "attributes": {"_WorkMode_": {"value": "office"}},
            },
        )
        assert result["id"] == 20001
        assert result["attributes"] == {"_WorkMode_": {"value": "office"}}

    def test_add_worklog_attributes_rejected_on_cloud(self):
        """Don't send the DC-only Tempo payload to Jira Cloud."""
        mixin = self._mixin(is_cloud=True)

        with pytest.raises(Exception, match="only available"):
            mixin.add_worklog(
                issue_key="PROJ-123",
                time_spent="2h",
                worklog_attributes={"_WorkMode_": {"value": "office"}},
            )

        mixin.jira.post.assert_not_called()
