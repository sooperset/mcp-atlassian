"""Tests for Jira development information operations."""

from unittest.mock import MagicMock, Mock

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.jira.development import DevelopmentMixin


class TestDevelopmentMixin:
    @pytest.fixture
    def development_mixin(self, mock_config, mock_atlassian_jira):
        mixin = DevelopmentMixin(config=mock_config)
        mixin.jira = mock_atlassian_jira
        return mixin

    @pytest.fixture
    def mock_dev_status_response(self):
        """Mock response from dev-status API with PRs."""
        return {
            "detail": [
                {
                    "_instance": {
                        "name": "Bitbucket Server",
                        "baseUrl": "https://stash.example.com",
                    },
                    "pullRequests": [
                        {
                            "id": "123",
                            "name": "[TEST-123] Fix bug in login",
                            "status": "MERGED",
                            "url": "https://stash.example.com/projects/PROJ/repos/app/pull-requests/123",
                            "source": {
                                "branch": "bugfix/TEST-123-login-fix",
                                "repository": {
                                    "name": "app",
                                    "url": "https://stash.example.com/projects/PROJ/repos/app",
                                },
                            },
                            "destination": {"branch": "develop"},
                            "author": {"name": "John Doe"},
                            "reviewers": [{"name": "Jane Smith"}],
                            "lastUpdate": "2024-01-15T10:30:00.000Z",
                        }
                    ],
                    "branches": [
                        {
                            "name": "bugfix/TEST-123-login-fix",
                            "url": "https://stash.example.com/projects/PROJ/repos/app/browse?at=bugfix/TEST-123-login-fix",
                            "createPullRequestUrl": "https://stash.example.com/projects/PROJ/repos/app/pull-requests?create&sourceBranch=bugfix/TEST-123-login-fix",
                        }
                    ],
                    "repositories": [],
                }
            ]
        }

    @pytest.fixture
    def mock_dev_status_with_commits(self):
        """Mock response with commits in repositories."""
        return {
            "detail": [
                {
                    "_instance": {
                        "name": "Bitbucket Server",
                        "baseUrl": "https://stash.example.com",
                    },
                    "pullRequests": [],
                    "branches": [],
                    "repositories": [
                        {
                            "name": "app",
                            "url": "https://stash.example.com/projects/PROJ/repos/app",
                            "avatar": "https://stash.example.com/avatar.png",
                            "commits": [
                                {
                                    "id": "abc123def456",
                                    "displayId": "abc123d",
                                    "message": "TEST-123: Fix login bug",
                                    "author": {"name": "John Doe"},
                                    "authorTimestamp": "2024-01-15T09:00:00.000Z",
                                    "url": "https://stash.example.com/projects/PROJ/repos/app/commits/abc123def456",
                                }
                            ],
                        }
                    ],
                }
            ]
        }

    def test_get_issue_development_info_success(
        self, development_mixin, mock_dev_status_response
    ):
        """Test successful retrieval of development info."""
        # Mock get_issue to return issue with ID
        development_mixin.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
        }

        # Mock the session.get call
        mock_response = MagicMock()
        mock_response.json.return_value = mock_dev_status_response
        mock_response.raise_for_status = MagicMock()
        development_mixin.jira._session.get.return_value = mock_response

        result = development_mixin.get_issue_development_info(
            "TEST-123", application_type="stash", data_type="pullrequest"
        )

        assert result["issue_key"] == "TEST-123"
        assert len(result["pullRequests"]) == 1
        assert result["pullRequests"][0]["name"] == "[TEST-123] Fix bug in login"
        assert result["pullRequests"][0]["status"] == "MERGED"
        assert result["pullRequests"][0]["author"] == "John Doe"
        assert len(result["branches"]) == 1
        assert result["branches"][0]["name"] == "bugfix/TEST-123-login-fix"

    def test_get_issue_development_info_with_commits(
        self, development_mixin, mock_dev_status_with_commits
    ):
        """Test retrieval of development info with commits."""
        development_mixin.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = mock_dev_status_with_commits
        mock_response.raise_for_status = MagicMock()
        development_mixin.jira._session.get.return_value = mock_response

        result = development_mixin.get_issue_development_info(
            "TEST-123", application_type="stash", data_type="repository"
        )

        assert result["issue_key"] == "TEST-123"
        assert len(result["commits"]) == 1
        assert result["commits"][0]["message"] == "TEST-123: Fix login bug"
        assert result["commits"][0]["author"] == "John Doe"
        assert len(result["repositories"]) == 1
        assert result["repositories"][0]["name"] == "app"

    def test_get_issue_development_info_empty_response(self, development_mixin):
        """Test handling of empty development info response."""
        development_mixin.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {"detail": []}
        mock_response.raise_for_status = MagicMock()
        development_mixin.jira._session.get.return_value = mock_response

        result = development_mixin.get_issue_development_info(
            "TEST-123", application_type="stash", data_type="pullrequest"
        )

        assert result["issue_key"] == "TEST-123"
        assert result["pullRequests"] == []
        assert result["branches"] == []
        assert result["commits"] == []

    def test_get_issue_development_info_issue_not_found(self, development_mixin):
        """Test error when issue is not found."""
        development_mixin.jira.get_issue.return_value = {"key": "TEST-123"}

        with pytest.raises(Exception, match="Could not get issue ID"):
            development_mixin.get_issue_development_info(
                "TEST-123", application_type="stash", data_type="pullrequest"
            )

    def test_get_issue_development_info_api_error(self, development_mixin):
        """Test handling of API errors."""
        development_mixin.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
        }

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = HTTPError(
            response=Mock(status_code=500)
        )
        development_mixin.jira._session.get.return_value = mock_response

        with pytest.raises(Exception, match="Error retrieving development info"):
            development_mixin.get_issue_development_info(
                "TEST-123", application_type="stash", data_type="pullrequest"
            )

    def test_get_issue_development_info_auto_discovery(self, development_mixin):
        """Test auto-discovery of application types when not specified."""
        development_mixin.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
        }

        # Return empty for all combinations
        mock_response = MagicMock()
        mock_response.json.return_value = {"detail": []}
        mock_response.raise_for_status = MagicMock()
        development_mixin.jira._session.get.return_value = mock_response

        result = development_mixin.get_issue_development_info("TEST-123")

        # Should have tried multiple app types
        assert development_mixin.jira._session.get.call_count > 1
        assert result["issue_key"] == "TEST-123"

    def test_get_issues_development_info_success(
        self, development_mixin, mock_dev_status_response
    ):
        """Test batch retrieval of development info for multiple issues."""
        development_mixin.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = mock_dev_status_response
        mock_response.raise_for_status = MagicMock()
        development_mixin.jira._session.get.return_value = mock_response

        results = development_mixin.get_issues_development_info(
            ["TEST-123", "TEST-456"], application_type="stash", data_type="pullrequest"
        )

        assert len(results) == 2
        # Each result has its own issue_key from the input list
        assert results[0]["issue_key"] == "TEST-123"
        assert results[1]["issue_key"] == "TEST-456"
        # Both should have PRs from the mock response
        assert len(results[0]["pullRequests"]) == 1
        assert len(results[1]["pullRequests"]) == 1

    def test_get_issues_development_info_partial_failure(self, development_mixin):
        """Test batch retrieval with some failures."""
        # First call succeeds, second fails
        development_mixin.jira.get_issue.side_effect = [
            {"id": "12345", "key": "TEST-123"},
            Exception("Issue not found"),
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {"detail": []}
        mock_response.raise_for_status = MagicMock()
        development_mixin.jira._session.get.return_value = mock_response

        results = development_mixin.get_issues_development_info(
            ["TEST-123", "TEST-456"], application_type="stash", data_type="pullrequest"
        )

        assert len(results) == 2
        assert results[0]["issue_key"] == "TEST-123"
        assert "error" in results[1]
        assert results[1]["pullRequests"] == []

    def test_parse_development_info_with_reviewers(self, development_mixin):
        """Test parsing of PR reviewers."""
        response = {
            "detail": [
                {
                    "_instance": {"name": "Bitbucket", "baseUrl": "https://bb.com"},
                    "pullRequests": [
                        {
                            "id": "1",
                            "name": "Test PR",
                            "status": "OPEN",
                            "url": "https://bb.com/pr/1",
                            "source": {"branch": "feature", "repository": {}},
                            "destination": {"branch": "main"},
                            "author": {"name": "Author"},
                            "reviewers": [
                                {"name": "Reviewer1"},
                                {"name": "Reviewer2"},
                            ],
                            "lastUpdate": "2024-01-01",
                        }
                    ],
                    "branches": [],
                    "repositories": [],
                }
            ]
        }

        result = development_mixin._parse_development_info(response, "TEST-1")

        assert len(result["pullRequests"]) == 1
        assert result["pullRequests"][0]["reviewers"] == ["Reviewer1", "Reviewer2"]

    def test_parse_development_info_missing_fields(self, development_mixin):
        """Test parsing handles missing optional fields gracefully."""
        response = {
            "detail": [
                {
                    "_instance": {},
                    "pullRequests": [
                        {
                            "id": "1",
                            "name": "Minimal PR",
                            "status": "OPEN",
                            "url": "https://example.com/pr/1",
                        }
                    ],
                    "branches": [],
                    "repositories": [],
                }
            ]
        }

        result = development_mixin._parse_development_info(response, "TEST-1")

        assert len(result["pullRequests"]) == 1
        pr = result["pullRequests"][0]
        assert pr["name"] == "Minimal PR"
        assert pr["source"] == ""
        assert pr["destination"] == ""
        assert pr["author"] == ""
        assert pr["reviewers"] == []
