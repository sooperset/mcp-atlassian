"""Utility functions for Jira operations."""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar

logger = logging.getLogger("mcp-jira")

T = TypeVar("T")


def parse_date(date_str: str | None, format_string: str = "%Y-%m-%d") -> str:
    """
    Parse a date string from ISO format to a specified format.

    This is a standalone utility function to be used by all mixins
    when consistent date formatting is needed.

    Args:
        date_str: Date string in ISO format or None
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
        # Handle Jira-specific ISO 8601 format with milliseconds
        if isinstance(date_str, str) and "T" in date_str:
            # Try direct parsing first
            try:
                # Replace Z with +00:00 for UTC timezone if present
                cleaned_date_str = date_str.replace("Z", "+00:00")

                # Handle milliseconds format with timezone
                if "." in cleaned_date_str and "+" in cleaned_date_str:
                    # Split at timezone marker
                    date_part, tz_part = cleaned_date_str.split("+", 1)

                    # If we have milliseconds with more than 6 digits, truncate to 6
                    if "." in date_part:
                        date_base, ms_part = date_part.split(".", 1)
                        if len(ms_part) > 6:
                            ms_part = ms_part[:6]
                        date_part = f"{date_base}.{ms_part}"

                    # Reconstruct with proper format
                    cleaned_date_str = f"{date_part}+{tz_part}"

                date_obj = datetime.fromisoformat(cleaned_date_str)
                result = date_obj.strftime(format_string)
                logger.debug(
                    f"TRACE utils.parse_date - successfully parsed: '{date_str}' -> '{result}'"
                )
                return result
            except (ValueError, TypeError) as e:
                logger.debug(
                    f"TRACE utils.parse_date - error in direct parsing: {str(e)}"
                )

            # Fallback: extract just the date part
            try:
                date_part = date_str.split("T")[0]
                date_obj = datetime.fromisoformat(date_part)
                result = date_obj.strftime(format_string)
                logger.debug(
                    f"TRACE utils.parse_date - fallback parsing succeeded: '{date_str}' -> '{result}'"
                )
                return result
            except (ValueError, TypeError) as e:
                logger.debug(
                    f"TRACE utils.parse_date - error in fallback parsing: {str(e)}"
                )

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


def get_mixin_method(
    instance: Any,
    method_name: str,
    current_class: type[T],
    default_impl: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """
    Get the appropriate method implementation from the mixin inheritance chain.

    This utility ensures we can find and call the right implementation of a method
    when multiple mixins might define it, avoiding circular references.

    Args:
        instance: The instance on which to call the method
        method_name: The name of the method to find
        current_class: The current class to avoid circular references
        default_impl: Default implementation if no other is found

    Returns:
        The method to call
    """
    logger.debug(f"TRACE utils.get_mixin_method called for method: {method_name}")

    # If we have a method by this name that isn't from current_class
    if hasattr(instance, method_name):
        method = getattr(instance.__class__, method_name)
        if method.__qualname__ != f"{current_class.__name__}.{method_name}":
            # Get the appropriate method from the MRO
            for cls in instance.__class__.__mro__:
                if cls is not current_class and hasattr(cls, method_name):
                    logger.debug(
                        f"TRACE utils.get_mixin_method found method in class: {cls.__name__}"
                    )
                    return getattr(cls, method_name).__get__(
                        instance, instance.__class__
                    )

    # Return the default implementation if provided
    if default_impl:
        logger.debug("TRACE utils.get_mixin_method using default implementation")
        return (
            default_impl.__get__(instance, instance.__class__)
            if hasattr(default_impl, "__get__")
            else default_impl
        )

    # If no method found and no default, use a dummy function
    logger.debug(
        "TRACE utils.get_mixin_method no implementation found, using dummy function"
    )
    return lambda *args, **kwargs: None


def escape_jql_string(value: str) -> str:
    """
    Escapes characters reserved within JQL string literals ('\\', '"')
    and encloses the result in double quotes.
    """
    # Escape backslash first, then double quote
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'  # Return the properly quoted and escaped string
