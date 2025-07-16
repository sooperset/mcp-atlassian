"""Tests for custom headers parsing functionality."""

from mcp_atlassian.utils.env import get_custom_headers


class TestParseCustomHeaders:
    """Test the parse_custom_headers function."""

    def test_empty_input(self, monkeypatch):
        """Test parse_custom_headers with empty/None inputs."""
        # Test unset environment variable
        monkeypatch.delenv("TEST_HEADERS", raising=False)
        assert get_custom_headers("TEST_HEADERS") == {}

        # Test empty string
        monkeypatch.setenv("TEST_HEADERS", "")
        assert get_custom_headers("TEST_HEADERS") == {}

        # Test whitespace only
        monkeypatch.setenv("TEST_HEADERS", "   ")
        assert get_custom_headers("TEST_HEADERS") == {}

        monkeypatch.setenv("TEST_HEADERS", "\t\n")
        assert get_custom_headers("TEST_HEADERS") == {}

    def test_single_header(self, monkeypatch):
        """Test parsing a single header."""
        monkeypatch.setenv("TEST_HEADERS", "X-Custom=value123")
        result = get_custom_headers("TEST_HEADERS")
        assert result == {"X-Custom": "value123"}

        # Test with spaces around key and value
        monkeypatch.setenv("TEST_HEADERS", " X-Spaced = value with spaces ")
        result = get_custom_headers("TEST_HEADERS")
        assert result == {"X-Spaced": "value with spaces"}

    def test_multiple_headers(self, monkeypatch):
        """Test parsing multiple comma-separated headers."""
        monkeypatch.setenv("TEST_HEADERS", "X-Corp-Auth=token123,X-Dept=engineering")
        result = get_custom_headers("TEST_HEADERS")
        expected = {"X-Corp-Auth": "token123", "X-Dept": "engineering"}
        assert result == expected

    def test_headers_with_spaces(self, monkeypatch):
        """Test parsing headers with various spacing."""
        monkeypatch.setenv("TEST_HEADERS", " X-Key = value , X-Another = value2 ")
        result = get_custom_headers("TEST_HEADERS")
        expected = {"X-Key": "value", "X-Another": "value2"}
        assert result == expected

    def test_value_with_equals_signs(self, monkeypatch):
        """Test parsing headers where values contain equals signs."""
        monkeypatch.setenv("TEST_HEADERS", "X-Token=abc=def=123")
        result = get_custom_headers("TEST_HEADERS")
        assert result == {"X-Token": "abc=def=123"}

        # Multiple headers with equals in values
        monkeypatch.setenv(
            "TEST_HEADERS", "X-Token=abc=def,X-URL=https://api.example.com/v1?key=value"
        )
        result = get_custom_headers("TEST_HEADERS")
        expected = {
            "X-Token": "abc=def",
            "X-URL": "https://api.example.com/v1?key=value",
        }
        assert result == expected

    def test_malformed_headers(self, monkeypatch):
        """Test handling of malformed header strings."""
        # Header without equals sign - should be skipped
        monkeypatch.setenv("TEST_HEADERS", "invalid-header-format")
        result = get_custom_headers("TEST_HEADERS")
        assert result == {}

        # Mix of valid and invalid headers
        monkeypatch.setenv(
            "TEST_HEADERS", "X-Valid=value,invalid-header,X-Another=value2"
        )
        result = get_custom_headers("TEST_HEADERS")
        expected = {"X-Valid": "value", "X-Another": "value2"}
        assert result == expected

    def test_empty_key_or_value(self, monkeypatch):
        """Test handling of empty keys or values."""
        # Empty key - should be skipped
        monkeypatch.setenv("TEST_HEADERS", "=value")
        result = get_custom_headers("TEST_HEADERS")
        assert result == {}

        # Empty value - should be included
        monkeypatch.setenv("TEST_HEADERS", "X-Empty=")
        result = get_custom_headers("TEST_HEADERS")
        assert result == {"X-Empty": ""}

        # Whitespace-only key - should be skipped
        monkeypatch.setenv("TEST_HEADERS", "  =value")
        result = get_custom_headers("TEST_HEADERS")
        assert result == {}

        # Mix of empty and valid
        monkeypatch.setenv("TEST_HEADERS", "=empty_key,X-Valid=value, =another_empty")
        result = get_custom_headers("TEST_HEADERS")
        assert result == {"X-Valid": "value"}

    def test_special_characters_in_values(self, monkeypatch):
        """Test headers with special characters in values."""
        monkeypatch.setenv("TEST_HEADERS", "X-Special=!@#$%^&*()_+-[]{}|;':\"/<>?")
        result = get_custom_headers("TEST_HEADERS")
        assert result == {"X-Special": "!@#$%^&*()_+-[]{}|;':\"/<>?"}

    def test_unicode_characters(self, monkeypatch):
        """Test headers with unicode characters."""
        monkeypatch.setenv("TEST_HEADERS", "X-Unicode=café,X-Emoji=🚀")
        result = get_custom_headers("TEST_HEADERS")
        expected = {"X-Unicode": "café", "X-Emoji": "🚀"}
        assert result == expected

    def test_empty_pairs_in_list(self, monkeypatch):
        """Test handling of empty pairs in comma-separated list."""
        # Empty pairs should be skipped
        monkeypatch.setenv("TEST_HEADERS", "X-First=value1,,X-Second=value2,")
        result = get_custom_headers("TEST_HEADERS")
        expected = {"X-First": "value1", "X-Second": "value2"}
        assert result == expected

        # Only commas
        monkeypatch.setenv("TEST_HEADERS", ",,,")
        result = get_custom_headers("TEST_HEADERS")
        assert result == {}

    def test_complex_real_world_example(self, monkeypatch):
        """Test a complex real-world example."""
        headers_string = (
            "Authorization=Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9,"
            "X-API-Key=sk-1234567890abcdef,"
            "X-Request-ID=req_123456789,"
            "X-Custom-Header=value with spaces and = signs,"
            "User-Agent=MyApp/1.0 (Custom Agent)"
        )

        monkeypatch.setenv("TEST_HEADERS", headers_string)
        result = get_custom_headers("TEST_HEADERS")
        expected = {
            "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9",
            "X-API-Key": "sk-1234567890abcdef",
            "X-Request-ID": "req_123456789",
            "X-Custom-Header": "value with spaces and = signs",
            "User-Agent": "MyApp/1.0 (Custom Agent)",
        }
        assert result == expected

    def test_case_sensitive_keys(self, monkeypatch):
        """Test that header keys are case-sensitive."""
        monkeypatch.setenv(
            "TEST_HEADERS", "x-lower=value1,X-UPPER=value2,X-Mixed=value3"
        )
        result = get_custom_headers("TEST_HEADERS")
        expected = {"x-lower": "value1", "X-UPPER": "value2", "X-Mixed": "value3"}
        assert result == expected

    def test_duplicate_keys(self, monkeypatch):
        """Test behavior with duplicate keys - later values should override."""
        monkeypatch.setenv("TEST_HEADERS", "X-Duplicate=first,X-Duplicate=second")
        result = get_custom_headers("TEST_HEADERS")
        assert result == {"X-Duplicate": "second"}

    def test_newlines_and_tabs_in_input(self, monkeypatch):
        """Test handling of newlines and tabs in input."""
        # These should be treated as part of values, not separators
        monkeypatch.setenv(
            "TEST_HEADERS", "X-Multi=line1\nline2,X-Tab=value\twith\ttabs"
        )
        result = get_custom_headers("TEST_HEADERS")
        expected = {"X-Multi": "line1\nline2", "X-Tab": "value\twith\ttabs"}
        assert result == expected
