"""Tests for the I/O utilities module."""

import os
import re
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_atlassian.utils.io import (
    is_read_only_mode,
    restrict_to_owner,
    validate_safe_path,
)


def test_is_read_only_mode_default():
    """Test that is_read_only_mode returns False by default."""
    # Arrange - Make sure READ_ONLY_MODE is not set
    with patch.dict(os.environ, clear=True):
        # Act
        result = is_read_only_mode()

        # Assert
        assert result is False


def test_is_read_only_mode_true():
    """Test that is_read_only_mode returns True when environment variable is set to true."""
    # Arrange - Set READ_ONLY_MODE to true
    with patch.dict(os.environ, {"READ_ONLY_MODE": "true"}):
        # Act
        result = is_read_only_mode()

        # Assert
        assert result is True


def test_is_read_only_mode_yes():
    """Test that is_read_only_mode returns True when environment variable is set to yes."""
    # Arrange - Set READ_ONLY_MODE to yes
    with patch.dict(os.environ, {"READ_ONLY_MODE": "yes"}):
        # Act
        result = is_read_only_mode()

        # Assert
        assert result is True


def test_is_read_only_mode_one():
    """Test that is_read_only_mode returns True when environment variable is set to 1."""
    # Arrange - Set READ_ONLY_MODE to 1
    with patch.dict(os.environ, {"READ_ONLY_MODE": "1"}):
        # Act
        result = is_read_only_mode()

        # Assert
        assert result is True


def test_is_read_only_mode_on():
    """Test that is_read_only_mode returns True when environment variable is set to on."""
    # Arrange - Set READ_ONLY_MODE to on
    with patch.dict(os.environ, {"READ_ONLY_MODE": "on"}):
        # Act
        result = is_read_only_mode()

        # Assert
        assert result is True


def test_is_read_only_mode_uppercase():
    """Test that is_read_only_mode is case-insensitive."""
    # Arrange - Set READ_ONLY_MODE to TRUE (uppercase)
    with patch.dict(os.environ, {"READ_ONLY_MODE": "TRUE"}):
        # Act
        result = is_read_only_mode()

        # Assert
        assert result is True


def test_is_read_only_mode_false():
    """Test that is_read_only_mode returns False when environment variable is set to false."""
    # Arrange - Set READ_ONLY_MODE to false
    with patch.dict(os.environ, {"READ_ONLY_MODE": "false"}):
        # Act
        result = is_read_only_mode()

        # Assert
        assert result is False


# --- validate_safe_path tests ---


class TestValidateSafePath:
    """Tests for validate_safe_path."""

    def test_safe_relative_path(self, tmp_path: Path) -> None:
        """Relative path within base_dir is accepted."""
        result = validate_safe_path("subdir/file.txt", base_dir=tmp_path)
        assert result == (tmp_path / "subdir" / "file.txt").resolve()

    def test_safe_absolute_path_within_base(self, tmp_path: Path) -> None:
        """Absolute path inside base_dir is accepted."""
        target = tmp_path / "sub" / "file.txt"
        result = validate_safe_path(str(target), base_dir=tmp_path)
        assert result == target.resolve()

    def test_traversal_dotdot(self, tmp_path: Path) -> None:
        """Relative path with ../ escaping base_dir raises ValueError."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_safe_path("../../etc/passwd", base_dir=tmp_path)

    def test_traversal_absolute_outside(self, tmp_path: Path) -> None:
        """Absolute path outside base_dir raises ValueError."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_safe_path("/etc/passwd", base_dir=tmp_path)

    def test_traversal_nested(self, tmp_path: Path) -> None:
        """Nested traversal normalised by resolve() raises ValueError."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_safe_path("ok/../../../etc/shadow", base_dir=tmp_path)

    def test_defaults_to_cwd(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When base_dir is None, defaults to os.getcwd()."""
        monkeypatch.chdir(tmp_path)
        result = validate_safe_path("child.txt")
        assert result == (tmp_path / "child.txt").resolve()


# --- File root boundary (remote transports) -----------------------------------


@pytest.fixture(autouse=True)
def _isolate_files_dir():
    """Override the suite-wide fixture: these tests check the real default.

    Every test here points HOME at a temporary directory instead.
    """
    from mcp_atlassian.utils import io as io_mod

    yield
    io_mod.set_remote_transport(False)


@pytest.fixture
def reset_file_root(monkeypatch: pytest.MonkeyPatch):
    """Isolate the module-level transport flag and the files-dir env var."""
    from mcp_atlassian.utils import io as io_mod

    monkeypatch.delenv(io_mod.FILES_DIR_ENV, raising=False)
    io_mod.set_remote_transport(False)
    yield io_mod
    io_mod.set_remote_transport(False)


class TestFileRoot:
    """The file-path boundary is explicit on remote transports, cwd on stdio."""

    def test_stdio_default_is_cwd(self, reset_file_root, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert reset_file_root.get_file_root() == tmp_path.resolve()

    def test_env_overrides_cwd(self, reset_file_root, tmp_path, monkeypatch):
        files = tmp_path / "files"
        monkeypatch.setenv(reset_file_root.FILES_DIR_ENV, str(files))
        assert reset_file_root.get_file_root() == files.resolve()

    def test_remote_default_is_dedicated_dir(
        self, reset_file_root, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.chdir(tmp_path)
        root = reset_file_root.configure_file_root_for_transport("streamable-http")
        assert root == (tmp_path / "home" / ".mcp-atlassian" / "files").resolve()
        assert root.is_dir()

    @pytest.mark.security_regression
    def test_remote_transport_from_root_cwd_does_not_expose_host_files(
        self, reset_file_root, tmp_path, monkeypatch
    ):
        """cwd=/ (systemd system unit default) must not widen the boundary."""
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.chdir("/")
        root = reset_file_root.configure_file_root_for_transport("sse")
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_safe_path("/etc/hostname")
        # A relative path lands in the dedicated directory, not under /.
        assert validate_safe_path("etc/hostname") == root / "etc" / "hostname"

    @pytest.mark.security_regression
    def test_remote_transport_from_home_cwd_does_not_expose_dotfiles(
        self, reset_file_root, tmp_path, monkeypatch
    ):
        home = tmp_path / "home"
        home.mkdir()
        (home / ".env").write_text("SECRET=1")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(home)
        root = reset_file_root.configure_file_root_for_transport("streamable-http")
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_safe_path(str(home / ".env"))
        assert validate_safe_path(".env") == root / ".env"

    @pytest.mark.parametrize("wide", ["root", "home"])
    def test_remote_transport_refuses_wide_files_dir(
        self, reset_file_root, tmp_path, monkeypatch, wide
    ):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        target = "/" if wide == "root" else str(home)
        monkeypatch.setenv(reset_file_root.FILES_DIR_ENV, target)
        with pytest.raises(ValueError, match="filesystem root or home"):
            reset_file_root.configure_file_root_for_transport("streamable-http")

    def test_stdio_keeps_wide_cwd(self, reset_file_root, monkeypatch):
        """Local stdio clients often start the server from / — unchanged."""
        monkeypatch.chdir("/")
        root = reset_file_root.configure_file_root_for_transport("stdio")
        assert root == Path("/")
        # /etc is a symlink on macOS, and validate_safe_path resolves symlinks.
        assert validate_safe_path("/etc/hostname") == Path("/etc/hostname").resolve()

    @pytest.mark.security_regression
    @pytest.mark.parametrize("wide", ["root", "home"])
    def test_stdio_warns_about_wide_root(
        self, reset_file_root, tmp_path, monkeypatch, caplog, wide
    ):
        """stdio keeps a wide root (no behaviour change) but says so at start."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir("/" if wide == "root" else home)
        with caplog.at_level("WARNING"):
            root = reset_file_root.configure_file_root_for_transport("stdio")
        assert root == (Path("/") if wide == "root" else home.resolve())
        assert reset_file_root.FILES_DIR_ENV in caplog.text

    def test_stdio_narrow_root_does_not_warn(
        self, reset_file_root, tmp_path, monkeypatch, caplog
    ):
        monkeypatch.chdir(tmp_path)
        with caplog.at_level("WARNING"):
            reset_file_root.configure_file_root_for_transport("stdio")
        assert reset_file_root.FILES_DIR_ENV not in caplog.text

    def test_is_in_cwd_root(self, reset_file_root, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert reset_file_root.is_in_cwd_root("victim.py")
        assert reset_file_root.is_in_cwd_root(tmp_path / "victim.py")
        assert not reset_file_root.is_in_cwd_root(tmp_path / "sub" / "victim.py")


# --- open_confined: the opened file is the validated file ----------------------


@pytest.fixture
def boundary(tmp_path: Path):
    base = tmp_path / "base"
    (base / "sub").mkdir(parents=True)
    (base / "sub" / "in.txt").write_text("inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "in.txt").write_text("SECRET")
    return base, outside


def _swap_after_validation(monkeypatch, swap):
    """Run ``swap`` right after validate_safe_path passes (the race window)."""
    from mcp_atlassian.utils import io as io_mod

    original = io_mod.validate_safe_path

    def validate_then_swap(*args, **kwargs):
        result = original(*args, **kwargs)
        swap()
        return result

    monkeypatch.setattr(io_mod, "validate_safe_path", validate_then_swap)


def _cannot_open_a_directory(monkeypatch):
    """Make ``os.open`` refuse directories, as Windows does."""
    real_open = os.open

    def windows_open(path, flags, mode=0o777, *, dir_fd=None):
        if os.path.isdir(path):
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", windows_open)


class TestOpenConfined:
    def test_reads_file_inside_boundary(self, boundary):
        from mcp_atlassian.utils.io import open_confined

        base, _ = boundary
        with open_confined(base / "sub" / "in.txt", "rb", base_dir=base) as f:
            assert f.read() == b"inside"
            assert f.name == str((base / "sub" / "in.txt").resolve())

    def test_writes_file_inside_boundary(self, boundary):
        from mcp_atlassian.utils.io import open_confined

        base, _ = boundary
        with open_confined(base / "sub" / "new.bin", "wb", base_dir=base) as f:
            f.write(b"data")
        assert (base / "sub" / "new.bin").read_bytes() == b"data"

    @pytest.mark.security_regression
    @pytest.mark.parametrize("mode", ["rb", "wb"])
    def test_directory_swapped_to_symlink_is_refused(self, boundary, monkeypatch, mode):
        from mcp_atlassian.utils.io import open_confined

        base, outside = boundary

        def swap():
            (base / "sub" / "in.txt").unlink()
            (base / "sub").rmdir()
            (base / "sub").symlink_to(outside, target_is_directory=True)

        _swap_after_validation(monkeypatch, swap)
        with pytest.raises(ValueError, match="outside"):
            open_confined(base / "sub" / "in.txt", mode, base_dir=base)
        assert (outside / "in.txt").read_text() == "SECRET"

    @pytest.mark.security_regression
    @pytest.mark.parametrize("mode", ["rb", "wb"])
    def test_file_swapped_to_symlink_is_refused(self, boundary, monkeypatch, mode):
        from mcp_atlassian.utils.io import open_confined

        base, outside = boundary
        target = base / "sub" / "in.txt"

        def swap():
            target.unlink()
            target.symlink_to(outside / "in.txt")

        _swap_after_validation(monkeypatch, swap)
        with pytest.raises(ValueError):
            open_confined(target, mode, base_dir=base)
        assert (outside / "in.txt").read_text() == "SECRET"

    def test_directory_is_not_opened_as_file(self, boundary):
        from mcp_atlassian.utils.io import open_confined

        base, _ = boundary
        with pytest.raises(ValueError):
            open_confined(base / "sub", "rb", base_dir=base)

    def test_traversal_still_rejected(self, boundary):
        from mcp_atlassian.utils.io import open_confined

        base, _ = boundary
        with pytest.raises(ValueError, match="Path traversal"):
            open_confined(base / ".." / "outside" / "in.txt", "rb", base_dir=base)

    def test_opens_file_where_a_directory_cannot_be_opened(self, boundary, monkeypatch):
        """A platform that cannot open a directory (Windows) still opens the file."""
        base, _ = boundary
        _cannot_open_a_directory(monkeypatch)
        from mcp_atlassian.utils.io import open_confined

        with open_confined(base / "sub" / "in.txt", "rb", base_dir=base) as f:
            assert f.read() == b"inside"

    @pytest.mark.security_regression
    def test_symlink_is_refused_where_a_directory_cannot_be_opened(
        self, boundary, monkeypatch
    ):
        """The fallback keeps refusing a symlink when no directory is opened."""
        base, outside = boundary
        target = base / "sub" / "in.txt"
        _cannot_open_a_directory(monkeypatch)
        from mcp_atlassian.utils.io import open_confined

        def swap():
            target.unlink()
            target.symlink_to(outside / "in.txt")

        _swap_after_validation(monkeypatch, swap)
        with pytest.raises(ValueError):
            open_confined(target, "rb", base_dir=base)
        assert (outside / "in.txt").read_text() == "SECRET"

    @pytest.mark.security_regression
    @pytest.mark.skipif(
        os.open not in os.supports_dir_fd, reason="needs dir_fd support"
    )
    def test_unopenable_directory_is_an_error_where_dir_fd_is_supported(
        self, boundary, monkeypatch
    ):
        """With dir_fd support, a directory that cannot be opened is not
        downgraded to the path-based open."""
        base, _ = boundary
        from mcp_atlassian.utils import io as io_mod

        real_open = os.open

        def refusing_open(path, flags, mode=0o777, *, dir_fd=None):
            if dir_fd is None and os.path.isdir(path):
                raise PermissionError(13, "Permission denied", str(path))
            return real_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(io_mod.os, "open", refusing_open)
        monkeypatch.setattr(
            io_mod.os, "supports_dir_fd", os.supports_dir_fd | {refusing_open}
        )
        with pytest.raises(PermissionError):
            io_mod.open_confined(base / "sub" / "in.txt", "rb", base_dir=base)

    @pytest.mark.security_regression
    @pytest.mark.skipif(
        os.open not in os.supports_dir_fd, reason="needs dir_fd support"
    )
    @pytest.mark.parametrize("mode", ["rb", "wb"])
    def test_parent_swapped_back_during_the_check_is_refused(
        self, boundary, monkeypatch, mode
    ):
        """A parent that is a symlink when opened and a directory when checked
        does not let the open reach the symlink's target."""
        base, outside = boundary
        from mcp_atlassian.utils import io as io_mod

        sub, saved = base / "sub", base / "sub-saved"

        def to_link():
            sub.rename(saved)
            sub.symlink_to(outside, target_is_directory=True)

        def to_dir():
            sub.unlink()
            saved.rename(sub)

        real_realpath = os.path.realpath
        armed = {"on": False}

        def swapping_realpath(path, *args, **kwargs):
            if not armed["on"]:
                return real_realpath(path, *args, **kwargs)
            armed["on"] = False
            to_dir()
            try:
                return real_realpath(path, *args, **kwargs)
            finally:
                to_link()

        def arm():
            to_link()
            armed["on"] = True

        _swap_after_validation(monkeypatch, arm)
        monkeypatch.setattr(io_mod.os.path, "realpath", swapping_realpath)
        try:
            with pytest.raises(ValueError):
                with io_mod.open_confined(sub / "in.txt", mode, base_dir=base) as f:
                    if mode == "rb":
                        f.read()
                    else:
                        f.write(b"overwritten")
        finally:
            if sub.is_symlink():
                to_dir()
        assert (outside / "in.txt").read_text() == "SECRET"


class TestRestrictToOwner:
    """``restrict_to_owner`` must leave a path readable only by its owner on
    every platform. ``os.chmod`` alone does not do that on Windows: it only
    changes the mode bits Python reports back, not the real ACL, so a
    mode-0600 chmod there silently left persisted OAuth token files (and
    their directory) readable by every local account -- see the regression
    history already covered by ``TestTokenFilePermissionsRegression`` in
    ``test_oauth.py`` (GHSA-g5xv, GHSA-76pr, GHSA-4596), which this extends
    to cover the Windows-specific gap those POSIX-focused tests could not
    catch.
    """

    @pytest.mark.skipif(os.name == "nt", reason="POSIX chmod semantics")
    def test_applies_posix_mode(self, tmp_path):
        target = tmp_path / "secret.json"
        target.write_text("{}")
        os.chmod(target, 0o644)

        restrict_to_owner(target, 0o600)

        assert stat.S_IMODE(target.stat().st_mode) == 0o600

    def test_windows_file_grant_is_owner_only_and_non_inheritable(
        self, tmp_path, monkeypatch
    ):
        """Simulates the Windows branch regardless of the platform tests run
        on, so CI exercises the icacls invocation even when it runs on
        Linux: a single file must be granted to its owner only, with no
        inheritance flags (meaningless, and refused by icacls, on a file).

        Patches ``_is_windows`` rather than ``os.name`` -- ``Path``'s own
        concrete class is chosen from ``os.name`` too, and constructing the
        one that does not match the real, running OS raises
        ``NotImplementedError`` regardless of what ``os.name`` is patched
        to, which broke this simulation on every platform but Windows.
        """
        from mcp_atlassian.utils import io as io_mod

        target = tmp_path / "secret.json"
        target.write_text("{}")
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if args[1:] == [str(target)]:
                return subprocess.CompletedProcess(args, 0, stdout="")
            return subprocess.CompletedProcess(args, 0)

        monkeypatch.setattr(io_mod, "_is_windows", lambda: True)
        monkeypatch.setattr(io_mod.subprocess, "run", fake_run)
        monkeypatch.setattr(io_mod, "_current_user_sid", lambda: "S-1-5-21-TEST")

        restrict_to_owner(target, 0o600)

        assert len(calls) == 2
        list_args, grant_args = calls
        assert list_args == [str(io_mod._system_icacls_path()), str(target)]
        assert grant_args[0] == str(io_mod._system_icacls_path())
        assert grant_args[1] == str(target)
        assert "/inheritance:r" in grant_args
        assert "/reset" not in grant_args
        assert grant_args[-2:] == ["/grant:r", "*S-1-5-21-TEST:(F)"]

    def test_windows_directory_grant_is_inheritable(self, tmp_path, monkeypatch):
        """A directory's grant must carry (OI)(CI) so Windows propagates the
        owner-only entry to files already inside it (e.g. a token file
        persisted by a pre-fix version of this server) and to files created
        in it afterwards -- confirmed empirically against both cases; a
        non-inheritable grant on the directory alone would leave existing
        and new files unprotected."""
        from mcp_atlassian.utils import io as io_mod

        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if args[1:] == [str(tmp_path)]:
                return subprocess.CompletedProcess(args, 0, stdout="")
            return subprocess.CompletedProcess(args, 0)

        monkeypatch.setattr(io_mod, "_is_windows", lambda: True)
        monkeypatch.setattr(io_mod.subprocess, "run", fake_run)
        monkeypatch.setattr(io_mod, "_current_user_sid", lambda: "S-1-5-21-TEST")

        restrict_to_owner(tmp_path, 0o700)

        assert len(calls) == 2
        assert calls[0] == [str(io_mod._system_icacls_path()), str(tmp_path)]
        assert "/reset" not in calls[1]
        assert calls[1][-2:] == ["/grant:r", "*S-1-5-21-TEST:(OI)(CI)F"]

    def test_icacls_path_is_resolved_from_system_root_not_the_search_path(
        self, monkeypatch
    ):
        """``_system_icacls_path`` must not depend on ``PATH`` or the
        current working directory at all, unlike the ``shutil.which``-based
        resolution this replaces: ``shutil.which("icacls")`` checks the
        current working directory before ``PATH`` for a bare command name on
        Windows (confirmed empirically), so a malicious ``icacls.cmd`` or
        ``icacls.exe`` placed there would run instead of the real tool and
        could silently skip the ACL hardening while reporting success."""
        from mcp_atlassian.utils import io as io_mod

        monkeypatch.setenv("SystemRoot", r"C:\FakeWindowsRoot")
        monkeypatch.delenv("WINDIR", raising=False)

        # Built through the same Path(...) joins the implementation uses,
        # not a single hardcoded backslash string: on a POSIX-path-
        # constructing runner (CI's Linux lint job, which only checks
        # import-time/collection-time code like this, not the Windows-only
        # runtime behavior), a lone string with literal backslashes becomes
        # one opaque path component, while joining with "/" adds real
        # component boundaries -- the two are not equal there even though
        # both print the same on Windows.
        assert (
            io_mod._system_icacls_path()
            == Path(r"C:\FakeWindowsRoot") / "System32" / "icacls.exe"
        )

    @pytest.mark.security_regression
    @pytest.mark.skipif(os.name != "nt", reason="exercises the real search path")
    def test_cwd_icacls_hijack_is_not_executed(self, tmp_path, monkeypatch):
        """Regression: a malicious ``icacls.cmd`` placed in the process's
        current working directory must not run in place of the real
        ``System32\\icacls.exe``."""

        marker = tmp_path / "hijacked.txt"
        (tmp_path / "icacls.cmd").write_text(
            f'@echo hijacked > "{marker}"\r\n@exit /b 0\r\n'
        )
        target = tmp_path / "secret.json"
        target.write_text("{}")
        monkeypatch.chdir(tmp_path)

        restrict_to_owner(target, 0o600)

        assert not marker.exists(), (
            "the planted icacls.cmd ran instead of the real tool"
        )
        after = subprocess.run(
            ["icacls", str(target)], capture_output=True, text=True, check=True
        ).stdout
        assert after.count(":(") == 1

    @pytest.mark.skipif(os.name != "nt", reason="resolves the real process token")
    def test_current_user_sid_has_the_expected_shape(self):
        from mcp_atlassian.utils.io import _current_user_sid

        sid = _current_user_sid()

        # A domain/local account SID is "S-1-5-21-<domain>-<domain>-<domain>-
        # <rid>", but a valid Windows account identity is not always that
        # shape: an Entra ID/AzureAD account uses "S-1-12-1-...", and service
        # identities use their own authorities again. Check general SID
        # syntax (authority "1", one or more numeric sub-authorities) rather
        # than this one account type's shape, so this test does not fail on
        # a supported Windows environment that ``_current_user_sid`` itself
        # resolves correctly.
        assert re.fullmatch(r"S-1-\d+(-\d+)+", sid), sid

    @pytest.mark.security_regression
    @pytest.mark.skipif(os.name != "nt", reason="asserts the real Windows ACL")
    def test_windows_real_acl_fixes_a_preexisting_broad_file(self, tmp_path):
        """Regression: a file that already has the OS default (broad) ACL --
        e.g. a token file a pre-fix version of this server already wrote to
        disk -- must end up owner-only once this touches its directory, not
        only files created after the fix is deployed."""
        target_dir = tmp_path / ".mcp-atlassian"
        target_dir.mkdir()
        stale = target_dir / "oauth-test.json"
        stale.write_text('{"old": "broad"}')

        def acl_text(path: Path) -> str:
            return subprocess.run(
                ["icacls", str(path)], capture_output=True, text=True, check=True
            ).stdout

        before = acl_text(stale)
        assert before.count(":(") > 1, (
            "expected a realistic multi-principal starting ACL -- if this "
            "fails, the test environment's default ACL changed and the "
            "regression this guards against may no longer be reproducible"
        )

        restrict_to_owner(target_dir, 0o700)
        restrict_to_owner(stale, 0o600)

        after = acl_text(stale)
        assert "Administrators" not in after
        assert "SYSTEM" not in after
        assert "Authenticated Users" not in after
        assert "BUILTIN\\Users" not in after
        assert after.count(":(") == 1

    @pytest.mark.security_regression
    @pytest.mark.skipif(os.name != "nt", reason="asserts the real Windows ACL")
    def test_windows_real_acl_removes_an_explicit_grant_for_another_principal(
        self, tmp_path
    ):
        """Regression: `/inheritance:r` only strips *inherited* entries and
        `/grant:r` only replaces the named user's *own* grant, so an
        existing explicit grant for some other principal -- however it got
        there -- survived both calls untouched. `/reset` first drops the
        path's entire existing ACL before the owner-only grant is applied,
        regardless of what was on it."""

        def acl_text(path: Path) -> str:
            return subprocess.run(
                ["icacls", str(path)], capture_output=True, text=True, check=True
            ).stdout

        target_dir = tmp_path / ".mcp-atlassian"
        target_dir.mkdir()
        stale = target_dir / "oauth-test.json"
        stale.write_text('{"old": "broad"}')
        # Grant by the well-known "Everyone" SID rather than that name
        # literally: the name itself is localized (e.g. "Jeder" on German
        # Windows), so passing it as text would fail on a non-English
        # runner, while a SID is universal.
        subprocess.run(
            ["icacls", str(stale), "/grant", "*S-1-1-0:(R)"],
            capture_output=True,
            check=True,
        )
        before = acl_text(stale)
        assert before.count(":(") > 1, (
            "expected the explicit grant just added to still be there -- if "
            "this fails, icacls itself rejected it rather than this code"
        )

        restrict_to_owner(target_dir, 0o700)
        restrict_to_owner(stale, 0o600)

        after = acl_text(stale)
        # Exactly one ACE (the owner-only grant just applied) rather than
        # checking for the absence of "Everyone" by name: that name is
        # itself localized, so the count is the locale-independent check.
        assert after.count(":(") == 1

    def test_windows_grant_never_resets_the_acl_first(self, tmp_path, monkeypatch):
        """Regression: an earlier version of this function ran `icacls
        /reset` before re-applying the owner-only grant. `/reset` replaces
        the path's ACL with whatever its parent currently grants, which can
        be broad -- confirmed empirically to propagate to files already
        inside a directory being reset, not just the directory itself -- so
        every subsequent save of an already-restricted directory (e.g. every
        OAuth token refresh) would transiently re-expose it and everything
        already inside it under the parent's wider ACL, and permanently if
        the second icacls call then failed. No call this function makes may
        use `/reset`."""
        from mcp_atlassian.utils import io as io_mod

        target = tmp_path / "secret.json"
        target.write_text("{}")
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if args[1:] == [str(target)]:
                return subprocess.CompletedProcess(args, 0, stdout="")
            return subprocess.CompletedProcess(args, 0)

        monkeypatch.setattr(io_mod, "_is_windows", lambda: True)
        monkeypatch.setattr(io_mod.subprocess, "run", fake_run)
        monkeypatch.setattr(io_mod, "_current_user_sid", lambda: "S-1-5-21-TEST")

        restrict_to_owner(target, 0o600)

        assert calls, "expected at least one icacls call"
        assert all("/reset" not in call for call in calls)

    @pytest.mark.security_regression
    @pytest.mark.skipif(os.name != "nt", reason="asserts the real Windows ACL")
    def test_windows_real_acl_resave_does_not_widen_an_already_restricted_file(
        self, tmp_path
    ):
        """Regression: restricting an already owner-only directory again
        (what every OAuth token refresh does, via `_save_tokens_to_file`)
        must never widen a file already inside it, even transiently, when
        the directory's own parent (e.g. the user's home directory) has a
        broader inheritable grant than owner-only -- the common case, and
        exactly the scenario `/reset` mishandled."""

        def acl_text(path: Path) -> str:
            return subprocess.run(
                ["icacls", str(path)], capture_output=True, text=True, check=True
            ).stdout

        home = tmp_path / "home"
        home.mkdir()
        subprocess.run(
            ["icacls", str(home), "/grant:r", "*S-1-1-0:(OI)(CI)R"],
            capture_output=True,
            check=True,
        )
        target_dir = home / ".mcp-atlassian"
        target_dir.mkdir()
        existing = target_dir / "oauth-test.json"
        existing.write_text('{"old": "secret"}')

        restrict_to_owner(target_dir, 0o700)
        restrict_to_owner(existing, 0o600)
        assert acl_text(existing).count(":(") == 1

        # The resave every token refresh performs.
        restrict_to_owner(target_dir, 0o700)

        after = acl_text(existing)
        assert "Everyone" not in after
        assert after.count(":(") == 1
