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


def is_multi_user_mode() -> bool:
    """True when the server runs in multi-user mode.

    In multi-user mode the server only requires `JIRA_URL` / `CONFLUENCE_URL`
    and expects every MCP client to supply its own credentials per request via
    `Authorization` or `X-Atlassian-*` headers. Tools remain available even if
    the server has no global credentials configured.

    Recognises the new `MCP_ATLASSIAN_MULTI_USER_MODE` flag and the legacy
    `ATLASSIAN_OAUTH_ENABLE` flag (kept as an alias for backwards compatibility
    with deployments that already use the OAuth-flavoured "user-provided
    tokens" mode).
    """
    return is_env_truthy("MCP_ATLASSIAN_MULTI_USER_MODE") or is_env_truthy(
        "ATLASSIAN_OAUTH_ENABLE"
    )


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
