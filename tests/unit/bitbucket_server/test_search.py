"""Tests for Bitbucket Server search module."""

import json
from unittest.mock import Mock

import pytest

from mcp_atlassian.bitbucket_server.client import BitbucketServerClient
from mcp_atlassian.bitbucket_server.config import BitbucketServerConfig
from mcp_atlassian.bitbucket_server.search import BitbucketServerSearch
from mcp_atlassian.exceptions import BitbucketServerApiError


@pytest.fixture
def mock_client():
    """Create a mock Bitbucket Server client."""
    client = Mock(spec=BitbucketServerClient)
    client.root_url = "https://stash.example.com"
    client.post_url.return_value = {"success": True}
    return client


@pytest.fixture
def mock_config():
    """Create a mock Bitbucket Server config."""
    config = Mock(spec=BitbucketServerConfig)
    config.url = "https://stash.example.com"
    config.api_base_url = "https://stash.example.com/rest/api/1.0"
    return config


@pytest.fixture
def bitbucket_search(mock_client, mock_config):
    """Create a BitbucketServerSearch instance with mock dependencies."""
    return BitbucketServerSearch(mock_client, mock_config)


class TestBitbucketServerSearch:
    """Tests for BitbucketServerSearch class."""

    def test_search_code_simple_query(self, bitbucket_search, mock_client):
        """Test searching code with a simple query."""
        bitbucket_search.search_code("test")

        expected_url = "https://stash.example.com/rest/search/latest/search"
        expected_payload = {
            "query": "test",
            "entities": {"code": {"start": 1, "limit": 10}},
        }

        mock_client.post_url.assert_called_once_with(
            expected_url, data=json.dumps(expected_payload)
        )

    def test_search_code_with_project_filter(self, bitbucket_search, mock_client):
        """Test searching code with a project filter."""
        bitbucket_search.search_code("test", project_key="PROJ")

        expected_url = "https://stash.example.com/rest/search/latest/search"
        expected_payload = {
            "query": "project:PROJ test",
            "entities": {"code": {"start": 1, "limit": 10}},
        }

        mock_client.post_url.assert_called_once_with(
            expected_url, data=json.dumps(expected_payload)
        )

    def test_search_code_with_repository_filter(self, bitbucket_search, mock_client):
        """Test searching code with a repository filter."""
        bitbucket_search.search_code("test", repository_slug="my-repo")

        expected_url = "https://stash.example.com/rest/search/latest/search"
        expected_payload = {
            "query": "repo:my-repo test",
            "entities": {"code": {"start": 1, "limit": 10}},
        }

        mock_client.post_url.assert_called_once_with(
            expected_url, data=json.dumps(expected_payload)
        )

    def test_search_code_with_all_filters(self, bitbucket_search, mock_client):
        """Test searching code with all filters."""
        bitbucket_search.search_code(
            "test", project_key="PROJ", repository_slug="my-repo", page=2, limit=20
        )

        expected_url = "https://stash.example.com/rest/search/latest/search"
        expected_payload = {
            "query": "repo:my-repo project:PROJ test",
            "entities": {"code": {"start": 2, "limit": 20}},
        }

        mock_client.post_url.assert_called_once_with(
            expected_url, data=json.dumps(expected_payload)
        )

    def test_search_code_error_handling(self, bitbucket_search, mock_client):
        """Test error handling when searching code."""
        mock_client.post_url.side_effect = Exception("Test error")

        with pytest.raises(BitbucketServerApiError) as excinfo:
            bitbucket_search.search_code("test")

        assert "Failed to search code: Test error" in str(excinfo.value)

    def test_search_repositories_simple_query(self, bitbucket_search, mock_client):
        """Test searching repositories with a simple query."""
        bitbucket_search.search_repositories("test")

        expected_url = "https://stash.example.com/rest/search/latest/search"
        expected_payload = {
            "query": "test",
            "entities": {"repositories": {"start": 1, "limit": 10}},
        }

        mock_client.post_url.assert_called_once_with(
            expected_url, data=json.dumps(expected_payload)
        )

    def test_search_repositories_with_project_filter(
        self, bitbucket_search, mock_client
    ):
        """Test searching repositories with a project filter."""
        bitbucket_search.search_repositories("test", project_key="PROJ")

        expected_url = "https://stash.example.com/rest/search/latest/search"
        expected_payload = {
            "query": "PROJ",
            "entities": {"repositories": {"start": 1, "limit": 10}},
        }

        mock_client.post_url.assert_called_once_with(
            expected_url, data=json.dumps(expected_payload)
        )

    def test_search_repositories_with_pagination(self, bitbucket_search, mock_client):
        """Test searching repositories with pagination."""
        bitbucket_search.search_repositories("test", page=3, limit=15)

        expected_url = "https://stash.example.com/rest/search/latest/search"
        expected_payload = {
            "query": "test",
            "entities": {"repositories": {"start": 3, "limit": 15}},
        }

        mock_client.post_url.assert_called_once_with(
            expected_url, data=json.dumps(expected_payload)
        )

    def test_search_repositories_error_handling(self, bitbucket_search, mock_client):
        """Test error handling when searching repositories."""
        mock_client.post_url.side_effect = Exception("Test error")

        with pytest.raises(BitbucketServerApiError) as excinfo:
            bitbucket_search.search_repositories("test")

        assert "Failed to search repositories: Test error" in str(excinfo.value)
