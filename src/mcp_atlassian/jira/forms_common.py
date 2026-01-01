"""Common utilities for ProForma form operations."""

import logging
from typing import TypeVar

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
