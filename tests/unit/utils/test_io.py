"""Tests for the I/O utilities module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_atlassian.utils.io import is_read_only_mode, validate_safe_path


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
        assert validate_safe_path("/etc/hostname") == Path("/etc/hostname")

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
