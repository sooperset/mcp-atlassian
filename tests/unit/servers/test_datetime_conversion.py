"""
Tests for datetime conversion functionality in ProForma forms.

These tests validate automatic conversion of ISO 8601 datetime strings
to Unix timestamps in milliseconds for the Jira Forms API.
"""

from datetime import datetime, timezone

import pytest

from src.mcp_atlassian.jira.forms_common import convert_datetime_to_timestamp


class TestDatetimeConversion:
    """Test cases for convert_datetime_to_timestamp function."""

    def test_iso8601_with_z_suffix(self):
        """Test conversion of ISO 8601 datetime with Z suffix."""
        result = convert_datetime_to_timestamp("2024-12-17T19:00:00Z", "DATETIME")
        # 2024-12-17 19:00:00 UTC = 1734462000 seconds = 1734462000000 milliseconds
        assert result == 1734462000000

    def test_iso8601_with_milliseconds(self):
        """Test conversion of ISO 8601 datetime with milliseconds."""
        result = convert_datetime_to_timestamp("2024-12-17T19:00:00.000Z", "DATETIME")
        assert result == 1734462000000

    def test_iso8601_with_timezone_offset(self):
        """Test conversion of ISO 8601 datetime with timezone offset."""
        # 2024-12-17 19:00:00 UTC is 2024-12-17 11:00:00 PST (-08:00)
        result = convert_datetime_to_timestamp("2024-12-17T11:00:00-08:00", "DATETIME")
        assert result == 1734462000000

    def test_iso8601_date_only(self):
        """Test conversion of ISO 8601 date without time."""
        result = convert_datetime_to_timestamp("2024-12-17", "DATE")
        # Should be midnight UTC on that date
        expected = int(
            datetime(2024, 12, 17, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
        )
        assert result == expected

    def test_iso8601_without_timezone_assumes_utc(self):
        """Test conversion of ISO 8601 datetime without timezone."""
        # Without timezone, we assume UTC for consistency
        result = convert_datetime_to_timestamp("2024-12-17T19:00:00", "DATETIME")
        expected = int(
            datetime(2024, 12, 17, 19, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
        )
        assert result == expected

    def test_unix_timestamp_passthrough_int(self):
        """Test that integer Unix timestamps pass through unchanged."""
        timestamp = 1734465600000
        result = convert_datetime_to_timestamp(timestamp, "DATETIME")
        assert result == timestamp

    def test_unix_timestamp_passthrough_float(self):
        """Test that float Unix timestamps are converted to int."""
        timestamp = 1734465600000.5
        result = convert_datetime_to_timestamp(timestamp, "DATETIME")
        assert result == 1734465600000  # Truncated to int

    @pytest.mark.parametrize(
        "value,field_type",
        [
            ("hello world", "TEXT"),
            (42, "NUMBER"),
            (["option1", "option2"], "MULTI_SELECT"),
            (True, "DATETIME"),  # Boolean shouldn't convert
            ({"key": "value"}, "DATETIME"),  # Dict shouldn't convert
        ],
    )
    def test_non_string_values_passthrough(self, value, field_type):
        """Non-string values pass through unchanged for any field type."""
        result = convert_datetime_to_timestamp(value, field_type)
        assert result == value

    def test_invalid_datetime_string_raises_error(self):
        """Test that invalid datetime strings raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            convert_datetime_to_timestamp("not-a-date", "DATETIME")
        assert "Invalid datetime format" in str(exc_info.value)
        assert "ISO 8601" in str(exc_info.value)

    def test_invalid_datetime_string_for_date_field(self):
        """Test that invalid date strings raise ValueError for DATE fields."""
        with pytest.raises(ValueError) as exc_info:
            convert_datetime_to_timestamp("invalid-date", "DATE")
        assert "Invalid datetime format" in str(exc_info.value)

    def test_none_value_passthrough(self):
        """Test that None values pass through unchanged."""
        result = convert_datetime_to_timestamp(None, "DATETIME")
        assert result is None

    def test_empty_string_raises_error_for_datetime(self):
        """Test that empty strings raise ValueError for DATE/DATETIME fields."""
        with pytest.raises(ValueError) as exc_info:
            convert_datetime_to_timestamp("", "DATETIME")
        assert "Invalid datetime format" in str(exc_info.value)

    def test_multiple_datetime_formats(self):
        """Test various valid ISO 8601 formats."""
        test_cases = [
            ("2024-12-17T19:00:00Z", "DATETIME"),
            ("2024-12-17T19:00:00.000Z", "DATETIME"),
            ("2024-12-17T19:00:00+00:00", "DATETIME"),
            ("2024-12-17", "DATE"),
        ]

        for value, field_type in test_cases:
            result = convert_datetime_to_timestamp(value, field_type)
            assert isinstance(result, int), f"Failed for {value}"
            assert result > 0, f"Invalid timestamp for {value}"

    def test_edge_case_epoch_time(self):
        """Test conversion of Unix epoch time."""
        result = convert_datetime_to_timestamp("1970-01-01T00:00:00Z", "DATETIME")
        assert result == 0

    def test_edge_case_future_date(self):
        """Test conversion of future dates."""
        result = convert_datetime_to_timestamp("2050-01-01T00:00:00Z", "DATETIME")
        # 2050-01-01 00:00:00 UTC
        expected = int(
            datetime(2050, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
        )
        assert result == expected

    def test_case_sensitive_field_types(self):
        """Test that field type matching is case-sensitive."""
        # "datetime" (lowercase) should not trigger conversion
        result = convert_datetime_to_timestamp("2024-12-17T19:00:00Z", "datetime")
        assert result == "2024-12-17T19:00:00Z"  # Passthrough
