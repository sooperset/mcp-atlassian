"""Utility functions for date operations."""

import logging
from datetime import datetime, timezone

import dateutil.parser

logger = logging.getLogger("mcp-atlassian")


def parse_date(date_str: str | int | None) -> datetime | None:
    """
    Parse a date string from any format to a datetime object for type consistency.

    The input string `date_str` accepts:
    - None
    - Epoch timestamp (only contains digits and is in milliseconds)
    - Other formats supported by `dateutil.parser` (ISO 8601, RFC 3339, etc.)

    Args:
        date_str: Date string

    Returns:
        Parsed date string or None if date_str is None / empty string
    """

    if not date_str:
        return None
    if isinstance(date_str, int) or date_str.isdigit():
        return datetime.fromtimestamp(int(date_str) / 1000, tz=timezone.utc)
    return dateutil.parser.parse(date_str)
