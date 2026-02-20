"""Common utilities for ProForma form operations."""

import logging
from datetime import datetime
from typing import Any, TypeVar

from requests.exceptions import HTTPError

from ..exceptions import MCPAtlassianAuthenticationError

logger = logging.getLogger("mcp-jira")

T = TypeVar("T")


def handle_forms_http_error(
    error: HTTPError,
    operation: str,
    resource_id: str,
) -> Exception:
    """
    Convert HTTPError to appropriate exception for form operations.

    Args:
        error: The HTTPError to handle
        operation: Description of the operation (e.g., "getting forms",
            "reopening form")
        resource_id: Identifier of the resource (e.g., issue key, form ID)

    Returns:
        Appropriate exception to raise

    Raises:
        MCPAtlassianAuthenticationError: For 403 permission errors
        ValueError: For 404 not found errors
        Exception: For other HTTP errors
    """
    status_code = error.response.status_code

    if status_code == 403:
        error_msg = f"Insufficient permissions for {operation}: {resource_id}"
        return MCPAtlassianAuthenticationError(error_msg)
    elif status_code == 404:
        error_msg = f"Resource not found for {operation}: {resource_id}"
        return ValueError(error_msg)
    else:
        error_msg = f"HTTP error {operation}: {str(error)}"
        return Exception(error_msg)


def convert_datetime_to_timestamp(value: Any, field_type: str) -> Any:
    """
    Convert ISO 8601 datetime strings to Unix timestamps in milliseconds for ProForma forms.

    This function automatically handles datetime conversion for DATE and DATETIME field types.
    If the value is already a number (Unix timestamp), it passes through unchanged.

    Args:
        value: The value to convert (can be ISO 8601 string, Unix timestamp, or other)
        field_type: The ProForma field type (DATE, DATETIME, TEXT, etc.)

    Returns:
        Unix timestamp in milliseconds if conversion was needed, otherwise original value

    Raises:
        ValueError: If the datetime string is in an invalid format

    Examples:
        >>> convert_datetime_to_timestamp("2024-12-17T19:00:00.000Z", "DATETIME")
        1734465600000
        >>> convert_datetime_to_timestamp("2024-12-17", "DATE")
        1734393600000
        >>> convert_datetime_to_timestamp(1734465600000, "DATETIME")
        1734465600000
        >>> convert_datetime_to_timestamp("hello", "TEXT")
        'hello'
    """
    # Only convert for DATE and DATETIME fields
    if field_type not in ("DATE", "DATETIME"):
        return value

    # Check for boolean before int (since bool is subclass of int)
    if isinstance(value, bool):
        return value

    # If already a number (Unix timestamp), pass through
    if isinstance(value, int | float):
        return int(value)

    # If not a string, pass through unchanged
    if not isinstance(value, str):
        return value

    # Try to parse as ISO 8601 datetime
    try:
        # Handle various ISO 8601 formats
        # Replace 'Z' with '+00:00' for Python datetime compatibility
        iso_string = value.replace("Z", "+00:00")

        # Try parsing with timezone info first
        try:
            dt = datetime.fromisoformat(iso_string)
        except ValueError:
            # Try without timezone (assume UTC)
            from datetime import timezone as tz

            dt = datetime.fromisoformat(value.replace("Z", ""))
            # Make it timezone-aware (UTC)
            dt = dt.replace(tzinfo=tz.utc)

        # Ensure we have timezone info, otherwise assume UTC
        if dt.tzinfo is None:
            from datetime import timezone as tz

            dt = dt.replace(tzinfo=tz.utc)

        # Convert to UTC timestamp
        timestamp_seconds = dt.timestamp()

        # Convert to milliseconds
        timestamp_ms = int(timestamp_seconds * 1000)
        logger.debug(
            f"Converted datetime '{value}' to timestamp {timestamp_ms} for field type {field_type}"
        )
        return timestamp_ms

    except (ValueError, AttributeError) as e:
        error_msg = (
            f"Invalid datetime format for {field_type} field: '{value}'. "
            f"Expected ISO 8601 format (e.g., '2024-12-17T19:00:00Z' or '2024-12-17') "
            f"or Unix timestamp in milliseconds. Error: {str(e)}"
        )
        raise ValueError(error_msg) from e
