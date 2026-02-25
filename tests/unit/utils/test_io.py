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
