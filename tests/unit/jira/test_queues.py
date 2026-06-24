"""Tests for Jira Service Management queue read operations."""

from unittest.mock import MagicMock

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


class TestJiraServiceManagementTools:
    """JSM tools exist and return structured data when mocked.

    Regression for https://github.com/sooperset/mcp-atlassian/issues/447
    """

    def test_get_service_desk_for_project_exists(
        self, queues_fetcher: JiraFetcher
    ) -> None:
        """get_service_desk_for_project is implemented on JiraFetcher."""
        assert hasattr(queues_fetcher, "get_service_desk_for_project")
        assert callable(queues_fetcher.get_service_desk_for_project)

    def test_get_service_desk_queues_exists(self, queues_fetcher: JiraFetcher) -> None:
        """get_service_desk_queues is implemented on JiraFetcher."""
        assert hasattr(queues_fetcher, "get_service_desk_queues")
        assert callable(queues_fetcher.get_service_desk_queues)

    def test_get_queue_issues_exists(self, queues_fetcher: JiraFetcher) -> None:
        """get_queue_issues is implemented on JiraFetcher."""
        assert hasattr(queues_fetcher, "get_queue_issues")
        assert callable(queues_fetcher.get_queue_issues)

    def test_get_service_desk_for_project_returns_model(
        self, queues_fetcher: JiraFetcher
    ) -> None:
        """get_service_desk_for_project returns a JiraServiceDesk model when found."""
        from mcp_atlassian.models.jira import JiraServiceDesk

        queues_fetcher.jira.get = MagicMock(
            return_value={
                "start": 0,
                "limit": 50,
                "isLastPage": True,
                "values": [
                    {
                        "id": "1",
                        "projectKey": "HELP",
                        "projectId": "10001",
                        "projectName": "Help Desk",
                    }
                ],
            }
        )
        result = queues_fetcher.get_service_desk_for_project("HELP")
        assert isinstance(result, JiraServiceDesk)
        assert result.project_key == "HELP"

    def test_get_service_desk_queues_returns_structured_result(
        self, queues_fetcher: JiraFetcher
    ) -> None:
        """get_service_desk_queues returns JiraServiceDeskQueuesResult."""
        queues_fetcher.jira.get = MagicMock(
            return_value={
                "start": 0,
                "limit": 50,
                "size": 1,
                "isLastPage": True,
                "values": [{"id": "10", "name": "Open Issues", "issueCount": 5}],
            }
        )
        result = queues_fetcher.get_service_desk_queues("1")
        assert isinstance(result, JiraServiceDeskQueuesResult)
        assert result.service_desk_id == "1"
        assert len(result.queues) == 1
        assert result.queues[0].name == "Open Issues"

    def test_get_queue_issues_returns_structured_result(
        self, queues_fetcher: JiraFetcher
    ) -> None:
        """get_queue_issues returns JiraQueueIssuesResult with issues list."""
        queues_fetcher.jira.get = MagicMock(
            side_effect=[
                {"id": "10", "name": "Open Issues", "issueCount": 1},
                {
                    "start": 0,
                    "limit": 50,
                    "size": 1,
                    "isLastPage": True,
                    "values": [
                        {
                            "id": "100",
                            "key": "HELP-1",
                            "fields": {"summary": "Need help"},
                        }
                    ],
                },
            ]
        )
        result = queues_fetcher.get_queue_issues("1", "10")
        assert isinstance(result, JiraQueueIssuesResult)
        assert result.service_desk_id == "1"
        assert result.queue_id == "10"
        assert len(result.issues) == 1
        assert result.issues[0]["key"] == "HELP-1"
