"""Tests for the date utility functions."""

from mcp_atlassian.utils import parse_date, parse_date_human_readable, parse_date_ymd


def test_parse_date_ymd_invalid_input():
    """Test that parse_date returns an empty string for invalid dates."""
    assert parse_date_ymd("invalid") == "invalid"


def test_parse_date_invalid_format():
    """Test that parse_date returns an empty string for invalid formats."""
    assert parse_date("2021-01-01", format_string="invalid") == "invalid"


def test_parse_date_ymd_valid():
    """Test that parse_date_ymd returns the correct date for valid dates."""
    assert parse_date_ymd("2021-01-01") == "2021-01-01"


def test_parse_date_ymd_epoch():
    """Test that parse_date_ymd returns the correct date for epoch timestamps."""
    assert parse_date_ymd("1612156800000") == "2021-02-01"


def test_parse_date_ymd_iso8601():
    """Test that parse_date_ymd returns the correct date for ISO 8601 timestamps."""
    assert parse_date_ymd("2021-01-01T00:00:00Z") == "2021-01-01"


def test_parse_date_ymd_rfc3339():
    """Test that parse_date_ymd returns the correct date for RFC 3339 timestamps."""
    assert parse_date_ymd("2021-01-01T00:00:00Z") == "2021-01-01"


def test_parse_date_human_readable():
    """Test that parse_date_human_readable returns the correct date
    for human readable dates."""
    assert parse_date_human_readable("2021-07-01") == "July 01, 2021"


def test_parse_date_human_readable_invalid_input():
    """Test that parse_date_human_readable returns an empty string for invalid dates."""
    assert parse_date_human_readable("invalid") == "invalid"
