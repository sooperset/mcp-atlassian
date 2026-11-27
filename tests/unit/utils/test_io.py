"""Tests for the I/O utilities module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_atlassian.utils.io import (
    deduplicate_filename,
    is_read_only_mode,
    sanitize_attachment_filename,
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


class TestSanitizeAttachmentFilename:
    """A colon in a server-reported attachment name must not survive into the
    on-disk path. On Windows, ``name:stream`` addresses an NTFS alternate
    data stream on whatever file already has that name, rather than
    creating a new file -- so an attachment named e.g.
    ``existing-file.txt:evil`` would write into a hidden stream of a
    same-named file already in the confined download directory instead of
    its own file, invisibly to a normal directory listing."""

    @pytest.mark.security_regression
    def test_strips_colon(self):
        assert sanitize_attachment_filename("report.pdf:hidden") == "report.pdf_hidden"

    @pytest.mark.security_regression
    def test_strips_directory_components_and_colon_together(self):
        assert (
            sanitize_attachment_filename("../../etc/passwd:stream") == "passwd_stream"
        )

    def test_leaves_an_ordinary_filename_unchanged(self):
        assert sanitize_attachment_filename("report.pdf") == "report.pdf"

    def test_empty_result_falls_back_to_a_safe_name(self):
        assert sanitize_attachment_filename("") == "attachment"
        assert sanitize_attachment_filename("/") == "attachment"

    @pytest.mark.security_regression
    def test_real_filesystem_write_does_not_create_an_alternate_data_stream(
        self, tmp_path
    ):
        """End-to-end: writing to the sanitized name must produce a normal,
        visible file, never a hidden stream on a pre-existing same-named
        file (the actual exploit this guards against)."""
        existing = tmp_path / "existing-file.txt"
        existing.write_text("original content")

        safe_name = sanitize_attachment_filename("existing-file.txt:evil")
        target = tmp_path / safe_name
        target.write_bytes(b"attacker-controlled content")

        assert existing.read_text() == "original content"
        assert {p.name for p in tmp_path.iterdir()} == {
            "existing-file.txt",
            safe_name,
        }
        assert target.read_bytes() == b"attacker-controlled content"


class TestDeduplicateFilename:
    """Two different attachment names can sanitize to the same safe name
    (e.g. ``report:2026.pdf`` and ``report_2026.pdf`` both become
    ``report_2026.pdf`` once the colon is replaced) -- writing both to the
    same path would silently overwrite the first download while still
    reporting it a success."""

    def test_first_use_of_a_name_is_unchanged(self):
        seen: set[str] = set()
        assert deduplicate_filename("report.pdf", seen) == "report.pdf"
        assert seen == {"report.pdf"}

    @pytest.mark.security_regression
    def test_colliding_sanitized_names_get_disambiguated(self):
        seen: set[str] = set()
        first = deduplicate_filename(
            sanitize_attachment_filename("report:2026.pdf"), seen
        )
        second = deduplicate_filename(
            sanitize_attachment_filename("report_2026.pdf"), seen
        )

        assert first != second
        assert first == "report_2026.pdf"
        assert second == "report_2026 (2).pdf"

    def test_three_way_collision_keeps_incrementing(self):
        seen: set[str] = set()
        results = [deduplicate_filename("a.txt", seen) for _ in range(3)]
        assert results == ["a.txt", "a (2).txt", "a (3).txt"]

    def test_collision_on_a_name_with_no_extension(self):
        seen: set[str] = set()
        results = [deduplicate_filename("README", seen) for _ in range(2)]
        assert results == ["README", "README (2)"]


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("report.", "report"),
        ("report ", "report"),
        ("report. . ", "report"),
        ("..", "attachment"),
        ("foo/..", "attachment"),
        (".", "attachment"),
        ("...  ", "attachment"),
        (" ", "attachment"),
        ('a<>"|?*b.txt', "a______b.txt"),
        ("COM0.txt", "COM0.txt"),
        ("COM10.txt", "COM10.txt"),
        ("LPT0", "LPT0"),
        (".env", ".env"),
        ("CoN.txt", "_CoN.txt"),
    ],
)
def test_portable_attachment_filename(filename: str, expected: str) -> None:
    assert sanitize_attachment_filename(filename) == expected


@pytest.mark.parametrize("character", [chr(i) for i in range(32)] + [chr(127)])
def test_attachment_filename_replaces_control_characters(character: str) -> None:
    assert sanitize_attachment_filename(f"a{character}b.txt") == "a_b.txt"


@pytest.mark.parametrize(
    "device",
    ["CON", "PRN", "AUX", "NUL"]
    + [f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)],
)
@pytest.mark.parametrize("extension", ["", ".txt", ".tar.gz"])
def test_attachment_filename_escapes_reserved_devices(
    device: str, extension: str
) -> None:
    name = device.lower() + extension
    assert sanitize_attachment_filename(name) == "_" + name


@pytest.mark.parametrize(
    "names, expected",
    [
        (
            ["Report:2026.pdf", "report_2026.pdf"],
            ["Report_2026.pdf", "report_2026 (2).pdf"],
        ),
        (
            ["REPORT (2).pdf", "Report.pdf", "report.pdf"],
            ["REPORT (2).pdf", "Report.pdf", "report (3).pdf"],
        ),
        (["Stra\u00dfe.txt", "STRASSE.txt"], ["Stra\u00dfe.txt", "STRASSE (2).txt"]),
        ([".env", ".ENV"], [".env", ".ENV (2)"]),
        ([".env.local", ".ENV.local"], [".env.local", ".ENV (2).local"]),
        (["report.", "report ", "report"], ["report", "report (2)", "report (3)"]),
    ],
)
def test_portable_attachment_collisions(
    names: list[str], expected: list[str], tmp_path: Path
) -> None:
    seen: set[str] = set()
    results = [
        deduplicate_filename(sanitize_attachment_filename(n), seen) for n in names
    ]
    assert results == expected
    assert seen == {name.casefold() for name in expected}
    for index, name in enumerate(results):
        (tmp_path / name).write_bytes(bytes([index]))
    assert len(list(tmp_path.iterdir())) == len(names)
    for index, name in enumerate(results):
        assert (tmp_path / name).read_bytes() == bytes([index])


@pytest.mark.security_regression
@pytest.mark.parametrize(
    "path",
    [
        "existing.txt:hidden",
        "sub/existing.txt:hidden",
        "sub:stream/file.txt",
        "sub:stream/../file.txt",
    ],
)
def test_windows_validation_rejects_streams(
    path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcp_atlassian.utils import io as io_mod

    monkeypatch.setattr(io_mod.sys, "platform", "win32")
    with pytest.raises(ValueError, match="Alternate data stream"):
        validate_safe_path(tmp_path / path, base_dir=tmp_path)
    for mode in ("rb", "wb"):
        with pytest.raises(ValueError, match="Alternate data stream"):
            io_mod.open_confined(tmp_path / path, mode, base_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_windows_validation_accepts_normal_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcp_atlassian.utils import io as io_mod

    monkeypatch.setattr(io_mod.sys, "platform", "win32")
    assert validate_safe_path(tmp_path / "file.txt", tmp_path) == tmp_path / "file.txt"
