"""Module for Jira Service Management customer request operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from ..models.jira import (
    JiraCustomerRequest,
    JiraRequestTypeField,
    JiraRequestTypeFieldsResult,
    JiraRequestTypesResult,
)
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class CustomerRequestsMixin(JiraClient):
    """Mixin for Jira Service Management customer request operations."""

    @staticmethod
    def _trace_prefix(
        service_desk_id: str,
        request_type_id: str,
        marker: str,
    ) -> str:
        """Build a stable prefix for tracing JSM customer request failures."""
        return (
            f"JSM_CUSTOMER_REQUEST_{marker} "
            f"service_desk_id={service_desk_id} request_type_id={request_type_id}"
        )

    @staticmethod
    def _get_servicedesk_headers(default_headers: dict[str, Any]) -> dict[str, Any]:
        """Return headers required for ServiceDesk API calls."""
        return {
            **default_headers,
            "X-ExperimentalApi": "opt-in",
        }

    @staticmethod
    def _is_missing_field_value(value: Any) -> bool:
        """Check whether a request field value should be treated as missing."""
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, list | dict):
            return len(value) == 0
        return False

    @staticmethod
    def _describe_value_shape(value: Any) -> str:
        """Return a trace-friendly summary of a field value without logging content."""
        if isinstance(value, str):
            return f"str[len={len(value)}]"
        if isinstance(value, list):
            return f"list[len={len(value)}]"
        if isinstance(value, dict):
            keys = ",".join(sorted(str(key) for key in value.keys()))
            return f"dict[keys={keys}]"
        if value is None:
            return "none"
        return type(value).__name__

    @staticmethod
    def _shorten_error_text(error_text: str, max_length: int = 400) -> str:
        """Shorten a raw Jira error text for logs and tool responses."""
        normalized = " ".join(error_text.split())
        if len(normalized) <= max_length:
            return normalized
        return f"{normalized[: max_length - 3]}..."

    @staticmethod
    def _field_display_name(
        field_id: str,
        field_definition: JiraRequestTypeField | None,
    ) -> str:
        """Return a readable field name for trace messages."""
        if field_definition and field_definition.name:
            return field_definition.name
        return field_id

    @staticmethod
    def _is_select_like_field(field_definition: JiraRequestTypeField | None) -> bool:
        """Determine whether a field behaves like a select/dropdown."""
        if not field_definition or not field_definition.jira_schema:
            return False

        jira_schema = field_definition.jira_schema
        field_type = str(jira_schema.get("type", "")).lower()
        custom_type = str(jira_schema.get("custom", "")).lower()
        return field_type == "option" or "select" in custom_type

    @staticmethod
    def _normalize_array_value(value: Any) -> list[Any]:
        """Normalize a request field value to a list."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            return parts or [value]
        return [value]

    @staticmethod
    def _extract_option_candidates(value: Any) -> list[str]:
        """Extract candidate strings from raw option input."""
        if isinstance(value, dict):
            candidates: list[str] = []
            for key in ("id", "value", "label", "name"):
                candidate = value.get(key)
                if candidate is None:
                    continue
                candidate_text = str(candidate).strip()
                if candidate_text:
                    candidates.append(candidate_text)
            return candidates

        if isinstance(value, str | int | float):
            candidate_text = str(value).strip()
            return [candidate_text] if candidate_text else []

        return []

    @staticmethod
    def _build_select_payload(option: dict[str, Any]) -> dict[str, str] | None:
        """Build a canonical JSM payload for a matched select option."""
        option_id = option.get("id") or option.get("value")
        option_label = option.get("label") or option.get("name")

        if option_id is not None and str(option_id).strip():
            return {"id": str(option_id).strip()}
        if option_label is not None and str(option_label).strip():
            return {"value": str(option_label).strip()}
        return None

    def _match_select_option(
        self,
        field_definition: JiraRequestTypeField,
        value: Any,
    ) -> dict[str, str] | None:
        """Match a raw select value against request type metadata."""
        candidates = self._extract_option_candidates(value)
        if not candidates:
            return None

        for candidate in candidates:
            candidate_lower = candidate.lower()
            for option in field_definition.valid_values:
                if not isinstance(option, dict):
                    continue

                option_id = option.get("id") or option.get("value")
                option_value = option.get("value")
                option_label = option.get("label") or option.get("name")
                payload = self._build_select_payload(option)
                if payload is None:
                    continue

                if option_id is not None and candidate == str(option_id).strip():
                    return payload
                if (
                    option_id is not None
                    and candidate_lower == str(option_id).strip().lower()
                ):
                    return payload
                if option_value is not None and candidate == str(option_value).strip():
                    return payload
                if (
                    option_value is not None
                    and candidate_lower == str(option_value).strip().lower()
                ):
                    return payload
                if option_label is not None and candidate == str(option_label).strip():
                    return payload
                if (
                    option_label is not None
                    and candidate_lower == str(option_label).strip().lower()
                ):
                    return payload

        return None

    @staticmethod
    def _summarize_allowed_values(
        field_definition: JiraRequestTypeField,
        limit: int = 6,
    ) -> str:
        """Summarize the first few allowed values for trace messages."""
        values: list[str] = []
        for option in field_definition.valid_values[:limit]:
            if isinstance(option, dict):
                label = option.get("label") or option.get("name") or option.get("value")
                if label is not None:
                    values.append(str(label))
            elif option is not None:
                values.append(str(option))

        summary = ", ".join(values)
        if len(field_definition.valid_values) > limit:
            return f"{summary}, ..."
        return summary or "n/a"

    def _normalize_select_field_value(
        self,
        field_id: str,
        value: Any,
        field_definition: JiraRequestTypeField,
    ) -> Any:
        """Normalize a select-like field to a canonical JSM payload shape."""
        jira_schema = field_definition.jira_schema or {}
        if jira_schema.get("type") == "array":
            if not field_definition.valid_values:
                return self._normalize_array_value(value)

            normalized_values: list[dict[str, str]] = []
            for item in self._normalize_array_value(value):
                matched_payload = self._match_select_option(field_definition, item)
                if matched_payload is None:
                    field_name = self._field_display_name(field_id, field_definition)
                    message = (
                        "invalid select value for "
                        f"field '{field_name}' ({field_id}); "
                        f"provided_shape={self._describe_value_shape(item)}; "
                        f"allowed_values={self._summarize_allowed_values(field_definition)}"
                    )
                    raise ValueError(message)
                normalized_values.append(matched_payload)
            return normalized_values

        matched_payload = self._match_select_option(field_definition, value)
        if matched_payload is not None:
            return matched_payload

        if not field_definition.valid_values:
            return value

        field_name = self._field_display_name(field_id, field_definition)
        message = (
            "invalid select value for "
            f"field '{field_name}' ({field_id}); "
            f"provided_shape={self._describe_value_shape(value)}; "
            f"allowed_values={self._summarize_allowed_values(field_definition)}"
        )
        raise ValueError(message)

    def _format_request_field_value(
        self,
        field_id: str,
        value: Any,
        field_definition: JiraRequestTypeField | None,
    ) -> Any:
        """Format request field values for the JSM customer request API."""
        jira_schema = field_definition.jira_schema if field_definition else None
        if not jira_schema or field_definition is None:
            return value

        if self._is_select_like_field(field_definition):
            return self._normalize_select_field_value(
                field_id,
                value,
                field_definition,
            )

        if jira_schema.get("type") == "array":
            return self._normalize_array_value(value)

        return value

    @staticmethod
    def _extract_error_details(exception: Exception) -> tuple[int | None, str]:
        """Extract status code and readable error text from an exception."""
        response = exception.response if isinstance(exception, HTTPError) else None
        if response is None:
            return None, str(exception).strip() or type(exception).__name__

        raw_text = response.text.strip()
        try:
            data = response.json()
        except ValueError:
            return response.status_code, raw_text or str(exception).strip()

        if isinstance(data, dict):
            error_text = data.get("errorMessage")
            if not error_text and isinstance(data.get("errorMessages"), list):
                error_text = "; ".join(str(item) for item in data["errorMessages"])
            if not error_text and isinstance(data.get("errors"), dict):
                error_text = "; ".join(
                    f"{field}: {message}" for field, message in data["errors"].items()
                )
            if error_text:
                return response.status_code, str(error_text)

        return response.status_code, raw_text or str(exception).strip()

    def _log_request_error(
        self,
        service_desk_id: str,
        request_type_id: str,
        request_field_values: dict[str, Any],
        exception: Exception,
    ) -> str:
        """Log a trace-friendly JSM request error and return a compact message."""
        status_code, error_text = self._extract_error_details(exception)
        shortened_error = self._shorten_error_text(error_text)
        prefix = self._trace_prefix(
            service_desk_id,
            request_type_id,
            "HTTP_ERROR",
        )
        field_shapes = {
            field_id: self._describe_value_shape(value)
            for field_id, value in request_field_values.items()
        }
        if status_code is None:
            logger.error(
                "%s field_shapes=%s error=%s",
                prefix,
                field_shapes,
                shortened_error,
            )
            return f"{prefix}: {shortened_error}"

        logger.error(
            "%s status=%s field_shapes=%s error=%s",
            prefix,
            status_code,
            field_shapes,
            shortened_error,
        )
        return f"{prefix} status={status_code}: {shortened_error}"

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
            "raise_on_behalf_of",
            "on behalf",
            "unknown user",
            "user does not exist",
            "invalid customer",
            "customer account",
            "permission to raise",
            "raise requests on behalf",
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
        except Exception as e:  # noqa: BLE001
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
        except Exception as e:  # noqa: BLE001
            logger.error(
                (
                    "Error getting request type fields for service desk %s "
                    "request type %s: %s"
                ),
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
        *,
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

        missing_required_fields = [
            f"{self._field_display_name(field.field_id, field)} ({field.field_id})"
            for field in fields_result.fields
            if field.field_id
            and field.required
            and field.visible is not False
            and self._is_missing_field_value(request_field_values.get(field.field_id))
        ]
        if missing_required_fields:
            missing_fields = ", ".join(missing_required_fields)
            prefix = self._trace_prefix(
                service_desk_id,
                request_type_id,
                "MISSING_REQUIRED_FIELDS",
            )
            message = f"{prefix}: {missing_fields}"
            raise ValueError(message)

        formatted_field_values: dict[str, Any] = {}
        for field_id, value in request_field_values.items():
            field_definition = field_definitions.get(field_id)
            if self._is_missing_field_value(value):
                continue

            try:
                formatted_field_values[field_id] = self._format_request_field_value(
                    field_id,
                    value,
                    field_definition,
                )
            except ValueError as exc:
                prefix = self._trace_prefix(
                    service_desk_id,
                    request_type_id,
                    "FIELD_ERROR",
                )
                message = f"{prefix} field_id={field_id}: {exc}"
                raise ValueError(message) from exc

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
            error_message = self._log_request_error(
                service_desk_id,
                request_type_id,
                formatted_field_values,
                e,
            )
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
                prefix = self._trace_prefix(
                    service_desk_id,
                    request_type_id,
                    "ON_BEHALF_FALLBACK",
                )
                warning_message = (
                    f"{prefix} "
                    f"raise_on_behalf_of='{raise_on_behalf_of}': {error_message}"
                )
                warnings.append(warning_message)
                try:
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
                except Exception as fallback_error:
                    fallback_message = self._log_request_error(
                        service_desk_id,
                        request_type_id,
                        formatted_field_values,
                        fallback_error,
                    )
                    message = f"{error_message}; fallback_failed: {fallback_message}"
                    raise ValueError(message) from fallback_error

                return JiraCustomerRequest.from_api_response(
                    response,
                    portal_url=self._build_portal_url(response, service_desk_id),
                    created_mode="created_as_agent_fallback",
                    on_behalf_user=raise_on_behalf_of,
                    request_participants=request_participants or [],
                    warnings=warnings,
                )

            raise ValueError(error_message) from e
