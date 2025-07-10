"""Tests for the auth utilities."""

import base64
import logging
import unittest
from unittest.mock import patch

from mcp_atlassian.utils.auth import AuthUtils


class TestAuthUtils(unittest.TestCase):
    """Test cases for the AuthUtils class."""

    def test_decode_basic_token_with_valid_token(self):
        """Test decoding a valid Basic Authentication token."""
        # Create a valid token: base64("user:pass")
        username = "testuser"
        password = "testpassword"
        token_content = f"{username}:{password}"
        token = base64.b64encode(token_content.encode()).decode()

        # Test with just the base64 part
        result = AuthUtils.decode_basic_token(token)
        self.assertIsNotNone(result)
        self.assertEqual(result, (username, password))

        # Test with "Basic " prefix
        result_with_prefix = AuthUtils.decode_basic_token(f"Basic {token}")
        self.assertIsNotNone(result_with_prefix)
        self.assertEqual(result_with_prefix, (username, password))

    def test_decode_basic_token_with_empty_token(self):
        """Test decoding an empty token."""
        with self.assertLogs(level=logging.WARNING):
            result = AuthUtils.decode_basic_token("")
            self.assertIsNone(result)

    def test_decode_basic_token_with_invalid_base64(self):
        """Test decoding an invalid base64 token."""
        with self.assertLogs(level=logging.ERROR):
            result = AuthUtils.decode_basic_token("not-valid-base64!")
            self.assertIsNone(result)

    def test_decode_basic_token_with_invalid_format(self):
        """Test decoding a token that doesn't contain a colon separator."""
        # Create a token without the colon separator
        token = base64.b64encode(b"useronly").decode()

        with self.assertLogs(level=logging.WARNING):
            result = AuthUtils.decode_basic_token(token)
            self.assertIsNone(result)

    @patch("mcp_atlassian.utils.auth.base64.b64decode")
    def test_decode_basic_token_with_unicode_error(self, mock_b64decode):
        """Test handling of UnicodeDecodeError during token decoding."""
        mock_b64decode.side_effect = UnicodeDecodeError(
            "utf-8", b"test", 0, 1, "test error"
        )

        with self.assertLogs(level=logging.ERROR):
            result = AuthUtils.decode_basic_token("validbase64==")
            self.assertIsNone(result)
