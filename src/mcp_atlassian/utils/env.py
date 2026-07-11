"""Environment variable utility functions for MCP Atlassian."""

import logging
import os

logger = logging.getLogger("mcp-atlassian.env")


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


def is_url_only_multi_user_mode() -> bool:
    """Check whether strict URL-only multi-user mode is enabled.

    Returns:
        True when ``MCP_ATLASSIAN_MULTI_USER_MODE`` is enabled.
    """
    return is_env_truthy("MCP_ATLASSIAN_MULTI_USER_MODE")


def is_multi_user_mode() -> bool:
    """Check whether any per-request credential mode is enabled.

    Strict URL-only mode requires `JIRA_URL` / `CONFLUENCE_URL`. Both modes
    expect every MCP client to supply its own credentials per request via the
    `Authorization` header. Strict URL-only mode resolves the Cloud OAuth
    tenant from the configured URL, while legacy mode accepts it from
    `X-Atlassian-Cloud-Id`. URL override headers are ignored in strict URL-only
    mode. Tools remain available without global credentials.

    The legacy `ATLASSIAN_OAUTH_ENABLE` mode is also recognised for service
    discovery. Unlike strict URL-only mode, it retains support for per-request
    URL headers for backwards compatibility.

    Returns:
        True when either per-request credential mode is enabled.
    """
    return is_url_only_multi_user_mode() or is_env_truthy("ATLASSIAN_OAUTH_ENABLE")


def is_env_ssl_verify(env_var_name: str, default: str = "true") -> bool:
    """Check SSL verification setting with secure defaults.

    Defaults to true unless explicitly set to false values.
    Used for SSL_VERIFY environment variables.

    Args:
        env_var_name: Name of the environment variable to check
        default: Default value if environment variable is not set

    Returns:
        True unless explicitly set to false values
    """
    return os.getenv(env_var_name, default).lower() not in ("false", "0", "no")


def get_int_env(env_var_name: str, default: int) -> int:
    """Read an environment variable as an integer, falling back to `default`.

    Logs a warning and falls back to `default` if the variable is set to a
    non-integer value.

    Args:
        env_var_name: Name of the environment variable to read
        default: Value to return when the variable is unset or unparseable

    Returns:
        Parsed integer value, or `default`
    """
    raw = os.getenv(env_var_name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid int for %s=%r; using default %d", env_var_name, raw, default
        )
        return default


def get_float_env(env_var_name: str, default: float) -> float:
    """Read an environment variable as a float, falling back to `default`.

    Logs a warning and falls back to `default` if the variable is set to a
    non-float value.

    Args:
        env_var_name: Name of the environment variable to read
        default: Value to return when the variable is unset or unparseable

    Returns:
        Parsed float value, or `default`
    """
    raw = os.getenv(env_var_name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Invalid float for %s=%r; using default %s", env_var_name, raw, default
        )
        return default


def get_custom_headers(env_var_name: str) -> dict[str, str]:
    """Parse custom headers from environment variable containing comma-separated key=value pairs.

    Args:
        env_var_name: Name of the environment variable to read

    Returns:
        Dictionary of parsed headers

    Examples:
        >>> # With CUSTOM_HEADERS="X-Custom=value1,X-Other=value2"
        >>> parse_custom_headers("CUSTOM_HEADERS")
        {'X-Custom': 'value1', 'X-Other': 'value2'}
        >>> # With unset environment variable
        >>> parse_custom_headers("UNSET_VAR")
        {}
    """
    header_string = os.getenv(env_var_name)
    if not header_string or not header_string.strip():
        return {}

    headers = {}
    pairs = header_string.split(",")

    for pair in pairs:
        pair = pair.strip()
        if not pair:
            continue

        if "=" not in pair:
            continue

        key, value = pair.split("=", 1)  # Split on first = only
        key = key.strip()
        value = value.strip()

        if key:  # Only add if key is not empty
            headers[key] = value

    return headers
