"""Tests for Bitbucket Server models."""

from datetime import datetime

from mcp_atlassian.models.bitbucket_server import (
    BitbucketServerPullRequest,
    BitbucketServerPullRequestReviewer,
    BitbucketServerRef,
    BitbucketServerRepository,
    BitbucketServerUser,
)


class TestBitbucketServerModels:
    """Tests for Bitbucket Server models."""

    def test_bitbucket_server_user_from_raw(self):
        """Test creating BitbucketServerUser from raw data."""
        raw_data = {
            "id": 123,
            "name": "username",
            "displayName": "User Display Name",
            "emailAddress": "user@example.com",
            "active": True,
        }

        user = BitbucketServerUser.from_raw(raw_data)

        assert user.id == 123
        assert user.name == "username"
        assert user.display_name == "User Display Name"
        assert user.email_address == "user@example.com"
        assert user.active is True

    def test_bitbucket_server_repository_from_raw(self):
        """Test creating BitbucketServerRepository from raw data."""
        raw_data = {
            "id": 456,
            "slug": "repo-slug",
            "name": "Repository Name",
            "project": {
                "key": "PROJ",
                "name": "Project Name",
            },
        }

        repo = BitbucketServerRepository.from_raw(raw_data)

        assert repo.id == 456
        assert repo.slug == "repo-slug"
        assert repo.name == "Repository Name"
        assert repo.project_key == "PROJ"
        assert repo.project_name == "Project Name"

    def test_bitbucket_server_ref_from_raw(self):
        """Test creating BitbucketServerRef from raw data."""
        raw_data = {
            "id": "refs/heads/branch-name",
            "displayId": "branch-name",
            "latestCommit": "abc123def456",
            "repository": {
                "id": 456,
                "slug": "repo-slug",
                "name": "Repository Name",
                "project": {
                    "key": "PROJ",
                    "name": "Project Name",
                },
            },
        }

        ref = BitbucketServerRef.from_raw(raw_data)

        assert ref.id == "refs/heads/branch-name"
        assert ref.display_id == "branch-name"
        assert ref.latest_commit == "abc123def456"
        assert ref.repository is not None
        assert ref.repository.slug == "repo-slug"
        assert ref.repository.project_key == "PROJ"

    def test_bitbucket_server_pull_request_reviewer_from_raw(self):
        """Test creating BitbucketServerPullRequestReviewer from raw data."""
        raw_data = {
            "user": {
                "id": 123,
                "name": "username",
                "displayName": "User Display Name",
                "emailAddress": "user@example.com",
                "active": True,
            },
            "status": "APPROVED",
        }

        reviewer = BitbucketServerPullRequestReviewer.from_raw(raw_data)

        assert reviewer.status == "APPROVED"
        assert reviewer.user is not None
        assert reviewer.user.name == "username"
        assert reviewer.user.display_name == "User Display Name"

    def test_bitbucket_server_pull_request_from_raw(self, mock_pull_request_response):
        """Test creating BitbucketServerPullRequest from raw data."""
        pr = BitbucketServerPullRequest.from_raw(mock_pull_request_response)

        assert pr.id == 101
        assert pr.version == 1
        assert pr.title == "Add new feature"
        assert pr.description == "This PR adds a new feature"
        assert pr.state == "OPEN"
        assert pr.open is True
        assert pr.closed is False

        # Verify timestamps converted to datetime objects
        assert isinstance(pr.created_date, datetime)
        assert isinstance(pr.updated_date, datetime)

        # Verify from_ref and to_ref
        assert pr.from_ref is not None
        assert pr.from_ref.display_id == "feature/new-feature"
        assert pr.to_ref is not None
        assert pr.to_ref.display_id == "main"

        # Verify author
        assert pr.author is not None
        assert pr.author.name == "user123"
        assert pr.author.display_name == "Test User"

        # Verify reviewers
        assert pr.reviewers is not None
        assert len(pr.reviewers) == 1
        assert pr.reviewers[0].status == "NEEDS_WORK"
        assert pr.reviewers[0].user.name == "reviewer1"

    def test_bitbucket_server_pull_request_to_simplified_dict(
        self, mock_pull_request_response
    ):
        """Test converting BitbucketServerPullRequest to simplified dict."""
        pr = BitbucketServerPullRequest.from_raw(mock_pull_request_response)
        result = pr.to_simplified_dict()

        assert isinstance(result, dict)
        assert result["id"] == 101
        assert result["title"] == "Add new feature"
        assert result["state"] == "OPEN"
        assert result["open"] is True

        # Check nested objects are also converted
        assert "from_ref" in result
        assert result["from_ref"]["display_id"] == "feature/new-feature"

        assert "to_ref" in result
        assert result["to_ref"]["display_id"] == "main"

        assert "author" in result
        assert result["author"]["name"] == "user123"

        assert "reviewers" in result
        assert len(result["reviewers"]) == 1
        assert result["reviewers"][0]["status"] == "NEEDS_WORK"
