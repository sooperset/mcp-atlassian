"""Tests for Bitbucket Server pull request comments."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.bitbucket_server.comments import BitbucketServerComments
from mcp_atlassian.models.bitbucket_server import BitbucketServerComment


@pytest.fixture
def mock_comment_response():
    """Mock single comment response data."""
    return {
        "id": 42,
        "version": 1,
        "text": "This is a test comment",
        "author": {
            "id": 1,
            "name": "user123",
            "displayName": "Test User",
            "emailAddress": "user@example.com",
            "active": True,
        },
        "createdDate": 1617293932000,
        "updatedDate": 1617293932000,
    }


@pytest.fixture
def mock_reply_comment_response():
    """Mock reply comment response data."""
    return {
        "id": 43,
        "version": 1,
        "text": "This is a reply comment",
        "author": {
            "id": 1,
            "name": "user123",
            "displayName": "Test User",
            "emailAddress": "user@example.com",
            "active": True,
        },
        "createdDate": 1617293932000,
        "updatedDate": 1617293932000,
        "parent": {
            "id": 42,
        },
    }


def test_add_comment(bitbucket_server_client, mock_comment_response):
    """Test adding a comment to a pull request."""
    # Create a mock client
    mock_client = MagicMock()
    mock_client.post.return_value = mock_comment_response

    # Create comments instance
    comments = BitbucketServerComments(mock_client)

    # Add a comment
    result = comments.add_comment(
        repository="test-repo",
        pr_id=101,
        text="This is a test comment",
        project="PROJ",
    )

    # Verify the client was called with correct parameters
    mock_client.post.assert_called_once_with(
        "/projects/PROJ/repos/test-repo/pull-requests/101/comments",
        json={"text": "This is a test comment"},
    )

    # Verify the result is a BitbucketServerComment
    assert isinstance(result, BitbucketServerComment)
    assert result.id == 42
    assert result.text == "This is a test comment"
    assert result.author.name == "user123"


def test_add_reply_comment(bitbucket_server_client, mock_reply_comment_response):
    """Test adding a reply comment to a pull request."""
    # Create a mock client
    mock_client = MagicMock()
    mock_client.post.return_value = mock_reply_comment_response

    # Create comments instance
    comments = BitbucketServerComments(mock_client)

    # Add a reply comment
    result = comments.add_comment(
        repository="test-repo",
        pr_id=101,
        text="This is a reply comment",
        project="PROJ",
        parent_id=42,
    )

    # Verify the client was called with correct parameters
    mock_client.post.assert_called_once_with(
        "/projects/PROJ/repos/test-repo/pull-requests/101/comments",
        json={"text": "This is a reply comment", "parent": {"id": 42}},
    )

    # Verify the result is a BitbucketServerComment with parent
    assert isinstance(result, BitbucketServerComment)
    assert result.id == 43
    assert result.text == "This is a reply comment"
    assert result.parent_id == 42


def test_add_comment_missing_project(bitbucket_server_client):
    """Test error when project is missing when adding a comment."""
    # Create comments instance
    comments = BitbucketServerComments(bitbucket_server_client)

    # Test that an error is raised when project is missing
    with pytest.raises(ValueError) as excinfo:
        comments.add_comment(
            repository="test-repo",
            pr_id=101,
            text="This is a test comment",
            # missing project parameter
        )

    assert "Project parameter is required" in str(excinfo.value)


def test_bitbucket_server_fetcher_add_comment(
    bitbucket_server_client, mock_comment_response
):
    """Test BitbucketServerFetcher add_comment method."""
    from mcp_atlassian.bitbucket_server import BitbucketServerFetcher

    # Mock the comments module
    with patch(
        "mcp_atlassian.bitbucket_server.BitbucketServerComments"
    ) as mock_comments_class:
        # Set up the mock return values
        mock_comments = MagicMock()
        mock_comments_class.return_value = mock_comments

        # Create comment instance to return
        comment = BitbucketServerComment.from_raw(mock_comment_response)
        mock_comments.add_comment.return_value = comment

        # Create bitbucket fetcher with the mocked client
        fetcher = BitbucketServerFetcher(MagicMock())

        # Override the comments attribute with our mock
        fetcher.comments = mock_comments

        # Test add_comment
        result_add = fetcher.add_comment(
            repository="test-repo",
            pr_id=101,
            text="This is a test comment",
            project="PROJ",
            parent_id=42,
        )

        # Verify method was called with correct parameters
        mock_comments.add_comment.assert_called_once_with(
            repository="test-repo",
            pr_id=101,
            text="This is a test comment",
            project="PROJ",
            parent_id=42,
        )

        # Verify result for add_comment
        assert result_add == comment
