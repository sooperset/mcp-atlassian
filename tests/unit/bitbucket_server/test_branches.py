"""Tests for Bitbucket Server branches operations."""

from unittest.mock import Mock

import pytest

from mcp_atlassian.bitbucket_server.branches import BitbucketServerBranches
from mcp_atlassian.exceptions import BitbucketServerApiError


@pytest.fixture
def mock_client():
    """Create a mock Bitbucket Server client."""
    client = Mock()
    return client


@pytest.fixture
def branches_api(mock_client):
    """Create a BitbucketServerBranches instance with a mock client."""
    return BitbucketServerBranches(mock_client)


class TestBitbucketServerBranches:
    """Tests for Bitbucket Server branches operations."""

    def test_get_branches(self, branches_api, mock_client):
        """Test getting branches for a repository."""
        # Mock response data
        mock_response = {
            "size": 2,
            "limit": 25,
            "isLastPage": True,
            "values": [
                {
                    "id": "refs/heads/master",
                    "displayId": "master",
                    "type": "BRANCH",
                    "latestCommit": "a123456789",
                    "isDefault": True,
                },
                {
                    "id": "refs/heads/develop",
                    "displayId": "develop",
                    "type": "BRANCH",
                    "latestCommit": "b123456789",
                    "isDefault": False,
                },
            ],
            "start": 0,
        }
        mock_client.get.return_value = mock_response

        # Call the method
        result = branches_api.get_branches(
            repository="test-repo",
            project="TEST",
            filter_text="master",
            start=0,
            limit=25,
        )

        # Verify the client was called correctly
        mock_client.get.assert_called_once_with(
            "/projects/TEST/repos/test-repo/branches",
            params={"start": 0, "limit": 25, "filterText": "master"},
        )

        # Verify the result
        assert result == mock_response
        assert result["size"] == 2
        assert len(result["values"]) == 2
        assert result["values"][0]["displayId"] == "master"
        assert result["values"][1]["displayId"] == "develop"

    def test_get_branches_required_params(self, branches_api):
        """Test that project is required for get_branches."""
        with pytest.raises(ValueError, match="Project parameter is required"):
            branches_api.get_branches(repository="test-repo")

    def test_get_branch_commits(self, branches_api, mock_client):
        """Test getting commits for a branch."""
        # Mock response data
        mock_response = {
            "values": [
                {
                    "id": "a123456789",
                    "displayId": "a1234567",
                    "author": {"name": "test", "emailAddress": "test@example.com"},
                    "authorTimestamp": 1602777600000,
                    "message": "Test commit",
                    "parents": [{"id": "b123456789"}],
                }
            ],
            "size": 1,
            "isLastPage": True,
            "start": 0,
            "limit": 1,
        }
        mock_client.get.return_value = mock_response

        # Call the method
        result = branches_api.get_branch_commits(
            repository="test-repo",
            branch="master",
            project="TEST",
            start=0,
            limit=1,
        )

        # Verify the client was called correctly
        mock_client.get.assert_called_once_with(
            "/projects/TEST/repos/test-repo/commits",
            params={"until": "refs/heads/master", "start": 0, "limit": 1},
        )

        # Verify the result
        assert result == mock_response
        assert len(result["values"]) == 1
        assert result["values"][0]["displayId"] == "a1234567"
        assert result["values"][0]["message"] == "Test commit"

    def test_get_branch_commits_with_ref(self, branches_api, mock_client):
        """Test getting commits with a branch ref instead of name."""
        # Mock response data
        mock_response = {
            "values": [
                {
                    "id": "a123456789",
                    "displayId": "a1234567",
                    "message": "Test commit",
                }
            ],
            "size": 1,
        }
        mock_client.get.return_value = mock_response

        # Call the method with a full ref
        result = branches_api.get_branch_commits(
            repository="test-repo",
            branch="refs/heads/feature/test",
            project="TEST",
        )

        # Verify the client was called correctly with the full ref
        mock_client.get.assert_called_once_with(
            "/projects/TEST/repos/test-repo/commits",
            params={"until": "refs/heads/feature/test", "start": 0, "limit": 1},
        )

        # Verify the result
        assert result == mock_response

    def test_get_branch_commits_required_params(self, branches_api):
        """Test that project is required for get_branch_commits."""
        with pytest.raises(ValueError, match="Project parameter is required"):
            branches_api.get_branch_commits(repository="test-repo", branch="master")

    def test_get_branches_error(self, branches_api, mock_client):
        """Test handling errors when getting branches."""
        # Mock an exception
        mock_client.get.side_effect = BitbucketServerApiError("API error")

        # Call the method and expect an exception
        with pytest.raises(BitbucketServerApiError, match="API error"):
            branches_api.get_branches(repository="test-repo", project="TEST")

    def test_get_branch_commits_error(self, branches_api, mock_client):
        """Test handling errors when getting branch commits."""
        # Mock an exception
        mock_client.get.side_effect = BitbucketServerApiError("API error")

        # Call the method and expect an exception
        with pytest.raises(BitbucketServerApiError, match="API error"):
            branches_api.get_branch_commits(
                repository="test-repo", branch="master", project="TEST"
            )
