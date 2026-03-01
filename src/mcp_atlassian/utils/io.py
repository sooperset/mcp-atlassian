"""I/O utility functions for MCP Atlassian."""

import os
from pathlib import Path

from mcp_atlassian.utils.env import is_env_extended_truthy


def is_delete_tools_allowed() -> bool:
    """Check if delete tools are allowed.

    When disabled (the default), tools tagged with ``"delete"`` are hidden
    from the tool listing, preventing destructive operations such as
    deleting issues or pages.  Set the ``ALLOW_DELETE_TOOLS`` environment
    variable to a truthy value (``true``, ``1``, ``yes``, ``y``, ``on``)
    to expose these tools.

    Returns:
        True if ALLOW_DELETE_TOOLS env var is set to a truthy value.
    """
    return is_env_extended_truthy("ALLOW_DELETE_TOOLS", "false")


def is_read_only_mode() -> bool:
    """Check if the server is running in read-only mode.

    Read-only mode prevents all write operations (create, update, delete)
    while allowing all read operations. This is useful for working with
    production Atlassian instances where you want to prevent accidental
    modifications.

    Returns:
        True if read-only mode is enabled, False otherwise
    """
    return is_env_extended_truthy("READ_ONLY_MODE", "false")


def validate_safe_path(
    path: str | os.PathLike[str],
    base_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Validate that a path does not escape the base directory.

    Resolves symlinks and normalizes the path to prevent path traversal
    attacks (e.g., ``../../etc/passwd``).

    Args:
        path: The path to validate.
        base_dir: The directory the path must stay within.
            Defaults to the current working directory.

    Returns:
        The resolved, validated path.

    Raises:
        ValueError: If the resolved path escapes *base_dir*.
    """
    if base_dir is None:
        base_dir = os.getcwd()

    resolved_base = Path(base_dir).resolve(strict=False)
    p = Path(path)
    # Resolve relative paths against base_dir, not cwd
    if not p.is_absolute():
        p = resolved_base / p
    resolved_path = p.resolve(strict=False)

    if not resolved_path.is_relative_to(resolved_base):
        raise ValueError(
            f"Path traversal detected: {path} resolves outside {resolved_base}"
        )

    return resolved_path
