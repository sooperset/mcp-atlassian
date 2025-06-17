"""
Test fixtures for Jira unit tests.

This module provides specialized fixtures for testing Jira-related functionality.
It builds upon the root conftest.py fixtures and provides Jira-specific mocks,
configurations, and utilities with efficient session-scoped caching.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig
from tests.utils.factories import AuthConfigFactory, JiraIssueFactory
from tests.utils.mocks import MockAtlassianClient

# ============================================================================
# Session-Scoped Jira Data Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def session_jira_field_definitions():
    """
    Session-scoped fixture providing Jira field definitions.

    This expensive-to-create data is cached for the entire test session
    to improve test performance.

    Returns:
        List[Dict[str, Any]]: Complete Jira field definitions
    """
    return [
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
        {
            "id": "customfield_10013",
            "name": "Sprint",
            "schema": {"type": "array", "items": "string"},
        },
        {
            "id": "components",
            "name": "Component/s",
            "schema": {"type": "array", "items": "component"},
        },
        {
            "id": "resolution",
            "name": "Resolution",
            "schema": {"type": "resolution"},
        },
        {
            "id": "resolutiondate",
            "name": "Resolved",
            "schema": {"type": "datetime"},
        },
        {
            "id": "workratio",
            "name": "Work Ratio",
            "schema": {"type": "number"},
        },
        {
            "id": "timeestimate",
            "name": "Remaining Estimate",
            "schema": {"type": "timetracking"},
        },
        {
            "id": "timespent",
            "name": "Time Spent",
            "schema": {"type": "timetracking"},
        },
        {
            "id": "timeoriginalestimate",
            "name": "Original Estimate",
            "schema": {"type": "timetracking"},
        },
    ]


@pytest.fixture(scope="session")
def session_jira_projects():
    """
    Session-scoped fixture providing Jira project definitions.

    Returns:
        List[Dict[str, Any]]: Mock Jira project data
    """
    return [
        {
            "id": "10000",
            "key": "TEST",
            "name": "Test Project",
            "projectTypeKey": "software",
            "lead": {"displayName": "Test Lead"},
            "description": "Test project for unit tests",
        },
        {
            "id": "10001",
            "key": "DEMO",
            "name": "Demo Project",
            "projectTypeKey": "business",
            "lead": {"displayName": "Demo Lead"},
            "description": "Demo project for testing",
        },
        {
            "id": "10002",
            "key": "SAMPLE",
            "name": "Sample Project",
            "projectTypeKey": "service_desk",
            "lead": {"displayName": "Sample Lead"},
            "description": "Sample project with service desk",
        },
    ]


@pytest.fixture(scope="session")
def session_jira_issue_types():
    """
    Session-scoped fixture providing Jira issue type definitions.

    Returns:
        List[Dict[str, Any]]: Mock Jira issue type data
    """
    return [
        {"id": "1", "name": "Bug", "iconUrl": "bug.png", "subtask": False},
        {"id": "2", "name": "Task", "iconUrl": "task.png", "subtask": False},
        {"id": "3", "name": "Story", "iconUrl": "story.png", "subtask": False},
        {"id": "4", "name": "Epic", "iconUrl": "epic.png", "subtask": False},
        {"id": "5", "name": "Sub-task", "iconUrl": "subtask.png", "subtask": True},
        {
            "id": "6",
            "name": "Improvement",
            "iconUrl": "improvement.png",
            "subtask": False,
        },
        {
            "id": "7",
            "name": "New Feature",
            "iconUrl": "newfeature.png",
            "subtask": False,
        },
    ]


# ============================================================================
# Configuration Fixtures
# ============================================================================


@pytest.fixture
def jira_config_factory():
    """
    Factory for creating JiraConfig instances with customizable options.

    Returns:
        Callable: Function that creates JiraConfig instances

    Example:
        def test_config(jira_config_factory):
            config = jira_config_factory(url="https://custom.atlassian.net")
            assert config.url == "https://custom.atlassian.net"
    """

    def _create_config(**overrides):
        defaults = {
            "url": "https://test.atlassian.net",
            "auth_type": "basic",
            "username": "test_username",
            "api_token": "test_token",
        }
        config_data = {**defaults, **overrides}
        return JiraConfig(**config_data)

    return _create_config


@pytest.fixture
def mock_config(jira_config_factory):
    """
    Create a standard mock JiraConfig instance.

    This fixture provides a consistent JiraConfig for tests that don't
    need custom configuration.

    Returns:
        JiraConfig: Standard test configuration
    """
    return jira_config_factory()


# ============================================================================
# Environment Fixtures
# ============================================================================


@pytest.fixture
def mock_env_vars():
    """
    Mock environment variables for testing.

    Note: This fixture is maintained for backward compatibility.
    Consider using the environment fixtures from root conftest.py.
    """
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
def jira_auth_environment():
    """
    Fixture providing Jira-specific authentication environment.

    This sets up environment variables specifically for Jira authentication
    and can be customized per test.
    """
    auth_config = AuthConfigFactory.create_basic_auth_config()
    jira_env = {
        "JIRA_URL": auth_config["url"],
        "JIRA_USERNAME": auth_config["username"],
        "JIRA_API_TOKEN": auth_config["api_token"],
    }

    with patch.dict(os.environ, jira_env, clear=False):
        yield jira_env


# ============================================================================
# Mock Atlassian Client Fixtures
# ============================================================================


@pytest.fixture
def mock_atlassian_jira(
    session_jira_field_definitions, session_jira_projects, session_jira_issue_types
):
    """
    Enhanced mock of the Atlassian Jira client.

    This fixture provides a comprehensive mock that uses session-scoped
    data for improved performance and consistency.

    Args:
        session_jira_field_definitions: Session-scoped field definitions
        session_jira_projects: Session-scoped project data
        session_jira_issue_types: Session-scoped issue type data

    Returns:
        MagicMock: Fully configured mock Jira client
    """
    mock_jira = MagicMock()

    # Use session-scoped data for consistent responses
    mock_jira.get_all_fields.return_value = session_jira_field_definitions
    mock_jira.projects.return_value = session_jira_projects
    mock_jira.issue_types.return_value = session_jira_issue_types

    # Set up common method returns using factory
    mock_jira.myself.return_value = {
        "accountId": "test-account-id",
        "displayName": "Test User",
    }
    mock_jira.get_issue.return_value = JiraIssueFactory.create()

    # Search results
    mock_jira.jql.return_value = {
        "issues": [
            JiraIssueFactory.create("TEST-1"),
            JiraIssueFactory.create("TEST-2"),
            JiraIssueFactory.create("TEST-3"),
        ],
        "total": 3,
        "startAt": 0,
        "maxResults": 50,
    }

    # Issue creation
    mock_jira.create_issue.return_value = JiraIssueFactory.create()

    # Issue update (returns None like real API)
    mock_jira.update_issue.return_value = None

    # Worklog operations
    mock_jira.get_issue_worklog.return_value = {
        "worklogs": [
            {
                "id": "10000",
                "timeSpent": "3h",
                "timeSpentSeconds": 10800,
                "comment": "Test work",
                "started": "2023-01-01T09:00:00.000+0000",
                "author": {"displayName": "Test User"},
            }
        ]
    }

    # Comments
    mock_jira.get_issue_comments.return_value = {
        "comments": [
            {
                "id": "10000",
                "body": "Test comment",
                "author": {"displayName": "Test User"},
                "created": "2023-01-01T12:00:00.000+0000",
            }
        ]
    }

    yield mock_jira


@pytest.fixture
def enhanced_mock_jira_client():
    """
    Enhanced mock Jira client using the new factory system.

    This provides a more flexible mock that can be easily customized
    and integrates with the factory system.

    Returns:
        MagicMock: Enhanced mock Jira client with factory integration
    """
    return MockAtlassianClient.create_jira_client()


# ============================================================================
# Client Instance Fixtures
# ============================================================================


@pytest.fixture
def jira_client(mock_config, mock_atlassian_jira):
    """
    Create a JiraClient instance with mocked dependencies.

    This fixture provides a fully functional JiraClient with mocked
    Atlassian API calls for testing.

    Args:
        mock_config: Mock configuration
        mock_atlassian_jira: Mock Atlassian client

    Returns:
        JiraClient: Configured client instance
    """
    with patch("atlassian.Jira") as mock_jira_class:
        mock_jira_class.return_value = mock_atlassian_jira

        client = JiraClient(config=mock_config)
        # Replace the actual Jira instance with our mock
        client.jira = mock_atlassian_jira
        yield client


@pytest.fixture
def jira_fetcher(mock_config, mock_atlassian_jira):
    """
    Create a JiraFetcher instance with mocked dependencies.

    Note: This fixture is maintained for backward compatibility.

    Args:
        mock_config: Mock configuration
        mock_atlassian_jira: Mock Atlassian client

    Returns:
        JiraFetcher: Configured fetcher instance
    """
    from mcp_atlassian.jira import JiraFetcher

    with patch("atlassian.Jira") as mock_jira_class:
        mock_jira_class.return_value = mock_atlassian_jira

        fetcher = JiraFetcher(config=mock_config)
        # Replace the actual Jira instance with our mock
        fetcher.jira = mock_atlassian_jira
        yield fetcher


# ============================================================================
# Specialized Test Data Fixtures
# ============================================================================


@pytest.fixture
def make_jira_issue_with_worklog():
    """
    Factory fixture for creating Jira issues with worklog data.

    Returns:
        Callable: Function that creates issue data with worklog

    Example:
        def test_worklog(make_jira_issue_with_worklog):
            issue = make_jira_issue_with_worklog(
                key="TEST-123",
                worklog_hours=5,
                worklog_comment="Development work"
            )
    """

    def _create_issue_with_worklog(
        key: str = "TEST-123",
        worklog_hours: int = 3,
        worklog_comment: str = "Test work",
        **overrides,
    ):
        issue = JiraIssueFactory.create(key, **overrides)
        issue["fields"]["worklog"] = {
            "worklogs": [
                {
                    "id": "10000",
                    "timeSpent": f"{worklog_hours}h",
                    "timeSpentSeconds": worklog_hours * 3600,
                    "comment": worklog_comment,
                    "started": "2023-01-01T09:00:00.000+0000",
                    "author": {"displayName": "Test User"},
                }
            ]
        }
        return issue

    return _create_issue_with_worklog


@pytest.fixture
def make_jira_search_results():
    """
    Factory fixture for creating Jira search results.

    Returns:
        Callable: Function that creates JQL search results

    Example:
        def test_search(make_jira_search_results):
            results = make_jira_search_results(
                issues=["TEST-1", "TEST-2"],
                total=2
            )
    """

    def _create_search_results(
        issues: list[str] = None, total: int = None, **overrides
    ):
        if issues is None:
            issues = ["TEST-1", "TEST-2", "TEST-3"]
        if total is None:
            total = len(issues)

        issue_objects = [JiraIssueFactory.create(key) for key in issues]

        defaults = {
            "issues": issue_objects,
            "total": total,
            "startAt": 0,
            "maxResults": 50,
        }

        return {**defaults, **overrides}

    return _create_search_results


# ============================================================================
# Integration Test Fixtures
# ============================================================================


@pytest.fixture
def jira_integration_client(session_auth_configs):
    """
    Create a JiraClient for integration testing.

    This fixture creates a client that can be used for integration tests
    when real API credentials are available.

    Args:
        session_auth_configs: Session-scoped auth configurations

    Returns:
        Optional[JiraClient]: Real client if credentials available, None otherwise
    """
    # Check if integration test environment variables are set
    required_vars = ["JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN"]
    if not all(os.environ.get(var) for var in required_vars):
        pytest.skip("Integration test environment variables not set")

    config = JiraConfig(
        url=os.environ["JIRA_URL"],
        auth_type="basic",
        username=os.environ["JIRA_USERNAME"],
        api_token=os.environ["JIRA_API_TOKEN"],
    )

    return JiraClient(config=config)


# ============================================================================
# Parameterized Fixtures
# ============================================================================


@pytest.fixture
def parametrized_jira_issue_type(request):
    """
    Parametrized fixture for testing with different Jira issue types.

    Use with pytest.mark.parametrize to test functionality across
    different issue types.

    Example:
        @pytest.mark.parametrize("parametrized_jira_issue_type",
                               ["Bug", "Task", "Story"], indirect=True)
        def test_issue_types(parametrized_jira_issue_type):
            # Test runs once for each issue type
            pass
    """
    issue_type = request.param
    return JiraIssueFactory.create(fields={"issuetype": {"name": issue_type}})


@pytest.fixture
def parametrized_jira_status(request):
    """
    Parametrized fixture for testing with different Jira statuses.

    Use with pytest.mark.parametrize to test functionality across
    different issue statuses.
    """
    status = request.param
    return JiraIssueFactory.create(fields={"status": {"name": status}})
