"""
Test fixtures for model testing.
"""

import os
from typing import Any

import pytest

from tests.fixtures.confluence_mocks import (
    MOCK_COMMENTS_RESPONSE,
    MOCK_CQL_SEARCH_RESPONSE,
    MOCK_PAGE_RESPONSE,
)

# Import mock data
from tests.fixtures.jira_mocks import (
    MOCK_JIRA_COMMENTS,
    MOCK_JIRA_ISSUE_RESPONSE,
    MOCK_JIRA_JQL_RESPONSE,
)


@pytest.fixture
def jira_issue_data() -> dict[str, Any]:
    """Return mock Jira issue data."""
    return MOCK_JIRA_ISSUE_RESPONSE


@pytest.fixture
def jira_search_data() -> dict[str, Any]:
    """Return mock Jira search (JQL) results."""
    return MOCK_JIRA_JQL_RESPONSE


@pytest.fixture
def jira_comments_data() -> dict[str, Any]:
    """Return mock Jira comments data."""
    return MOCK_JIRA_COMMENTS


@pytest.fixture
def confluence_search_data() -> dict[str, Any]:
    """Return mock Confluence search (CQL) results."""
    return MOCK_CQL_SEARCH_RESPONSE


@pytest.fixture
def confluence_page_data() -> dict[str, Any]:
    """Return mock Confluence page data."""
    return MOCK_PAGE_RESPONSE


@pytest.fixture
def confluence_comments_data() -> dict[str, Any]:
    """Return mock Confluence comments data."""
    return MOCK_COMMENTS_RESPONSE


# Conditional fixtures for accessing real data if the user wants to use it
@pytest.fixture
def use_real_jira_data() -> bool:
    """
    Check if we should use real Jira data from the API.

    This will only return True if:
    1. The JIRA_URL, JIRA_USERNAME, and JIRA_API_TOKEN environment variables are set
    2. The USE_REAL_DATA environment variable is set to "true"
    """
    required_vars = ["JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN"]
    if not all(os.environ.get(var) for var in required_vars):
        return False

    return os.environ.get("USE_REAL_DATA", "").lower() == "true"


@pytest.fixture
def use_real_confluence_data() -> bool:
    """
    Check if we should use real Confluence data from the API.

    This will only return True if:
    1. The CONFLUENCE_URL, CONFLUENCE_USERNAME, and CONFLUENCE_API_TOKEN environment variables are set
    2. The USE_REAL_DATA environment variable is set to "true"
    """
    required_vars = ["CONFLUENCE_URL", "CONFLUENCE_USERNAME", "CONFLUENCE_API_TOKEN"]
    if not all(os.environ.get(var) for var in required_vars):
        return False

    return os.environ.get("USE_REAL_DATA", "").lower() == "true"


@pytest.fixture
def default_confluence_page_id() -> str:
    """
    Provides a default Confluence page ID to use for tests.

    Skips the test if CONFLUENCE_TEST_PAGE_ID environment variable is not set.
    """
    page_id = os.environ.get("CONFLUENCE_TEST_PAGE_ID")
    if not page_id:
        pytest.skip("CONFLUENCE_TEST_PAGE_ID environment variable not set")
    return page_id


@pytest.fixture
def default_jira_issue_key() -> str:
    """
    Provides a default Jira issue key to use for tests.

    Skips the test if JIRA_TEST_ISSUE_KEY environment variable is not set.
    """
    issue_key = os.environ.get("JIRA_TEST_ISSUE_KEY")
    if not issue_key:
        pytest.skip("JIRA_TEST_ISSUE_KEY environment variable not set")
    return issue_key
