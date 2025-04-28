"Tests for the date utility functions."

import pytest

from mcp_atlassian.utils import parse_date


def test_parse_date_invalid_input():
    """Test that parse_date returns an empty string for invalid dates."""
    with pytest.raises(ValueError):
        parse_date("invalid")


def test_parse_date_valid():
    """Test that parse_date returns the correct date for valid dates."""
    assert str(parse_date("2021-01-01")) == "2021-01-01 00:00:00"


def test_parse_date_epoch_as_str():
    """Test that parse_date returns the correct date for epoch timestamps as str."""
    assert str(parse_date("1612156800000")) == "2021-02-01 05:20:00+00:00"


def test_parse_date_epoch_as_int():
    """Test that parse_date returns the correct date for epoch timestamps as int."""
    assert str(parse_date(1612156800000)) == "2021-02-01 05:20:00+00:00"


def test_parse_date_iso8601():
    """Test that parse_date returns the correct date for ISO 8601."""
    assert str(parse_date("2021-01-01T00:00:00Z")) == "2021-01-01 00:00:00+00:00"


def test_parse_date_rfc3339():
    """Test that parse_date returns the correct date for RFC 3339."""
    assert (
        str(parse_date("1937-01-01T12:00:27.87+00:20"))
        == "1937-01-01 12:00:27.870000+00:20"
    )
