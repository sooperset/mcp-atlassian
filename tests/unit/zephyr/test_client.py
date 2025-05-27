"""Tests for the Zephyr Essential client module."""

import json
import pytest
from unittest.mock import patch, MagicMock

from mcp_atlassian.zephyr.client import ZephyrClient
from mcp_atlassian.zephyr.config import ZephyrConfig


class TestZephyrClient:
    """Test class for Zephyr Essential client."""

    def test_client_init(self):
        """Test initializing ZephyrClient with a config object."""
        config = ZephyrConfig(
            base_url="https://test-api.zephyr.com",
            account_id="test-account-id",
            access_key="test-access-key",
            secret_key="test-secret-key"
        )
        client = ZephyrClient(config)

        assert client.config == config
        assert client.session.headers["Content-Type"] == "application/json"
        assert client.session.headers["Accept"] == "application/json"

    @patch("mcp_atlassian.zephyr.config.ZephyrConfig.from_env")
    def test_client_init_from_env(self, mock_from_env):
        """Test initializing ZephyrClient from environment variables."""
        mock_config = ZephyrConfig(
            base_url="https://test-api.zephyr.com",
            account_id="test-account-id",
            access_key="test-access-key",
            secret_key="test-secret-key"
        )
        mock_from_env.return_value = mock_config

        client = ZephyrClient()

        assert client.config == mock_config
        assert mock_from_env.called

    @patch("mcp_atlassian.zephyr.auth.generate_zephyr_jwt")
    @patch("requests.Session.request")
    def test_request_method(self, mock_request, mock_generate_jwt):
        """Test the _request method of ZephyrClient."""
        # Mock the JWT generation
        mock_generate_jwt.return_value = "test-jwt-token"

        # Mock the response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = json.dumps({"key": "value"}).encode("utf-8")
        mock_response.json.return_value = {"key": "value"}
        mock_request.return_value = mock_response

        # Create client
        config = ZephyrConfig(
            base_url="https://test-api.zephyr.com",
            account_id="test-account-id",
            access_key="test-access-key",
            secret_key="test-secret-key"
        )
        client = ZephyrClient(config)

        # Test GET request
        result = client._request("GET", "/testcases", params={"projectKey": "PROJ"})

        # Verify JWT was generated with correct parameters
        mock_generate_jwt.assert_called_once_with(
            method="GET",
            api_path="/testcases",
            query_params={"projectKey": "PROJ"},
            account_id="test-account-id",
            access_key="test-access-key",
            secret_key="test-secret-key"
        )

        # Verify request was made with correct parameters
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        assert args[0] == "GET"
        assert args[1] == "https://test-api.zephyr.com/testcases"
        assert kwargs["params"] == {"projectKey": "PROJ"}
        assert kwargs["headers"]["Authorization"] == "JWT test-jwt-token"

        # Verify result
        assert result == {"key": "value"}

    @patch("mcp_atlassian.zephyr.auth.generate_zephyr_jwt")
    @patch("requests.Session.request")
    def test_request_method_with_error(self, mock_request, mock_generate_jwt):
        """Test the _request method of ZephyrClient with an error response."""
        # Mock the JWT generation
        mock_generate_jwt.return_value = "test-jwt-token"

        # Mock the response with an error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error")
        mock_response.content = json.dumps({"error": "Not found"}).encode("utf-8")
        mock_response.json.return_value = {"error": "Not found"}
        mock_request.return_value = mock_response

        # Create client
        config = ZephyrConfig(
            base_url="https://test-api.zephyr.com",
            account_id="test-account-id",
            access_key="test-access-key",
            secret_key="test-secret-key"
        )
        client = ZephyrClient(config)

        # Test GET request with error
        with pytest.raises(Exception) as excinfo:
            client._request("GET", "/testcases", params={"projectKey": "PROJ"})

        assert "API Error" in str(excinfo.value)