"""I/O utility functions for MCP Atlassian."""

import ctypes
import errno
import logging
import os
import stat
import subprocess
from pathlib import Path
from typing import IO, Literal

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


def _is_windows() -> bool:
    """Whether to apply the Windows ACL branch of :func:`restrict_to_owner`.

    A thin wrapper around the real check so tests can simulate the Windows
    branch on any platform without touching ``os.name`` itself: ``Path``'s
    own concrete class (``WindowsPath``/``PosixPath``) is also chosen from
    ``os.name``, and instantiating the one that does not match the real,
    running OS raises ``NotImplementedError`` regardless of what ``os.name``
    is patched to -- so flipping ``os.name`` directly breaks on every other
    platform rather than simulating Windows on it.
    """
    return os.name == "nt"


def _current_user_sid() -> str:
    """Return the current process token's user SID as a string.

    Resolved directly through the Win32 API (``OpenProcessToken`` +
    ``GetTokenInformation(TokenUser)`` + ``ConvertSidToStringSidW``) rather
    than by shelling out to ``whoami /user`` and parsing its output, which is
    localized and so not a stable thing to parse. A SID, unlike a bare
    username, is unambiguous even when a local account and a domain/AzureAD
    account happen to share a display name.

    Returns:
        The SID in its string form (e.g. ``S-1-5-21-...``).

    Raises:
        OSError: If a Win32 call in the resolution fails.
    """
    import ctypes.wintypes as wintypes

    # ctypes.WinDLL/WinError/get_last_error exist only in the Windows-specific
    # typeshed stubs, so mypy (run on Linux in CI) does not know them.
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.argtypes = []
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    token_query = 0x0008
    token_user = 1

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), token_query, ctypes.byref(token)
    ):
        raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, token_user, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
            token, token_user, buf, size, ctypes.byref(size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        # TOKEN_USER is { SID_AND_ATTRIBUTES User } and SID_AND_ATTRIBUTES is
        # { PSID Sid; DWORD Attributes }: the first pointer-sized field.
        sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        str_sid = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(str_sid)):
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        try:
            value = str_sid.value
            if value is None:
                raise OSError("ConvertSidToStringSidW returned a null string")
            return value
        finally:
            kernel32.LocalFree(str_sid)
    finally:
        kernel32.CloseHandle(token)


def _system_icacls_path() -> Path:
    """Return the real ``System32\\icacls.exe``, not whatever ``icacls``
    resolves to on the search path.

    ``shutil.which("icacls")`` -- the previous implementation -- checks the
    current working directory before ``PATH`` for a bare command name on
    Windows, confirmed empirically: a malicious ``icacls.cmd`` or
    ``icacls.exe`` placed in the process's working directory runs instead of
    the real tool and can simply exit 0, silently skipping the ACL hardening
    below while this function still reports success.

    Returns:
        The resolved path to the system ``icacls.exe``.
    """
    system_root = (
        os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    )
    return Path(system_root) / "System32" / "icacls.exe"


def restrict_to_owner(path: str | os.PathLike[str], mode: int = 0o600) -> None:
    """Restrict *path* so only its owner can read or write it.

    ``os.chmod`` only changes the POSIX mode bits Python reports back; on
    Windows those bits are a Python-level emulation and do not touch the
    real access control list, so a mode-0600 chmod there silently leaves the
    file (or directory) readable by every local account that inherited
    access from its parent — including, by default, every account on the
    machine. This additionally resets the Windows ACL to grant only the
    current user when running on Windows.

    Args:
        path: The file or directory to restrict.
        mode: The POSIX mode to apply via :func:`os.chmod`.

    Raises:
        OSError: If ``os.chmod`` or SID resolution fails.
        subprocess.CalledProcessError: If an ``icacls`` call exits non-zero.
        subprocess.TimeoutExpired: If an ``icacls`` call does not finish
            within its timeout.
    """
    path = Path(path)
    os.chmod(path, mode)
    if not _is_windows():
        return
    sid = _current_user_sid()
    # A freshly created file under a directory with no inheritable ACE of its
    # own falls back to a default DACL that, on this machine, included the
    # file's owner *and* BUILTIN\Administrators and NT AUTHORITY\SYSTEM as
    # separate explicit (non-inherited) entries -- `/grant:r` only replaces
    # the named principal's own grant, so it would leave those other,
    # pre-existing entries in place. Making the grant on a directory
    # inheritable (`(OI)(CI)`) avoids that fallback entirely: Windows then
    # propagates the owner-only entry to every file already inside the
    # directory immediately, and to every file created in it afterwards,
    # confirmed empirically against both cases.
    #
    # Granted by SID (`*S-1-...`, the `*` tells icacls the name is a SID)
    # rather than by username string: a bare username is ambiguous when a
    # local account and a domain/AzureAD account happen to share a display
    # name, and icacls's own name-to-principal lookup can behave
    # unexpectedly in that case.
    grant = f"*{sid}:(OI)(CI)F" if path.is_dir() else f"*{sid}:(F)"
    icacls_path = str(_system_icacls_path())
    # `/inheritance:r /grant:r` alone only strips *inherited* entries and
    # only replaces the named user's own grant, so an existing *explicit*
    # grant for some other principal (e.g. a stray `Everyone:(R)`, however
    # it got there) survives untouched -- confirmed empirically. An earlier
    # version of this function ran `/reset` first to clear that, but `/reset`
    # replaces the path's ACL with whatever its parent currently grants,
    # which can be broad; for an already-owner-only path, that step alone
    # instantly re-exposes it (and every file already inside it, for a
    # directory) under the parent's wider ACL until the second call
    # restricts it again -- confirmed empirically, and permanently if that
    # second call fails. List the path's current explicit grantees first
    # (read-only, no ACL change) and strip exactly those by name in the same
    # call that applies the owner-only grant, so the ACL only ever goes
    # from whatever it was straight to owner-only, with no broader
    # intermediate state.
    stale_grantees = _explicit_grant_principals(icacls_path, path)
    args = [icacls_path, str(path), "/inheritance:r", "/grant:r", grant]
    for principal in stale_grantees:
        args += ["/remove:g", principal]
    subprocess.run(  # noqa: S603 -- fixed args, no shell, path resolved directly
        args,
        check=True,
        capture_output=True,
        timeout=10,
    )


def _explicit_grant_principals(icacls_path: str, path: Path) -> list[str]:
    """Return principals holding an explicit (non-inherited) grant on ``path``.

    Read-only: lists the current ACL without changing it, so the caller can
    strip exactly these principals in the same ``icacls`` call that applies
    the owner-only grant, instead of a ``/reset`` that would briefly restore
    the parent's (possibly broader) ACL first.
    """
    result = subprocess.run(  # noqa: S603 -- fixed args, no shell, path resolved directly
        [icacls_path, str(path)],
        check=True,
        capture_output=True,
        timeout=10,
        text=True,
    )
    path_str = str(path)
    principals: list[str] = []
    for raw_line in result.stdout.splitlines():
        line = (
            raw_line[len(path_str) :] if raw_line.startswith(path_str) else raw_line
        ).strip()
        if not line or ":" not in line:
            continue
        principal, _, flags = line.partition(":")
        if "(I)" not in flags:
            principals.append(principal.strip())
    return principals


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
        if is_wide_directory(root):
            # Kept for existing local setups; a tool call (possibly steered by
            # content it read) can then upload any file the user can read.
            logger.warning(
                "File path inputs are confined to %s, a filesystem root or home "
                "directory. Tools that upload files can read anything there. "
                "Set %s to a dedicated directory to narrow it.",
                root,
                FILES_DIR_ENV,
            )
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


_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_BINARY = getattr(os, "O_BINARY", 0)


def _open_dir_beneath(base: Path, directory: Path, path: str | os.PathLike[str]) -> int:
    """Open *directory* by walking down from *base* without following links.

    Each component is opened relative to the descriptor of the one above it
    with ``O_NOFOLLOW | O_DIRECTORY``, so the returned descriptor is a
    directory reached from *base* through real directories only, even if a
    component is swapped for a symlink while the walk runs.

    Raises:
        ValueError: If a component is a symlink or not a directory.
        OSError: If a component cannot be opened for another reason.
    """
    flags = os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC
    fd = os.open(base, flags)
    try:
        for part in directory.relative_to(base).parts:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except OSError as e:
                if e.errno in (errno.ELOOP, errno.ENOTDIR):
                    msg = f"Path {path} resolves outside {base}"
                    raise ValueError(msg) from e
                raise
            os.close(fd)
            fd = next_fd
    except BaseException:
        os.close(fd)
        raise
    return fd


def open_confined(
    path: str | os.PathLike[str],
    mode: Literal["rb", "wb"],
    base_dir: str | os.PathLike[str] | None = None,
) -> IO[bytes]:
    """Open *path* for binary read or write, verifying the opened file.

    :func:`validate_safe_path` checks a path, but a symlink swapped in after
    that check (on the file or on any parent directory) would make a plain
    ``open`` reach a file outside the boundary. This opens the parent
    directory by walking down from the boundary one component at a time
    without following symlinks, so the directory descriptor actually used is
    inside the boundary, and opens the file relative to that directory with
    ``O_NOFOLLOW``. The result must be a regular file.

    Args:
        path: The file to open.
        mode: ``"rb"`` to read an existing file, ``"wb"`` to create or
            truncate one.
        base_dir: The boundary directory. Defaults to :func:`get_file_root`.

    Returns:
        A binary file object whose ``name`` is the resolved path.

    Raises:
        ValueError: If the path, its directory or the opened file is outside
            the boundary, is a symlink, or is not a regular file.
        OSError: If the file cannot be opened for another reason (for
            example ``FileNotFoundError``).
    """
    if mode not in ("rb", "wb"):
        msg = f"Unsupported mode {mode!r}"
        raise ValueError(msg)
    if base_dir is None:
        base_dir = get_file_root()
    resolved_base = Path(base_dir).resolve(strict=False)
    resolved = validate_safe_path(path, resolved_base)
    parent, name = resolved.parent, resolved.name
    if not name:
        msg = f"Not a file path: {path}"
        raise ValueError(msg)

    # Anchor the open on a directory descriptor only where ``os.open`` accepts
    # ``dir_fd``. Windows cannot open a directory with ``os.open`` (it raises
    # PermissionError), so it opens the file by path below. On other platforms
    # a failure to open the directory is a real error and is not downgraded.
    if os.open in os.supports_dir_fd:
        dir_fd = _open_dir_beneath(resolved_base, parent, path)
    else:
        dir_fd = -1
    fd = -1
    try:
        real_parent = parent
        if dir_fd < 0:
            real_parent = Path(os.path.realpath(parent))
            if not real_parent.is_relative_to(resolved_base):
                msg = f"Path {path} resolves outside {resolved_base}"
                raise ValueError(msg)

        flags = _O_NOFOLLOW | _O_CLOEXEC | _O_BINARY
        if mode == "rb":
            flags |= os.O_RDONLY
        else:
            flags |= os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        try:
            if dir_fd >= 0:
                fd = os.open(name, flags, 0o666, dir_fd=dir_fd)
            else:  # no dir_fd support (Windows)
                if os.path.islink(real_parent / name):
                    msg = f"Refusing to follow a symlink: {path}"
                    raise ValueError(msg)
                fd = os.open(real_parent / name, flags, 0o666)
        except OSError as e:
            if os.path.islink(real_parent / name):
                msg = f"Refusing to follow a symlink: {path}"
                raise ValueError(msg) from e
            if isinstance(e, IsADirectoryError):
                msg = f"Not a regular file: {path}"
                raise ValueError(msg) from e
            raise
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            msg = f"Not a regular file: {path}"
            raise ValueError(msg)
        file_obj = os.fdopen(fd, mode)
        fd = -1
    finally:
        if fd >= 0:
            os.close(fd)
        if dir_fd >= 0:
            os.close(dir_fd)
    # Keep the path as the name (requests uses it as the upload filename).
    file_obj.raw.name = str(real_parent / name)  # type: ignore[attr-defined]
    return file_obj
