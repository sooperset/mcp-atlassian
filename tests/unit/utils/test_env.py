"""Tests for environment variable utility functions."""

from mcp_atlassian.utils.env import (
    is_env_extended_truthy,
    is_env_ssl_verify,
    is_env_truthy,
)


class TestIsEnvTruthy:
    """Test the is_env_truthy function."""

    def test_standard_truthy_values(self, monkeypatch):
        """Test standard truthy values: 'true', '1', 'yes'."""
        truthy_values = ["true", "1", "yes"]

        for value in truthy_values:
            monkeypatch.setenv("TEST_VAR", value)
            assert is_env_truthy("TEST_VAR") is True

        # Test uppercase variants
        for value in truthy_values:
            monkeypatch.setenv("TEST_VAR", value.upper())
            assert is_env_truthy("TEST_VAR") is True

        # Test mixed case variants
        for value in truthy_values:
            monkeypatch.setenv("TEST_VAR", value.capitalize())
            assert is_env_truthy("TEST_VAR") is True

    def test_standard_falsy_values(self, monkeypatch):
        """Test that standard falsy values return False."""
        falsy_values = ["false", "0", "no", "", "invalid", "y", "on"]

        for value in falsy_values:
            monkeypatch.setenv("TEST_VAR", value)
            assert is_env_truthy("TEST_VAR") is False

    def test_unset_variable_with_default(self, monkeypatch):
        """Test behavior when variable is unset with various defaults."""
        monkeypatch.delenv("TEST_VAR", raising=False)

        # Default empty string
        assert is_env_truthy("TEST_VAR") is False

        # Default truthy value
        assert is_env_truthy("TEST_VAR", "true") is True
        assert is_env_truthy("TEST_VAR", "1") is True
        assert is_env_truthy("TEST_VAR", "yes") is True

        # Default falsy value
        assert is_env_truthy("TEST_VAR", "false") is False
        assert is_env_truthy("TEST_VAR", "0") is False

    def test_empty_string_environment_variable(self, monkeypatch):
        """Test behavior when environment variable is set to empty string."""
        monkeypatch.setenv("TEST_VAR", "")
        assert is_env_truthy("TEST_VAR") is False


class TestIsEnvExtendedTruthy:
    """Test the is_env_extended_truthy function."""

    def test_extended_truthy_values(self, monkeypatch):
        """Test extended truthy values: 'true', '1', 'yes', 'y', 'on'."""
        truthy_values = ["true", "1", "yes", "y", "on"]

        for value in truthy_values:
            monkeypatch.setenv("TEST_VAR", value)
            assert is_env_extended_truthy("TEST_VAR") is True

        # Test uppercase variants
        for value in truthy_values:
            monkeypatch.setenv("TEST_VAR", value.upper())
            assert is_env_extended_truthy("TEST_VAR") is True

        # Test mixed case variants
        for value in truthy_values:
            monkeypatch.setenv("TEST_VAR", value.capitalize())
            assert is_env_extended_truthy("TEST_VAR") is True

    def test_extended_falsy_values(self, monkeypatch):
        """Test that extended falsy values return False."""
        falsy_values = ["false", "0", "no", "", "invalid", "off"]

        for value in falsy_values:
            monkeypatch.setenv("TEST_VAR", value)
            assert is_env_extended_truthy("TEST_VAR") is False

    def test_extended_vs_standard_difference(self, monkeypatch):
        """Test that extended truthy accepts 'y' and 'on' while standard doesn't."""
        extended_only_values = ["y", "on"]

        for value in extended_only_values:
            monkeypatch.setenv("TEST_VAR", value)
            # Extended should be True
            assert is_env_extended_truthy("TEST_VAR") is True
            # Standard should be False
            assert is_env_truthy("TEST_VAR") is False

    def test_unset_variable_with_default(self, monkeypatch):
        """Test behavior when variable is unset with various defaults."""
        monkeypatch.delenv("TEST_VAR", raising=False)

        # Default empty string
        assert is_env_extended_truthy("TEST_VAR") is False

        # Default truthy values
        assert is_env_extended_truthy("TEST_VAR", "true") is True
        assert is_env_extended_truthy("TEST_VAR", "y") is True
        assert is_env_extended_truthy("TEST_VAR", "on") is True

        # Default falsy value
        assert is_env_extended_truthy("TEST_VAR", "false") is False


class TestIsEnvSslVerify:
    """Test the is_env_ssl_verify function."""

    def test_ssl_verify_default_true(self, monkeypatch):
        """Test that SSL verification defaults to True when unset."""
        monkeypatch.delenv("TEST_VAR", raising=False)
        assert is_env_ssl_verify("TEST_VAR") is True

    def test_ssl_verify_explicit_false_values(self, monkeypatch):
        """Test that SSL verification is False only for explicit false values."""
        false_values = ["false", "0", "no"]

        for value in false_values:
            monkeypatch.setenv("TEST_VAR", value)
            assert is_env_ssl_verify("TEST_VAR") is False

        # Test uppercase variants
        for value in false_values:
            monkeypatch.setenv("TEST_VAR", value.upper())
            assert is_env_ssl_verify("TEST_VAR") is False

        # Test mixed case variants
        for value in false_values:
            monkeypatch.setenv("TEST_VAR", value.capitalize())
            assert is_env_ssl_verify("TEST_VAR") is False

    def test_ssl_verify_truthy_and_other_values(self, monkeypatch):
        """Test that SSL verification is True for truthy and other values."""
        truthy_values = ["true", "1", "yes", "y", "on", "enable", "enabled", "anything"]

        for value in truthy_values:
            monkeypatch.setenv("TEST_VAR", value)
            assert is_env_ssl_verify("TEST_VAR") is True

    def test_ssl_verify_custom_default(self, monkeypatch):
        """Test SSL verification with custom defaults."""
        monkeypatch.delenv("TEST_VAR", raising=False)

        # Custom default true
        assert is_env_ssl_verify("TEST_VAR", "true") is True

        # Custom default false
        assert is_env_ssl_verify("TEST_VAR", "false") is False

        # Custom default other value
        assert is_env_ssl_verify("TEST_VAR", "anything") is True

    def test_ssl_verify_empty_string(self, monkeypatch):
        """Test SSL verification when set to empty string."""
        monkeypatch.setenv("TEST_VAR", "")
        # Empty string is not in the false values, so should be True
        assert is_env_ssl_verify("TEST_VAR") is True


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_whitespace_handling(self, monkeypatch):
        """Test that whitespace in values is not stripped."""
        # Values with leading/trailing whitespace should not match
        monkeypatch.setenv("TEST_VAR", " true ")
        assert is_env_truthy("TEST_VAR") is False
        assert is_env_extended_truthy("TEST_VAR") is False

        monkeypatch.setenv("TEST_VAR", " false ")
        assert is_env_ssl_verify("TEST_VAR") is True  # Not in false values

    def test_special_characters(self, monkeypatch):
        """Test behavior with special characters."""
        special_values = ["true!", "@yes", "1.0", "y,", "on;"]

        for value in special_values:
            monkeypatch.setenv("TEST_VAR", value)
            assert is_env_truthy("TEST_VAR") is False
            assert is_env_extended_truthy("TEST_VAR") is False
            assert is_env_ssl_verify("TEST_VAR") is True  # Not in false values

    def test_unicode_values(self, monkeypatch):
        """Test behavior with unicode values."""
        unicode_values = ["truë", "yés", "1️⃣"]

        for value in unicode_values:
            monkeypatch.setenv("TEST_VAR", value)
            assert is_env_truthy("TEST_VAR") is False
            assert is_env_extended_truthy("TEST_VAR") is False
            assert is_env_ssl_verify("TEST_VAR") is True  # Not in false values

    def test_numeric_string_edge_cases(self, monkeypatch):
        """Test numeric string edge cases."""
        numeric_values = ["01", "1.0", "10", "-1", "2"]

        for value in numeric_values:
            monkeypatch.setenv("TEST_VAR", value)
            if value == "01":
                # "01" is not exactly "1", so should be False
                assert is_env_truthy("TEST_VAR") is False
                assert is_env_extended_truthy("TEST_VAR") is False
            else:
                assert is_env_truthy("TEST_VAR") is False
                assert is_env_extended_truthy("TEST_VAR") is False
            assert is_env_ssl_verify("TEST_VAR") is True  # Not in false values
