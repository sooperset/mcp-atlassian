"""Test fixtures for Jira unit tests."""

import os
from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing."""
    with patch.dict(
        os.environ,
        {
            "JIRA_URL": "https://test.atlassian.net",
            "JIRA_USERNAME": "test_username",
            "JIRA_API_TOKEN": "test_token",
        },
        clear=True,  # Clear existing environment variables
    ):
        yield


@pytest.fixture
def mock_config():
    """Create a mock JiraConfig instance."""
    return JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="test_username",
        api_token="test_token",
    )


@pytest.fixture
def mock_atlassian_jira():
    """Mock the Atlassian Jira client."""
    mock_jira = MagicMock()

    mock_jira.get_all_fields.return_value = [
        {"id": "summary", "name": "Summary", "schema": {"type": "string"}},
        {"id": "description", "name": "Description", "schema": {"type": "string"}},
        {"id": "issuetype", "name": "Issue Type", "schema": {"type": "issuetype"}},
        {"id": "status", "name": "Status", "schema": {"type": "status"}},
        {"id": "priority", "name": "Priority", "schema": {"type": "priority"}},
        {
            "id": "labels",
            "name": "Labels",
            "schema": {"type": "array", "items": "string"},
        },
        {"id": "assignee", "name": "Assignee", "schema": {"type": "user"}},
        {"id": "reporter", "name": "Reporter", "schema": {"type": "user"}},
        {"id": "created", "name": "Created", "schema": {"type": "datetime"}},
        {"id": "updated", "name": "Updated", "schema": {"type": "datetime"}},
        {
            "id": "fixVersions",
            "name": "Fix Version/s",
            "schema": {"type": "array", "items": "version"},
        },
        {
            "id": "customfield_10010",
            "name": "Epic Link",
            "schema": {
                "type": "string",
                "custom": "com.pyxis.greenhopper.jira:gh-epic-link",
            },
        },
        {
            "id": "customfield_10011",
            "name": "Epic Name",
            "schema": {
                "type": "string",
                "custom": "com.pyxis.greenhopper.jira:gh-epic-label",
            },
        },
        {
            "id": "customfield_10012",
            "name": "Story Points",
            "schema": {"type": "number"},
        },
    ]

    # Set up common method returns
    mock_jira.myself.return_value = {"accountId": "test-account-id"}
    mock_jira.get_issue.return_value = {
        "key": "TEST-123",
        "fields": {
            "summary": "Test Issue",
            "description": "This is a test issue",
            "status": {"name": "Open"},
            "issuetype": {"name": "Bug"},
            "created": "2023-01-01T00:00:00.000+0000",
            "updated": "2023-01-02T00:00:00.000+0000",
        },
    }

    yield mock_jira


@pytest.fixture
def jira_client(mock_config, mock_atlassian_jira):
    """Create a JiraClient instance with mocked dependencies."""
    with patch("atlassian.Jira") as mock_jira_class:
        mock_jira_class.return_value = mock_atlassian_jira

        client = JiraClient(config=mock_config)
        # Replace the actual Jira instance with our mock
        client.jira = mock_atlassian_jira
        yield client


@pytest.fixture
def jira_fetcher(mock_config, mock_atlassian_jira):
    """Create a JiraFetcher instance with mocked dependencies."""
    from mcp_atlassian.jira import JiraFetcher

    with patch("atlassian.Jira") as mock_jira_class:
        mock_jira_class.return_value = mock_atlassian_jira

        fetcher = JiraFetcher(config=mock_config)
        # Replace the actual Jira instance with our mock
        fetcher.jira = mock_atlassian_jira
        yield fetcher
