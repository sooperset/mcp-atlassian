"""
Tests for the base models and utility classes.
"""

from typing import Any

import pytest

from src.mcp_atlassian.models.base import ApiModel, TimestampMixin
from src.mcp_atlassian.models.constants import EMPTY_STRING


class TestApiModel:
    """Tests for the ApiModel base class."""

    def test_base_from_api_response_not_implemented(self):
        """Test that from_api_response raises NotImplementedError if not overridden."""
        with pytest.raises(NotImplementedError):
            ApiModel.from_api_response({})

    def test_base_to_simplified_dict(self):
        """Test that to_simplified_dict returns a dictionary with non-None values."""

        # Create a test subclass with some fields
        class TestModel(ApiModel):
            field1: str = "test"
            field2: int = 123
            field3: str = None

            @classmethod
            def from_api_response(cls, data: dict[str, Any], **kwargs):
                return cls()

        model = TestModel()
        result = model.to_simplified_dict()

        assert isinstance(result, dict)
        assert "field1" in result
        assert "field2" in result
        assert "field3" not in result  # None values should be excluded
        assert result["field1"] == "test"
        assert result["field2"] == 123


class TestTimestampMixin:
    """Tests for the TimestampMixin utility class."""

    def test_format_timestamp_valid(self):
        """Test formatting a valid ISO 8601 timestamp."""
        timestamp = "2024-01-01T12:34:56.789+0000"
        formatter = TimestampMixin()

        result = formatter.format_timestamp(timestamp)

        assert result == "2024-01-01 12:34:56"

    def test_format_timestamp_with_z(self):
        """Test formatting a timestamp with Z (UTC) timezone."""
        timestamp = "2024-01-01T12:34:56.789Z"
        formatter = TimestampMixin()

        result = formatter.format_timestamp(timestamp)

        assert result == "2024-01-01 12:34:56"

    def test_format_timestamp_none(self):
        """Test formatting a None timestamp."""
        formatter = TimestampMixin()

        result = formatter.format_timestamp(None)

        assert result == EMPTY_STRING

    def test_format_timestamp_invalid(self):
        """Test formatting an invalid timestamp string."""
        invalid_timestamp = "not-a-timestamp"
        formatter = TimestampMixin()

        result = formatter.format_timestamp(invalid_timestamp)

        assert result == invalid_timestamp  # Should return the original string

    def test_is_valid_timestamp_valid(self):
        """Test validating a valid ISO 8601 timestamp."""
        timestamp = "2024-01-01T12:34:56.789+0000"
        formatter = TimestampMixin()

        assert formatter.is_valid_timestamp(timestamp) is True

    def test_is_valid_timestamp_with_z(self):
        """Test validating a timestamp with Z (UTC) timezone."""
        timestamp = "2024-01-01T12:34:56.789Z"
        formatter = TimestampMixin()

        assert formatter.is_valid_timestamp(timestamp) is True

    def test_is_valid_timestamp_none(self):
        """Test validating a None timestamp."""
        formatter = TimestampMixin()

        assert formatter.is_valid_timestamp(None) is False

    def test_is_valid_timestamp_invalid(self):
        """Test validating an invalid timestamp string."""
        invalid_timestamp = "not-a-timestamp"
        formatter = TimestampMixin()

        assert formatter.is_valid_timestamp(invalid_timestamp) is False
