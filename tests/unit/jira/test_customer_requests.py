"""Tests for Jira Service Management customer request operations."""

from unittest.mock import MagicMock

import pytest
from requests.exceptions import HTTPError

import mcp_atlassian.jira.customer_requests as customer_requests_module
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.models.jira import (
    JiraCustomerRequest,
    JiraCustomerRequestDetails,
    JiraRequestApproval,
    JiraRequestApprovalsResult,
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


def _make_http_error(
    *,
    status_code: int = 400,
    errors: dict[str, str] | None = None,
    error_messages: list[str] | None = None,
    text: str = "Bad Request",
) -> HTTPError:
    """Create an HTTPError with a mocked JSON response body."""
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = {
        "errors": errors or {},
        "errorMessages": error_messages or [],
    }
    return HTTPError(response=response)


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


def test_get_request_type_fields_propagates_api_errors(
    jira_fetcher: JiraFetcher,
) -> None:
    """Field discovery failures must not look like a valid empty field set."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(side_effect=_make_http_error(status_code=403))

    with pytest.raises(HTTPError):
        fetcher.get_request_type_fields("4", "23")


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


def test_create_customer_request_normalizes_select_value_to_option_id(
    jira_fetcher: JiraFetcher,
) -> None:
    """Select-like JSM fields should normalize semantic input to canonical payload."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(
        return_value={
            "requestTypeFields": [
                {
                    "fieldId": "customfield_17902",
                    "name": "Витрина",
                    "required": False,
                    "visible": True,
                    "jiraSchema": {
                        "type": "option",
                        "custom": (
                            "com.atlassian.jira.plugin.system.customfieldtypes:select"
                        ),
                    },
                    "validValues": [
                        {
                            "value": "21721",
                            "label": "users",
                        }
                    ],
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

    fetcher.create_customer_request(
        service_desk_id="4",
        request_type_id="23",
        request_field_values={
            "summary": "Production incident",
            "customfield_17902": {"value": "21721"},
        },
    )

    post_payload = fetcher.jira.post.call_args.kwargs["data"]
    assert post_payload["requestFieldValues"]["customfield_17902"] == {"id": "21721"}


def test_create_customer_request_normalizes_radio_button_value(
    jira_fetcher: JiraFetcher,
) -> None:
    """JSM radio buttons should use the option object expected by Jira."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(
        return_value={
            "requestTypeFields": [
                {
                    "fieldId": "customfield_10001",
                    "name": "Gifts",
                    "required": True,
                    "visible": True,
                    "jiraSchema": {
                        "type": "string",
                        "custom": (
                            "com.atlassian.jira.plugin.system."
                            "customfieldtypes:radiobuttons"
                        ),
                    },
                    "validValues": [{"value": "10000", "label": "Bottle of Wine"}],
                }
            ]
        }
    )
    fetcher.jira.post = MagicMock(
        return_value={"issueId": "10010", "issueKey": "SUP-101"}
    )

    fetcher.create_customer_request(
        service_desk_id="4",
        request_type_id="23",
        request_field_values={"customfield_10001": "Bottle of Wine"},
    )

    post_payload = fetcher.jira.post.call_args.kwargs["data"]
    assert post_payload["requestFieldValues"]["customfield_10001"] == {"id": "10000"}


def test_create_customer_request_rejects_unknown_select_value_before_post(
    jira_fetcher: JiraFetcher,
) -> None:
    """Unknown select values should fail with a traceable field-level error."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(
        return_value={
            "requestTypeFields": [
                {
                    "fieldId": "customfield_17902",
                    "name": "Витрина",
                    "required": False,
                    "visible": True,
                    "jiraSchema": {
                        "type": "option",
                        "custom": (
                            "com.atlassian.jira.plugin.system.customfieldtypes:select"
                        ),
                    },
                    "validValues": [
                        {
                            "value": "21721",
                            "label": "users",
                        }
                    ],
                }
            ]
        }
    )
    fetcher.jira.post = MagicMock()

    with pytest.raises(ValueError) as exc_info:
        fetcher.create_customer_request(
            service_desk_id="4",
            request_type_id="23",
            request_field_values={
                "summary": "Production incident",
                "customfield_17902": "unknown-datamart",
            },
        )

    error_message = str(exc_info.value)
    assert "JSM_CUSTOMER_REQUEST_FIELD_ERROR" in error_message
    assert "service_desk_id=4 request_type_id=23" in error_message
    assert "field_id=customfield_17902" in error_message
    assert "allowed_values=users" in error_message
    fetcher.jira.post.assert_not_called()


def test_create_customer_request_validates_visible_required_fields(
    jira_fetcher: JiraFetcher,
) -> None:
    """Missing visible required fields should fail before calling the API."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(
        return_value={
            "requestTypeFields": [
                {
                    "fieldId": "summary",
                    "name": "Summary",
                    "required": True,
                    "visible": True,
                    "jiraSchema": {"type": "string"},
                },
                {
                    "fieldId": "hidden_field",
                    "name": "Hidden Field",
                    "required": True,
                    "visible": False,
                    "jiraSchema": {"type": "string"},
                },
            ]
        }
    )
    fetcher.jira.post = MagicMock()

    with pytest.raises(ValueError) as exc_info:
        fetcher.create_customer_request(
            service_desk_id="4",
            request_type_id="23",
            request_field_values={},
        )

    error_message = str(exc_info.value)
    assert "JSM_CUSTOMER_REQUEST_MISSING_REQUIRED_FIELDS" in error_message
    assert "Summary (summary)" in error_message
    assert "Hidden Field" not in error_message
    fetcher.jira.post.assert_not_called()


def test_create_customer_request_retries_without_on_behalf(
    jira_fetcher: JiraFetcher,
) -> None:
    """Non-strict on-behalf mode should retry without raiseOnBehalfOf."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value={"requestTypeFields": []})
    fetcher.jira.post = MagicMock(
        side_effect=[
            _make_http_error(
                errors={"raiseOnBehalfOf": "Unknown user"},
                text="raiseOnBehalfOf rejected",
            ),
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


def test_create_customer_request_does_not_retry_for_field_http_error(
    jira_fetcher: JiraFetcher,
) -> None:
    """Field validation API errors must not trigger on-behalf fallback retries."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value={"requestTypeFields": []})
    fetcher.jira.post = MagicMock(
        side_effect=_make_http_error(
            errors={
                "customfield_17902": (
                    "Could not find valid 'id' or 'value' in the Parent Option object."
                )
            },
            text="customfield_17902 rejected",
        )
    )

    with pytest.raises(ValueError) as exc_info:
        fetcher.create_customer_request(
            service_desk_id="4",
            request_type_id="23",
            request_field_values={
                "summary": "Fallback test",
                "customfield_17902": "21721",
            },
            raise_on_behalf_of="d.zagitov",
            strict_on_behalf=False,
        )

    error_message = str(exc_info.value)
    assert "JSM_CUSTOMER_REQUEST_HTTP_ERROR" in error_message
    assert "status=400" in error_message
    assert "customfield_17902" in error_message
    assert fetcher.jira.post.call_count == 1


def test_create_customer_request_strict_on_behalf_raises(
    jira_fetcher: JiraFetcher,
) -> None:
    """Strict on-behalf mode should not retry silently."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value={"requestTypeFields": []})
    fetcher.jira.post = MagicMock(
        side_effect=_make_http_error(
            errors={"raiseOnBehalfOf": "Unknown user"},
            text="raiseOnBehalfOf rejected",
        )
    )

    with pytest.raises(ValueError) as exc_info:
        fetcher.create_customer_request(
            service_desk_id="4",
            request_type_id="23",
            request_field_values={"summary": "Strict test"},
            raise_on_behalf_of="d.zagitov",
            strict_on_behalf=True,
        )

    assert "JSM_CUSTOMER_REQUEST_HTTP_ERROR" in str(exc_info.value)
    assert fetcher.jira.post.call_count == 1


def test_create_customer_request_does_not_retry_non_http_errors(
    jira_fetcher: JiraFetcher,
) -> None:
    """Ambiguous client errors must not trigger a second write request."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value={"requestTypeFields": []})
    fetcher.jira.post = MagicMock(side_effect=ValueError("unknown user"))

    with pytest.raises(ValueError, match="unknown user"):
        fetcher.create_customer_request(
            service_desk_id="4",
            request_type_id="23",
            request_field_values={"summary": "No retry"},
            raise_on_behalf_of="d.zagitov",
        )

    fetcher.jira.post.assert_called_once()


def _make_session_response(payload: dict) -> MagicMock:
    """Build a mocked requests.Response for multipart uploads."""
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    return response


def test_attach_temporary_files_uploads_and_returns_ids(
    jira_fetcher: JiraFetcher,
) -> None:
    """Temporary upload should send multipart data and return attachment IDs."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.url = "https://api.atlassian.com/ex/jira/cloud-id"
    fetcher.jira._session = MagicMock()
    fetcher.jira._session.post = MagicMock(
        return_value=_make_session_response(
            {"temporaryAttachments": [{"temporaryAttachmentId": "temp-1"}]}
        )
    )

    result = fetcher.attach_temporary_files(
        "4",
        [{"filename": "log.txt", "mime_type": "text/plain", "base64": "aGVsbG8="}],
    )

    assert result == ["temp-1"]
    call = fetcher.jira._session.post.call_args
    assert call.args[0] == (
        "https://api.atlassian.com/ex/jira/cloud-id/"
        "rest/servicedeskapi/servicedesk/4/attachTemporaryFile"
    )
    assert call.kwargs["headers"]["X-Atlassian-Token"] == "no-check"
    assert "Content-Type" not in call.kwargs["headers"]
    uploaded_files = call.kwargs["files"]
    assert uploaded_files[0][0] == "file"
    assert uploaded_files[0][1] == ("log.txt", b"hello", "text/plain")


def test_decode_attachment_file_rejects_invalid_base64(
    jira_fetcher: JiraFetcher,
) -> None:
    """Invalid base64 content should raise a descriptive ValueError."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)

    with pytest.raises(ValueError, match="invalid base64 content"):
        fetcher._decode_attachment_file(
            {"filename": "bad.txt", "mime_type": "text/plain", "base64": "!!!"}
        )


def test_decode_attachment_file_rejects_oversized_content(
    jira_fetcher: JiraFetcher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inline attachments must respect the shared in-memory size limit."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    monkeypatch.setattr(customer_requests_module, "ATTACHMENT_MAX_BYTES", 4)

    with pytest.raises(ValueError, match="exceeds the 0 MiB inline limit"):
        fetcher._decode_attachment_file(
            {"filename": "big.txt", "mime_type": "text/plain", "base64": "aGVsbG8="}
        )


def test_create_customer_request_validates_attachments_before_post(
    jira_fetcher: JiraFetcher,
) -> None:
    """Malformed attachment input must fail before the request is created."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value={"requestTypeFields": []})
    fetcher.jira.post = MagicMock()

    with pytest.raises(ValueError, match="invalid base64 content"):
        fetcher.create_customer_request(
            service_desk_id="4",
            request_type_id="23",
            request_field_values={"summary": "Invalid attachment"},
            attachments=[
                {"filename": "bad.txt", "mime_type": "text/plain", "base64": "!!!"}
            ],
        )

    fetcher.jira.post.assert_not_called()


def test_create_customer_request_attaches_files(
    jira_fetcher: JiraFetcher,
) -> None:
    """Created requests should upload and attach provided base64 files."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value={"requestTypeFields": []})
    fetcher.jira._session = MagicMock()
    fetcher.jira._session.post = MagicMock(
        return_value=_make_session_response(
            {"temporaryAttachments": [{"temporaryAttachmentId": "temp-1"}]}
        )
    )
    fetcher.jira.post = MagicMock(
        side_effect=[
            {"issueId": "10010", "issueKey": "SUP-101"},
            {"id": "20001"},
        ]
    )

    result = fetcher.create_customer_request(
        service_desk_id="4",
        request_type_id="23",
        request_field_values={"summary": "With attachment"},
        attachments=[
            {"filename": "log.txt", "mime_type": "text/plain", "base64": "aGVsbG8="}
        ],
    )

    assert result.request_key == "SUP-101"
    assert result.warnings == []
    fetcher.jira._session.post.assert_called_once()
    assert fetcher.jira.post.call_count == 2
    attach_call = fetcher.jira.post.call_args_list[1]
    assert attach_call.args[0] == "rest/servicedeskapi/request/SUP-101/attachment"
    assert attach_call.kwargs["data"]["temporaryAttachmentIds"] == ["temp-1"]
    assert attach_call.kwargs["data"]["public"] is True


def test_create_customer_request_attachment_failure_adds_warning(
    jira_fetcher: JiraFetcher,
) -> None:
    """Attachment failures must not break a successfully created request."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value={"requestTypeFields": []})
    fetcher.jira._session = MagicMock()
    fetcher.jira._session.post = MagicMock(
        side_effect=_make_http_error(status_code=413, text="Payload Too Large")
    )
    fetcher.jira.post = MagicMock(
        return_value={"issueId": "10010", "issueKey": "SUP-101"}
    )

    result = fetcher.create_customer_request(
        service_desk_id="4",
        request_type_id="23",
        request_field_values={"summary": "With attachment"},
        attachments=[
            {"filename": "log.txt", "mime_type": "text/plain", "base64": "aGVsbG8="}
        ],
    )

    assert result.request_key == "SUP-101"
    assert len(result.warnings) == 1
    assert "JSM_CUSTOMER_REQUEST_ATTACH_ERROR" in result.warnings[0]
    assert "issue_key=SUP-101" in result.warnings[0]
    assert fetcher.jira.post.call_count == 1


EXPERIMENTAL_HEADER = {"X-ExperimentalApi": "opt-in"}


def _servicedesk_date(iso: str) -> dict:
    """Build a Service Management date object."""
    return {"iso8601": iso, "jira": iso, "friendly": "Today", "epochMillis": 0}


def _servicedesk_user(name: str, display_name: str) -> dict:
    """Build a Service Management user payload with noisy metadata."""
    return {
        "name": name,
        "key": name,
        "emailAddress": f"{name}@example.com",
        "displayName": display_name,
        "active": True,
        "timeZone": "UTC",
        "avatarUrls": {"48x48": "https://jira.example.com/avatar.png"},
        "_links": {"self": "https://jira.example.com/rest/api/2/user"},
    }


def _approval_payload(
    approval_id: str = "42",
    final_decision: str = "pending",
    can_answer: bool = True,
) -> dict:
    """Build an approval payload as returned by the approval endpoints."""
    return {
        "id": approval_id,
        "name": "Manager approval",
        "finalDecision": final_decision,
        "canAnswerApproval": can_answer,
        "approvers": [
            {
                "approver": _servicedesk_user("jdoe", "Jane Doe"),
                "approverDecision": "pending",
            }
        ],
        "createdDate": _servicedesk_date("2026-01-05T10:00:00+0000"),
        "_links": {"self": "https://jira.example.com/rest/servicedeskapi/x"},
    }


def _approvals_page(*approvals: dict) -> dict:
    """Wrap approvals in a paged response."""
    return {
        "start": 0,
        "limit": 50,
        "size": len(approvals),
        "isLastPage": True,
        "values": list(approvals),
    }


def _request_payload(issue_key: str, summary: str = "Contract review") -> dict:
    """Build a customer request payload."""
    return {
        "issueId": "10001",
        "issueKey": issue_key,
        "requestTypeId": "23",
        "serviceDeskId": "4",
        "requestType": {
            "id": "23",
            "name": "Document approval",
            "_links": {"self": "https://jira.example.com/x"},
        },
        "createdDate": _servicedesk_date("2026-01-05T09:00:00+0000"),
        "reporter": _servicedesk_user("asmith", "Alex Smith"),
        "currentStatus": {
            "status": "Waiting for approval",
            "statusDate": _servicedesk_date("2026-01-05T09:30:00+0000"),
        },
        "requestFieldValues": [
            {"fieldId": "summary", "label": "Summary", "value": summary},
            {
                "fieldId": "customfield_10010",
                "label": "Department",
                "value": {
                    "self": "https://jira.example.com/x",
                    "value": "Finance",
                    "id": "1",
                },
            },
            {
                "fieldId": "attachment",
                "label": "Attachment",
                "value": [
                    {
                        "self": "https://jira.example.com/x",
                        "id": "500",
                        "filename": "contract.pdf",
                        "author": _servicedesk_user("asmith", "Alex Smith"),
                        "size": 1024,
                        "mimeType": "application/pdf",
                        "content": "https://jira.example.com/secure/500",
                    }
                ],
            },
        ],
        "participants": {
            "size": 1,
            "start": 0,
            "limit": 50,
            "isLastPage": True,
            "values": [_servicedesk_user("bwong", "Bo Wong")],
        },
        "_links": {
            "web": "https://jira.example.com/servicedesk/customer/portal/4/PROJ-1",
            "self": "https://jira.example.com/rest/servicedeskapi/request/10001",
        },
    }


def _request_list_page(issue_keys: list[str], *, is_last_page: bool = True) -> dict:
    """Wrap customer requests in a paged list response."""
    return {
        "start": 0,
        "limit": 50,
        "size": len(issue_keys),
        "isLastPage": is_last_page,
        "values": [_request_payload(key) for key in issue_keys],
    }


def test_get_customer_request_returns_compact_details(
    jira_fetcher: JiraFetcher,
) -> None:
    """Customer request reads should drop links and avatars."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value=_request_payload("PROJ-1"))

    result = fetcher.get_customer_request(" PROJ-1 ")

    assert isinstance(result, JiraCustomerRequestDetails)
    fetcher.jira.get.assert_called_once_with(
        "rest/servicedeskapi/request/PROJ-1",
        params={"expand": "participant,status,requestType"},
        headers={"Accept": "application/json", **EXPERIMENTAL_HEADER},
    )
    simplified = result.to_simplified_dict()
    assert simplified["issue_key"] == "PROJ-1"
    assert simplified["request_type"] == {"id": "23", "name": "Document approval"}
    assert simplified["status"] == "Waiting for approval"
    assert simplified["reporter"]["display_name"] == "Alex Smith"
    assert simplified["participants"][0]["name"] == "bwong"
    assert simplified["portal_url"].endswith("/portal/4/PROJ-1")
    values = {field["field_id"]: field["value"] for field in simplified["fields"]}
    assert values["summary"] == "Contract review"
    assert values["customfield_10010"] == "Finance"
    assert values["attachment"] == [
        {
            "filename": "contract.pdf",
            "id": "500",
            "mime_type": "application/pdf",
            "size": 1024,
        }
    ]
    serialized = str(simplified)
    assert "avatarUrls" not in serialized
    assert "_links" not in serialized


def test_get_customer_request_requires_issue_key(jira_fetcher: JiraFetcher) -> None:
    """A blank issue key should fail before any API call."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock()

    with pytest.raises(ValueError, match="Issue key is required"):
        fetcher.get_customer_request("  ")

    fetcher.jira.get.assert_not_called()


@pytest.mark.parametrize(
    ("status_code", "hint"),
    [
        (403, "not allowed to view"),
        (404, "does not exist or is not visible"),
        (412, "experimental API opt-in"),
    ],
)
def test_get_customer_request_explains_http_errors(
    jira_fetcher: JiraFetcher,
    status_code: int,
    hint: str,
) -> None:
    """HTTP failures should surface the status code and a readable hint."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(
        side_effect=_make_http_error(
            status_code=status_code,
            error_messages=["Jira said no"],
        )
    )

    with pytest.raises(ValueError, match=f"HTTP {status_code}") as exc_info:
        fetcher.get_customer_request("PROJ-1")

    assert hint in str(exc_info.value)
    assert "Jira said no" in str(exc_info.value)


@pytest.mark.parametrize("is_cloud", [False, True])
def test_get_request_approvals_sends_experimental_header(
    jira_fetcher: JiraFetcher,
    is_cloud: bool,
) -> None:
    """Approval reads need the experimental opt-in on Server/Data Center."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.config.is_cloud = is_cloud
    fetcher.jira.get = MagicMock(return_value=_approvals_page(_approval_payload()))

    result = fetcher.get_request_approvals("PROJ-1", start_at=0, limit=10)

    assert isinstance(result, JiraRequestApprovalsResult)
    fetcher.jira.get.assert_called_once_with(
        "rest/servicedeskapi/request/PROJ-1/approval",
        params={"start": 0, "limit": 10},
        headers={"Accept": "application/json", **EXPERIMENTAL_HEADER},
    )
    approval = result.to_simplified_dict()["approvals"][0]
    assert approval == {
        "id": "42",
        "name": "Manager approval",
        "final_decision": "pending",
        "can_answer_approval": True,
        "approvers": [
            {
                "approver": {
                    "display_name": "Jane Doe",
                    "name": "jdoe",
                    "email": "jdoe@example.com",
                },
                "decision": "pending",
            }
        ],
        "created_date": "2026-01-05T10:00:00+0000",
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"start_at": -1}, "start_at must be >= 0"),
        ({"limit": 0}, "limit must be >= 1"),
    ],
)
def test_get_request_approvals_validates_pagination(
    jira_fetcher: JiraFetcher,
    kwargs: dict,
    message: str,
) -> None:
    """Invalid pagination arguments should fail before any API call."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock()

    with pytest.raises(ValueError, match=message):
        fetcher.get_request_approvals("PROJ-1", **kwargs)

    fetcher.jira.get.assert_not_called()


def _route_get(
    request_pages: list[dict],
    approvals_by_key: dict[str, dict],
) -> MagicMock:
    """Route mocked GET calls to request list pages and approval payloads."""
    pages = iter(request_pages)

    def side_effect(endpoint: str, params=None, headers=None):  # noqa: ANN001, ANN202
        if endpoint == "rest/servicedeskapi/request":
            return next(pages)
        issue_key = endpoint.split("/")[3]
        return approvals_by_key[issue_key]

    return MagicMock(side_effect=side_effect)


def _portal_unavailable() -> MagicMock:
    """Simulate a Server/Data Center instance without the portal approval list."""
    return MagicMock(side_effect=_make_http_error(status_code=404))


def _portal_page(
    issue_keys: list[str],
    *,
    selected_page: int = 1,
    total_pages: int = 1,
    per_page: int = 20,
) -> dict:
    """Build a portal approvalListFilter model response."""
    return {
        "xsrfToken": "token",
        "approvalListFilter": {
            "approvalFilterValue": "myPending",
            "portalId": "",
            "requestTypeId": "",
            "selectedPage": selected_page,
            "resultsPerPage": per_page,
            "totalResults": len(issue_keys),
            "totalPages": total_pages,
            "requests": [
                {"key": key, "summary": "Contract review", "status": "Waiting"}
                for key in issue_keys
            ],
            "portalRequestTypes": [],
        },
    }


def _route_get_by_key(approvals_by_key: dict[str, dict]) -> MagicMock:
    """Route mocked GET calls for request details and approvals by issue key."""

    def side_effect(endpoint: str, params=None, headers=None):  # noqa: ANN001, ANN202
        issue_key = endpoint.split("/")[3]
        if endpoint.endswith("/approval"):
            return approvals_by_key[issue_key]
        return _request_payload(issue_key)

    return MagicMock(side_effect=side_effect)


def test_get_my_pending_approvals_server_uses_portal_approval_list(
    jira_fetcher: JiraFetcher,
) -> None:
    """Server/Data Center should read the portal "My approvals" list."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.post = MagicMock(return_value=_portal_page(["PROJ-1", "PROJ-2"]))
    fetcher.jira.get = _route_get_by_key(
        {
            "PROJ-1": _approvals_page(_approval_payload("42")),
            "PROJ-2": _approvals_page(_approval_payload("43", can_answer=False)),
        }
    )

    result = fetcher.get_my_pending_approvals()

    fetcher.jira.post.assert_called_once_with(
        "rest/servicedesk/1/customer/models",
        data={
            "models": ["approvalListFilter"],
            "options": {
                "approvalListFilter": {
                    "approvalFilterValue": "myPending",
                    "selectedPage": 1,
                }
            },
        },
        headers={"Accept": "application/json", "X-Atlassian-Token": "no-check"},
    )
    request_list_calls = [
        call
        for call in fetcher.jira.get.call_args_list
        if call.args[0] == "rest/servicedeskapi/request"
    ]
    assert request_list_calls == []
    simplified = result.to_simplified_dict()
    assert [item["issue_key"] for item in simplified["requests"]] == ["PROJ-1"]
    assert simplified["requests"][0]["approvals"] == [
        {"id": "42", "name": "Manager approval"}
    ]
    assert simplified["is_last_page"] is True
    assert "warnings" not in simplified


def test_get_my_pending_approvals_server_portal_follows_pages(
    jira_fetcher: JiraFetcher,
) -> None:
    """The portal list should be read page by page with continuation offsets."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.post = MagicMock(
        side_effect=[
            _portal_page(["PROJ-1", "PROJ-2"], total_pages=2, per_page=2),
            _portal_page(["PROJ-3"], selected_page=2, total_pages=2, per_page=2),
        ]
    )
    fetcher.jira.get = _route_get_by_key(
        {
            "PROJ-1": _approvals_page(_approval_payload("41")),
            "PROJ-2": _approvals_page(_approval_payload("42")),
            "PROJ-3": _approvals_page(_approval_payload("43")),
        }
    )

    first = fetcher.get_my_pending_approvals(limit=2)

    assert [item.request.issue_key for item in first.requests] == ["PROJ-1", "PROJ-2"]
    assert first.next_start == 2
    assert first.is_last_page is False

    fetcher.jira.post = MagicMock(
        side_effect=[
            _portal_page(["PROJ-1", "PROJ-2"], total_pages=2, per_page=2),
            _portal_page(["PROJ-3"], selected_page=2, total_pages=2, per_page=2),
        ]
    )
    second = fetcher.get_my_pending_approvals(start_at=first.next_start, limit=2)

    pages = [
        call.kwargs["data"]["options"]["approvalListFilter"]["selectedPage"]
        for call in fetcher.jira.post.call_args_list
    ]
    assert pages == [1, 2]
    assert [item.request.issue_key for item in second.requests] == ["PROJ-3"]
    assert second.is_last_page is True


def test_get_my_pending_approvals_server_portal_stops_on_ignored_page(
    jira_fetcher: JiraFetcher,
) -> None:
    """A page the portal does not honor must not be read twice."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.post = MagicMock(
        side_effect=[
            _portal_page(["PROJ-1"], total_pages=2, per_page=1),
            _portal_page(["PROJ-1"], selected_page=1, total_pages=2, per_page=1),
        ]
    )
    fetcher.jira.get = _route_get_by_key(
        {"PROJ-1": _approvals_page(_approval_payload("41"))}
    )

    result = fetcher.get_my_pending_approvals()

    assert [item.request.issue_key for item in result.requests] == ["PROJ-1"]
    assert result.is_last_page is True


@pytest.mark.parametrize(
    "portal_response",
    [
        {"approvalListFilter": {"approvalFilterValue": "myPending"}},
        {"unexpected": True},
        _portal_page(["PROJ-1"])
        | {
            "approvalListFilter": {
                **_portal_page(["PROJ-1"])["approvalListFilter"],
                "approvalFilterValue": "myHistory",
            }
        },
    ],
)
def test_get_my_pending_approvals_server_falls_back_on_unexpected_portal_shape(
    jira_fetcher: JiraFetcher,
    portal_response: dict,
) -> None:
    """An unexpected portal response should fall back to the scan with a warning."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.post = MagicMock(return_value=portal_response)
    fetcher.jira.get = _route_get(
        [_request_list_page(["PROJ-2"])],
        {"PROJ-2": _approvals_page(_approval_payload("42"))},
    )

    result = fetcher.get_my_pending_approvals()

    assert [item.request.issue_key for item in result.requests] == ["PROJ-2"]
    assert len(result.warnings) == 1
    assert "only an approver may be missing" in result.warnings[0]


def test_get_my_pending_approvals_server_fallback_reports_http_status(
    jira_fetcher: JiraFetcher,
) -> None:
    """A failing portal endpoint should be named in the fallback warning."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.post = _portal_unavailable()
    fetcher.jira.get = _route_get([_request_list_page([])], {})

    result = fetcher.get_my_pending_approvals()

    assert result.requests == []
    assert result.to_simplified_dict()["warnings"] == [
        "The customer portal approval list is unavailable (HTTP 404); only open "
        "requests you reported or participate in were checked, so requests "
        "where you are only an approver may be missing."
    ]


def test_get_my_pending_approvals_cloud_uses_approver_filter(
    jira_fetcher: JiraFetcher,
) -> None:
    """Cloud should use the native approver and approval status filters."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.config.is_cloud = True
    fetcher.jira.get = _route_get(
        [_request_list_page(["PROJ-1", "PROJ-2"], is_last_page=False)],
        {
            "PROJ-1": _approvals_page(_approval_payload("42")),
            "PROJ-2": _approvals_page(
                _approval_payload("43", final_decision="approved", can_answer=False)
            ),
        },
    )

    fetcher.jira.post = MagicMock()

    result = fetcher.get_my_pending_approvals(start_at=0, limit=2)

    fetcher.jira.post.assert_not_called()
    list_call = fetcher.jira.get.call_args_list[0]
    assert list_call.args == ("rest/servicedeskapi/request",)
    assert list_call.kwargs["params"] == {
        "requestOwnership": "APPROVER",
        "approvalStatus": "MY_PENDING_APPROVAL",
        "expand": "requestType",
        "start": 0,
        "limit": 2,
    }
    simplified = result.to_simplified_dict()
    assert simplified["size"] == 1
    assert simplified["is_last_page"] is False
    assert simplified["next_start"] == 2
    assert simplified["requests"][0]["issue_key"] == "PROJ-1"
    assert simplified["requests"][0]["summary"] == "Contract review"
    assert simplified["requests"][0]["approvals"] == [
        {"id": "42", "name": "Manager approval"}
    ]


def test_get_my_pending_approvals_server_fallback_scans_open_requests(
    jira_fetcher: JiraFetcher,
) -> None:
    """Server/Data Center has no approver filter, so open requests are scanned."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.post = _portal_unavailable()
    fetcher.config.is_cloud = False
    fetcher.jira.get = _route_get(
        [_request_list_page(["PROJ-1", "PROJ-2", "PROJ-3"])],
        {
            "PROJ-1": _approvals_page(),
            "PROJ-2": _approvals_page(_approval_payload("42")),
            "PROJ-3": _approvals_page(_approval_payload("43", can_answer=False)),
        },
    )

    result = fetcher.get_my_pending_approvals()

    list_call = fetcher.jira.get.call_args_list[0]
    assert list_call.kwargs["params"] == {
        "requestOwnership": "ALL_REQUESTS",
        "requestStatus": "OPEN_REQUESTS",
        "expand": "requestType",
        "start": 0,
        "limit": 50,
    }
    assert "APPROVER" not in str(list_call.kwargs["params"])
    for call in fetcher.jira.get.call_args_list:
        assert call.kwargs["headers"]["X-ExperimentalApi"] == "opt-in"
    simplified = result.to_simplified_dict()
    assert simplified["is_last_page"] is True
    assert "next_start" not in simplified
    assert [item["issue_key"] for item in simplified["requests"]] == ["PROJ-2"]


def test_get_my_pending_approvals_server_fallback_stops_at_limit(
    jira_fetcher: JiraFetcher,
) -> None:
    """The scan should stop at the limit and report where to continue."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.post = _portal_unavailable()
    fetcher.jira.get = _route_get(
        [_request_list_page(["PROJ-1", "PROJ-2", "PROJ-3"])],
        {
            "PROJ-1": _approvals_page(_approval_payload("41")),
            "PROJ-2": _approvals_page(_approval_payload("42")),
        },
    )

    result = fetcher.get_my_pending_approvals(start_at=5, limit=2)

    assert result.is_last_page is False
    assert result.next_start == 7
    assert [item.request.issue_key for item in result.requests] == [
        "PROJ-1",
        "PROJ-2",
    ]
    assert fetcher.jira.get.call_args_list[0].kwargs["params"]["start"] == 5


def test_get_my_pending_approvals_server_fallback_follows_pages(
    jira_fetcher: JiraFetcher,
) -> None:
    """The scan should continue across request list pages."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.post = _portal_unavailable()
    first_page = _request_list_page(["PROJ-1"], is_last_page=False)
    second_page = _request_list_page(["PROJ-2"])
    fetcher.jira.get = _route_get(
        [first_page, second_page],
        {
            "PROJ-1": _approvals_page(),
            "PROJ-2": _approvals_page(_approval_payload("42")),
        },
    )

    result = fetcher.get_my_pending_approvals()

    list_calls = [
        call
        for call in fetcher.jira.get.call_args_list
        if call.args[0] == "rest/servicedeskapi/request"
    ]
    assert [call.kwargs["params"]["start"] for call in list_calls] == [0, 1]
    assert [item.request.issue_key for item in result.requests] == ["PROJ-2"]
    assert result.is_last_page is True


def test_get_my_pending_approvals_server_fallback_skips_unreadable_approvals(
    jira_fetcher: JiraFetcher,
) -> None:
    """A request whose approvals cannot be read should not fail the scan."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.post = _portal_unavailable()
    pages = iter([_request_list_page(["PROJ-1", "PROJ-2"])])

    def side_effect(endpoint: str, params=None, headers=None):  # noqa: ANN001, ANN202
        if endpoint == "rest/servicedeskapi/request":
            return next(pages)
        if "PROJ-1" in endpoint:
            raise _make_http_error(status_code=403, error_messages=["Forbidden"])
        return _approvals_page(_approval_payload("42"))

    fetcher.jira.get = MagicMock(side_effect=side_effect)

    result = fetcher.get_my_pending_approvals()

    assert [item.request.issue_key for item in result.requests] == ["PROJ-2"]


@pytest.mark.parametrize("decision", ["approve", "DECLINE", " Approve "])
def test_answer_approval_posts_normalized_decision(
    jira_fetcher: JiraFetcher,
    decision: str,
) -> None:
    """Valid decisions should be normalized and posted with the opt-in header."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    expected = decision.strip().lower()
    fetcher.jira.get = MagicMock(return_value=_approval_payload("42"))
    fetcher.jira.post = MagicMock(
        return_value=_approval_payload(
            "42",
            final_decision="approved" if expected == "approve" else "declined",
            can_answer=False,
        )
    )

    result = fetcher.answer_approval("PROJ-1", "42", decision)

    assert isinstance(result, JiraRequestApproval)
    fetcher.jira.get.assert_called_once_with(
        "rest/servicedeskapi/request/PROJ-1/approval/42",
        params=None,
        headers={"Accept": "application/json", **EXPERIMENTAL_HEADER},
    )
    fetcher.jira.post.assert_called_once_with(
        "rest/servicedeskapi/request/PROJ-1/approval/42",
        data={"decision": expected},
        headers={"Accept": "application/json", **EXPERIMENTAL_HEADER},
    )
    assert result.final_decision in {"approved", "declined"}


@pytest.mark.parametrize("decision", ["", "yes", "approved", "reject"])
def test_answer_approval_rejects_invalid_decision(
    jira_fetcher: JiraFetcher,
    decision: str,
) -> None:
    """Only approve and decline are accepted, before any API call."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock()
    fetcher.jira.post = MagicMock()

    with pytest.raises(ValueError, match="Invalid decision"):
        fetcher.answer_approval("PROJ-1", "42", decision)

    fetcher.jira.get.assert_not_called()
    fetcher.jira.post.assert_not_called()


def test_answer_approval_requires_approval_id(jira_fetcher: JiraFetcher) -> None:
    """A blank approval ID should fail before any API call."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.post = MagicMock()

    with pytest.raises(ValueError, match="Approval ID is required"):
        fetcher.answer_approval("PROJ-1", " ", "approve")

    fetcher.jira.post.assert_not_called()


@pytest.mark.parametrize(
    ("approval", "message"),
    [
        (
            _approval_payload(final_decision="approved", can_answer=False),
            "already decided",
        ),
        (_approval_payload(can_answer=False), "canAnswerApproval=false"),
    ],
)
def test_answer_approval_refuses_unanswerable_approval(
    jira_fetcher: JiraFetcher,
    approval: dict,
    message: str,
) -> None:
    """Decided or unanswerable approvals should never be posted."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value=approval)
    fetcher.jira.post = MagicMock()

    with pytest.raises(ValueError, match=message):
        fetcher.answer_approval("PROJ-1", "42", "approve")

    fetcher.jira.post.assert_not_called()


def test_answer_approval_explains_post_failure(jira_fetcher: JiraFetcher) -> None:
    """A rejected decision should surface the HTTP status and Jira message."""
    fetcher = _make_customer_requests_fetcher(jira_fetcher)
    fetcher.jira.get = MagicMock(return_value=_approval_payload("42"))
    fetcher.jira.post = MagicMock(
        side_effect=_make_http_error(
            status_code=412,
            error_messages=["This API is experimental"],
        )
    )

    with pytest.raises(ValueError, match="HTTP 412") as exc_info:
        fetcher.answer_approval("PROJ-1", "42", "approve")

    assert "This API is experimental" in str(exc_info.value)
