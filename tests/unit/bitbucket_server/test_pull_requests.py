"""Tests for Bitbucket Server pull requests."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.bitbucket_server.pull_requests import BitbucketServerPullRequests
from mcp_atlassian.models.bitbucket_server import BitbucketServerPullRequest


def test_get_pull_request(mock_pull_request_response):
    """Test getting a pull request."""
    # Create a mock client
    mock_client = MagicMock()
    mock_client.get.return_value = mock_pull_request_response

    # Create pull requests instance
    pull_requests = BitbucketServerPullRequests(mock_client)

    # Get a pull request
    result = pull_requests.get_pull_request(
        repository="test-repo",
        pr_id=101,
        project="PROJ",
    )

    # Verify the client was called with correct parameters
    mock_client.get.assert_called_once_with(
        "/projects/PROJ/repos/test-repo/pull-requests/101"
    )

    # Verify the result is a BitbucketServerPullRequest
    assert isinstance(result, BitbucketServerPullRequest)
    assert result.id == 101
    assert result.title == "Add new feature"
    assert result.state == "OPEN"


def test_get_pull_request_missing_project(bitbucket_server_client):
    """Test error when project is missing."""
    # Create pull requests instance
    pull_requests = BitbucketServerPullRequests(bitbucket_server_client)

    # Test that an error is raised when project is missing
    with pytest.raises(ValueError) as excinfo:
        pull_requests.get_pull_request(
            repository="test-repo",
            pr_id=101,
            # missing project parameter
        )

    assert "Project parameter is required" in str(excinfo.value)


def test_bitbucket_server_fetcher_get_pull_request(
    bitbucket_server_client, mock_pull_request_response
):
    """Test BitbucketServerFetcher.get_pull_request method."""
    from mcp_atlassian.bitbucket_server import BitbucketServerFetcher

    # Mock the pull request module
    with patch(
        "mcp_atlassian.bitbucket_server.BitbucketServerPullRequests"
    ) as mock_pull_requests_class:
        # Set up the mock return values
        mock_pull_requests = MagicMock()
        mock_pull_requests_class.return_value = mock_pull_requests

        # Create a pull request instance to return
        pr = BitbucketServerPullRequest.from_raw(mock_pull_request_response)
        mock_pull_requests.get_pull_request.return_value = pr

        # Create bitbucket fetcher with the mocked client
        fetcher = BitbucketServerFetcher(MagicMock())

        # Override the pull_requests attribute with our mock
        fetcher.pull_requests = mock_pull_requests

        # Call the method
        result = fetcher.get_pull_request(
            repository="test-repo",
            pr_id=101,
            project="PROJ",
        )

        # Verify method was called with correct parameters
        mock_pull_requests.get_pull_request.assert_called_once_with(
            repository="test-repo",
            pr_id=101,
            project="PROJ",
        )

        # Verify result
        assert result == pr
