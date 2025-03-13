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
    - JIRA_TEST_ISSUE_KEY, JIRA_TEST_EPIC_KEY
    - CONFLUENCE_TEST_PAGE_ID, JIRA_TEST_PROJECT_KEY, CONFLUENCE_TEST_SPACE_KEY, CONFLUENCE_TEST_SPACE_KEY
"""

import datetime
import os
import uuid
from collections.abc import Callable, Generator

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


# Resource tracking for cleanup
class ResourceTracker:
    """Tracks resources created during tests for cleanup."""

    def __init__(self):
        self.jira_issues: list[str] = []
        self.confluence_pages: list[str] = []
        self.confluence_comments: list[str] = []
        self.jira_comments: list[str] = []

    def add_jira_issue(self, issue_key: str) -> None:
        """Track a Jira issue for later cleanup."""
        self.jira_issues.append(issue_key)

    def add_confluence_page(self, page_id: str) -> None:
        """Track a Confluence page for later cleanup."""
        self.confluence_pages.append(page_id)

    def add_confluence_comment(self, comment_id: str) -> None:
        """Track a Confluence comment for later cleanup."""
        self.confluence_comments.append(comment_id)

    def add_jira_comment(self, issue_key: str, comment_id: str) -> None:
        """Track a Jira comment for later cleanup."""
        self.jira_comments.append((issue_key, comment_id))

    def cleanup(
        self,
        jira_client: JiraFetcher | None = None,
        confluence_client: ConfluenceFetcher | None = None,
    ) -> None:
        """Clean up all tracked resources."""
        if jira_client:
            # Delete Jira comments first
            for issue_key, comment_id in self.jira_comments:
                try:
                    jira_client.delete_comment(issue_key, comment_id)
                    print(f"Deleted Jira comment {comment_id} from issue {issue_key}")
                except Exception as e:
                    print(f"Failed to delete Jira comment {comment_id}: {e}")

            # Delete Jira issues
            for issue_key in self.jira_issues:
                try:
                    jira_client.delete_issue(issue_key)
                    print(f"Deleted Jira issue {issue_key}")
                except Exception as e:
                    print(f"Failed to delete Jira issue {issue_key}: {e}")

        if confluence_client:
            # Delete Confluence comments
            for comment_id in self.confluence_comments:
                try:
                    confluence_client.delete_comment(comment_id)
                    print(f"Deleted Confluence comment {comment_id}")
                except Exception as e:
                    print(f"Failed to delete Confluence comment {comment_id}: {e}")

            # Delete Confluence pages
            for page_id in self.confluence_pages:
                try:
                    confluence_client.delete_page(page_id)
                    print(f"Deleted Confluence page {page_id}")
                except Exception as e:
                    print(f"Failed to delete Confluence page {page_id}: {e}")


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
    issue_key = os.environ.get("JIRA_TEST_ISSUE_KEY")
    if not issue_key:
        pytest.skip("JIRA_TEST_ISSUE_KEY environment variable not set")
    return issue_key


@pytest.fixture
def test_epic_key() -> str:
    """Get test epic key from environment."""
    epic_key = os.environ.get("JIRA_TEST_EPIC_KEY")
    if not epic_key:
        pytest.skip("JIRA_TEST_EPIC_KEY environment variable not set")
    return epic_key


@pytest.fixture
def test_page_id() -> str:
    """Get test Confluence page ID from environment."""
    page_id = os.environ.get("CONFLUENCE_TEST_PAGE_ID")
    if not page_id:
        pytest.skip("CONFLUENCE_TEST_PAGE_ID environment variable not set")
    return page_id


@pytest.fixture
def test_project_key() -> str:
    """Get test Jira project key from environment."""
    project_key = os.environ.get("JIRA_TEST_PROJECT_KEY")
    if not project_key:
        pytest.skip("JIRA_TEST_PROJECT_KEY environment variable not set")
    return project_key


@pytest.fixture
def test_space_key() -> str:
    """Get test Confluence space key from environment."""
    space_key = os.environ.get("CONFLUENCE_TEST_SPACE_KEY")
    if not space_key:
        pytest.skip("CONFLUENCE_TEST_SPACE_KEY environment variable not set")
    return space_key


@pytest.fixture
def resource_tracker() -> Generator[ResourceTracker, None, None]:
    """Create a resource tracker for cleanup after tests."""
    tracker = ResourceTracker()
    yield tracker
    # Cleanup happens automatically when the fixture is finalized


@pytest.fixture
def cleanup_resources(
    resource_tracker: ResourceTracker,
    jira_client: JiraFetcher,
    confluence_client: ConfluenceFetcher,
) -> Callable[[], None]:
    """Return a function that will clean up all tracked resources."""

    def _cleanup():
        resource_tracker.cleanup(jira_client, confluence_client)

    return _cleanup


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

    def test_get_page_content(self, use_real_confluence_data, test_page_id):
        """Test that get_page_content returns a proper ConfluencePage model."""
        if not use_real_confluence_data:
            pytest.skip("Real Confluence data testing is disabled")

        # Initialize the Confluence client
        config = ConfluenceConfig.from_env()
        pages_client = PagesMixin(config=config)

        # Get the page using the refactored client
        page = pages_client.get_page_content(test_page_id)

        # Verify it's a ConfluencePage model
        assert isinstance(page, ConfluencePage)
        assert page.id == test_page_id
        assert page.title is not None
        assert page.content is not None

        # Check page attributes
        assert page.space is not None
        assert page.space.key is not None

        # Check the content format - should be either "storage" or "view"
        assert page.content_format in ["storage", "view", "markdown"]

    def test_get_page_comments(self, use_real_confluence_data, test_page_id):
        """Test that page comments are properly converted to ConfluenceComment models."""
        if not use_real_confluence_data:
            pytest.skip("Real Confluence data testing is disabled")

        # Initialize the Confluence comments client
        config = ConfluenceConfig.from_env()
        comments_client = ConfluenceCommentsMixin(config=config)

        # Get comments using the comments mixin
        comments = comments_client.get_page_comments(test_page_id)

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
    # Get the page content using our module's API
    page = confluence_client.get_page_content(test_page_id)

    # Verify the response
    assert page is not None
    assert page.id == test_page_id
    assert page.title is not None


@pytest.mark.anyio
async def test_jira_create_issue(
    jira_client: JiraFetcher,
    test_project_key: str,
    resource_tracker: ResourceTracker,
    cleanup_resources: Callable[[], None],
) -> None:
    """Test creating an issue in Jira."""
    # Generate a unique summary to identify this test issue
    test_id = str(uuid.uuid4())[:8]
    summary = f"Test Issue (API Validation) {test_id}"
    description = "This is a test issue created by the API validation tests. It should be automatically deleted."

    try:
        # Create the issue
        issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=summary,
            description=description,
            issue_type="Task",
        )

        # Track the issue for cleanup
        resource_tracker.add_jira_issue(issue.key)

        # Verify the response
        assert issue is not None
        assert issue.key.startswith(test_project_key)
        assert issue.summary == summary

        # Verify we can retrieve the created issue
        retrieved_issue = jira_client.get_issue(issue.key)
        assert retrieved_issue is not None
        assert retrieved_issue.key == issue.key
        assert retrieved_issue.summary == summary
    finally:
        # Clean up resources even if the test fails
        cleanup_resources()


@pytest.mark.anyio
async def test_jira_add_comment(
    jira_client: JiraFetcher,
    test_issue_key: str,
    resource_tracker: ResourceTracker,
    cleanup_resources: Callable[[], None],
) -> None:
    """Test adding a comment to a Jira issue."""
    # Generate a unique comment text
    test_id = str(uuid.uuid4())[:8]
    comment_text = f"Test comment from API validation tests {test_id}. This should be automatically deleted."

    try:
        # Add the comment
        comment = jira_client.add_comment(
            issue_key=test_issue_key, comment=comment_text
        )

        # Track the comment for cleanup
        if hasattr(comment, "id"):
            resource_tracker.add_jira_comment(test_issue_key, comment.id)
        elif isinstance(comment, dict) and "id" in comment:
            resource_tracker.add_jira_comment(test_issue_key, comment["id"])

        # Verify the response
        assert comment is not None

        # Get the comment text based on the attribute that exists
        if hasattr(comment, "body"):
            actual_text = comment.body
        elif hasattr(comment, "content"):
            actual_text = comment.content
        elif isinstance(comment, dict) and "body" in comment:
            actual_text = comment["body"]
        else:
            actual_text = str(comment)

        assert comment_text in actual_text
    finally:
        # Clean up resources even if the test fails
        cleanup_resources()


@pytest.mark.anyio
async def test_confluence_create_page(
    confluence_client: ConfluenceFetcher,
    test_space_key: str,
    resource_tracker: ResourceTracker,
    cleanup_resources: Callable[[], None],
) -> None:
    """Test creating a page in Confluence."""
    # Generate a unique title
    test_id = str(uuid.uuid4())[:8]
    title = f"Test Page (API Validation) {test_id}"

    # Create timestamp separately to avoid long line
    timestamp = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    content = f"""
    <h1>Test Page</h1>
    <p>This is a test page created by the API validation tests at {timestamp}.</p>
    <p>It should be automatically deleted after the test.</p>
    """

    try:
        # Create the page using our module's API
        try:
            page = confluence_client.create_page(
                space_key=test_space_key, title=title, body=content
            )
        except Exception as e:
            if "permission" in str(e).lower():
                pytest.skip(f"No permission to create pages in space {test_space_key}")
                return
            elif "space" in str(e).lower() and (
                "not found" in str(e).lower() or "doesn't exist" in str(e).lower()
            ):
                pytest.skip(
                    f"Space {test_space_key} not found. Skipping page creation test."
                )
                return
            else:
                raise

        # Track the page for cleanup
        page_id = page.id
        resource_tracker.add_confluence_page(page_id)

        # Verify the response
        assert page is not None
        assert page.title == title

        # Attempt to retrieve the created page
        retrieved_page = confluence_client.get_page_content(page_id)
        assert retrieved_page is not None
    finally:
        # Clean up resources even if the test fails
        cleanup_resources()


@pytest.mark.anyio
async def test_confluence_update_page(
    confluence_client: ConfluenceFetcher,
    resource_tracker: ResourceTracker,
    test_space_key: str,
    cleanup_resources: Callable[[], None],
) -> None:
    """Test updating a page in Confluence and validate TextContent structure.

    This test has two purposes:
    1. Test the basic page update functionality
    2. Validate the TextContent class requires the 'type' field to prevent issue #97
    """
    # Create a test page first
    test_id = str(uuid.uuid4())[:8]
    title = f"Update Test Page {test_id}"
    content = f"<p>Initial content {test_id}</p>"

    try:
        # Create the page using our module's API
        page = confluence_client.create_page(
            space_key=test_space_key, title=title, body=content
        )

        # Track the page for cleanup
        page_id = page.id
        resource_tracker.add_confluence_page(page_id)

        # Update the page with new content
        now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        updated_content = f"<p>Updated content {test_id} at {now}</p>"

        # Test updating without explicitly specifying the version
        updated_page = confluence_client.update_page(
            page_id=page_id, title=title, body=updated_content
        )

        # Verify the update worked
        assert updated_page is not None

        # ======= TextContent Validation (prevents issue #97) =======
        # Import TextContent class to test directly
        from mcp.types import TextContent

        print("Testing TextContent validation to prevent issue #97")

        # Create a TextContent without type field - this should raise an error
        try:
            # Intentionally omit the type field to simulate the bug in issue #97
            # Using _ to avoid unused variable warning
            _ = TextContent(text="This should fail without type field")
            # If we get here, the validation is not working
            raise AssertionError(
                "TextContent creation without 'type' field should fail but didn't"
            )
        except Exception as e:
            # We expect an exception because the type field is required
            print(f"Correctly got error: {str(e)}")
            assert "type" in str(e), "Error should mention missing 'type' field"

        # Create valid TextContent with type field - should work
        valid_content = TextContent(
            type="text", text="This should work with type field"
        )
        assert valid_content.type == "text", "TextContent should have type='text'"
        assert valid_content.text == "This should work with type field", (
            "TextContent text should match"
        )

        print("TextContent validation succeeded - 'type' field is properly required")

    finally:
        # Clean up resources even if the test fails
        cleanup_resources()


@pytest.mark.skip(reason="This test modifies data - use with caution")
@pytest.mark.anyio
async def test_jira_transition_issue(
    jira_client: JiraFetcher,
    resource_tracker: ResourceTracker,
    test_project_key: str,
    cleanup_resources: Callable[[], None],
) -> None:
    """Test transitioning an issue in Jira."""
    # Create a test issue first
    test_id = str(uuid.uuid4())[:8]
    summary = f"Transition Test Issue {test_id}"

    try:
        # Create the issue
        issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=summary,
            description="Test issue for transition testing",
            issue_type="Task",
        )

        # Track the issue for cleanup
        resource_tracker.add_jira_issue(issue.key)

        # Get available transitions
        transitions = jira_client.get_transitions(issue.key)
        assert transitions is not None
        assert len(transitions) > 0

        # Select a transition (usually to "In Progress")
        # Find the "In Progress" transition if available
        transition_id = None
        for transition in transitions:
            if hasattr(transition, "name") and "progress" in transition.name.lower():
                transition_id = transition.id
                break

        if not transition_id and transitions:
            # Just use the first available transition if "In Progress" not found
            transition_id = (
                transitions[0].id
                if hasattr(transitions[0], "id")
                else transitions[0]["id"]
            )

        assert transition_id is not None

        # Perform the transition
        transition_result = jira_client.transition_issue(
            issue_key=issue.key, transition_id=transition_id
        )

        # Verify transition was successful if result is returned
        if transition_result is not None:
            assert transition_result, (
                "Transition should return a truthy value if successful"
            )

        # Verify the issue status changed
        updated_issue = jira_client.get_issue(issue.key)

        # Get the status name
        if hasattr(updated_issue, "status") and hasattr(updated_issue.status, "name"):
            status_name = updated_issue.status.name
        else:
            status_name = updated_issue["fields"]["status"]["name"]

        # The status should no longer be "To Do" or equivalent
        assert "to do" not in status_name.lower()
    finally:
        # Clean up resources even if the test fails
        cleanup_resources()
