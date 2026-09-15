"""Unit tests for Tempo Core work attribute support."""

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from requests.exceptions import HTTPError

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

    def test_get_work_attribute_catalog_reuses_inline_static_list_values(self):
        """Tempo sends values inline, so the catalog must not re-fetch them.

        Tempo Core returns ``staticListValues`` on the attribute definition
        itself; requesting them again costs a redundant request per attribute.
        Shape captured from a live Jira Data Center instance.
        """
        mixin = self._mixin()
        mixin.jira.get.return_value = [
            {
                "id": 1,
                "key": "_WorkType_",
                "name": "Work type",
                "type": {"name": "Static List", "value": "STATIC_LIST"},
                "required": True,
                "sequence": 0,
                "staticListValues": [
                    {
                        "id": 27,
                        "name": "Analysis",
                        "value": "Analysis",
                        "removed": False,
                        "sequence": 1,
                        "workAttributeId": 1,
                    }
                ],
            }
        ]

        result = mixin.get_work_attribute_catalog()

        assert result[0].static_list_values[0].value == "Analysis"
        mixin.jira.get.assert_called_once_with("rest/tempo-core/1/work-attribute")

    def test_invalid_attribute_id_is_rejected(self):
        """Reject invalid path parameters before making a request."""
        mixin = self._mixin()

        with pytest.raises(ValueError, match="greater than zero"):
            mixin.get_work_attribute_values(attribute_id=0)

        mixin.jira.get.assert_not_called()


class _WorklogWithAttributes(WorklogMixin, WorkAttributeMixin):
    """Worklog mixin composed with the catalog mixin, like `JiraFetcher`."""


class TestAddWorklogWithAttributes:
    """Tests for creating Tempo Timesheets v4 worklogs with attributes.

    Only the ``self.jira`` HTTP boundary is mocked. The asserted payload is the
    exact wire body verified against a live Jira Data Center + Tempo instance:
    mocking ``jira.post`` wholesale is what let an invalid contract ship.
    """

    # Attribute definition shape captured from Tempo Core on Data Center.
    WORK_ATTRIBUTE = {
        "id": 1,
        "key": "_WorkType_",
        "name": "Work type",
        "type": {"name": "Static List", "value": "STATIC_LIST"},
        "required": True,
        "sequence": 0,
        "staticListValues": [
            {
                "id": 3,
                "name": "Development",
                "value": "Development",
                "workAttributeId": 1,
            }
        ],
    }

    # Tempo echoes the created worklog, attributes included.
    CREATED_WORKLOG = {
        "tempoWorklogId": 10001,
        "jiraWorklogId": 20001,
        "timeSpent": "1 hour",
        "timeSpentSeconds": 3600,
        "dateCreated": "2026-09-11T08:00:00.000+0000",
        "dateUpdated": "2026-09-11T08:00:00.000+0000",
        "startDate": "2026-09-11T08:00:00.000+0000",
        "workerKey": "JIRAUSER12345",
        "comment": "Development",
        "attributes": {
            "_WorkType_": {
                "type": "WORK_ATTRIBUTE",
                "key": "_WorkType_",
                "name": "Work type",
                "workAttributeId": 1,
                "value": "Development",
            }
        },
    }

    ENRICHED_ATTRIBUTES = {
        "_WorkType_": {
            "name": "Work type",
            "workAttributeId": 1,
            "value": "Development",
        }
    }

    @staticmethod
    def _mixin(*, is_cloud: bool = False, with_catalog: bool = True) -> WorklogMixin:
        """Create the worklog mixin with only the Jira client mocked."""
        target = _WorklogWithAttributes if with_catalog else WorklogMixin
        mixin = target.__new__(target)
        mixin.config = MagicMock(is_cloud=is_cloud)
        mixin.jira = MagicMock()
        mixin._clean_text = MagicMock(side_effect=lambda text: text or "")
        mixin._markdown_to_jira = MagicMock(side_effect=lambda text: text)
        mixin.jira.myself.return_value = {
            "key": "JIRAUSER12345",
            "name": "jdoe",
            "displayName": "J. Doe",
        }
        return mixin

    @classmethod
    def _stub_reads(cls, mixin: WorklogMixin, issue_id: int | str = 100500) -> None:
        """Serve the read endpoints the Tempo write path depends on."""

        def fake_get(url: str, *args: Any, **kwargs: Any) -> Any:
            if url == "rest/tempo-core/1/work-attribute":
                return [dict(cls.WORK_ATTRIBUTE)]
            if url == "rest/api/2/issue/PROJ-123?fields=id":
                return {"id": issue_id}
            raise AssertionError(f"Unexpected GET {url}")

        mixin.jira.get.side_effect = fake_get

    @classmethod
    def _write(cls, mixin: WorklogMixin, **overrides: Any) -> dict[str, Any]:
        """Call `add_worklog` using the verified happy-path defaults."""
        mixin.jira.post.return_value = [dict(cls.CREATED_WORKLOG)]
        kwargs: dict[str, Any] = {
            "issue_key": "PROJ-123",
            "time_spent": "1h",
            "comment": "Development",
            "started": "2026-09-11T08:00:00.000",
            "worklog_attributes": {"_WorkType_": {"value": "Development"}},
        }
        kwargs.update(overrides)
        return mixin.add_worklog(**kwargs)

    def test_add_worklog_uses_tempo_endpoint(self):
        """Send the exact body Tempo Data Center accepts for attributes."""
        mixin = self._mixin()
        self._stub_reads(mixin)

        result = self._write(mixin)

        # The markdown -> Jira conversion still happens before the Tempo call.
        mixin._markdown_to_jira.assert_called_once_with("Development")
        mixin.jira.post.assert_called_once_with(
            "rest/tempo-timesheets/4/worklogs",
            data={
                "attributes": self.ENRICHED_ATTRIBUTES,
                "billableSeconds": "",
                "worker": "JIRAUSER12345",
                "comment": "Development",
                "timeSpentSeconds": 3600,
                "originTaskId": "100500",
                "remainingEstimate": None,
                "endDate": None,
                "includeNonWorkingDays": False,
                "started": "2026-09-11T08:00:00.000",
            },
        )
        mixin.jira.edit_issue.assert_not_called()
        assert result["id"] == 20001
        assert result["attributes"] == self.CREATED_WORKLOG["attributes"]

    def test_origin_task_id_uses_numeric_issue_id(self):
        """Tempo keys worklogs by internal issue id, never by issue key."""
        mixin = self._mixin()
        self._stub_reads(mixin, issue_id=100500)

        self._write(mixin)

        mixin.jira.get.assert_any_call("rest/api/2/issue/PROJ-123?fields=id")
        payload = mixin.jira.post.call_args.kwargs["data"]
        assert payload["originTaskId"] == "100500"
        assert isinstance(payload["originTaskId"], str)

    def test_worker_uses_the_internal_user_key(self):
        """Tempo rejects the username, so `worker` must be the user key."""
        mixin = self._mixin()
        self._stub_reads(mixin)

        self._write(mixin)

        mixin.jira.myself.assert_called_once()
        payload = mixin.jira.post.call_args.kwargs["data"]
        assert payload["worker"] == "JIRAUSER12345"
        assert payload["worker"] != "jdoe"

    def test_remaining_estimate_is_applied_through_jira(self):
        """The estimate goes to Jira's timetracking, not to the Tempo body.

        Whether Tempo v4 honours a numeric-seconds `remainingEstimate` was never
        verified, and re-parsing a duration locally is lossy, so the raw value is
        handed to Jira instead.
        """
        mixin = self._mixin()
        self._stub_reads(mixin)

        result = self._write(mixin, remaining_estimate="3h")

        mixin.jira.edit_issue.assert_called_once_with(
            issue_id_or_key="PROJ-123",
            fields={"timetracking": {"remainingEstimate": "3h"}},
        )
        payload = mixin.jira.post.call_args.kwargs["data"]
        assert payload["remainingEstimate"] is None
        assert result["remaining_estimate_updated"] is True

    def test_remaining_estimate_is_applied_after_the_worklog(self):
        """Tempo recomputes the estimate when logging work, so order matters.

        Jira's native `adjustEstimate=new` is applied together with the worklog
        and leaves the issue at exactly `newEstimate`; writing the estimate first
        would let Tempo overwrite it.
        """
        mixin = self._mixin()
        self._stub_reads(mixin)
        calls: list[str] = []

        def fake_post(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            calls.append("worklog")
            return [dict(self.CREATED_WORKLOG)]

        mixin.jira.post.side_effect = fake_post
        mixin.jira.edit_issue.side_effect = lambda *args, **kwargs: calls.append(
            "estimate"
        )

        self._write(mixin, remaining_estimate="3h")

        assert calls == ["worklog", "estimate"]

    def test_unparsable_remaining_estimate_reaches_jira_verbatim(self):
        """A duration Jira cannot parse must not be coerced to 60 seconds."""
        mixin = self._mixin()
        self._stub_reads(mixin)

        self._write(mixin, remaining_estimate="3 days of work")

        fields = mixin.jira.edit_issue.call_args.kwargs["fields"]
        assert fields == {"timetracking": {"remainingEstimate": "3 days of work"}}
        payload = mixin.jira.post.call_args.kwargs["data"]
        assert payload["remainingEstimate"] is None

    def test_rejected_remaining_estimate_is_not_reported_as_applied(self):
        """A failed estimate update must show up in the reported flag."""
        mixin = self._mixin()
        self._stub_reads(mixin)
        mixin.jira.edit_issue.side_effect = Exception(
            "400: '3 days of work' is not a valid duration"
        )

        result = self._write(mixin, remaining_estimate="3 days of work")

        # The worklog itself was still created, so the call must not raise.
        mixin.jira.post.assert_called_once()
        assert result["remaining_estimate_updated"] is False

    def test_started_is_always_sent(self):
        """Tempo rejects a payload with no `started` ('Date can not be empty').

        The API documentation marks the field optional, but a live Data Center
        instance refuses it, so the default has to be a real timestamp.
        """
        mixin = self._mixin()
        self._stub_reads(mixin)

        self._write(mixin, started=None)

        sent = mixin.jira.post.call_args.kwargs["data"]["started"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}", sent)
        # The default is 'now', not a fixed placeholder date.
        sent_epoch = time.mktime(time.strptime(sent, "%Y-%m-%dT%H:%M:%S.%f"))
        assert abs(sent_epoch - time.time()) < 60

    @pytest.mark.parametrize("comment", [None, "", "   "])
    def test_comment_is_required_for_attributed_worklogs(self, comment):
        """Fail fast instead of inventing placeholder text for a timesheet."""
        mixin = self._mixin()
        self._stub_reads(mixin)

        with pytest.raises(ValueError, match="non-empty comment"):
            self._write(mixin, comment=comment)

        mixin.jira.post.assert_not_called()

    def test_started_offset_is_dropped_and_instant_preserved(self):
        """Tempo answers 'Date is invalid' for any timezone offset."""
        mixin = self._mixin()
        self._stub_reads(mixin)

        self._write(mixin, started="2026-09-11T08:00:00.000+0300")

        sent = mixin.jira.post.call_args.kwargs["data"]["started"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}", sent)
        # `mktime` reads the struct as local time, so equality here means the
        # naive wall clock still denotes the instant that was sent in.
        assert (
            time.mktime(time.strptime(sent, "%Y-%m-%dT%H:%M:%S.%f"))
            == datetime(
                2026, 9, 11, 8, 0, tzinfo=timezone(timedelta(hours=3))
            ).timestamp()
        )

    def test_started_rejects_unparsable_values(self):
        """Name the expected format instead of sending junk to Tempo."""
        mixin = self._mixin()
        self._stub_reads(mixin)

        with pytest.raises(ValueError, match="yyyy-MM-ddTHH:mm:ss.SSS"):
            self._write(mixin, started="yesterday")

        mixin.jira.post.assert_not_called()

    def test_unknown_attribute_key_is_rejected(self):
        """An unknown key must not reach an endpoint that would reject it."""
        mixin = self._mixin()
        self._stub_reads(mixin)

        with pytest.raises(ValueError, match="_NotAnAttribute_"):
            self._write(mixin, worklog_attributes={"_NotAnAttribute_": {"value": "X"}})

        mixin.jira.post.assert_not_called()

    def test_catalog_lookup_is_skipped_for_complete_attribute(self):
        """Caller-supplied name/workAttributeId must not trigger a refetch."""
        mixin = self._mixin()
        self._stub_reads(mixin)
        attributes = {"_WorkType_": dict(self.ENRICHED_ATTRIBUTES["_WorkType_"])}

        self._write(mixin, worklog_attributes=attributes)

        requested = [call.args[0] for call in mixin.jira.get.call_args_list]
        assert "rest/tempo-core/1/work-attribute" not in requested
        assert mixin.jira.post.call_args.kwargs["data"]["attributes"] == attributes

    def test_catalog_failure_names_the_unresolved_attribute(self):
        """A broken catalog lookup must surface as an actionable error."""
        mixin = self._mixin()
        self._stub_reads(mixin)

        def failing_get(url: str, *args: Any, **kwargs: Any) -> Any:
            if url == "rest/tempo-core/1/work-attribute":
                raise HTTPError("403 Forbidden")
            return {"id": 100500}

        mixin.jira.get.side_effect = failing_get

        with pytest.raises(ValueError, match="_WorkType_"):
            self._write(mixin)

        mixin.jira.post.assert_not_called()

    def test_missing_catalog_collaborator_is_rejected(self):
        """Without the attribute mixin the keys cannot be validated."""
        mixin = self._mixin(with_catalog=False)
        self._stub_reads(mixin)

        with pytest.raises(ValueError, match="catalog is unavailable"):
            self._write(mixin)

        mixin.jira.post.assert_not_called()

    def test_add_worklog_attributes_rejected_on_cloud(self):
        """Don't send the DC-only Tempo payload to Jira Cloud."""
        mixin = self._mixin(is_cloud=True)

        with pytest.raises(Exception, match="only available"):
            mixin.add_worklog(
                issue_key="PROJ-123",
                time_spent="1h",
                comment="Development",
                worklog_attributes={"_WorkType_": {"value": "Development"}},
            )

        mixin.jira.post.assert_not_called()
