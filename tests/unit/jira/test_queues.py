"""Tests for Jira Service Management queue read operations."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.models.jira import (
    JiraQueueIssuesResult,
    JiraRequestStatusResult,
    JiraRequestTransitionsResult,
    JiraRequestType,
    JiraRequestTypesResult,
    JiraServiceDeskQueuesResult,
    JiraServiceDeskRequest,
    JiraTemporaryAttachment,
)


@pytest.fixture
def queues_fetcher(jira_fetcher: JiraFetcher) -> JiraFetcher:
    """Create a Jira fetcher configured for queue endpoint testing."""
    fetcher = jira_fetcher
    fetcher.config = MagicMock()
    fetcher.config.is_cloud = False
    return fetcher


def test_get_service_desk_for_project_found_on_second_page(queues_fetcher: JiraFetcher):
    """Service desk lookup should paginate until a matching project key is found."""
    queues_fetcher.jira.get = MagicMock(
        side_effect=[
            {
                "start": 0,
                "limit": 1,
                "isLastPage": False,
                "values": [
                    {
                        "id": "1",
                        "projectKey": "TIC",
                        "projectId": "10001",
                        "projectName": "Ticketing",
                    }
                ],
            },
            {
                "start": 1,
                "limit": 1,
                "isLastPage": True,
                "values": [
                    {
                        "id": "4",
                        "projectKey": "SUP",
                        "projectId": "10400",
                        "projectName": "support",
                        "_links": {"self": "https://test/rest/servicedeskapi/4"},
                    }
                ],
            },
        ]
    )

    result = queues_fetcher.get_service_desk_for_project("sup")

    assert result is not None
    assert result.id == "4"
    assert result.project_key == "SUP"
    assert result.project_name == "support"
    assert queues_fetcher.jira.get.call_count == 2


def test_get_service_desk_for_project_not_found(queues_fetcher: JiraFetcher):
    """Service desk lookup should return None when project key has no service desk."""
    queues_fetcher.jira.get = MagicMock(
        return_value={"start": 0, "limit": 50, "isLastPage": True, "values": []}
    )

    result = queues_fetcher.get_service_desk_for_project("NOTFOUND")

    assert result is None


def test_get_service_desk_queues_success(queues_fetcher: JiraFetcher):
    """Queue listing should parse queues and pagination metadata."""
    queues_fetcher.jira.get = MagicMock(
        return_value={
            "start": 0,
            "limit": 50,
            "size": 2,
            "isLastPage": True,
            "_links": {"self": "https://test/rest/servicedeskapi/servicedesk/4/queue"},
            "values": [
                {"id": "47", "name": "Support Team", "issueCount": 11},
                {"id": "48", "name": "Waiting for customer", "issueCount": 33},
            ],
        }
    )

    result = queues_fetcher.get_service_desk_queues("4", start_at=0, limit=50)

    assert isinstance(result, JiraServiceDeskQueuesResult)
    assert result.service_desk_id == "4"
    assert result.size == 2
    assert len(result.queues) == 2
    assert result.queues[0].id == "47"
    assert result.queues[0].issue_count == 11


def test_get_queue_issues_success(queues_fetcher: JiraFetcher):
    """Queue issues call should include queue metadata and issue payloads."""
    queues_fetcher.jira.get = MagicMock(
        side_effect=[
            {
                "id": "47",
                "name": "Support Team",
                "issueCount": 11,
                "_links": {"self": "https://test/rest/servicedeskapi/servicedesk/4/47"},
            },
            {
                "start": 0,
                "limit": 2,
                "size": 2,
                "isLastPage": True,
                "values": [
                    {"id": "1", "key": "SUP-1", "fields": {"summary": "Issue 1"}},
                    {"id": "2", "key": "SUP-2", "fields": {"summary": "Issue 2"}},
                ],
            },
        ]
    )

    result = queues_fetcher.get_queue_issues("4", "47", start_at=0, limit=2)

    assert isinstance(result, JiraQueueIssuesResult)
    assert result.service_desk_id == "4"
    assert result.queue_id == "47"
    assert result.queue is not None
    assert result.queue.name == "Support Team"
    assert result.size == 2
    assert len(result.issues) == 2
    assert result.issues[0]["key"] == "SUP-1"


def test_get_queue_issues_invalid_payload_returns_safe_default(
    queues_fetcher: JiraFetcher,
):
    """Invalid queue-issues payload should return an empty safe default."""
    queues_fetcher.jira.get = MagicMock(
        side_effect=[
            {"id": "47", "name": "Support Team", "issueCount": 11},
            "invalid-payload",
        ]
    )

    result = queues_fetcher.get_queue_issues("4", "47", start_at=0, limit=2)

    assert isinstance(result, JiraQueueIssuesResult)
    assert result.queue is not None
    assert result.queue.id == "47"
    assert result.issues == []
    assert result.size == 0


@pytest.fixture
def cloud_queues_fetcher(jira_fetcher: JiraFetcher) -> JiraFetcher:
    """Create a Jira fetcher configured as Cloud for queue rejection testing."""
    fetcher = jira_fetcher
    fetcher.config = MagicMock()
    fetcher.config.is_cloud = True
    return fetcher


@pytest.mark.parametrize(
    "method,args",
    [
        ("get_service_desk_for_project", ("SUP",)),
        ("get_service_desk_queues", ("4",)),
        ("get_queue_issues", ("4", "47")),
    ],
)
def test_queue_methods_reject_cloud(
    cloud_queues_fetcher: JiraFetcher, method: str, args: tuple[str, ...]
) -> None:
    """All queue methods should raise NotImplementedError on Cloud."""
    with pytest.raises(NotImplementedError, match="Server/Data Center"):
        getattr(cloud_queues_fetcher, method)(*args)


# ---------------------------------------------------------------------------
# Service Desk request type + create-request operations
# ---------------------------------------------------------------------------


def test_get_request_types_success(queues_fetcher: JiraFetcher) -> None:
    """Request type listing should parse pagination and request types."""
    queues_fetcher.jira.get = MagicMock(
        return_value={
            "start": 0,
            "limit": 50,
            "size": 1,
            "isLastPage": True,
            "values": [
                {
                    "id": "10100",
                    "name": "Get IT help",
                    "description": "Generic IT help request",
                    "issueTypeId": "10001",
                    "serviceDeskId": "4",
                }
            ],
        }
    )

    result = queues_fetcher.get_request_types("4")

    assert isinstance(result, JiraRequestTypesResult)
    assert result.service_desk_id == "4"
    assert result.size == 1
    assert result.request_types[0].id == "10100"
    assert result.request_types[0].name == "Get IT help"


def test_get_request_types_validates_args(queues_fetcher: JiraFetcher) -> None:
    """Empty service desk id should raise ValueError."""
    with pytest.raises(ValueError):
        queues_fetcher.get_request_types("")


def test_get_request_type_fields_parses_fields(queues_fetcher: JiraFetcher) -> None:
    """Request type field metadata should be parsed into JiraRequestType.fields."""
    queues_fetcher.jira.get = MagicMock(
        return_value={
            "requestTypeFields": [
                {
                    "fieldId": "summary",
                    "name": "Summary",
                    "required": True,
                    "defaultValues": [],
                    "validValues": [],
                },
                {
                    "fieldId": "description",
                    "name": "Description",
                    "required": False,
                },
            ]
        }
    )

    result = queues_fetcher.get_request_type_fields("4", "10100")

    assert isinstance(result, JiraRequestType)
    assert result.id == "10100"
    assert result.service_desk_id == "4"
    assert [f.field_id for f in result.fields] == ["summary", "description"]
    assert result.fields[0].required is True


def test_create_service_desk_request_success(queues_fetcher: JiraFetcher) -> None:
    """Creating a request should POST the expected payload and parse the response."""
    posted: dict[str, Any] = {}

    def _post(path: str, **kwargs: Any) -> dict[str, Any]:
        posted["path"] = path
        posted["kwargs"] = kwargs
        return {
            "issueId": "12345",
            "issueKey": "SUP-7",
            "serviceDesk": {"id": "4"},
            "requestType": {"id": "10100", "name": "Get IT help"},
            "createdDate": {"iso8601": "2026-01-02T03:04:05+0000"},
            "requestFieldValues": [],
        }

    queues_fetcher.jira.post = MagicMock(side_effect=_post)

    result = queues_fetcher.create_service_desk_request(
        service_desk_id="4",
        request_type_id="10100",
        request_field_values={"summary": "Need access", "description": "Please"},
        request_participants=["user1"],
    )

    assert isinstance(result, JiraServiceDeskRequest)
    assert result.issue_key == "SUP-7"
    assert posted["path"] == "rest/servicedeskapi/request"
    payload = posted["kwargs"]["data"]
    assert payload["serviceDeskId"] == "4"
    assert payload["requestTypeId"] == "10100"
    assert payload["requestFieldValues"]["summary"] == "Need access"
    assert payload["requestParticipants"] == ["user1"]
    headers = posted["kwargs"]["headers"]
    assert headers.get("X-ExperimentalApi") == "opt-in"


def test_create_service_desk_request_rejects_empty_field_values(
    queues_fetcher: JiraFetcher,
) -> None:
    """Empty request_field_values should raise ValueError."""
    with pytest.raises(ValueError):
        queues_fetcher.create_service_desk_request(
            service_desk_id="4",
            request_type_id="10100",
            request_field_values={},
        )


def test_add_request_participants_cloud_payload(queues_fetcher: JiraFetcher) -> None:
    """Cloud accounts should be sent via accountIds."""
    queues_fetcher.config.is_cloud = True
    captured: dict[str, Any] = {}

    def _post(path: str, **kwargs: Any) -> dict[str, Any]:
        captured["path"] = path
        captured["data"] = kwargs.get("data")
        return {"ok": True}

    queues_fetcher.jira.post = MagicMock(side_effect=_post)

    result = queues_fetcher.add_request_participants("SUP-7", ["acct-1", "acct-2"])

    assert result == {"ok": True}
    assert captured["path"] == "rest/servicedeskapi/request/SUP-7/participant"
    assert captured["data"] == {"accountIds": ["acct-1", "acct-2"]}


def test_add_request_participants_dc_payload(queues_fetcher: JiraFetcher) -> None:
    """Server/DC participants should be sent via usernames."""
    queues_fetcher.config.is_cloud = False
    captured: dict[str, Any] = {}

    def _post(path: str, **kwargs: Any) -> dict[str, Any]:
        captured["data"] = kwargs.get("data")
        return {"ok": True}

    queues_fetcher.jira.post = MagicMock(side_effect=_post)

    queues_fetcher.add_request_participants("SUP-7", ["alice", "bob"])

    assert captured["data"] == {"usernames": ["alice", "bob"]}


def test_get_request_status_parses_history(queues_fetcher: JiraFetcher) -> None:
    """Status endpoint should parse status entries with iso8601 dates."""
    queues_fetcher.jira.get = MagicMock(
        return_value={
            "start": 0,
            "limit": 50,
            "size": 1,
            "isLastPage": True,
            "values": [
                {
                    "status": "Open",
                    "statusCategory": "NEW",
                    "statusDate": {"iso8601": "2026-01-02T03:04:05+0000"},
                }
            ],
        }
    )

    result = queues_fetcher.get_request_status("SUP-7")

    assert isinstance(result, JiraRequestStatusResult)
    assert result.size == 1
    assert result.statuses[0].status == "Open"
    assert result.statuses[0].status_date == "2026-01-02T03:04:05+0000"


def test_get_request_transitions_parses_payload(queues_fetcher: JiraFetcher) -> None:
    """Transition endpoint should parse available transitions."""
    queues_fetcher.jira.get = MagicMock(
        return_value={
            "start": 0,
            "limit": 50,
            "size": 1,
            "isLastPage": True,
            "values": [{"id": "31", "name": "Resolve"}],
        }
    )

    result = queues_fetcher.get_request_transitions("SUP-7")

    assert isinstance(result, JiraRequestTransitionsResult)
    assert result.transitions[0].id == "31"
    assert result.transitions[0].name == "Resolve"


def test_transition_service_desk_request_posts_payload(
    queues_fetcher: JiraFetcher,
) -> None:
    """Transition should POST id and optional additionalComment."""
    captured: dict[str, Any] = {}

    def _post(path: str, **kwargs: Any) -> dict[str, Any]:
        captured["path"] = path
        captured["data"] = kwargs.get("data")
        return {}

    queues_fetcher.jira.post = MagicMock(side_effect=_post)

    queues_fetcher.transition_service_desk_request(
        "SUP-7", transition_id="31", comment="Done"
    )

    assert captured["path"] == "rest/servicedeskapi/request/SUP-7/transition"
    assert captured["data"] == {"id": "31", "additionalComment": {"body": "Done"}}


def test_attach_temporary_files_uploads_named_pairs(
    queues_fetcher: JiraFetcher, tmp_path: Any
) -> None:
    """attach_temporary_files should upload multiple files and parse the response."""
    file_one = tmp_path / "screenshot.png"
    file_one.write_bytes(b"png-bytes")
    captured: dict[str, Any] = {}

    def _post(path: str, **kwargs: Any) -> dict[str, Any]:
        captured["path"] = path
        captured["files"] = kwargs.get("files")
        captured["headers"] = kwargs.get("headers")
        return {
            "temporaryAttachments": [
                {"temporaryAttachmentId": "tmp-1", "fileName": "screenshot.png"}
            ]
        }

    queues_fetcher.jira.post = MagicMock(side_effect=_post)

    result = queues_fetcher.attach_temporary_files("4", [str(file_one)])

    assert len(result) == 1
    assert isinstance(result[0], JiraTemporaryAttachment)
    assert result[0].temporary_attachment_id == "tmp-1"
    assert captured["path"].endswith("/attachTemporaryFile")
    assert captured["headers"].get("X-Atlassian-Token") == "no-check"
    # files is a list of (field_name, (filename, fh)) tuples
    assert captured["files"][0][0] == "file"
    assert captured["files"][0][1][0] == "screenshot.png"


def test_attach_temporary_files_missing_path(queues_fetcher: JiraFetcher) -> None:
    """Missing file path should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        queues_fetcher.attach_temporary_files("4", ["/tmp/does-not-exist-12345.txt"])


def test_create_request_attachment_posts_expected_payload(
    queues_fetcher: JiraFetcher,
) -> None:
    """create_request_attachment should POST temporary ids and comment."""
    captured: dict[str, Any] = {}

    def _post(path: str, **kwargs: Any) -> dict[str, Any]:
        captured["path"] = path
        captured["data"] = kwargs.get("data")
        return {"ok": True}

    queues_fetcher.jira.post = MagicMock(side_effect=_post)

    result = queues_fetcher.create_request_attachment(
        issue_key="SUP-7",
        temporary_attachment_ids=["tmp-1", "tmp-2"],
        public=False,
        comment="see attached",
    )

    assert result == {"ok": True}
    assert captured["path"] == "rest/servicedeskapi/request/SUP-7/attachment"
    assert captured["data"]["temporaryAttachmentIds"] == ["tmp-1", "tmp-2"]
    assert captured["data"]["public"] is False
    assert captured["data"]["additionalComment"] == {"body": "see attached"}
