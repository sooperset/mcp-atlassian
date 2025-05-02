"""Tests for Bitbucket Server fetcher."""

from unittest.mock import MagicMock

from mcp_atlassian.bitbucket_server import BitbucketServerFetcher


class TestBitbucketServerFetcher:
    """Tests for BitbucketServerFetcher class."""

    def test_get_branches(self):
        """Test that get_branches delegates to the branches component."""
        # Create mocks for all needed components
        mock_branches = MagicMock()
        mock_branches.get_branches.return_value = {"values": [{"displayId": "master"}]}

        # Create a fetcher with mocked components
        fetcher = MagicMock(spec=BitbucketServerFetcher)
        fetcher.branches = mock_branches

        # Store the original method to call it directly
        original_method = BitbucketServerFetcher.get_branches

        # Call the method directly (this is not ideal but works for testing)
        result = original_method(
            fetcher,
            repository="test-repo",
            project="TEST",
            filter_text="master",
            start=0,
            limit=25,
        )

        # Verify the branches component was called correctly
        mock_branches.get_branches.assert_called_once_with(
            repository="test-repo",
            project="TEST",
            filter_text="master",
            start=0,
            limit=25,
        )

        # Verify the result
        assert result == {"values": [{"displayId": "master"}]}

    def test_get_branch_commits(self):
        """Test that get_branch_commits delegates to the branches component."""
        # Create mocks for all needed components
        mock_branches = MagicMock()
        mock_branches.get_branch_commits.return_value = {
            "values": [{"displayId": "a1234567"}]
        }

        # Create a fetcher with mocked components
        fetcher = MagicMock(spec=BitbucketServerFetcher)
        fetcher.branches = mock_branches

        # Store the original method to call it directly
        original_method = BitbucketServerFetcher.get_branch_commits

        # Call the method directly
        result = original_method(
            fetcher,
            repository="test-repo",
            branch="master",
            project="TEST",
            start=0,
            limit=1,
        )

        # Verify the branches component was called correctly
        mock_branches.get_branch_commits.assert_called_once_with(
            repository="test-repo",
            branch="master",
            project="TEST",
            start=0,
            limit=1,
        )

        # Verify the result
        assert result == {"values": [{"displayId": "a1234567"}]}

    def test_get_commit(self):
        """Test that get_commit delegates to the commits component."""
        # Create mocks for all needed components
        mock_commits = MagicMock()
        mock_commits.get_commit.return_value = {"displayId": "a1234567"}

        # Create a fetcher with mocked components
        fetcher = MagicMock(spec=BitbucketServerFetcher)
        fetcher.commits = mock_commits

        # Store the original method to call it directly
        original_method = BitbucketServerFetcher.get_commit

        # Call the method directly
        result = original_method(
            fetcher,
            repository="test-repo",
            commit_id="a123456789",
            project="TEST",
        )

        # Verify the commits component was called correctly
        mock_commits.get_commit.assert_called_once_with(
            repository="test-repo",
            commit_id="a123456789",
            project="TEST",
        )

        # Verify the result
        assert result == {"displayId": "a1234567"}

    def test_get_commit_changes(self):
        """Test that get_commit_changes delegates to the commits component."""
        # Create mocks for all needed components
        mock_commits = MagicMock()
        mock_commits.get_commit_changes.return_value = {
            "values": [{"path": {"toString": "test.java"}}]
        }

        # Create a fetcher with mocked components
        fetcher = MagicMock(spec=BitbucketServerFetcher)
        fetcher.commits = mock_commits

        # Store the original method to call it directly
        original_method = BitbucketServerFetcher.get_commit_changes

        # Call the method directly
        result = original_method(
            fetcher,
            repository="test-repo",
            commit_id="a123456789",
            project="TEST",
        )

        # Verify the commits component was called correctly
        mock_commits.get_commit_changes.assert_called_once_with(
            repository="test-repo",
            commit_id="a123456789",
            project="TEST",
        )

        # Verify the result
        assert result == {"values": [{"path": {"toString": "test.java"}}]}

    def test_get_build_status(self):
        """Test that get_build_status delegates to the builds component."""
        # Create mocks for all needed components
        mock_builds = MagicMock()
        mock_builds.get_build_status.return_value = {
            "values": [{"state": "SUCCESSFUL"}]
        }

        # Create a fetcher with mocked components
        fetcher = MagicMock(spec=BitbucketServerFetcher)
        fetcher.builds = mock_builds

        # Store the original method to call it directly
        original_method = BitbucketServerFetcher.get_build_status

        # Call the method directly
        result = original_method(fetcher, commit_id="a123456789")

        # Verify the builds component was called correctly
        mock_builds.get_build_status.assert_called_once_with(
            commit_id="a123456789",
        )

        # Verify the result
        assert result == {"values": [{"state": "SUCCESSFUL"}]}
