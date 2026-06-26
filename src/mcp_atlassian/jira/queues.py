"""Module for Jira Service Management queue and request operations."""

import logging
import os
from typing import Any, BinaryIO, cast

from ..models.jira import (
    JiraQueue,
    JiraQueueIssuesResult,
    JiraRequestStatusResult,
    JiraRequestTransitionsResult,
    JiraRequestType,
    JiraRequestTypeField,
    JiraRequestTypesResult,
    JiraServiceDesk,
    JiraServiceDeskQueuesResult,
    JiraServiceDeskRequest,
    JiraTemporaryAttachment,
)
from .client import JiraClient

logger = logging.getLogger("mcp-jira")

_SERVICEDESK_HEADERS = {"X-ExperimentalApi": "opt-in"}


class QueuesMixin(JiraClient):
    """Mixin for Jira Service Management queue and request operations."""

    def _ensure_server_mode(self) -> None:
        """Ensure queue endpoints are used only on Server/Data Center in v1."""
        if self.config.is_cloud:
            raise NotImplementedError(
                "Jira Service Desk queue read endpoints are currently implemented "
                "for Server/Data Center in v1."
            )

    def get_service_desk_for_project(self, project_key: str) -> JiraServiceDesk | None:
        """
        Get the Jira Service Desk associated with a project key.

        Args:
            project_key: The Jira project key (e.g. 'SUP')

        Returns:
            Matched JiraServiceDesk model or None if not found
        """
        if not project_key or not project_key.strip():
            raise ValueError("Project key is required")

        self._ensure_server_mode()

        normalized_project_key = project_key.strip().upper()
        start = 0
        limit = 50

        try:
            while True:
                response = self.jira.get(
                    "rest/servicedeskapi/servicedesk",
                    params={"start": start, "limit": limit},
                )
                if not isinstance(response, dict):
                    logger.error(
                        "Unexpected response type from servicedesk list endpoint: %s",
                        type(response),
                    )
                    return None

                service_desks = response.get("values", [])
                if not isinstance(service_desks, list):
                    logger.error(
                        "Unexpected service desk list payload type: %s",
                        type(service_desks),
                    )
                    return None

                for service_desk_data in service_desks:
                    if not isinstance(service_desk_data, dict):
                        continue
                    current_key = str(service_desk_data.get("projectKey", "")).upper()
                    if current_key == normalized_project_key:
                        return JiraServiceDesk.from_api_response(service_desk_data)

                if response.get("isLastPage", True) or not service_desks:
                    break
                start += len(service_desks)

            return None
        except Exception as e:
            logger.error(
                "Error getting service desk for project %s: %s", project_key, str(e)
            )
            return None

    def get_service_desk_queues(
        self,
        service_desk_id: str,
        start_at: int = 0,
        limit: int = 50,
        include_count: bool = True,
    ) -> JiraServiceDeskQueuesResult:
        """
        Get queues for a specific service desk.

        Args:
            service_desk_id: The service desk ID (e.g. '4')
            start_at: Starting index for pagination
            limit: Maximum number of queues to return
            include_count: Whether to request queue issue counts from API

        Returns:
            JiraServiceDeskQueuesResult with queues and pagination metadata
        """
        if not service_desk_id or not service_desk_id.strip():
            raise ValueError("Service desk ID is required")
        if start_at < 0:
            raise ValueError("start_at must be >= 0")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        self._ensure_server_mode()

        try:
            response = self.jira.get(
                f"rest/servicedeskapi/servicedesk/{service_desk_id}/queue",
                params={
                    "start": start_at,
                    "limit": limit,
                    "includeCount": str(include_count).lower(),
                },
            )
            if not isinstance(response, dict):
                logger.error(
                    "Unexpected response type from queue list endpoint: %s",
                    type(response),
                )
                return JiraServiceDeskQueuesResult(service_desk_id=service_desk_id)

            return JiraServiceDeskQueuesResult.from_api_response(
                response, service_desk_id=service_desk_id
            )
        except Exception as e:
            logger.error(
                "Error getting queues for service desk %s: %s", service_desk_id, str(e)
            )
            return JiraServiceDeskQueuesResult(service_desk_id=service_desk_id)

    def get_queue_issues(
        self,
        service_desk_id: str,
        queue_id: str,
        start_at: int = 0,
        limit: int = 50,
    ) -> JiraQueueIssuesResult:
        """
        Get issues from a specific service desk queue.

        Args:
            service_desk_id: The service desk ID (e.g. '4')
            queue_id: The queue ID (e.g. '47')
            start_at: Starting index for pagination
            limit: Maximum number of issues to return

        Returns:
            JiraQueueIssuesResult containing queue metadata and queue issues
        """
        if not service_desk_id or not service_desk_id.strip():
            raise ValueError("Service desk ID is required")
        if not queue_id or not queue_id.strip():
            raise ValueError("Queue ID is required")
        if start_at < 0:
            raise ValueError("start_at must be >= 0")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        self._ensure_server_mode()

        queue_model: JiraQueue | None = None

        try:
            queue_response = self.jira.get(
                f"rest/servicedeskapi/servicedesk/{service_desk_id}/queue/{queue_id}",
                params={"includeCount": "true"},
            )
            if isinstance(queue_response, dict):
                queue_model = JiraQueue.from_api_response(queue_response)
        except Exception as e:
            logger.debug(
                "Unable to fetch queue metadata for service desk %s queue %s: %s",
                service_desk_id,
                queue_id,
                str(e),
            )

        try:
            response = self.jira.get(
                f"rest/servicedeskapi/servicedesk/{service_desk_id}/queue/{queue_id}/issue",
                params={"start": start_at, "limit": limit},
            )
            if not isinstance(response, dict):
                logger.error(
                    "Unexpected response type from queue issues endpoint: %s",
                    type(response),
                )
                return JiraQueueIssuesResult(
                    service_desk_id=service_desk_id,
                    queue_id=queue_id,
                    queue=queue_model,
                )

            return JiraQueueIssuesResult.from_api_response(
                response,
                service_desk_id=service_desk_id,
                queue_id=queue_id,
                queue=queue_model,
            )
        except Exception as e:
            logger.error(
                "Error getting queue issues for service desk %s queue %s: %s",
                service_desk_id,
                queue_id,
                str(e),
            )
            return JiraQueueIssuesResult(
                service_desk_id=service_desk_id,
                queue_id=queue_id,
                queue=queue_model,
            )

    def get_request_types(
        self,
        service_desk_id: str,
        start_at: int = 0,
        limit: int = 50,
        search_query: str | None = None,
    ) -> JiraRequestTypesResult:
        """
        Get available request types for a Service Desk.

        Works on both Jira Cloud and Server/Data Center.

        Args:
            service_desk_id: The service desk ID (e.g. '4')
            start_at: Starting index for pagination
            limit: Maximum number of request types to return
            search_query: Optional text query to filter request type names

        Returns:
            JiraRequestTypesResult with request types and pagination metadata

        Raises:
            ValueError: If service_desk_id is empty or pagination is invalid
        """
        if not service_desk_id or not service_desk_id.strip():
            raise ValueError("Service desk ID is required")
        if start_at < 0:
            raise ValueError("start_at must be >= 0")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        params: dict[str, Any] = {"start": start_at, "limit": limit}
        if search_query:
            params["searchQuery"] = search_query

        try:
            response = self.jira.get(
                f"rest/servicedeskapi/servicedesk/{service_desk_id}/requesttype",
                params=params,
                headers={**self.jira.default_headers, **_SERVICEDESK_HEADERS},
            )
        except Exception as e:
            logger.error(
                "Error getting request types for service desk %s: %s",
                service_desk_id,
                str(e),
            )
            return JiraRequestTypesResult(service_desk_id=service_desk_id)

        if not isinstance(response, dict):
            logger.error(
                "Unexpected response type from request types endpoint: %s",
                type(response),
            )
            return JiraRequestTypesResult(service_desk_id=service_desk_id)

        return JiraRequestTypesResult.from_api_response(
            response, service_desk_id=service_desk_id
        )

    def get_request_type_fields(
        self,
        service_desk_id: str,
        request_type_id: str,
    ) -> JiraRequestType:
        """
        Get fields metadata for a specific request type.

        Works on both Jira Cloud and Server/Data Center.

        Args:
            service_desk_id: The service desk ID
            request_type_id: The request type ID

        Returns:
            JiraRequestType populated with field definitions

        Raises:
            ValueError: If ids are empty
        """
        if not service_desk_id or not service_desk_id.strip():
            raise ValueError("Service desk ID is required")
        if not request_type_id or not request_type_id.strip():
            raise ValueError("Request type ID is required")

        url = (
            f"rest/servicedeskapi/servicedesk/{service_desk_id}"
            f"/requesttype/{request_type_id}/field"
        )

        try:
            response = self.jira.get(
                url,
                headers={**self.jira.default_headers, **_SERVICEDESK_HEADERS},
            )
        except Exception as e:
            logger.error(
                "Error getting fields for request type %s: %s",
                request_type_id,
                str(e),
            )
            return JiraRequestType(id=request_type_id, service_desk_id=service_desk_id)

        if not isinstance(response, dict):
            logger.error(
                "Unexpected response type from request type fields endpoint: %s",
                type(response),
            )
            return JiraRequestType(id=request_type_id, service_desk_id=service_desk_id)

        raw_fields = response.get("requestTypeFields", [])
        fields: list[JiraRequestTypeField] = []
        if isinstance(raw_fields, list):
            fields = [
                JiraRequestTypeField.from_api_response(item)
                for item in raw_fields
                if isinstance(item, dict)
            ]

        return JiraRequestType(
            id=request_type_id,
            service_desk_id=service_desk_id,
            fields=fields,
        )

    def create_service_desk_request(
        self,
        service_desk_id: str,
        request_type_id: str,
        request_field_values: dict[str, Any],
        raise_on_behalf_of: str | None = None,
        request_participants: list[str] | None = None,
        channel: str | None = None,
    ) -> JiraServiceDeskRequest:
        """
        Create a customer request on a Service Desk via the JSM portal API.

        Works on both Jira Cloud and Server/Data Center.

        Args:
            service_desk_id: The service desk ID
            request_type_id: The request type ID
            request_field_values: Map of field id -> value. Use field ids
                returned by get_request_type_fields (e.g. {"summary": "x",
                "description": "y"}).
            raise_on_behalf_of: Optional account id (Cloud) or username
                (Server/DC) of the user the request is raised for.
            request_participants: Optional list of account ids (Cloud) or
                usernames (Server/DC) to add as participants.
            channel: Optional request channel (e.g. "jira", "api").

        Returns:
            JiraServiceDeskRequest representing the created request

        Raises:
            ValueError: If required arguments are missing
            Exception: If the API request fails
        """
        if not service_desk_id or not service_desk_id.strip():
            raise ValueError("Service desk ID is required")
        if not request_type_id or not request_type_id.strip():
            raise ValueError("Request type ID is required")
        if not isinstance(request_field_values, dict) or not request_field_values:
            raise ValueError("request_field_values must be a non-empty mapping")

        payload: dict[str, Any] = {
            "serviceDeskId": str(service_desk_id),
            "requestTypeId": str(request_type_id),
            "requestFieldValues": request_field_values,
        }
        if raise_on_behalf_of:
            payload["raiseOnBehalfOf"] = raise_on_behalf_of
        if request_participants:
            payload["requestParticipants"] = list(request_participants)
        if channel:
            payload["channel"] = channel

        try:
            response = self.jira.post(
                "rest/servicedeskapi/request",
                data=payload,
                headers={**self.jira.default_headers, **_SERVICEDESK_HEADERS},
            )
        except Exception as e:
            logger.error("Error creating service desk request: %s", str(e))
            raise

        if not isinstance(response, dict):
            msg = (
                "Unexpected return value type from ServiceDesk create "
                f"request API: {type(response)}"
            )
            logger.error(msg)
            raise TypeError(msg)

        return JiraServiceDeskRequest.from_api_response(response)

    def get_service_desk_request(self, issue_key: str) -> JiraServiceDeskRequest:
        """
        Get a Service Desk customer request by issue key or id.

        Works on both Jira Cloud and Server/Data Center.

        Args:
            issue_key: Issue key (e.g. 'SUP-123') or numeric issue id

        Returns:
            JiraServiceDeskRequest representing the request

        Raises:
            ValueError: If issue_key is empty
        """
        if not issue_key or not str(issue_key).strip():
            raise ValueError("Issue key is required")

        try:
            response = self.jira.get(
                f"rest/servicedeskapi/request/{issue_key}",
                headers={**self.jira.default_headers, **_SERVICEDESK_HEADERS},
            )
        except Exception as e:
            logger.error("Error getting service desk request %s: %s", issue_key, str(e))
            raise

        if not isinstance(response, dict):
            msg = (
                "Unexpected return value type from ServiceDesk request "
                f"API: {type(response)}"
            )
            logger.error(msg)
            raise TypeError(msg)

        return JiraServiceDeskRequest.from_api_response(response)

    def add_request_participants(
        self,
        issue_key: str,
        participants: list[str],
    ) -> dict[str, Any]:
        """
        Add participants to a Service Desk customer request.

        Args:
            issue_key: Issue key (e.g. 'SUP-123')
            participants: List of account ids (Cloud) or usernames (DC) to add

        Returns:
            Raw API response dict

        Raises:
            ValueError: If arguments are invalid
        """
        if not issue_key or not issue_key.strip():
            raise ValueError("Issue key is required")
        if not participants:
            raise ValueError("participants must be a non-empty list")

        payload: dict[str, Any]
        if self.config.is_cloud:
            payload = {"accountIds": list(participants)}
        else:
            payload = {"usernames": list(participants)}

        try:
            response = self.jira.post(
                f"rest/servicedeskapi/request/{issue_key}/participant",
                data=payload,
                headers={**self.jira.default_headers, **_SERVICEDESK_HEADERS},
            )
        except Exception as e:
            logger.error(
                "Error adding participants to request %s: %s", issue_key, str(e)
            )
            raise

        if not isinstance(response, dict):
            return {"raw": response}
        return response

    def get_request_status(
        self,
        issue_key: str,
        start_at: int = 0,
        limit: int = 50,
    ) -> JiraRequestStatusResult:
        """
        Get the status history of a Service Desk customer request.

        Args:
            issue_key: Issue key (e.g. 'SUP-123')
            start_at: Starting index for pagination
            limit: Max number of status entries to return

        Returns:
            JiraRequestStatusResult with status entries

        Raises:
            ValueError: If arguments are invalid
        """
        if not issue_key or not issue_key.strip():
            raise ValueError("Issue key is required")
        if start_at < 0:
            raise ValueError("start_at must be >= 0")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        try:
            response = self.jira.get(
                f"rest/servicedeskapi/request/{issue_key}/status",
                params={"start": start_at, "limit": limit},
                headers={**self.jira.default_headers, **_SERVICEDESK_HEADERS},
            )
        except Exception as e:
            logger.error("Error getting request status for %s: %s", issue_key, str(e))
            return JiraRequestStatusResult(issue_key=issue_key)

        if not isinstance(response, dict):
            logger.error(
                "Unexpected response type from request status endpoint: %s",
                type(response),
            )
            return JiraRequestStatusResult(issue_key=issue_key)

        return JiraRequestStatusResult.from_api_response(response, issue_key=issue_key)

    def get_request_transitions(
        self,
        issue_key: str,
        start_at: int = 0,
        limit: int = 50,
    ) -> JiraRequestTransitionsResult:
        """
        Get available transitions for a Service Desk customer request.

        Args:
            issue_key: Issue key (e.g. 'SUP-123')
            start_at: Starting index for pagination
            limit: Max number of transitions to return

        Returns:
            JiraRequestTransitionsResult with transitions

        Raises:
            ValueError: If arguments are invalid
        """
        if not issue_key or not issue_key.strip():
            raise ValueError("Issue key is required")
        if start_at < 0:
            raise ValueError("start_at must be >= 0")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        try:
            response = self.jira.get(
                f"rest/servicedeskapi/request/{issue_key}/transition",
                params={"start": start_at, "limit": limit},
                headers={**self.jira.default_headers, **_SERVICEDESK_HEADERS},
            )
        except Exception as e:
            logger.error(
                "Error getting request transitions for %s: %s",
                issue_key,
                str(e),
            )
            return JiraRequestTransitionsResult(issue_key=issue_key)

        if not isinstance(response, dict):
            logger.error(
                "Unexpected response type from request transitions endpoint: %s",
                type(response),
            )
            return JiraRequestTransitionsResult(issue_key=issue_key)

        return JiraRequestTransitionsResult.from_api_response(
            response, issue_key=issue_key
        )

    def transition_service_desk_request(
        self,
        issue_key: str,
        transition_id: str,
        comment: str | None = None,
    ) -> None:
        """
        Apply a transition to a Service Desk customer request.

        Args:
            issue_key: Issue key (e.g. 'SUP-123')
            transition_id: Transition id from get_request_transitions
            comment: Optional public comment to add with the transition

        Raises:
            ValueError: If arguments are invalid
            Exception: If the API request fails
        """
        if not issue_key or not issue_key.strip():
            raise ValueError("Issue key is required")
        if not transition_id or not str(transition_id).strip():
            raise ValueError("Transition ID is required")

        payload: dict[str, Any] = {"id": str(transition_id)}
        if comment:
            payload["additionalComment"] = {"body": comment}

        try:
            self.jira.post(
                f"rest/servicedeskapi/request/{issue_key}/transition",
                data=payload,
                headers={**self.jira.default_headers, **_SERVICEDESK_HEADERS},
            )
        except Exception as e:
            logger.error(
                "Error transitioning request %s with transition %s: %s",
                issue_key,
                transition_id,
                str(e),
            )
            raise

    def attach_temporary_files(
        self,
        service_desk_id: str,
        files: list[str | tuple[str, BinaryIO]],
    ) -> list[JiraTemporaryAttachment]:
        """
        Upload one or more files as temporary attachments on a Service Desk.

        These can later be attached to a customer request with
        :meth:`create_request_attachment`.

        Args:
            service_desk_id: The service desk ID
            files: List of either absolute file paths or
                ``(file_name, file_obj)`` tuples for in-memory files.

        Returns:
            List of JiraTemporaryAttachment metadata for the uploaded files

        Raises:
            ValueError: If arguments are invalid
            FileNotFoundError: If a file path does not exist
        """
        if not service_desk_id or not service_desk_id.strip():
            raise ValueError("Service desk ID is required")
        if not files:
            raise ValueError("files must be a non-empty list")

        prepared: list[tuple[str, tuple[str, BinaryIO]]] = []
        opened: list[BinaryIO] = []
        try:
            for item in files:
                if isinstance(item, tuple):
                    name, fh = item
                    prepared.append(("file", (name, fh)))
                else:
                    if not os.path.exists(item):
                        raise FileNotFoundError(f"File not found: {item}")
                    fh = open(item, "rb")  # noqa: SIM115 - closed in finally
                    opened.append(fh)
                    prepared.append(("file", (os.path.basename(item), fh)))

            headers = {
                **self.jira.default_headers,
                **_SERVICEDESK_HEADERS,
                "X-Atlassian-Token": "no-check",
            }
            # Let requests set its own multipart Content-Type boundary.
            headers.pop("Content-Type", None)

            # The atlassian-python-api types `files` as Optional[dict] but the
            # underlying requests library accepts a list of (name, (filename,
            # fileobj)) tuples for repeated form fields, which is required to
            # send multiple files under the same "file" key.
            response = self.jira.post(
                f"rest/servicedeskapi/servicedesk/{service_desk_id}/attachTemporaryFile",
                files=cast("dict[str, Any]", prepared),
                headers=headers,
            )
        finally:
            for fh in opened:
                try:
                    fh.close()
                except Exception as close_err:  # noqa: BLE001 - best-effort cleanup
                    logger.debug("Failed to close attachment handle: %s", close_err)

        if not isinstance(response, dict):
            raise TypeError(
                "Unexpected response type from attachTemporaryFile endpoint: "
                f"{type(response)}"
            )

        raw_attachments = response.get("temporaryAttachments", [])
        if not isinstance(raw_attachments, list):
            return []
        return [
            JiraTemporaryAttachment.from_api_response(item)
            for item in raw_attachments
            if isinstance(item, dict)
        ]

    def create_request_attachment(
        self,
        issue_key: str,
        temporary_attachment_ids: list[str],
        *,
        public: bool = True,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """
        Attach previously uploaded temporary files to a Service Desk request.

        Args:
            issue_key: Issue key (e.g. 'SUP-123')
            temporary_attachment_ids: IDs returned by
                :meth:`attach_temporary_files`
            public: True for customer-visible, False for internal
            comment: Optional plain-text comment to post with the attachment

        Returns:
            Raw API response dict

        Raises:
            ValueError: If arguments are invalid
        """
        if not issue_key or not issue_key.strip():
            raise ValueError("Issue key is required")
        if not temporary_attachment_ids:
            raise ValueError("temporary_attachment_ids must be a non-empty list")

        payload: dict[str, Any] = {
            "temporaryAttachmentIds": list(temporary_attachment_ids),
            "public": public,
        }
        if comment:
            payload["additionalComment"] = {"body": comment}

        try:
            response = self.jira.post(
                f"rest/servicedeskapi/request/{issue_key}/attachment",
                data=payload,
                headers={**self.jira.default_headers, **_SERVICEDESK_HEADERS},
            )
        except Exception as e:
            logger.error("Error attaching files to request %s: %s", issue_key, str(e))
            raise

        if not isinstance(response, dict):
            return {"raw": response}
        return response
