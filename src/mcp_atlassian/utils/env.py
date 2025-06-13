"""Environment variable utility functions for MCP Atlassian."""

import os


def is_env_truthy(env_var_name: str, default: str = "") -> bool:
    """Check if an environment variable is set to a truthy value.

    Considers 'true', '1', 'yes', 'y', 'on' as truthy values (case-insensitive).

    Args:
        env_var_name: Name of the environment variable to check
        default: Default value if environment variable is not set

    Returns:
        True if the environment variable is set to a truthy value, False otherwise
    """
    return os.getenv(env_var_name, default).lower() in ("true", "1", "yes", "y", "on")
