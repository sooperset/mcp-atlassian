"""Module for Jira Service Management customer request operations."""

import logging
from typing import Any

from ..models.jira import (
    JiraCustomerRequest,
    JiraRequestTypeFieldsResult,
    JiraRequestTypesResult,
)
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class CustomerRequestsMixin(JiraClient):
    """Mixin for Jira Service Management customer request operations."""

    @staticmethod
    def _get_servicedesk_headers(default_headers: dict[str, Any]) -> dict[str, Any]:
        """Return headers required for ServiceDesk API calls."""
        return {
            **default_headers,
            "X-ExperimentalApi": "opt-in",
        }

    @staticmethod
    def _format_request_field_value(
        value: Any, jira_schema: dict[str, Any] | None
    ) -> Any:
        """Format request field values for the JSM customer request API."""
        if not jira_schema:
            return value

        if jira_schema.get("type") == "array":
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                parts = [part.strip() for part in value.split(",") if part.strip()]
                return parts or [value]
            return [value]

        return value

    def _build_portal_url(
        self,
        response_data: dict[str, Any],
        service_desk_id: str,
    ) -> str:
        """Build an absolute portal URL from the API response."""
        links = response_data.get("_links")
        if isinstance(links, dict):
            web_link = links.get("web") or links.get("self")
            if isinstance(web_link, str) and web_link:
                if web_link.startswith("http://") or web_link.startswith("https://"):
                    return web_link
                return f"{self.config.url.rstrip('/')}{web_link}"

        issue_key = response_data.get("issueKey") or response_data.get("key")
        if issue_key:
            return (
                f"{self.config.url.rstrip('/')}/servicedesk/customer/portal/"
                f"{service_desk_id}/{issue_key}"
            )

        return ""

    @staticmethod
    def _should_retry_without_on_behalf(error_message: str) -> bool:
        """Decide whether an on-behalf failure should retry without that field."""
        normalized = error_message.lower()
        retry_markers = [
            "raiseonbehalfof",
            "on behalf",
            "unknown user",
            "permission",
            "forbidden",
            "customer",
            "400",
            "403",
            "404",
        ]
        return any(marker in normalized for marker in retry_markers)

    def get_request_types(
        self,
        service_desk_id: str,
        start_at: int = 0,
        limit: int = 50,
    ) -> JiraRequestTypesResult:
        """Get request types for a Jira Service Management service desk."""
        if not service_desk_id or not service_desk_id.strip():
            raise ValueError("Service desk ID is required")
        if start_at < 0:
            raise ValueError("start_at must be >= 0")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        try:
            response = self.jira.get(
                f"rest/servicedeskapi/servicedesk/{service_desk_id}/requesttype",
                params={"start": start_at, "limit": limit},
            )
            if not isinstance(response, dict):
                logger.error(
                    "Unexpected response type from request type list endpoint: %s",
                    type(response),
                )
                return JiraRequestTypesResult(service_desk_id=service_desk_id)

            return JiraRequestTypesResult.from_api_response(
                response,
                service_desk_id=service_desk_id,
            )
        except Exception as e:
            logger.error(
                "Error getting request types for service desk %s: %s",
                service_desk_id,
                str(e),
            )
            return JiraRequestTypesResult(service_desk_id=service_desk_id)

    def get_request_type_fields(
        self,
        service_desk_id: str,
        request_type_id: str,
    ) -> JiraRequestTypeFieldsResult:
        """Get field definitions for a Jira Service Management request type."""
        if not service_desk_id or not service_desk_id.strip():
            raise ValueError("Service desk ID is required")
        if not request_type_id or not request_type_id.strip():
            raise ValueError("Request type ID is required")

        try:
            response = self.jira.get(
                "rest/servicedeskapi/servicedesk/"
                f"{service_desk_id}/requesttype/{request_type_id}/field"
            )
            if not isinstance(response, dict):
                logger.error(
                    "Unexpected response type from request type fields endpoint: %s",
                    type(response),
                )
                return JiraRequestTypeFieldsResult(
                    service_desk_id=service_desk_id,
                    request_type_id=request_type_id,
                )

            return JiraRequestTypeFieldsResult.from_api_response(
                response,
                service_desk_id=service_desk_id,
                request_type_id=request_type_id,
            )
        except Exception as e:
            logger.error(
                "Error getting request type fields for service desk %s request type %s: %s",
                service_desk_id,
                request_type_id,
                str(e),
            )
            return JiraRequestTypeFieldsResult(
                service_desk_id=service_desk_id,
                request_type_id=request_type_id,
            )

    def create_customer_request(
        self,
        service_desk_id: str,
        request_type_id: str,
        request_field_values: dict[str, Any],
        raise_on_behalf_of: str | None = None,
        request_participants: list[str] | None = None,
        strict_on_behalf: bool = False,
    ) -> JiraCustomerRequest:
        """Create a Jira Service Management customer request."""
        if not service_desk_id or not service_desk_id.strip():
            raise ValueError("Service desk ID is required")
        if not request_type_id or not request_type_id.strip():
            raise ValueError("Request type ID is required")
        if not isinstance(request_field_values, dict):
            raise ValueError("request_field_values must be a dictionary")

        fields_result = self.get_request_type_fields(
            service_desk_id=service_desk_id,
            request_type_id=request_type_id,
        )
        field_definitions = {
            field.field_id: field for field in fields_result.fields if field.field_id
        }

        formatted_field_values = {
            field_id: self._format_request_field_value(
                value,
                field_definitions.get(field_id).jira_schema
                if field_id in field_definitions
                else None,
            )
            for field_id, value in request_field_values.items()
        }

        payload: dict[str, Any] = {
            "serviceDeskId": str(service_desk_id),
            "requestTypeId": str(request_type_id),
            "requestFieldValues": formatted_field_values,
        }
        if raise_on_behalf_of:
            payload["raiseOnBehalfOf"] = raise_on_behalf_of
        if request_participants:
            payload["requestParticipants"] = request_participants

        headers = self._get_servicedesk_headers(self.jira.default_headers)
        endpoint = "rest/servicedeskapi/request"
        warnings: list[str] = []

        try:
            response = self.jira.post(endpoint, data=payload, headers=headers)
            if not isinstance(response, dict):
                msg = (
                    "Unexpected return value type from "
                    f"ServiceDesk request create API: {type(response)}"
                )
                logger.error(msg)
                raise TypeError(msg)

            return JiraCustomerRequest.from_api_response(
                response,
                portal_url=self._build_portal_url(response, service_desk_id),
                created_mode=(
                    "created_on_behalf_of" if raise_on_behalf_of else "created_direct"
                ),
                on_behalf_user=raise_on_behalf_of,
                request_participants=request_participants or [],
                warnings=warnings,
            )
        except Exception as e:
            error_message = str(e)
            if (
                raise_on_behalf_of
                and not strict_on_behalf
                and self._should_retry_without_on_behalf(error_message)
            ):
                fallback_payload = {
                    key: value
                    for key, value in payload.items()
                    if key != "raiseOnBehalfOf"
                }
                warnings.append(
                    "Could not apply raise_on_behalf_of "
                    f"'{raise_on_behalf_of}': {error_message}"
                )
                response = self.jira.post(
                    endpoint,
                    data=fallback_payload,
                    headers=headers,
                )
                if not isinstance(response, dict):
                    msg = (
                        "Unexpected return value type from "
                        f"ServiceDesk request create API: {type(response)}"
                    )
                    logger.error(msg)
                    raise TypeError(msg)

                return JiraCustomerRequest.from_api_response(
                    response,
                    portal_url=self._build_portal_url(response, service_desk_id),
                    created_mode="created_as_agent_fallback",
                    on_behalf_user=raise_on_behalf_of,
                    request_participants=request_participants or [],
                    warnings=warnings,
                )

            raise
