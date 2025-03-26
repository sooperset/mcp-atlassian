"""Logging utilities for MCP Atlassian.

This module provides enhanced logging capabilities for MCP Atlassian,
including level-dependent stream handling to route logs to the appropriate
output stream based on their level.
"""

import logging


def setup_logging(level: int = logging.WARNING) -> logging.Logger:
    """
    Configure MCP-Atlassian logging with level-based stream routing.

    Args:
        level: The minimum logging level to display (default: WARNING)

    Returns:
        The configured logger instance
    """
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to prevent duplication
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add the level-dependent handler
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(levelname)s - %(name)s - %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Configure specific loggers
    loggers = ["mcp-atlassian", "mcp.server", "mcp.server.lowlevel.server", "mcp-jira"]

    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)

    # Return the application logger
    return logging.getLogger("mcp-atlassian")
