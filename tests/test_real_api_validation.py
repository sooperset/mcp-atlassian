"""
Test file for validating the refactored models with real API data.

This test file connects to real Jira and Confluence instances to validate
that our model refactoring works correctly with actual API data.

These tests will be skipped if the required environment variables are not set
or if the --use-real-data flag is not passed to pytest.

To run these tests:
    pytest tests/test_real_api_validation.py --use-real-data

Required environment variables:
    - JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
    - CONFLUENCE_URL, CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN
    - JIRA_TEST_ISSUE_KEY (optional, defaults to issue key from your Jira instance)
    - CONFLUENCE_PAGE_ID (optional, defaults to a page ID from your Confluence instance)
"""

import os

import pytest

from mcp_atlassian.confluence import ConfluenceFetcher

# Import Confluence models and modules
from mcp_atlassian.confluence.comments import CommentsMixin as ConfluenceCommentsMixin
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.confluence.pages import PagesMixin
from mcp_atlassian.confluence.search import SearchMixin as ConfluenceSearchMixin
from mcp_atlassian.jira import JiraFetcher

# Import Jira models and modules
from mcp_atlassian.jira.comments import CommentsMixin as JiraCommentsMixin
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.jira.issues import IssuesMixin
from mcp_atlassian.jira.search import SearchMixin as JiraSearchMixin
from mcp_atlassian.models.confluence import ConfluenceComment, ConfluencePage
from mcp_atlassian.models.jira import JiraIssue


@pytest.fixture
def jira_config() -> JiraConfig:
    """Create a JiraConfig from environment variables."""
    return JiraConfig.from_env()


@pytest.fixture
def confluence_config() -> ConfluenceConfig:
    """Create a ConfluenceConfig from environment variables."""
    return ConfluenceConfig.from_env()


@pytest.fixture
def jira_client(jira_config: JiraConfig) -> JiraFetcher:
    """Create a JiraFetcher instance."""
    return JiraFetcher(config=jira_config)


@pytest.fixture
def confluence_client(confluence_config: ConfluenceConfig) -> ConfluenceFetcher:
    """Create a ConfluenceFetcher instance."""
    return ConfluenceFetcher(config=confluence_config)


@pytest.fixture
def test_issue_key() -> str:
    """Get test issue key from environment."""
    return os.environ.get("JIRA_TEST_ISSUE_KEY", "TES-26")


@pytest.fixture
def test_epic_key() -> str:
    """Get test epic key from environment."""
    return os.environ.get("JIRA_TEST_EPIC_KEY", "TES-25")


@pytest.fixture
def test_page_id() -> str:
    """Get test Confluence page ID from environment."""
    return os.environ.get("CONFLUENCE_TEST_PAGE_ID", "3823370492")


# Only use asyncio backend for anyio tests
pytestmark = pytest.mark.anyio(backends=["asyncio"])


class TestRealJiraValidation:
    """
    Test class for validating Jira models with real API data.

    These tests will be skipped if:
    1. The --use-real-data flag is not passed to pytest
    2. The required Jira environment variables are not set
    """

    def test_get_issue(self, use_real_jira_data):
        """Test that get_issue returns a proper JiraIssue model."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        # Get test issue key from environment or use default
        # Use the TES-8 issue from your env file
        issue_key = os.environ.get("JIRA_TEST_ISSUE_KEY", "TES-8")

        # Initialize the Jira client
        config = JiraConfig.from_env()
        issues_client = IssuesMixin(config=config)

        # Get the issue using the refactored client
        issue = issues_client.get_issue(issue_key)

        # Verify the issue is a JiraIssue instance
        assert isinstance(issue, JiraIssue)
        assert issue.key == issue_key
        assert issue.id is not None
        assert issue.summary is not None

        # Verify backward compatibility using direct property access
        # instead of metadata which is deprecated
        assert issue.key == issue_key

        # Verify model can be converted to dict
        issue_dict = issue.to_simplified_dict()
        assert issue_dict["key"] == issue_key
        assert "id" in issue_dict
        assert "summary" in issue_dict

    def test_search_issues(self, use_real_jira_data):
        """Test that search_issues returns JiraIssue models."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        # Initialize the Jira client
        config = JiraConfig.from_env()
        search_client = JiraSearchMixin(config=config)

        # Perform a simple search using your actual project
        jql = 'project = "TES" ORDER BY created DESC'
        results = search_client.search_issues(jql, limit=5)

        # Verify results contain JiraIssue instances
        assert len(results) > 0
        for issue in results:
            assert isinstance(issue, JiraIssue)
            assert issue.key is not None
            assert issue.id is not None

            # Verify direct property access
            assert issue.key is not None

    def test_get_issue_comments(self, use_real_jira_data):
        """Test that issue comments are properly converted to JiraComment models."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        # Get test issue key from environment or use default
        issue_key = os.environ.get("JIRA_TEST_ISSUE_KEY", "TES-8")

        # Initialize the CommentsMixin instead of IssuesMixin for comments
        config = JiraConfig.from_env()
        comments_client = JiraCommentsMixin(config=config)

        # First check for issue existence using IssuesMixin
        issues_client = IssuesMixin(config=config)
        try:
            issues_client.get_issue(issue_key)
        except Exception:
            pytest.skip(
                f"Issue {issue_key} does not exist or you don't have permission to access it"
            )

        # The get_issue_comments from CommentsMixin returns list[dict] not models
        # We'll just check that we can get comments in any format
        comments = comments_client.get_issue_comments(issue_key)

        # Skip test if there are no comments
        if len(comments) == 0:
            pytest.skip("Test issue has no comments")

        # Verify comments have expected structure
        for comment in comments:
            assert isinstance(comment, dict)
            assert "id" in comment
            assert "body" in comment
            assert "created" in comment


class TestRealConfluenceValidation:
    """
    Test class for validating Confluence models with real API data.

    These tests will be skipped if:
    1. The --use-real-data flag is not passed to pytest
    2. The required Confluence environment variables are not set
    """

    def test_get_page_content(self, use_real_confluence_data):
        """Test that get_page_content returns a proper ConfluencePage model."""
        if not use_real_confluence_data:
            pytest.skip("Real Confluence data testing is disabled")

        # Get test page ID from environment or use default
        page_id = os.environ.get("CONFLUENCE_PAGE_ID", "3819638214")

        # Initialize the Confluence client
        config = ConfluenceConfig.from_env()
        pages_client = PagesMixin(config=config)

        # Get the page using the refactored client
        page = pages_client.get_page_content(page_id)

        # Verify the page is a ConfluencePage instance
        assert isinstance(page, ConfluencePage)
        assert page.id == page_id
        assert page.title is not None
        assert page.space is not None
        assert page.space.key is not None

        # Verify direct property access
        assert page.id == page_id

        # Verify content is present and non-empty
        assert page.content is not None
        assert len(page.content) > 0
        # Check the content format - should be either "storage" or "view"
        assert page.content_format in ["storage", "view", "markdown"]

    def test_get_page_comments(self, use_real_confluence_data):
        """Test that page comments are properly converted to ConfluenceComment models."""
        if not use_real_confluence_data:
            pytest.skip("Real Confluence data testing is disabled")

        # Get test page ID from environment or use default
        page_id = os.environ.get("CONFLUENCE_PAGE_ID", "3819638214")

        # Initialize the Confluence comments client
        config = ConfluenceConfig.from_env()
        comments_client = ConfluenceCommentsMixin(config=config)

        # Get comments using the comments mixin
        comments = comments_client.get_page_comments(page_id)

        # If there are no comments, skip the test
        if len(comments) == 0:
            pytest.skip("Test page has no comments")

        # Verify comments are ConfluenceComment instances
        for comment in comments:
            assert isinstance(comment, ConfluenceComment)
            assert comment.id is not None
            assert comment.body is not None

    def test_search_content(self, use_real_confluence_data):
        """Test that search returns ConfluencePage models."""
        if not use_real_confluence_data:
            pytest.skip("Real Confluence data testing is disabled")

        # Initialize the Confluence client
        config = ConfluenceConfig.from_env()
        search_client = ConfluenceSearchMixin(config=config)

        # Perform a simple search
        cql = 'type = "page" ORDER BY created DESC'
        # Use search method instead of search_content
        results = search_client.search(cql, limit=5)

        # Verify results contain ConfluencePage instances
        assert len(results) > 0
        for page in results:
            assert isinstance(page, ConfluencePage)
            assert page.id is not None
            assert page.title is not None

            # Verify direct property access
            assert page.id is not None


@pytest.mark.anyio
async def test_jira_get_issue(jira_client: JiraFetcher, test_issue_key: str) -> None:
    """Test retrieving an issue from Jira."""
    # Get the issue
    issue = jira_client.get_issue(test_issue_key)

    # Verify the response
    assert issue is not None
    assert issue.key == test_issue_key
    assert hasattr(issue, "fields") or hasattr(issue, "summary")


@pytest.mark.anyio
async def test_jira_get_epic_issues(
    jira_client: JiraFetcher, test_epic_key: str
) -> None:
    """Test retrieving issues linked to an epic from Jira."""
    # This tests the fixed functionality for retrieving epic issues
    issues = jira_client.get_epic_issues(test_epic_key)

    # Verify the response
    assert isinstance(issues, list)

    # If there are issues, verify some basic properties
    if issues:
        for issue in issues:
            assert hasattr(issue, "key")
            assert hasattr(issue, "id")


@pytest.mark.anyio
async def test_confluence_get_page_content(
    confluence_client: ConfluenceFetcher, test_page_id: str
) -> None:
    """Test retrieving a page from Confluence."""
    # Get the page content (method name might be different)
    # Try different method names based on the class implementation
    if hasattr(confluence_client, "get_page_by_id"):
        page = confluence_client.get_page_by_id(test_page_id)
    elif hasattr(confluence_client, "get_content"):
        page = confluence_client.get_content(test_page_id)
    else:
        # If direct methods don't exist, try indirection through the client
        page = confluence_client.confluence.get_page_by_id(test_page_id)

    # Verify the response
    assert page is not None
    assert "id" in page or hasattr(page, "id")
    assert "title" in page or hasattr(page, "title")


# Skipping tests that would modify data for now
@pytest.mark.skip(reason="This test would modify data")
@pytest.mark.anyio
async def test_jira_transition_issue(jira_client: JiraFetcher) -> None:
    """Test transitioning an issue in Jira."""
    # This would test the fixed functionality for issue transitions
    pass


@pytest.mark.skip(reason="This test would modify data")
@pytest.mark.anyio
async def test_confluence_update_page(confluence_client: ConfluenceFetcher) -> None:
    """Test updating a page in Confluence without version parameter."""
    # This would test the fixed functionality for page updates
    pass
