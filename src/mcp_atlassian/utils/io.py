"""I/O utility functions for MCP Atlassian."""

import os


def is_read_only_mode() -> bool:
    """Check if the server is running in read-only mode.

    Read-only mode prevents all write operations (create, update, delete)
    while allowing all read operations. This is useful for working with
    production Atlassian instances where you want to prevent accidental
    modifications.

    Returns:
        True if read-only mode is enabled, False otherwise
    """
    value = os.getenv("READ_ONLY_MODE", "false")
    return value.lower() in ("true", "1", "yes", "y", "on")
