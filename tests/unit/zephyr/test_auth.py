"""Tests for the Zephyr Essential authentication module."""

import json
import pytest
from unittest.mock import patch

from mcp_atlassian.zephyr.auth import generate_zephyr_jwt


class TestZephyrAuth:
    """Test class for Zephyr Essential authentication."""

    @patch("mcp_atlassian.zephyr.auth.time.time")
    def test_generate_zephyr_jwt(self, mock_time):
        """Test generating a JWT token for Zephyr Essential API."""
        # Mock time.time() to return a fixed timestamp
        mock_time.return_value = 1600000000

        # Test parameters
        method = "GET"
        api_path = "/testcases"
        query_params = {"projectKey": "PROJ", "maxResults": "10"}
        account_id = "test-account-id"
        access_key = "test-access-key"
        secret_key = "test-secret-key"

        # Generate JWT token
        token = generate_zephyr_jwt(
            method=method,
            api_path=api_path,
            query_params=query_params,
            account_id=account_id,
            access_key=access_key,
            secret_key=secret_key,
            expiration_sec=3600
        )

        # Verify token is a string
        assert isinstance(token, str)

        # Verify token has three parts (header, payload, signature)
        parts = token.split(".")
        assert len(parts) == 3

        # Verify payload contains expected claims
        import base64
        payload_json = base64.b64decode(parts[1] + "==").decode("utf-8")
        payload = json.loads(payload_json)

        assert payload["sub"] == account_id
        assert payload["iss"] == access_key
        assert "qsh" in payload
        assert payload["iat"] == 1600000000
        assert payload["exp"] == 1600000000 + 3600

    def test_generate_zephyr_jwt_with_empty_params(self):
        """Test generating a JWT token with empty query parameters."""
        # Test parameters
        method = "POST"
        api_path = "/testcases"
        account_id = "test-account-id"
        access_key = "test-access-key"
        secret_key = "test-secret-key"

        # Generate JWT token with empty query params
        token = generate_zephyr_jwt(
            method=method,
            api_path=api_path,
            query_params={},
            account_id=account_id,
            access_key=access_key,
            secret_key=secret_key
        )

        # Verify token is a string
        assert isinstance(token, str)

        # Verify token has three parts (header, payload, signature)
        parts = token.split(".")
        assert len(parts) == 3