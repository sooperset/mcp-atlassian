"""
Root pytest configuration file for MCP Atlassian tests.

This module provides session-scoped fixtures and utilities that are shared
across all test modules. It integrates with the new test utilities framework
to provide efficient, reusable test fixtures.
"""

import pytest

from tests.utils.factories import (
    AuthConfigFactory,
    ConfluencePageFactory,
    ErrorResponseFactory,
    JiraIssueFactory,
)
from tests.utils.mocks import MockAtlassianClient, MockEnvironment

# Restrict anyio tests to asyncio backend only (FastMCP client requires asyncio)
pytest_plugins = ("anyio",)


@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    """Override anyio backend to only use asyncio."""
    return request.param


def pytest_addoption(parser):
    """Add command-line options for tests."""
    parser.addoption(
        "--use-real-data",
        action="store_true",
        default=False,
        help="Run tests that use real API data (requires env vars)",
    )


# ============================================================================
# Session-Scoped Configuration Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def session_auth_configs():
    """
    Session-scoped fixture providing authentication configuration templates.

    This fixture is computed once per test session and provides standard
    authentication configurations for OAuth and basic auth scenarios.

    Returns:
        Dict[str, Dict[str, str]]: Authentication configuration templates
    """
    return {
        "oauth": AuthConfigFactory.create_oauth_config(),
        "basic_auth": AuthConfigFactory.create_basic_auth_config(),
        "jira_basic": {
            "url": "https://test.atlassian.net",
            "username": "test@example.com",
            "api_token": "test-jira-token",
        },
        "confluence_basic": {
            "url": "https://test.atlassian.net/wiki",
            "username": "test@example.com",
            "api_token": "test-confluence-token",
        },
    }


@pytest.fixture(scope="session")
def session_mock_data():
    """
    Session-scoped fixture providing mock data templates.

    This fixture creates mock data templates once per session to avoid
    recreating expensive mock objects for every test.

    Returns:
        Dict[str, Any]: Mock data templates for various API responses
    """
    return {
        "jira_issue": JiraIssueFactory.create(),
        "jira_issue_minimal": JiraIssueFactory.create_minimal(),
        "confluence_page": ConfluencePageFactory.create(),
        "api_error": ErrorResponseFactory.create_api_error(),
        "auth_error": ErrorResponseFactory.create_auth_error(),
        "jira_search_results": {
            "issues": [
                JiraIssueFactory.create("TEST-1"),
                JiraIssueFactory.create("TEST-2"),
                JiraIssueFactory.create("TEST-3"),
            ],
            "total": 3,
            "startAt": 0,
            "maxResults": 50,
        },
    }


# ============================================================================
# Environment and Configuration Fixtures
# ============================================================================


@pytest.fixture
def clean_environment():
    """
    Fixture that provides a clean environment with no auth variables.

    This is useful for testing error conditions and configuration validation.
    """
    with MockEnvironment.clean_env() as env:
        yield env


@pytest.fixture
def oauth_environment():
    """
    Fixture that provides a complete OAuth environment setup.

    This sets up all necessary OAuth environment variables for testing
    OAuth-based authentication flows.
    """
    with MockEnvironment.oauth_env() as env:
        yield env


@pytest.fixture
def basic_auth_environment():
    """
    Fixture that provides basic authentication environment setup.

    This sets up username/token authentication for both Jira and Confluence.
    """
    with MockEnvironment.basic_auth_env() as env:
        yield env


# ============================================================================
# Factory-Based Fixtures
# ============================================================================


@pytest.fixture
def make_jira_issue():
    """
    Factory fixture for creating Jira issues with customizable properties.

    Returns:
        Callable: Factory function that creates Jira issue data

    Example:
        def test_issue_creation(make_jira_issue):
            issue = make_jira_issue(key="CUSTOM-123",
                                  fields={"priority": {"name": "High"}})
            assert issue["key"] == "CUSTOM-123"
    """
    return JiraIssueFactory.create


@pytest.fixture
def make_confluence_page():
    """
    Factory fixture for creating Confluence pages with customizable properties.

    Returns:
        Callable: Factory function that creates Confluence page data

    Example:
        def test_page_creation(make_confluence_page):
            page = make_confluence_page(title="Custom Page",
                                      space={"key": "CUSTOM"})
            assert page["title"] == "Custom Page"
    """
    return ConfluencePageFactory.create


@pytest.fixture
def make_auth_config():
    """
    Factory fixture for creating authentication configurations.

    Returns:
        Dict[str, Callable]: Factory functions for different auth types

    Example:
        def test_oauth_config(make_auth_config):
            config = make_auth_config["oauth"](client_id="custom-id")
            assert config["client_id"] == "custom-id"
    """
    return {
        "oauth": AuthConfigFactory.create_oauth_config,
        "basic": AuthConfigFactory.create_basic_auth_config,
    }


@pytest.fixture
def make_api_error():
    """
    Factory fixture for creating API error responses.

    Returns:
        Callable: Factory function that creates error response data

    Example:
        def test_error_handling(make_api_error):
            error = make_api_error(status_code=404, message="Not Found")
            assert error["status"] == 404
    """
    return ErrorResponseFactory.create_api_error


# ============================================================================
# Mock Client Fixtures
# ============================================================================


@pytest.fixture
def mock_jira_client():
    """
    Fixture providing a pre-configured mock Jira client.

    The client comes with sensible defaults for common operations
    but can be customized per test as needed.

    Returns:
        MagicMock: Configured mock Jira client
    """
    return MockAtlassianClient.create_jira_client()


@pytest.fixture
def mock_confluence_client():
    """
    Fixture providing a pre-configured mock Confluence client.

    The client comes with sensible defaults for common operations
    but can be customized per test as needed.

    Returns:
        MagicMock: Configured mock Confluence client
    """
    return MockAtlassianClient.create_confluence_client()


# ============================================================================
# Compatibility Fixtures (maintain backward compatibility)
# ============================================================================


@pytest.fixture
def use_real_jira_data(request):
    """
    Check if real Jira data tests should be run.

    This will be True if the --use-real-data flag is passed to pytest.

    Note: This fixture is maintained for backward compatibility.
    """
    return request.config.getoption("--use-real-data")


@pytest.fixture
def use_real_confluence_data(request):
    """
    Check if real Confluence data tests should be run.

    This will be True if the --use-real-data flag is passed to pytest.

    Note: This fixture is maintained for backward compatibility.
    """
    return request.config.getoption("--use-real-data")


# ============================================================================
# Advanced Environment Utilities
# ============================================================================


@pytest.fixture
def env_var_manager():
    """
    Fixture providing utilities for managing environment variables in tests.

    Returns:
        MockEnvironment: Environment management utilities

    Example:
        def test_with_custom_env(env_var_manager):
            with env_var_manager.oauth_env():
                # Test OAuth functionality
                pass
    """
    return MockEnvironment


@pytest.fixture
def parametrized_auth_env(request):
    """
    Parametrized fixture for testing with different authentication environments.

    This fixture can be used with pytest.mark.parametrize to test the same
    functionality with different authentication setups.

    Example:
        @pytest.mark.parametrize("parametrized_auth_env",
                               ["oauth", "basic_auth"], indirect=True)
        def test_auth_scenarios(parametrized_auth_env):
            # Test will run once for OAuth and once for basic auth
            pass
    """
    auth_type = request.param

    if auth_type == "oauth":
        with MockEnvironment.oauth_env() as env:
            yield env
    elif auth_type == "basic_auth":
        with MockEnvironment.basic_auth_env() as env:
            yield env
    elif auth_type == "clean":
        with MockEnvironment.clean_env() as env:
            yield env
    else:
        raise ValueError(f"Unknown auth type: {auth_type}")


# ============================================================================
# Session Validation and Health Checks
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def validate_test_environment():
    """
    Session-scoped fixture that validates the test environment setup.

    This fixture runs automatically and ensures that the test environment
    is properly configured for running the test suite.
    """
    # Validate that test utilities are importable
    try:
        import importlib.util

        # Check if modules can be imported
        for module_name in [
            "tests.fixtures.confluence_mocks",
            "tests.fixtures.jira_mocks",
            "tests.utils.base",
            "tests.utils.factories",
            "tests.utils.mocks",
        ]:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                pytest.fail(f"Failed to find module: {module_name}")
    except ImportError as e:
        pytest.fail(f"Failed to import test utilities: {e}")

    # Log session start
    print("\n🧪 Starting MCP Atlassian test session with enhanced fixtures")

    yield

    # Log session end
    print("\n✅ Completed MCP Atlassian test session")
