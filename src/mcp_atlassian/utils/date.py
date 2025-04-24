"""Utility functions for date operations."""

import logging
from datetime import datetime, timezone

import dateutil.parser

logger = logging.getLogger("mcp-atlassian")


def parse_date(date_str: str | None, format_string: str = "%Y-%m-%d") -> str:
    """
    Parse a date string from ISO format to a specified format.

    This is a standalone utility function to be used by all mixins
    when consistent date formatting is needed.

    The input string `date_str` accepts:
    - None
    - Epoch timestamp (only contains digits and is in milliseconds)
    - Other formats supported by `dateutil.parser` (ISO 8601, RFC 3339, etc.)

    Args:
        date_str: Date string
        format_string: The output format (default: "%Y-%m-%d")

    Returns:
        Formatted date string or empty string if date_str is None
    """
    logger.debug(
        f"TRACE utils.parse_date called with: '{date_str}', format: {format_string}"
    )

    # Handle None or empty string
    if not date_str:
        logger.debug(
            "TRACE utils.parse_date - empty date string, returning empty string"
        )
        return ""

    try:
        if date_str.isdigit():
            date = datetime.fromtimestamp(int(date_str) / 1000, tz=timezone.utc)
        else:
            date = dateutil.parser.parse(date_str)
        return date.strftime(format_string)

    except (ValueError, TypeError) as e:
        logger.debug(
            f"TRACE utils.parse_date - error parsing date '{date_str}': {str(e)}"
        )

    # Return original string if parsing fails
    return date_str


def parse_date_ymd(date_str: str | None) -> str:
    """
    Parse a date string to YYYY-MM-DD format.

    Args:
        date_str: The date string to parse or None

    Returns:
        Date in YYYY-MM-DD format or empty string if date_str is None
    """
    logger.debug(f"TRACE utils.parse_date_ymd called with: '{date_str}'")
    result = parse_date(date_str, "%Y-%m-%d")
    logger.debug(f"TRACE utils.parse_date_ymd returning: '{result}'")
    return result


def parse_date_human_readable(date_str: str | None) -> str:
    """
    Parse a date string to a human-readable format (Month Day, Year).

    Args:
        date_str: The date string to parse or None

    Returns:
        Date in human-readable format or empty string if date_str is None
    """
    logger.debug(f"TRACE utils.parse_date_human_readable called with: '{date_str}'")
    result = parse_date(date_str, "%B %d, %Y")
    logger.debug(f"TRACE utils.parse_date_human_readable returning: '{result}'")
    return result
