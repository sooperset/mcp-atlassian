"""Environment variable utility functions for MCP Atlassian."""

import os


def is_env_truthy(env_var_name: str, default: str = "") -> bool:
    """Check if environment variable is set to a standard truthy value.

    Considers 'true', '1', 'yes' as truthy values (case-insensitive).
    Used for most MCP environment variables.

    Args:
        env_var_name: Name of the environment variable to check
        default: Default value if environment variable is not set

    Returns:
        True if the environment variable is set to a truthy value, False otherwise
    """
    return os.getenv(env_var_name, default).lower() in ("true", "1", "yes")


def is_env_extended_truthy(env_var_name: str, default: str = "") -> bool:
    """Check if environment variable is set to an extended truthy value.

    Considers 'true', '1', 'yes', 'y', 'on' as truthy values (case-insensitive).
    Used for READ_ONLY_MODE and similar flags.

    Args:
        env_var_name: Name of the environment variable to check
        default: Default value if environment variable is not set

    Returns:
        True if the environment variable is set to a truthy value, False otherwise
    """
    return os.getenv(env_var_name, default).lower() in ("true", "1", "yes", "y", "on")


def is_env_ssl_verify(
    env: dict[str, str], env_var_name: str, default: str = "true"
) -> bool:
    """Check SSL verification setting with secure defaults.

    Defaults to true unless explicitly set to false values.
    Used for SSL_VERIFY environment variables.

    Args:
        env_var_name: Name of the environment variable to check
        default: Default value if environment variable is not set

    Returns:
        True unless explicitly set to false values
    """
    return getenv(env, env_var_name, default).lower() not in ("false", "0", "no")


def getenv(
    env: dict[str, str], env_var_name: str, default: str | None = None
) -> str | None:
    """Retrieve the value of an environment variable.

    This function checks for the presence of a variable in the provided `env` dictionary first.
    If the variable is not found in `env`, it falls back to checking the system's environment variables.

    Args:
        env (dict[str, str]): A dictionary containing environment variables and their values.
        env_var_name (str): The name of the environment variable to retrieve.

    Returns:
        str | None: The value of the environment variable if found, otherwise None.
    """
    return env.get(env_var_name, os.getenv(env_var_name, default))
