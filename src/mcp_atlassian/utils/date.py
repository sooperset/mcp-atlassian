"""Utility functions for date operations."""

import logging
from datetime import datetime, timezone

import dateutil.parser

logger = logging.getLogger("mcp-atlassian")


def parse_date(date_str: str | int | None) -> datetime | str | None:
    """
    Parse a date string from any format to a datetime object for type consistency.

    The input string `date_str` accepts:
    - None
    - Epoch timestamp (only contains digits and is in milliseconds)
    - Other formats supported by `dateutil.parser` (ISO 8601, RFC 3339, etc.)

    Args:
        date_str: Date string

    Returns:
        Parsed date string or None if date_str is None / empty string.
        Returns string representation if timestamp is out of Python datetime range.
    """

    if not date_str:
        return None
    if isinstance(date_str, int) or date_str.isdigit():
        try:
            timestamp_ms = int(date_str)
            # Python datetime supports years 1-9999
            # Check if timestamp is within valid range to avoid OSError
            # Valid range: -62135596800000 (year 1) to 253402300799999 (year 9999)
            if -62135596800000 <= timestamp_ms <= 253402300799999:
                return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            else:
                # Timestamp out of range - return ISO format string representation
                logger.warning(
                    f"Timestamp {timestamp_ms} is out of Python datetime range"
                    f" (year 1-9999). Returning as string. "
                    "This may occur with legacy Jira Server instances."
                )
                return f"<timestamp:{timestamp_ms}>"
        except (OSError, OverflowError, ValueError) as e:
            # Handle edge cases where fromtimestamp still fails
            logger.warning(
                f"Failed to parse timestamp {date_str}: {e}. Returning as string."
            )
            return f"<timestamp:{date_str}>"
    try:
        return dateutil.parser.parse(date_str)
    except (ValueError, TypeError) as e:
        # If date parsing fails, return the original string
        logger.warning(
            f"Failed to parse date string '{date_str}': {e}. Returning as-is."
        )
        return date_str
