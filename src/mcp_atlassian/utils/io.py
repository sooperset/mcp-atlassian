"""I/O utility functions for MCP Atlassian."""

from typing import Any

from mcp_atlassian.utils.env import is_env_extended_truthy


def is_read_only_mode(request_context: dict[str, Any] | None = None) -> bool:
    """Check if the server is running in read-only mode.

    Read-only mode prevents all write operations (create, update, delete)
    while allowing all read operations. This is useful for working with
    production Atlassian instances where you want to prevent accidental
    modifications.

    Per-request headers take precedence over environment variables,
    enabling multi-user HTTP deployments to control read-only mode
    on a per-request basis.

    Args:
        request_context: Optional request state dict from middleware containing
            per-request configuration overrides (e.g., from X-Read-Only-Mode header).

    Returns:
        True if read-only mode is enabled, False otherwise
    """
    # Check per-request override first (from X-Read-Only-Mode header)
    if request_context:
        header_value = request_context.get("read_only_mode")
        if header_value is not None:
            return str(header_value).lower() == "true"

    # Fall back to environment variable
    return is_env_extended_truthy("READ_ONLY_MODE", "false")
