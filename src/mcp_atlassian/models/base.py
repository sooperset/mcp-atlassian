"""
Base models and utility classes for the MCP Atlassian API models.

This module provides base classes and mixins that are used by the
Jira and Confluence models to ensure consistent behavior and reduce
code duplication.
"""

from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from .constants import EMPTY_STRING

# Type variable for the return type of from_api_response
T = TypeVar("T", bound="ApiModel")


class ApiModel(BaseModel):
    """
    Base model for all API models with common conversion methods.

    This provides a standard interface for converting API responses
    to models and for converting models to simplified dictionaries
    for API responses.
    """

    @classmethod
    def from_api_response(cls: type[T], data: dict[str, Any], **kwargs: Any) -> T:
        """
        Convert an API response to a model instance.

        Args:
            data: The API response data
            **kwargs: Additional context parameters

        Returns:
            An instance of the model

        Raises:
            NotImplementedError: If the subclass does not implement this method
        """
        raise NotImplementedError("Subclasses must implement from_api_response")

    def to_simplified_dict(self) -> dict[str, Any]:
        """
        Convert the model to a simplified dictionary for API responses.

        Returns:
            A dictionary with only the essential fields for API responses
        """
        return self.model_dump(exclude_none=True)


class TimestampMixin:
    """
    Mixin for handling Atlassian API timestamp formats.
    """

    @staticmethod
    def format_timestamp(timestamp: str | None) -> str:
        """
        Format an Atlassian timestamp to a human-readable format.

        Args:
            timestamp: An ISO 8601 timestamp string

        Returns:
            A formatted date string or empty string if the input is invalid
        """
        if not timestamp:
            return EMPTY_STRING

        try:
            # Parse ISO 8601 format like "2024-01-01T10:00:00.000+0000"
            # Convert Z format to +00:00 for compatibility with fromisoformat
            ts = timestamp.replace("Z", "+00:00")

            # Handle timezone format without colon (+0000 -> +00:00)
            if "+" in ts and ":" not in ts[-5:]:
                tz_pos = ts.rfind("+")
                if tz_pos != -1 and len(ts) >= tz_pos + 5:
                    ts = ts[: tz_pos + 3] + ":" + ts[tz_pos + 3 :]
            elif "-" in ts and ":" not in ts[-5:]:
                tz_pos = ts.rfind("-")
                if tz_pos != -1 and len(ts) >= tz_pos + 5:
                    ts = ts[: tz_pos + 3] + ":" + ts[tz_pos + 3 :]

            dt = datetime.fromisoformat(ts)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return timestamp or EMPTY_STRING

    @staticmethod
    def is_valid_timestamp(timestamp: str | None) -> bool:
        """
        Check if a string is a valid ISO 8601 timestamp.

        Args:
            timestamp: The string to check

        Returns:
            True if the string is a valid timestamp, False otherwise
        """
        if not timestamp:
            return False

        try:
            # Convert Z format to +00:00 for compatibility with fromisoformat
            ts = timestamp.replace("Z", "+00:00")

            # Handle timezone format without colon (+0000 -> +00:00)
            if "+" in ts and ":" not in ts[-5:]:
                tz_pos = ts.rfind("+")
                if tz_pos != -1 and len(ts) >= tz_pos + 5:
                    ts = ts[: tz_pos + 3] + ":" + ts[tz_pos + 3 :]
            elif "-" in ts and ":" not in ts[-5:]:
                tz_pos = ts.rfind("-")
                if tz_pos != -1 and len(ts) >= tz_pos + 5:
                    ts = ts[: tz_pos + 3] + ":" + ts[tz_pos + 3 :]

            datetime.fromisoformat(ts)
            return True
        except (ValueError, TypeError):
            return False
