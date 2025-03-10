"""
Root pytest configuration file for MCP Atlassian tests.
"""

import pytest


def pytest_addoption(parser):
    """Add command-line options for tests."""
    parser.addoption(
        "--use-real-data",
        action="store_true",
        default=False,
        help="Run tests that use real API data (requires env vars)",
    )


@pytest.fixture
def use_real_jira_data(request):
    """
    Check if real Jira data tests should be run.

    This will be True if the --use-real-data flag is passed to pytest.
    """
    return request.config.getoption("--use-real-data")


@pytest.fixture
def use_real_confluence_data(request):
    """
    Check if real Confluence data tests should be run.

    This will be True if the --use-real-data flag is passed to pytest.
    """
    return request.config.getoption("--use-real-data")
