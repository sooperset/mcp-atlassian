"""Tests for Bitbucket Server build status operations."""

from unittest.mock import MagicMock, Mock

import httpx
import pytest

from mcp_atlassian.bitbucket_server.builds import BitbucketServerBuilds


@pytest.fixture
def mock_client():
    """Create a mock Bitbucket Server client."""
    client = Mock()
    # Mock the session and response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "size": 2,
        "limit": 25,
        "isLastPage": True,
        "values": [
            {
                "state": "SUCCESSFUL",
                "key": "BUILD-123",
                "name": "Main build",
                "url": "https://ci.example.com/BUILD-123",
                "description": "Build successful",
                "dateAdded": 1602777600000,
            },
            {
                "state": "FAILED",
                "key": "BUILD-124",
                "name": "Test build",
                "url": "https://ci.example.com/BUILD-124",
                "description": "Build failed",
                "dateAdded": 1602777700000,
            },
        ],
        "start": 0,
    }
    mock_response.raise_for_status = Mock()
    client.session.get.return_value = mock_response
    client.root_url = "https://bitbucket.example.com"
    return client


@pytest.fixture
def builds_api(mock_client):
    """Create a BitbucketServerBuilds instance with a mock client."""
    return BitbucketServerBuilds(mock_client)


class TestBitbucketServerBuilds:
    """Tests for Bitbucket Server build status operations."""

    def test_get_build_status(self, builds_api, mock_client):
        """Test getting build status for a commit."""
        # Call the method
        result = builds_api.get_build_status(commit_id="a123456789")

        # Verify the client's session.get was called correctly
        mock_client.session.get.assert_called_once_with(
            "https://bitbucket.example.com/rest/build-status/1.0/commits/a123456789"
        )

        # Verify the result
        assert result["size"] == 2
        assert len(result["values"]) == 2
        assert result["values"][0]["state"] == "SUCCESSFUL"
        assert result["values"][0]["key"] == "BUILD-123"
        assert result["values"][1]["state"] == "FAILED"
        assert result["values"][1]["key"] == "BUILD-124"

    def test_get_build_status_http_error(self, builds_api, mock_client):
        """Test handling HTTP errors when getting build status."""
        # Mock an HTTP error
        mock_response = mock_client.session.get.return_value
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "HTTP error", request=Mock(), response=Mock()
        )

        # Call the method and expect an exception
        with pytest.raises(Exception):
            builds_api.get_build_status(commit_id="a123456789")

    def test_get_build_status_request_error(self, builds_api, mock_client):
        """Test handling request errors when getting build status."""
        # Mock a request error
        mock_client.session.get.side_effect = httpx.RequestError(
            "Request error", request=Mock()
        )

        # Call the method and expect an exception
        with pytest.raises(Exception):
            builds_api.get_build_status(commit_id="a123456789")

    def test_get_build_status_json_error(self, builds_api, mock_client):
        """Test handling JSON parsing errors when getting build status."""
        # Mock a JSON parsing error
        mock_response = mock_client.session.get.return_value
        mock_response.json.side_effect = ValueError("Invalid JSON")

        # Call the method and expect an exception
        with pytest.raises(Exception):
            builds_api.get_build_status(commit_id="a123456789")
