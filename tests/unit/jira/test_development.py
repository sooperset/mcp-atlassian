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

        assert development_mixin.jira._session.get.call_count == 1
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

    def test_get_issue_development_info_plugin_not_found(self, development_mixin):
        """Test 404 response returns descriptive error message without raising."""
        development_mixin.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
        }

        mock_response = MagicMock()
        mock_response.status_code = 404
        development_mixin.jira._session.get.return_value = mock_response

        result = development_mixin.get_issue_development_info(
            "TEST-123", application_type="stash", data_type="pullrequest"
        )

        assert "error" in result
        assert "dev-status plugin" in result["error"]
        assert result["pullRequests"] == []
        assert result["branches"] == []
        assert result["commits"] == []

    def test_get_issue_development_info_access_denied(self, development_mixin):
        """Test 403 response returns descriptive error message without raising."""
        development_mixin.jira.get_issue.return_value = {
            "id": "12345",
            "key": "TEST-123",
        }

        mock_response = MagicMock()
        mock_response.status_code = 403
        development_mixin.jira._session.get.return_value = mock_response

        result = development_mixin.get_issue_development_info(
            "TEST-123", application_type="stash", data_type="pullrequest"
        )

        assert "error" in result
        assert "Access denied" in result["error"]
        assert result["pullRequests"] == []
        assert result["branches"] == []
        assert result["commits"] == []

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

    def test_discover_application_types_success(self, development_mixin):
        """Test successful discovery of application types from summary endpoint."""
        mock_issue = {"id": "12345", "key": "TEST-123"}
        mock_summary = {
            "summary": {
                "pullrequest": {
                    "byInstanceType": {
                        "bitbucket": {"count": 2, "name": "Bitbucket Cloud"},
                        "githube": {"count": 1, "name": "GitHub Enterprise"},
                    }
                },
                "branch": {
                    "byInstanceType": {
                        "bitbucket": {"count": 1, "name": "Bitbucket Cloud"}
                    }
                },
            }
        }

        development_mixin.jira.get_issue = Mock(return_value=mock_issue)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_summary
        mock_response.raise_for_status = MagicMock()
        development_mixin.jira._session.get.return_value = mock_response

        app_types = development_mixin._discover_application_types(
            issue_key="TEST-123", issue_id="12345"
        )

        # Should find both bitbucket and githube, sorted alphabetically
        assert app_types == {"bitbucket", "githube"}

    def test_discover_application_types_fallback_on_404(self, development_mixin):
        """Test fallback to common types when summary endpoint returns 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        development_mixin.jira._session.get.return_value = mock_response

        app_types = development_mixin._discover_application_types(
            issue_key="TEST-123", issue_id="12345"
        )

        # Should fallback to default list
        assert app_types == ["stash", "bitbucket", "github", "gitlab"]

    def test_discover_application_types_fallback_on_403(self, development_mixin):
        """Test fallback to common types when summary endpoint returns 403."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        development_mixin.jira._session.get.return_value = mock_response

        app_types = development_mixin._discover_application_types(
            issue_key="TEST-123", issue_id="12345"
        )

        # Should fallback to default list
        assert app_types == ["stash", "bitbucket", "github", "gitlab"]

    def test_discover_application_types_with_data_type_filter(self, development_mixin):
        """Test discovery with specific data type filter."""
        mock_summary = {
            "summary": {
                "pullrequest": {
                    "byInstanceType": {
                        "githube": {"count": 3, "name": "GitHub Enterprise"}
                    }
                },
                "branch": {
                    "byInstanceType": {
                        "bitbucket": {"count": 1, "name": "Bitbucket Cloud"}
                    }
                },
            }
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_summary
        mock_response.raise_for_status = MagicMock()
        development_mixin.jira._session.get.return_value = mock_response

        # Filter by pullrequest data type - should only find githube
        app_types = development_mixin._discover_application_types(
            issue_key="TEST-123", issue_id="12345", data_type="pullrequest"
        )

        assert app_types == {"githube"}

    def test_discover_application_types_empty_summary(self, development_mixin):
        """Test discovery when summary has no application types."""
        mock_summary = {
            "summary": {
                "pullrequest": {"byInstanceType": {}},
                "branch": {"byInstanceType": {}},
            }
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_summary
        mock_response.raise_for_status = MagicMock()
        development_mixin.jira._session.get.return_value = mock_response

        app_types = development_mixin._discover_application_types(
            issue_key="TEST-123", issue_id="12345"
        )

        # Should fallback to default list
        assert app_types == set()

    def test_discover_application_types_exception_handling(self, development_mixin):
        """Test discovery handles exceptions gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = Exception("Network error")
        development_mixin.jira._session.get.return_value = mock_response

        app_types = development_mixin._discover_application_types(
            issue_key="TEST-123", issue_id="12345"
        )

        # Should fallback to default list
        assert app_types == ["stash", "bitbucket", "github", "gitlab"]

    def test_get_issue_development_info_uses_discovery(
        self, development_mixin, mock_dev_status_response
    ):
        """Test that auto-discovery uses the discovery method."""
        mock_issue = {"id": "12345", "key": "TEST-123"}
        mock_summary = {
            "summary": {
                "pullrequest": {
                    "byInstanceType": {
                        "githube": {"count": 1, "name": "GitHub Enterprise"}
                    }
                }
            }
        }

        development_mixin.jira.get_issue = Mock(return_value=mock_issue)

        # First call returns summary, second returns dev info
        mock_summary_response = MagicMock()
        mock_summary_response.status_code = 200
        mock_summary_response.json.return_value = mock_summary
        mock_summary_response.raise_for_status = MagicMock()

        mock_detail_response = MagicMock()
        mock_detail_response.status_code = 200
        mock_detail_response.json.return_value = mock_dev_status_response
        mock_detail_response.raise_for_status = MagicMock()

        development_mixin.jira._session.get.side_effect = [
            mock_summary_response,  # summary call
            mock_detail_response,  # detail call for pullrequest
            mock_detail_response,  # detail call for branch
            mock_detail_response,  # detail call for repository
        ]

        result = development_mixin.get_issue_development_info(issue_key="TEST-123")

        assert result["issue_key"] == "TEST-123"
        # Should have made calls to both summary and detail endpoints
        assert development_mixin.jira._session.get.call_count >= 2
