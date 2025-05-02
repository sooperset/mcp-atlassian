"""Pytest fixtures for Bitbucket Server tests."""

import os
from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.bitbucket_server.client import BitbucketServerClient
from mcp_atlassian.bitbucket_server.config import BitbucketServerConfig


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for Bitbucket Server."""
    with patch.dict(
        os.environ,
        {
            "BITBUCKET_URL": "https://bitbucket.example.com",
            "BITBUCKET_USERNAME": "username",
            "BITBUCKET_API_TOKEN": "api_token",
            "BITBUCKET_PROJECTS_FILTER": "PROJ,TEST",
        },
    ):
        yield


@pytest.fixture
def mock_env_vars_personal_token():
    """Mock environment variables for Bitbucket Server with personal token."""
    with patch.dict(
        os.environ,
        {
            "BITBUCKET_URL": "https://bitbucket.example.com",
            "BITBUCKET_PERSONAL_TOKEN": "personal_token",
            "BITBUCKET_PROJECTS_FILTER": "PROJ,TEST",
        },
    ):
        yield


@pytest.fixture
def bitbucket_server_config():
    """Create a BitbucketServerConfig instance for tests."""
    return BitbucketServerConfig(
        url="https://bitbucket.example.com",
        auth_type="basic",
        username="username",
        api_token="api_token",
        ssl_verify=True,
        projects_filter="PROJ,TEST",
    )


@pytest.fixture
def bitbucket_server_client(bitbucket_server_config):
    """Create a BitbucketServerClient with mocked session."""
    client = BitbucketServerClient(bitbucket_server_config)
    client.session = MagicMock()
    return client


@pytest.fixture
def mock_pull_request_response():
    """Mock pull request response data."""
    return {
        "id": 101,
        "version": 1,
        "title": "Add new feature",
        "description": "This PR adds a new feature",
        "state": "OPEN",
        "open": True,
        "closed": False,
        "createdDate": 1617293932000,
        "updatedDate": 1617293932000,
        "fromRef": {
            "id": "refs/heads/feature/new-feature",
            "displayId": "feature/new-feature",
            "latestCommit": "abc123",
            "repository": {
                "id": 1,
                "slug": "test-repo",
                "name": "Test Repository",
                "project": {"key": "PROJ", "name": "Project"},
            },
        },
        "toRef": {
            "id": "refs/heads/main",
            "displayId": "main",
            "latestCommit": "def456",
            "repository": {
                "id": 1,
                "slug": "test-repo",
                "name": "Test Repository",
                "project": {"key": "PROJ", "name": "Project"},
            },
        },
        "author": {
            "id": 1,
            "name": "user123",
            "displayName": "Test User",
            "emailAddress": "user@example.com",
            "active": True,
        },
        "reviewers": [
            {
                "user": {
                    "id": 2,
                    "name": "reviewer1",
                    "displayName": "Reviewer One",
                    "emailAddress": "reviewer1@example.com",
                    "active": True,
                },
                "status": "NEEDS_WORK",
            }
        ],
    }
