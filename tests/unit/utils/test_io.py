"""Tests for the I/O utilities module."""

import os
from unittest.mock import patch

from mcp_atlassian.utils.io import is_read_only_mode


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
