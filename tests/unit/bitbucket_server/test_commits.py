"""Tests for Bitbucket Server commits operations."""

from unittest.mock import Mock

import pytest

from mcp_atlassian.bitbucket_server.commits import BitbucketServerCommits
from mcp_atlassian.exceptions import BitbucketServerApiError


@pytest.fixture
def mock_client():
    """Create a mock Bitbucket Server client."""
    client = Mock()
    return client


@pytest.fixture
def commits_api(mock_client):
    """Create a BitbucketServerCommits instance with a mock client."""
    return BitbucketServerCommits(mock_client)


class TestBitbucketServerCommits:
    """Tests for Bitbucket Server commits operations."""

    def test_get_commit(self, commits_api, mock_client):
        """Test getting a specific commit."""
        # Mock response data
        mock_response = {
            "id": "a123456789",
            "displayId": "a1234567",
            "author": {"name": "test", "emailAddress": "test@example.com"},
            "authorTimestamp": 1602777600000,
            "message": "Test commit",
            "parents": [{"id": "b123456789"}],
        }
        mock_client.get.return_value = mock_response

        # Call the method
        result = commits_api.get_commit(
            repository="test-repo", commit_id="a123456789", project="TEST"
        )

        # Verify the client was called correctly
        mock_client.get.assert_called_once_with(
            "/projects/TEST/repos/test-repo/commits/a123456789"
        )

        # Verify the result
        assert result == mock_response
        assert result["displayId"] == "a1234567"
        assert result["message"] == "Test commit"

    def test_get_commit_required_params(self, commits_api):
        """Test that project is required for get_commit."""
        with pytest.raises(ValueError, match="Project parameter is required"):
            commits_api.get_commit(repository="test-repo", commit_id="a123456789")

    def test_get_commit_changes(self, commits_api, mock_client):
        """Test getting changes for a specific commit."""
        # Mock response data
        mock_response = {
            "fromHash": "b123456789",
            "toHash": "a123456789",
            "values": [
                {
                    "contentId": "c123456789",
                    "path": {
                        "components": ["src", "main", "java", "test.java"],
                        "name": "test.java",
                        "extension": "java",
                        "toString": "src/main/java/test.java",
                    },
                    "type": "MODIFY",
                    "nodeType": "FILE",
                }
            ],
            "size": 1,
            "isLastPage": True,
        }
        mock_client.get.return_value = mock_response

        # Call the method
        result = commits_api.get_commit_changes(
            repository="test-repo", commit_id="a123456789", project="TEST"
        )

        # Verify the client was called correctly
        mock_client.get.assert_called_once_with(
            "/projects/TEST/repos/test-repo/commits/a123456789/changes"
        )

        # Verify the result
        assert result == mock_response
        assert result["toHash"] == "a123456789"
        assert len(result["values"]) == 1
        assert result["values"][0]["type"] == "MODIFY"
        assert result["values"][0]["path"]["toString"] == "src/main/java/test.java"

    def test_get_commit_changes_required_params(self, commits_api):
        """Test that project is required for get_commit_changes."""
        with pytest.raises(ValueError, match="Project parameter is required"):
            commits_api.get_commit_changes(
                repository="test-repo", commit_id="a123456789"
            )

    def test_get_commit_error(self, commits_api, mock_client):
        """Test handling errors when getting a commit."""
        # Mock an exception
        mock_client.get.side_effect = BitbucketServerApiError("API error")

        # Call the method and expect an exception
        with pytest.raises(BitbucketServerApiError, match="API error"):
            commits_api.get_commit(
                repository="test-repo", commit_id="a123456789", project="TEST"
            )

    def test_get_commit_changes_error(self, commits_api, mock_client):
        """Test handling errors when getting commit changes."""
        # Mock an exception
        mock_client.get.side_effect = BitbucketServerApiError("API error")

        # Call the method and expect an exception
        with pytest.raises(BitbucketServerApiError, match="API error"):
            commits_api.get_commit_changes(
                repository="test-repo", commit_id="a123456789", project="TEST"
            )
