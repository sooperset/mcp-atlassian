"""Test the masking utility functions."""

import logging
from unittest.mock import patch

from mcp_atlassian.utils.logging import log_config_param, mask_sensitive


class TestMaskSensitive:
    """Test the _mask_sensitive function."""

    def test_none_value(self):
        """Test masking None value."""
        assert mask_sensitive(None) == "Not Provided"

    def test_short_value(self):
        """Test masking short value."""
        assert mask_sensitive("abc") == "***"
        assert mask_sensitive("abcdef") == "******"
        assert mask_sensitive("abcdefgh", keep_chars=4) == "********"

    def test_normal_value(self):
        """Test masking normal value."""
        assert mask_sensitive("abcdefghijkl", keep_chars=2) == "ab********kl"
        assert mask_sensitive("abcdefghijkl") == "abcd****ijkl"
        assert (
            mask_sensitive("abcdefghijklmnopqrstuvwxyz", keep_chars=5)
            == "abcde****************vwxyz"
        )


class TestLogConfigParam:
    """Test the _log_config_param function."""

    @patch("mcp_atlassian.utils.logging.logging.Logger")
    def test_normal_param(self, mock_logger):
        """Test logging normal parameter."""
        log_config_param(mock_logger, "Jira", "URL", "https://jira.example.com")
        mock_logger.info.assert_called_once_with("Jira URL: https://jira.example.com")

    @patch("mcp_atlassian.utils.logging.logging.Logger")
    def test_none_param(self, mock_logger):
        """Test logging None parameter."""
        log_config_param(mock_logger, "Jira", "Projects Filter", None)
        mock_logger.info.assert_called_once_with("Jira Projects Filter: Not Provided")

    @patch("mcp_atlassian.utils.logging.logging.Logger")
    def test_sensitive_param(self, mock_logger):
        """Test logging sensitive parameter."""
        log_config_param(
            mock_logger, "Jira", "API Token", "abcdefghijklmnop", sensitive=True
        )
        mock_logger.info.assert_called_once_with("Jira API Token: abcd********mnop")

    def test_log_config_param_masks_proxy_url(self, caplog):
        """Test that log_config_param masks credentials in proxy URLs when sensitive=True."""
        logger = logging.getLogger("test-proxy-logger")
        proxy_url = "socks5://user:pass@proxy.example.com:1080"
        with caplog.at_level(logging.INFO, logger="test-proxy-logger"):
            log_config_param(logger, "Jira", "SOCKS_PROXY", proxy_url, sensitive=True)
        # Should mask the middle part of the URL, not show user:pass
        assert any(
            rec.message.startswith("Jira SOCKS_PROXY: sock")
            and rec.message.endswith("1080")
            and "user:pass" not in rec.message
            for rec in caplog.records
        )
