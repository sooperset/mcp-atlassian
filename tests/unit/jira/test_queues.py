"""Tests for Jira Service Management queue read operations."""

from unittest.mock import MagicMock, call

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.models.jira import JiraQueueIssuesResult, JiraServiceDeskQueuesResult


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
    assert queues_fetcher.jira.get.call_args_list == [
        call(
            "rest/servicedeskapi/servicedesk",
            params={"start": 0, "limit": 50},
        ),
        call(
            "rest/servicedeskapi/servicedesk",
            params={"start": 1, "limit": 50},
        ),
    ]


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
    queues_fetcher.jira.get.assert_called_once_with(
        "rest/servicedeskapi/servicedesk/4/queue",
        params={"start": 0, "limit": 50, "includeCount": "true"},
    )


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
    assert queues_fetcher.jira.get.call_args_list == [
        call(
            "rest/servicedeskapi/servicedesk/4/queue/47",
            params={"includeCount": "true"},
        ),
        call(
            "rest/servicedeskapi/servicedesk/4/queue/47/issue",
            params={"start": 0, "limit": 2},
        ),
    ]


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


@pytest.mark.parametrize(
    "method,args,error",
    [
        ("get_service_desk_for_project", ("",), "Project key is required"),
        ("get_service_desk_queues", ("",), "Service desk ID is required"),
        ("get_service_desk_queues", ("4", -1), "start_at must be >= 0"),
        ("get_service_desk_queues", ("4", 0, 0), "limit must be >= 1"),
        ("get_queue_issues", ("", "47"), "Service desk ID is required"),
        ("get_queue_issues", ("4", ""), "Queue ID is required"),
        ("get_queue_issues", ("4", "47", -1), "start_at must be >= 0"),
        ("get_queue_issues", ("4", "47", 0, 0), "limit must be >= 1"),
    ],
)
def test_queue_methods_validate_input(
    queues_fetcher: JiraFetcher,
    method: str,
    args: tuple[object, ...],
    error: str,
) -> None:
    """Queue methods should reject invalid identifiers and pagination values."""
    with pytest.raises(ValueError, match=error):
        getattr(queues_fetcher, method)(*args)


@pytest.mark.security_regression
def test_queue_issues_are_filtered_by_the_project_allowlist() -> None:
    import json

    from mcp_atlassian.jira import JiraConfig

    fetcher = JiraFetcher(
        config=JiraConfig(
            url="https://jira.example.test",
            auth_type="pat",
            personal_token="dummy",
            projects_filter="ALLOWED",
        )
    )
    backend = MagicMock(spec_set=["get"])

    def get(path: str, params: dict | None = None) -> dict:
        if path.endswith("/issue"):
            return {
                "size": 2,
                "values": [
                    {
                        "key": "ALLOWED-1",
                        "fields": {
                            "summary": "in scope",
                            "project": {"key": "ALLOWED"},
                            "issuelinks": [
                                {
                                    "outwardIssue": {
                                        "key": "SECRET-7",
                                        "fields": {"summary": "SECRET-SUMMARY"},
                                    }
                                },
                                {"outwardIssue": {"key": "ALLOWED-2"}},
                            ],
                            "parent": {"key": "SECRET-3"},
                            "subtasks": [{"key": "SECRET-4"}],
                        },
                    },
                    {"key": "SECRET-1", "fields": {"summary": "SECRET-ONE"}},
                ],
            }
        if path.endswith("/queue"):
            return {
                "values": [
                    {
                        "id": "99",
                        "name": "Queue",
                        "jql": "project = SECRET",
                        "issueCount": 7,
                    }
                ]
            }
        return {"id": "99", "name": "Queue", "jql": "project = SECRET", "issueCount": 7}

    backend.get.side_effect = get
    fetcher.jira = backend

    result = fetcher.get_queue_issues("4", "99").to_simplified_dict()
    text = json.dumps(result)

    assert [i["key"] for i in result["issues"]] == ["ALLOWED-1"]
    for leaked in ("SECRET-1", "SECRET-ONE", "SECRET-7", "SECRET-3", "SECRET-4"):
        assert leaked not in text, leaked
    assert "ALLOWED-2" in text
    assert result["queue"]["issue_count"] == 1
    assert "jql" not in result["queue"] or result["queue"]["jql"] is None

    listing = fetcher.get_service_desk_queues("4").to_simplified_dict()
    assert "SECRET" not in json.dumps(listing)
    assert all(q.get("issue_count") is None for q in listing["queues"])


def _queue_fetcher(issues_response: object) -> JiraFetcher:
    from mcp_atlassian.jira import JiraConfig

    fetcher = JiraFetcher(
        config=JiraConfig(
            url="https://jira.example.test",
            auth_type="pat",
            personal_token="dummy",
            projects_filter="ALLOWED",
        )
    )
    backend = MagicMock(spec_set=["get", "get_all_fields"])
    backend.get_all_fields.return_value = [
        {
            "id": "customfield_10800",
            "name": "Notes",
            "schema": {
                "type": "string",
                "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
            },
        }
    ]

    def get(path: str, params: dict | None = None) -> object:
        if path.endswith("/issue"):
            if isinstance(issues_response, Exception):
                raise issues_response
            return issues_response
        return {"id": "99", "name": "Q", "jql": "project = SECRET", "issueCount": 123}

    backend.get.side_effect = get
    fetcher.jira = backend
    return fetcher


@pytest.mark.security_regression
@pytest.mark.parametrize(
    "issues_response", [{}, None, RuntimeError("boom")], ids=["empty", "none", "error"]
)
def test_queue_metadata_is_cleaned_on_every_return_path(issues_response) -> None:
    import json

    result = _queue_fetcher(issues_response).get_queue_issues("4", "99")
    text = json.dumps(result.to_simplified_dict())

    assert "SECRET" not in text
    assert "123" not in text


@pytest.mark.security_regression
def test_queue_keeps_text_field_values() -> None:
    fetcher = _queue_fetcher(
        {
            "values": [
                {
                    "key": "ALLOWED-1",
                    "fields": {
                        "project": {"key": "ALLOWED"},
                        "customfield_10800": "SECRET-7",
                    },
                }
            ]
        }
    )

    result = fetcher.get_queue_issues("4", "99").to_simplified_dict()

    assert result["issues"][0]["fields"]["customfield_10800"] == "SECRET-7"
