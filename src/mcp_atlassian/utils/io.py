"""I/O utility functions for MCP Atlassian."""

import logging
import os
from pathlib import Path

from mcp_atlassian.utils.env import is_env_extended_truthy

logger = logging.getLogger("mcp-atlassian.utils.io")

#: Environment variable naming the directory that confines every server-side
#: file path a tool accepts (attachment upload sources, ``content_file`` reads,
#: attachment download targets).
FILES_DIR_ENV = "MCP_ATLASSIAN_FILES_DIR"

#: Transports where tool callers are remote and must not reach the server's
#: working directory implicitly.
REMOTE_TRANSPORTS = frozenset({"sse", "streamable-http"})

_remote_transport_active = False


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


def default_files_dir() -> Path:
    """Return the dedicated default file directory for remote transports.

    Returns:
        ``~/.mcp-atlassian/files`` for the user running the server.
    """
    return Path.home() / ".mcp-atlassian" / "files"


def set_remote_transport(active: bool) -> None:
    """Record whether the server runs on a remote (HTTP/SSE) transport.

    Args:
        active: True when the server was started with a remote transport.
    """
    global _remote_transport_active
    _remote_transport_active = active


def get_file_root() -> Path:
    """Return the directory that confines server-side file path inputs.

    Resolution order:

    1. ``MCP_ATLASSIAN_FILES_DIR`` when set (any transport).
    2. On a remote transport, the dedicated :func:`default_files_dir`; the
       process working directory is never used, because its value is set by
       the deployment method (``/`` for a systemd system unit) rather than
       chosen by the operator.
    3. Otherwise (stdio, direct library use) the current working directory,
       which keeps the documented local behaviour unchanged.

    Returns:
        The resolved root directory.
    """
    configured = os.getenv(FILES_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    if _remote_transport_active:
        return default_files_dir().resolve(strict=False)
    return Path(os.getcwd()).resolve(strict=False)


def _home_dir() -> Path | None:
    try:
        return Path.home().resolve(strict=False)
    except (KeyError, RuntimeError):
        return None


def is_wide_directory(path: str | os.PathLike[str]) -> bool:
    """Return True if *path* is a filesystem root or the user's home directory.

    Args:
        path: The directory to check.

    Returns:
        True when confining paths to *path* would expose host-wide or
        home-directory files.
    """
    resolved = Path(path).resolve(strict=False)
    if resolved == Path(resolved.anchor):
        return True
    home = _home_dir()
    return home is not None and resolved == home


def configure_file_root_for_transport(transport: str) -> Path:
    """Set up the file-path boundary for the chosen transport at startup.

    For remote transports this switches the boundary away from the working
    directory, creates the default directory when no explicit one is set, and
    refuses a boundary that is a filesystem root or a home directory.

    Args:
        transport: The transport name (``stdio``, ``sse``, ``streamable-http``).

    Returns:
        The resolved file root in effect.

    Raises:
        ValueError: If a remote transport would confine file paths to a
            filesystem root or a home directory.
    """
    remote = transport in REMOTE_TRANSPORTS
    set_remote_transport(remote)
    root = get_file_root()
    if not remote:
        return root

    configured = bool(os.getenv(FILES_DIR_ENV, "").strip())
    if is_wide_directory(root):
        raise ValueError(
            f"{FILES_DIR_ENV} resolves to {root}, a filesystem root or home "
            f"directory. With the {transport} transport this would let remote "
            "callers read and overwrite any file there. Point it at a "
            "dedicated directory."
        )
    if not configured:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        cwd = Path(os.getcwd()).resolve(strict=False)
        if is_wide_directory(cwd):
            logger.warning(
                "Working directory is %s. File path inputs are confined to %s, "
                "not the working directory; set %s to change it.",
                cwd,
                root,
                FILES_DIR_ENV,
            )
    logger.info("File path inputs are confined to %s", root)
    return root


def is_in_cwd_root(path: str | os.PathLike[str]) -> bool:
    """Return True if *path* would land directly in the working-directory root.

    Python resolves imports from there first, so writing a file into it can
    overwrite an importable module and gain code execution on import.

    Args:
        path: The target file path.

    Returns:
        True when the resolved parent of *path* is the working directory.
    """
    resolved = Path(path).resolve(strict=False)
    return resolved.parent == Path(os.getcwd()).resolve(strict=False)


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
            Defaults to :func:`get_file_root`.

    Returns:
        The resolved, validated path.

    Raises:
        ValueError: If the resolved path escapes *base_dir*.
    """
    if base_dir is None:
        base_dir = get_file_root()

    resolved_base = Path(base_dir).resolve(strict=False)
    p = Path(path)
    # Resolve relative paths against base_dir, not cwd
    if not p.is_absolute():
        p = resolved_base / p
    resolved_path = p.resolve(strict=False)

    if not resolved_path.is_relative_to(resolved_base):
        raise ValueError(
            f"Path traversal detected: {path} resolves outside {resolved_base} "
            f"(set {FILES_DIR_ENV} to change the allowed directory)"
        )

    return resolved_path
