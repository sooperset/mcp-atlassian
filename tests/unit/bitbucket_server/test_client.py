"""Tests for Bitbucket Server client module."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from mcp_atlassian.bitbucket_server.client import BitbucketServerClient
from mcp_atlassian.exceptions import BitbucketServerApiError


def test_bitbucket_server_client_init(bitbucket_server_config):
    """Test BitbucketServerClient initialization."""
    with patch("httpx.Client", MagicMock()) as mock_client:
        client = BitbucketServerClient(bitbucket_server_config)

        assert client.config == bitbucket_server_config
        assert client.base_url == "https://bitbucket.example.com/rest/api/latest"
        mock_client.assert_called_once()


def test_bitbucket_server_client_create_session_basic_auth(bitbucket_server_config):
    """Test creating a session with basic auth."""
    with patch("httpx.Client", MagicMock()) as mock_client:
        instance = mock_client.return_value

        client = BitbucketServerClient(bitbucket_server_config)

        # Verify auth is set for basic auth
        assert instance.auth == ("username", "api_token")


def test_bitbucket_server_client_create_session_token_auth():
    """Test creating a session with token auth."""
    from mcp_atlassian.bitbucket_server.config import BitbucketServerConfig
    from mcp_atlassian.bitbucket_server.constants import AUTH_TYPE_PERSONAL_TOKEN

    config = BitbucketServerConfig(
        url="https://bitbucket.example.com",
        auth_type=AUTH_TYPE_PERSONAL_TOKEN,
        personal_token="personal_token",
    )

    with patch("httpx.Client", MagicMock()) as mock_client:
        instance = mock_client.return_value
        instance.headers = {}

        client = BitbucketServerClient(config)

        # Verify headers are set for token auth
        assert instance.headers.get("Authorization") == "Bearer personal_token"


def test_bitbucket_server_client_get_success(bitbucket_server_client):
    """Test successful GET request."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"key": "value"}
    bitbucket_server_client.session.get.return_value = mock_response

    result = bitbucket_server_client.get("/test")

    bitbucket_server_client.session.get.assert_called_once_with(
        "https://bitbucket.example.com/rest/api/latest/test", params=None
    )
    assert result == {"key": "value"}


def test_bitbucket_server_client_get_with_params(bitbucket_server_client):
    """Test GET request with parameters."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"key": "value"}
    bitbucket_server_client.session.get.return_value = mock_response

    params = {"param1": "value1", "param2": "value2"}
    result = bitbucket_server_client.get("/test", params=params)

    bitbucket_server_client.session.get.assert_called_once_with(
        "https://bitbucket.example.com/rest/api/latest/test", params=params
    )
    assert result == {"key": "value"}


def test_bitbucket_server_client_get_http_error(bitbucket_server_client):
    """Test GET request with HTTP error."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Error", request=MagicMock(), response=MagicMock()
    )
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    # Set the response attribute on the exception
    mock_response.raise_for_status.side_effect.response = mock_response

    bitbucket_server_client.session.get.return_value = mock_response

    with pytest.raises(BitbucketServerApiError) as excinfo:
        bitbucket_server_client.get("/test")

    assert "HTTP error: 404 - Not Found" in str(excinfo.value)


def test_bitbucket_server_client_get_request_error(bitbucket_server_client):
    """Test GET request with request error."""
    bitbucket_server_client.session.get.side_effect = httpx.RequestError(
        "Connection error", request=MagicMock()
    )

    with pytest.raises(BitbucketServerApiError) as excinfo:
        bitbucket_server_client.get("/test")

    assert "Request error: Connection error" in str(excinfo.value)


def test_bitbucket_server_client_get_unexpected_error(bitbucket_server_client):
    """Test GET request with unexpected error."""
    bitbucket_server_client.session.get.side_effect = Exception("Unexpected error")

    with pytest.raises(BitbucketServerApiError) as excinfo:
        bitbucket_server_client.get("/test")

    assert "Unexpected error: Unexpected error" in str(excinfo.value)


def test_bitbucket_server_client_close(bitbucket_server_client):
    """Test closing the client session."""
    bitbucket_server_client.close()

    bitbucket_server_client.session.close.assert_called_once()
