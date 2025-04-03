"""Tests for the Confluence utility functions."""

from mcp_atlassian.confluence.constants import RESERVED_CQL_WORDS
from mcp_atlassian.confluence.utils import quote_cql_identifier_if_needed


class TestCQLQuoting:
    """Tests for CQL quoting utility functions."""

    def test_quote_personal_space_key(self):
        """Test quoting of personal space keys."""
        # Personal space keys starting with ~ should be quoted
        assert quote_cql_identifier_if_needed("~username") == '"~username"'
        assert quote_cql_identifier_if_needed("~admin") == '"~admin"'
        assert quote_cql_identifier_if_needed("~user.name") == '"~user.name"'

    def test_quote_reserved_words(self):
        """Test quoting of reserved CQL words."""
        # Reserved words should be quoted (case-insensitive)
        for word in list(RESERVED_CQL_WORDS)[:5]:  # Test a subset for brevity
            assert quote_cql_identifier_if_needed(word) == f'"{word}"'
            assert quote_cql_identifier_if_needed(word.upper()) == f'"{word.upper()}"'
            assert (
                quote_cql_identifier_if_needed(word.capitalize())
                == f'"{word.capitalize()}"'
            )

    def test_quote_numeric_keys(self):
        """Test quoting of keys starting with numbers."""
        # Keys starting with numbers should be quoted
        assert quote_cql_identifier_if_needed("123space") == '"123space"'
        assert quote_cql_identifier_if_needed("42") == '"42"'
        assert quote_cql_identifier_if_needed("1test") == '"1test"'

    def test_quote_special_characters(self):
        """Test quoting and escaping of identifiers with special characters."""
        # Keys with quotes or backslashes should be quoted and escaped
        assert quote_cql_identifier_if_needed('my"space') == '"my\\"space"'
        assert quote_cql_identifier_if_needed("test\\space") == '"test\\\\space"'

        # Test combined quotes and backslashes
        input_str = 'quote"and\\slash'
        result = quote_cql_identifier_if_needed(input_str)
        assert result == '"quote\\"and\\\\slash"'

        # Verify the result by checking individual characters
        assert result[0] == '"'  # opening quote
        assert result[-1] == '"'  # closing quote
        assert "\\\\" in result  # escaped backslash
        assert '\\"' in result  # escaped quote

    def test_no_quote_regular_keys(self):
        """Test that regular keys are not quoted."""
        # Regular space keys should not be quoted
        assert quote_cql_identifier_if_needed("DEV") == "DEV"
        assert quote_cql_identifier_if_needed("MYSPACE") == "MYSPACE"
        assert quote_cql_identifier_if_needed("documentation") == "documentation"
