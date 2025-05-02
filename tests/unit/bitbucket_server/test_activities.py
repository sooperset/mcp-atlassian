"""Tests for Bitbucket Server pull request activities."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.bitbucket_server.activities import BitbucketServerActivities


@pytest.fixture
def mock_activities_response():
    """Mock activities response data."""
    return {
        "size": 2,
        "limit": 25,
        "isLastPage": True,
        "start": 0,
        "values": [
            {
                "id": 1,
                "createdDate": 1617293932000,
                "user": {
                    "name": "user123",
                    "displayName": "Test User",
                    "emailAddress": "user@example.com",
                    "active": True,
                },
                "action": "APPROVED",
                "commit": None,
                "commentAction": None,
                "comment": None,
            },
            {
                "id": 2,
                "createdDate": 1617293933000,
                "user": {
                    "name": "user456",
                    "displayName": "Another User",
                    "emailAddress": "another@example.com",
                    "active": True,
                },
                "action": "COMMENTED",
                "commit": None,
                "commentAction": "ADDED",
                "comment": {
                    "id": 42,
                    "text": "This is a comment",
                },
            },
        ],
    }


def test_get_activities(bitbucket_server_client, mock_activities_response):
    """Test getting activities for a pull request."""
    # Create a mock client
    mock_client = MagicMock()
    mock_client.get.return_value = mock_activities_response

    # Create activities instance
    activities = BitbucketServerActivities(mock_client)

    # Get activities
    result = activities.get_activities(
        repository="test-repo",
        pr_id=101,
        project="PROJ",
    )

    # Verify the client was called with correct parameters
    mock_client.get.assert_called_once_with(
        "/projects/PROJ/repos/test-repo/pull-requests/101/activities",
        params={"start": 0, "limit": 25},
    )

    # Verify the result is the activities data
    assert result == mock_activities_response
    assert result["size"] == 2
    assert len(result["values"]) == 2
    assert result["values"][0]["action"] == "APPROVED"
    assert result["values"][1]["action"] == "COMMENTED"


def test_get_activities_with_params(bitbucket_server_client):
    """Test getting activities with pagination parameters."""
    # Create a mock client
    mock_client = MagicMock()
    mock_client.get.return_value = {
        "size": 0,
        "limit": 10,
        "isLastPage": True,
        "start": 5,
        "values": [],
    }

    # Create activities instance
    activities = BitbucketServerActivities(mock_client)

    # Get activities with parameters
    activities.get_activities(
        repository="test-repo",
        pr_id=101,
        project="PROJ",
        start=5,
        limit=10,
    )

    # Verify the client was called with correct parameters
    mock_client.get.assert_called_once_with(
        "/projects/PROJ/repos/test-repo/pull-requests/101/activities",
        params={"start": 5, "limit": 10},
    )


def test_get_activities_missing_project(bitbucket_server_client):
    """Test error when project is missing."""
    # Create activities instance
    activities = BitbucketServerActivities(bitbucket_server_client)

    # Test that an error is raised when project is missing
    with pytest.raises(ValueError) as excinfo:
        activities.get_activities(
            repository="test-repo",
            pr_id=101,
            # missing project parameter
        )

    assert "Project parameter is required" in str(excinfo.value)


def test_get_reviews(bitbucket_server_client, mock_activities_response):
    """Test getting reviews for a pull request."""
    # Create a mock client
    mock_client = MagicMock()
    mock_client.get.return_value = mock_activities_response

    # Create activities instance
    activities = BitbucketServerActivities(mock_client)

    # Get reviews
    reviews = activities.get_reviews(
        repository="test-repo",
        pr_id=101,
        project="PROJ",
    )

    # Verify the client was called with correct parameters
    mock_client.get.assert_called_once_with(
        "/projects/PROJ/repos/test-repo/pull-requests/101/activities",
        params={"start": 0, "limit": 25},
    )

    # Verify the result is the filtered review activities
    assert len(reviews) == 1
    assert reviews[0]["action"] == "APPROVED"
    assert reviews[0]["user"]["name"] == "user123"


def test_bitbucket_server_fetcher_methods(
    bitbucket_server_client, mock_activities_response
):
    """Test BitbucketServerFetcher activities methods."""
    from mcp_atlassian.bitbucket_server import BitbucketServerFetcher

    # Mock the activities module
    with patch(
        "mcp_atlassian.bitbucket_server.BitbucketServerActivities"
    ) as mock_activities_class:
        # Set up the mock return values
        mock_activities = MagicMock()
        mock_activities_class.return_value = mock_activities

        # Set return values for activities and reviews
        mock_activities.get_activities.return_value = mock_activities_response
        mock_activities.get_reviews.return_value = [
            mock_activities_response["values"][0]
        ]

        # Create bitbucket fetcher with the mocked client
        fetcher = BitbucketServerFetcher(MagicMock())

        # Override the activities attribute with our mock
        fetcher.activities = mock_activities

        # Test get_activities
        result_activities = fetcher.get_activities(
            repository="test-repo",
            pr_id=101,
            project="PROJ",
            start=5,
            limit=10,
        )

        # Verify method was called with correct parameters
        mock_activities.get_activities.assert_called_once_with(
            repository="test-repo",
            pr_id=101,
            project="PROJ",
            start=5,
            limit=10,
        )

        # Verify result for get_activities
        assert result_activities == mock_activities_response

        # Test get_reviews
        result_reviews = fetcher.get_reviews(
            repository="test-repo",
            pr_id=101,
            project="PROJ",
            start=5,
            limit=10,
        )

        # Verify method was called with correct parameters
        mock_activities.get_reviews.assert_called_once_with(
            repository="test-repo",
            pr_id=101,
            project="PROJ",
            start=5,
            limit=10,
        )

        # Verify result for get_reviews
        assert result_reviews == [mock_activities_response["values"][0]]
