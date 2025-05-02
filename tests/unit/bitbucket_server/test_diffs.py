"""Tests for Bitbucket Server pull request diffs."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.bitbucket_server.diffs import BitbucketServerDiffs


@pytest.fixture
def mock_diff_response():
    """Mock diff response data."""
    return {
        "fromHash": "abc123",
        "toHash": "def456",
        "contextLines": 10,
        "whitespace": False,
        "diffs": [
            {
                "source": {
                    "components": ["src", "main.py"],
                    "name": "main.py",
                    "extension": "py",
                    "toString": "src/main.py",
                },
                "destination": {
                    "components": ["src", "main.py"],
                    "name": "main.py",
                    "extension": "py",
                    "toString": "src/main.py",
                },
                "hunks": [
                    {
                        "sourceLine": 10,
                        "sourceSpan": 6,
                        "destinationLine": 10,
                        "destinationSpan": 8,
                        "segments": [
                            {
                                "type": "CONTEXT",
                                "lines": [
                                    {
                                        "source": 10,
                                        "destination": 10,
                                        "line": "def example():",
                                    },
                                    {
                                        "source": 11,
                                        "destination": 11,
                                        "line": "    return True",
                                    },
                                ],
                            },
                            {
                                "type": "ADDED",
                                "lines": [
                                    {"destination": 12, "line": "    # New comment"},
                                    {
                                        "destination": 13,
                                        "line": "    print('Hello World')",
                                    },
                                ],
                            },
                            {
                                "type": "CONTEXT",
                                "lines": [
                                    {"source": 12, "destination": 14, "line": ""},
                                    {
                                        "source": 13,
                                        "destination": 15,
                                        "line": "if __name__ == '__main__':",
                                    },
                                    {
                                        "source": 14,
                                        "destination": 16,
                                        "line": "    example()",
                                    },
                                ],
                            },
                        ],
                    }
                ],
                "truncated": False,
            }
        ],
    }


def test_get_diff(bitbucket_server_client, mock_diff_response):
    """Test getting diff for a pull request."""
    # Create a mock client
    mock_client = MagicMock()
    mock_client.get.return_value = mock_diff_response

    # Create diffs instance
    diffs = BitbucketServerDiffs(mock_client)

    # Get diff
    result = diffs.get_diff(
        repository="test-repo",
        pr_id=101,
        project="PROJ",
    )

    # Verify the client was called with correct parameters
    mock_client.get.assert_called_once_with(
        "/projects/PROJ/repos/test-repo/pull-requests/101/diff",
        params={"contextLines": 10},
    )

    # Verify the result is the diff data
    assert result == mock_diff_response
    assert result["fromHash"] == "abc123"
    assert result["toHash"] == "def456"
    assert len(result["diffs"]) == 1
    assert result["diffs"][0]["source"]["toString"] == "src/main.py"


def test_get_diff_with_params(bitbucket_server_client, mock_diff_response):
    """Test getting diff with additional parameters."""
    # Create a mock client
    mock_client = MagicMock()
    mock_client.get.return_value = mock_diff_response

    # Create diffs instance
    diffs = BitbucketServerDiffs(mock_client)

    # Get diff with parameters
    diffs.get_diff(
        repository="test-repo",
        pr_id=101,
        project="PROJ",
        context_lines=5,
        since_revision="abc123",
        whitespace=True,
    )

    # Verify the client was called with correct parameters
    mock_client.get.assert_called_once_with(
        "/projects/PROJ/repos/test-repo/pull-requests/101/diff",
        params={"contextLines": 5, "since": "abc123", "whitespace": "ignore-all"},
    )


def test_get_diff_missing_project(bitbucket_server_client):
    """Test error when project is missing."""
    # Create diffs instance
    diffs = BitbucketServerDiffs(bitbucket_server_client)

    # Test that an error is raised when project is missing
    with pytest.raises(ValueError) as excinfo:
        diffs.get_diff(
            repository="test-repo",
            pr_id=101,
            # missing project parameter
        )

    assert "Project parameter is required" in str(excinfo.value)


def test_bitbucket_server_fetcher_get_diff(bitbucket_server_client, mock_diff_response):
    """Test BitbucketServerFetcher.get_diff method."""
    from mcp_atlassian.bitbucket_server import BitbucketServerFetcher

    # Mock the diffs module
    with patch(
        "mcp_atlassian.bitbucket_server.BitbucketServerDiffs"
    ) as mock_diffs_class:
        # Set up the mock return values
        mock_diffs = MagicMock()
        mock_diffs_class.return_value = mock_diffs

        # Set return value for get_diff
        mock_diffs.get_diff.return_value = mock_diff_response

        # Create bitbucket fetcher with the mocked client
        fetcher = BitbucketServerFetcher(MagicMock())

        # Override the diffs attribute with our mock
        fetcher.diffs = mock_diffs

        # Call the method
        result = fetcher.get_diff(
            repository="test-repo",
            pr_id=101,
            project="PROJ",
            context_lines=5,
            since_revision="abc123",
            whitespace=True,
        )

        # Verify method was called with correct parameters
        mock_diffs.get_diff.assert_called_once_with(
            repository="test-repo",
            pr_id=101,
            project="PROJ",
            context_lines=5,
            since_revision="abc123",
            whitespace=True,
        )

        # Verify result
        assert result == mock_diff_response
