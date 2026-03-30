"""Tests for Jira Service Management customer request operations."""

from unittest.mock import MagicMock

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.models.jira import (
    JiraCustomerRequest,
    JiraRequestTypeFieldsResult,
    JiraRequestTypesResult,
)


def _make_customer_requests_fetcher(jira_fetcher: JiraFetcher) -> JiraFetcher:
    """Create a Jira fetcher configured for JSM customer request tests."""
    fetcher = jira_fetcher
    fetcher.config = MagicMock()
    fetcher.config.is_cloud = False
    fetcher.config.url = "https://jira.example.com"
    fetcher.jira.default_headers = {"Accept": "application/json"}
    return fetcher


def test_get_request_types_success(jira_fetcher: JiraFetcher) -> None:
    """Request type listing should parse values and pagination metadata."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(
        return_value={
            "start": 0,
            "limit": 50,
            "size": 2,
            "isLastPage": True,
            "values": [
                {
                    "id": "23",
                    "name": "Incident",
                    "description": "Report an incident",
                    "helpText": "Use this for production incidents",
                },
                {
                    "id": "24",
                    "name": "Access Request",
                },
            ],
        }
    )

    result = fetcher.get_request_types("4")

    assert isinstance(result, JiraRequestTypesResult)
    assert result.service_desk_id == "4"
    assert result.size == 2
    assert len(result.request_types) == 2
    assert result.request_types[0].id == "23"
    assert result.request_types[0].help_text == "Use this for production incidents"


def test_get_request_type_fields_success(jira_fetcher: JiraFetcher) -> None:
    """Request type field discovery should expose schema and capability flags."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(
        return_value={
            "canRaiseOnBehalfOf": True,
            "canAddRequestParticipants": False,
            "requestTypeFields": [
                {
                    "fieldId": "summary",
                    "name": "Summary",
                    "description": "Short summary",
                    "required": True,
                    "visible": True,
                    "jiraSchema": {"type": "string"},
                },
                {
                    "fieldId": "customfield_10001",
                    "name": "Approvers",
                    "required": False,
                    "jiraSchema": {"type": "array"},
                    "validValues": ["alice", "bob"],
                },
            ],
        }
    )

    result = fetcher.get_request_type_fields("4", "23")

    assert isinstance(result, JiraRequestTypeFieldsResult)
    assert result.service_desk_id == "4"
    assert result.request_type_id == "23"
    assert result.can_raise_on_behalf_of is True
    assert result.can_add_request_participants is False
    assert len(result.fields) == 2
    assert result.fields[1].supports_multiple is True
    assert result.fields[1].valid_values == ["alice", "bob"]


def test_create_customer_request_success(jira_fetcher: JiraFetcher) -> None:
    """Customer request creation should format fields and return portal URL."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(
        return_value={
            "requestTypeFields": [
                {
                    "fieldId": "customfield_10001",
                    "name": "Approvers",
                    "required": False,
                    "jiraSchema": {"type": "array"},
                }
            ]
        }
    )
    fetcher.jira.post = MagicMock(
        return_value={
            "issueId": "10010",
            "issueKey": "SUP-101",
            "_links": {"web": "/servicedesk/customer/portal/4/SUP-101"},
        }
    )

    result = fetcher.create_customer_request(
        service_desk_id="4",
        request_type_id="23",
        request_field_values={
            "summary": "Production incident",
            "customfield_10001": "alice,bob",
        },
        raise_on_behalf_of="d.zagitov",
        request_participants=["ops-team"],
    )

    assert isinstance(result, JiraCustomerRequest)
    assert result.request_id == "10010"
    assert result.request_key == "SUP-101"
    assert (
        result.portal_url
        == "https://jira.example.com/servicedesk/customer/portal/4/SUP-101"
    )
    assert result.created_mode == "created_on_behalf_of"
    assert result.on_behalf_user == "d.zagitov"
    assert result.request_participants == ["ops-team"]

    post_payload = fetcher.jira.post.call_args.kwargs["data"]
    assert post_payload["raiseOnBehalfOf"] == "d.zagitov"
    assert post_payload["requestFieldValues"]["customfield_10001"] == ["alice", "bob"]


def test_create_customer_request_retries_without_on_behalf(
    jira_fetcher: JiraFetcher,
) -> None:
    """Non-strict on-behalf mode should retry without raiseOnBehalfOf."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value={"requestTypeFields": []})
    fetcher.jira.post = MagicMock(
        side_effect=[
            Exception("403 Client Error: Forbidden for raiseOnBehalfOf"),
            {
                "issueId": "10011",
                "issueKey": "SUP-102",
                "_links": {"web": "/servicedesk/customer/portal/4/SUP-102"},
            },
        ]
    )

    result = fetcher.create_customer_request(
        service_desk_id="4",
        request_type_id="23",
        request_field_values={"summary": "Fallback test"},
        raise_on_behalf_of="d.zagitov",
        strict_on_behalf=False,
    )

    assert result.created_mode == "created_as_agent_fallback"
    assert result.request_key == "SUP-102"
    assert result.warnings
    assert "raise_on_behalf_of" in result.warnings[0]

    first_payload = fetcher.jira.post.call_args_list[0].kwargs["data"]
    second_payload = fetcher.jira.post.call_args_list[1].kwargs["data"]
    assert "raiseOnBehalfOf" in first_payload
    assert "raiseOnBehalfOf" not in second_payload


def test_create_customer_request_strict_on_behalf_raises(
    jira_fetcher: JiraFetcher,
) -> None:
    """Strict on-behalf mode should not retry silently."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value={"requestTypeFields": []})
    fetcher.jira.post = MagicMock(
        side_effect=Exception("403 Client Error: Forbidden for raiseOnBehalfOf")
    )

    try:
        fetcher.create_customer_request(
            service_desk_id="4",
            request_type_id="23",
            request_field_values={"summary": "Strict test"},
            raise_on_behalf_of="d.zagitov",
            strict_on_behalf=True,
        )
    except Exception as exc:
        assert "Forbidden" in str(exc)
    else:
        raise AssertionError("Expected strict on-behalf mode to raise an exception")
