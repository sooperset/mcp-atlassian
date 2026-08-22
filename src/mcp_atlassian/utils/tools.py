"""Tool-related utility functions for MCP Atlassian."""

import logging
import os

logger = logging.getLogger(__name__)


def get_enabled_tools() -> list[str] | None:
    """Get the list of enabled tools from environment variable.

    This function reads and parses the ENABLED_TOOLS environment variable
    to determine which tools should be available in the server.

    The environment variable should contain a comma-separated list of tool names.
    Whitespace around tool names is stripped.

    Returns:
        List of enabled tool names if ENABLED_TOOLS is set and non-empty,
        None if ENABLED_TOOLS is not set or empty after stripping whitespace.

    Examples:
        ENABLED_TOOLS="tool1,tool2" -> ["tool1", "tool2"]
        ENABLED_TOOLS="tool1, tool2 , tool3" -> ["tool1", "tool2", "tool3"]
        ENABLED_TOOLS="" -> None
        ENABLED_TOOLS not set -> None
        ENABLED_TOOLS=" , " -> None
    """
    enabled_tools_str = os.getenv("ENABLED_TOOLS")
    if not enabled_tools_str:
        logger.debug("ENABLED_TOOLS environment variable not set or empty.")
        return None

    # Split by comma and strip whitespace
    tools = [tool.strip() for tool in enabled_tools_str.split(",")]
    # Filter out empty strings
    tools = [tool for tool in tools if tool]

    logger.debug(f"Parsed enabled tools from environment: {tools}")

    return tools if tools else None


def should_include_tool(tool_name: str, enabled_tools: list[str] | None) -> bool:
    """Check if a tool should be included based on the enabled tools list.

    Args:
        tool_name: The name of the tool to check.
        enabled_tools: List of enabled tool names, or None to include all tools.

    Returns:
        True if the tool should be included, False otherwise.
    """
    if enabled_tools is None:
        logger.debug(
            f"Including tool '{tool_name}' because enabled_tools filter is None."
        )
        return True
    should_include = tool_name in enabled_tools
    logger.debug(
        f"Tool '{tool_name}' included: {should_include} (based on enabled_tools: {enabled_tools})"
    )
    return should_include
