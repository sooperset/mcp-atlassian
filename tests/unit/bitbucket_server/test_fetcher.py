"""Tests for Bitbucket Server fetcher."""

from unittest.mock import Mock

import pytest

from mcp_atlassian.bitbucket_server import BitbucketServerFetcher
from mcp_atlassian.bitbucket_server.config import BitbucketServerConfig


@pytest.fixture
def mock_config():
    """Create a mock Bitbucket Server configuration."""
    config = Mock(spec=BitbucketServerConfig)
    config.url = "https://bitbucket.example.com"
    config.auth_type = "token"
    config.personal_token = "test-token"
    config.ssl_verify = True
    config.projects_filter = "TEST,PROJECT"
    return config


@pytest.fixture
def mock_fetcher(mock_config):
    """Create a mock Bitbucket Server fetcher with mocked components."""
    fetcher = BitbucketServerFetcher(config=mock_config)

    # Mock all the components
    fetcher.branches = Mock()
    fetcher.builds = Mock()
    fetcher.commits = Mock()
    fetcher.pull_requests = Mock()
    fetcher.comments = Mock()
    fetcher.diffs = Mock()
    fetcher.activities = Mock()
    fetcher.search = Mock()
    fetcher.files = Mock()

    return fetcher


class TestBitbucketServerFetcher:
    """Tests for BitbucketServerFetcher class."""

    def test_get_branches(self, mock_fetcher):
        """Test that get_branches delegates to the branches component."""
        # Set up mock return value
        mock_fetcher.branches.get_branches.return_value = {
            "values": [{"displayId": "master"}]
        }

        # Call the method
        result = mock_fetcher.get_branches(
            repository="test-repo",
            project="TEST",
            filter_text="master",
            start=0,
            limit=25,
        )

        # Verify the branches component was called correctly
        mock_fetcher.branches.get_branches.assert_called_once_with(
            repository="test-repo",
            project="TEST",
            filter_text="master",
            start=0,
            limit=25,
        )

        # Verify the result
        assert result == {"values": [{"displayId": "master"}]}

    def test_get_branch_commits(self, mock_fetcher):
        """Test that get_branch_commits delegates to the branches component."""
        # Set up mock return value
        mock_fetcher.branches.get_branch_commits.return_value = {
            "values": [{"displayId": "a1234567"}]
        }

        # Call the method
        result = mock_fetcher.get_branch_commits(
            repository="test-repo",
            branch="master",
            project="TEST",
            start=0,
            limit=1,
        )

        # Verify the branches component was called correctly
        mock_fetcher.branches.get_branch_commits.assert_called_once_with(
            repository="test-repo",
            branch="master",
            project="TEST",
            start=0,
            limit=1,
        )

        # Verify the result
        assert result == {"values": [{"displayId": "a1234567"}]}

    def test_get_commit(self, mock_fetcher):
        """Test that get_commit delegates to the commits component."""
        # Set up mock return value
        mock_fetcher.commits.get_commit.return_value = {"displayId": "a1234567"}

        # Call the method
        result = mock_fetcher.get_commit(
            repository="test-repo",
            commit_id="a123456789",
            project="TEST",
        )

        # Verify the commits component was called correctly
        mock_fetcher.commits.get_commit.assert_called_once_with(
            repository="test-repo",
            commit_id="a123456789",
            project="TEST",
        )

        # Verify the result
        assert result == {"displayId": "a1234567"}

    def test_get_commit_changes(self, mock_fetcher):
        """Test that get_commit_changes delegates to the commits component."""
        # Set up mock return value
        mock_fetcher.commits.get_commit_changes.return_value = {
            "values": [{"path": {"toString": "test.java"}}]
        }

        # Call the method
        result = mock_fetcher.get_commit_changes(
            repository="test-repo",
            commit_id="a123456789",
            project="TEST",
        )

        # Verify the commits component was called correctly
        mock_fetcher.commits.get_commit_changes.assert_called_once_with(
            repository="test-repo",
            commit_id="a123456789",
            project="TEST",
        )

        # Verify the result
        assert result == {"values": [{"path": {"toString": "test.java"}}]}

    def test_get_build_status(self, mock_fetcher):
        """Test that get_build_status delegates to the builds component."""
        # Set up mock return value
        mock_fetcher.builds.get_build_status.return_value = {
            "values": [{"state": "SUCCESSFUL"}]
        }

        # Call the method
        result = mock_fetcher.get_build_status(commit_id="a123456789")

        # Verify the builds component was called correctly
        mock_fetcher.builds.get_build_status.assert_called_once_with(
            commit_id="a123456789",
        )

        # Verify the result
        assert result == {"values": [{"state": "SUCCESSFUL"}]}
