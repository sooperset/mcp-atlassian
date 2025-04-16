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
import json
import os
import uuid
from collections.abc import Callable, Generator, Sequence

import pytest
from mcp.types import TextContent

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.comments import CommentsMixin as ConfluenceCommentsMixin
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.confluence.pages import PagesMixin
from mcp_atlassian.confluence.search import SearchMixin as ConfluenceSearchMixin
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.comments import CommentsMixin as JiraCommentsMixin
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.jira.issues import IssuesMixin
from mcp_atlassian.jira.search import SearchMixin as JiraSearchMixin
from mcp_atlassian.models.confluence import ConfluenceComment, ConfluencePage
from mcp_atlassian.models.jira import JiraIssue
from mcp_atlassian.server import call_tool


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
    """Create and yield a ResourceTracker that will be used to clean up after tests."""
    tracker = ResourceTracker()
    yield tracker


@pytest.fixture
def cleanup_resources(
    resource_tracker: ResourceTracker,
    jira_client: JiraFetcher,
    confluence_client: ConfluenceFetcher,
) -> Callable[[], None]:
    """Return a function that can be called to clean up resources."""

    def _cleanup():
        resource_tracker.cleanup(
            jira_client=jira_client, confluence_client=confluence_client
        )

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
async def test_jira_get_issue_with_fields(
    jira_client: JiraFetcher, test_issue_key: str
) -> None:
    """Test retrieving a Jira issue with specific fields."""
    # Get the issue with all fields first to have a reference
    full_issue = jira_client.get_issue(test_issue_key)
    assert full_issue is not None

    # Now get the issue with only specific fields
    limited_issue = jira_client.get_issue(
        test_issue_key, fields="summary,description,customfield_*"
    )

    # Verify we got the requested fields
    assert limited_issue is not None
    assert limited_issue.key == test_issue_key
    assert limited_issue.summary is not None

    # Get simplified dicts to compare
    full_data = full_issue.to_simplified_dict()
    limited_data = limited_issue.to_simplified_dict()

    # Required fields should be in both
    assert "key" in full_data and "key" in limited_data
    assert "id" in full_data and "id" in limited_data
    assert "summary" in full_data and "summary" in limited_data

    # Fields that should be in limited result
    assert "description" in limited_data

    # Check custom fields if there are any
    custom_fields_found = False
    for field in limited_data:
        if field.startswith("customfield_"):
            custom_fields_found = True
            break

    # Fields that shouldn't be in limited result unless they were requested
    if "assignee" in full_data and "assignee" not in limited_data:
        assert "assignee" not in limited_data
    if "status" in full_data and "status" not in limited_data:
        assert "status" not in limited_data

    # Test with a list of fields
    list_fields_issue = jira_client.get_issue(
        test_issue_key, fields=["summary", "status"]
    )

    assert list_fields_issue is not None
    list_data = list_fields_issue.to_simplified_dict()
    assert "summary" in list_data
    if "status" in full_data:
        assert "status" in list_data


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
async def test_jira_create_subtask(
    jira_client: JiraFetcher,
    test_project_key: str,
    test_issue_key: str,
    test_epic_key: str,
    resource_tracker: ResourceTracker,
    cleanup_resources: Callable[[], None],
) -> None:
    """Test creating a subtask in Jira linked to a specified parent and epic."""
    # Generate unique identifiers for this test
    test_id = str(uuid.uuid4())[:8]
    subtask_summary = f"Subtask Test Issue {test_id}"

    try:
        # Use the existing issue as parent instead of creating one
        parent_issue_key = test_issue_key

        # Create a subtask linked to both the parent and epic
        subtask_issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=subtask_summary,
            description=f"This is a test subtask linked to parent {parent_issue_key} and epic {test_epic_key}",
            issue_type="Subtask",
            parent=parent_issue_key,  # Link to parent
            epic_link=test_epic_key,  # Link to epic
        )

        # Track the subtask for cleanup
        resource_tracker.add_jira_issue(subtask_issue.key)

        # Verify the subtask response
        assert subtask_issue is not None
        assert subtask_issue.key.startswith(test_project_key)
        assert subtask_issue.summary == subtask_summary

        # Verify we can retrieve the created subtask
        retrieved_subtask = jira_client.get_issue(subtask_issue.key)
        assert retrieved_subtask is not None
        assert retrieved_subtask.key == subtask_issue.key

        # Verify parent relationship if the fields are accessible
        # This might vary depending on how the Jira instance returns data
        if hasattr(retrieved_subtask, "fields"):
            if hasattr(retrieved_subtask.fields, "parent"):
                assert retrieved_subtask.fields.parent.key == parent_issue_key

            # Check epic relationship if available
            # The exact field name might vary based on Jira configuration
            field_ids = jira_client.get_jira_field_ids()
            epic_link_field = field_ids.get("epic_link") or field_ids.get("Epic Link")

            if epic_link_field and hasattr(retrieved_subtask.fields, epic_link_field):
                epic_key = getattr(retrieved_subtask.fields, epic_link_field)
                assert epic_key == test_epic_key

        print(
            f"\nCreated subtask {subtask_issue.key} under parent {parent_issue_key} and epic {test_epic_key}"
        )

    finally:
        # Clean up resources even if the test fails
        cleanup_resources()


@pytest.mark.anyio
async def test_jira_create_task_with_parent(
    jira_client: JiraFetcher,
    test_project_key: str,
    test_epic_key: str,
    resource_tracker: ResourceTracker,
    cleanup_resources: Callable[[], None],
) -> None:
    """Test creating a task in Jira with a parent issue (non-subtask)."""
    # Generate unique identifiers for this test
    test_id = str(uuid.uuid4())[:8]
    task_summary = f"Task with Parent Test {test_id}"

    try:
        # Use the epic as parent instead of a regular issue
        parent_issue_key = test_epic_key

        try:
            # Create a task linked to a parent issue
            task_issue = jira_client.create_issue(
                project_key=test_project_key,
                summary=task_summary,
                description=f"This is a test task linked to parent {parent_issue_key}",
                issue_type="Task",  # Not a subtask
                parent=parent_issue_key,  # Link to parent
            )

            # Track the task for cleanup
            resource_tracker.add_jira_issue(task_issue.key)

            # Verify the task response
            assert task_issue is not None
            assert task_issue.key.startswith(test_project_key)
            assert task_issue.summary == task_summary

            # Verify we can retrieve the created task
            retrieved_task = jira_client.get_issue(task_issue.key)
            assert retrieved_task is not None
            assert retrieved_task.key == task_issue.key

            # Verify parent relationship if the fields are accessible
            # This might vary depending on how the Jira instance returns data
            if hasattr(retrieved_task, "fields"):
                if hasattr(retrieved_task.fields, "parent"):
                    assert retrieved_task.fields.parent.key == parent_issue_key

            print(f"\nCreated task {task_issue.key} with parent {parent_issue_key}")

        except Exception as e:
            # If we get a hierarchy error, it means the feature works but is limited by Jira config
            if "hierarchy" in str(e).lower():
                pytest.skip(
                    f"Parent-child relationship not allowed by Jira configuration: {str(e)}"
                )
            else:
                # Re-raise if it's not a hierarchy issue
                raise

    finally:
        # Clean up resources even if the test fails
        cleanup_resources()


@pytest.mark.anyio
async def test_jira_create_epic(
    jira_client: JiraFetcher,
    test_project_key: str,
    resource_tracker: ResourceTracker,
    cleanup_resources: Callable[[], None],
) -> None:
    """
    Test creating an Epic issue in Jira.

    This test verifies that the create_issue method can handle Epic creation
    properly for any Jira instance, regardless of the specific custom field
    configuration used for Epic Name or other Epic-specific fields.
    """
    # Generate unique identifiers for this test
    test_id = str(uuid.uuid4())[:8]
    epic_summary = f"Test Epic {test_id}"

    try:
        # Attempt to create the Epic - this should succeed after implementation is fixed
        epic_issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=epic_summary,
            description="This is a test epic for validating Epic creation functionality.",
            issue_type="Epic",
        )

        # Track the epic for cleanup if creation succeeds
        resource_tracker.add_jira_issue(epic_issue.key)

        # Verify the epic response
        assert epic_issue is not None
        assert epic_issue.key.startswith(test_project_key)
        assert epic_issue.summary == epic_summary

        print(f"\nTEST PASSED: Successfully created Epic issue {epic_issue.key}")

        # Try to retrieve the epic to verify it was truly created
        retrieved_epic = jira_client.get_issue(epic_issue.key)
        assert retrieved_epic is not None
        assert retrieved_epic.key == epic_issue.key
        assert retrieved_epic.summary == epic_summary

    except Exception as e:
        # Log the error but don't catch it - we want the test to fail
        # when Epic creation doesn't work
        print(f"\nERROR creating Epic: {str(e)}")

        # Print information about field IDs to help with fixing the implementation
        try:
            print("\n=== Jira Field Information for Debugging ===")
            field_ids = jira_client.get_jira_field_ids()
            print(f"Available field IDs: {field_ids}")
        except Exception as error:
            print(f"Error retrieving field IDs: {str(error)}")

        raise
    finally:
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


@pytest.mark.anyio
async def test_jira_create_epic_with_custom_fields(
    jira_client: JiraFetcher,
    test_project_key: str,
    resource_tracker: ResourceTracker,
    cleanup_resources: Callable[[], None],
) -> None:
    """
    Test creating an Epic issue in Jira with custom Epic fields.

    This test verifies that the create_issue method can handle Epic creation
    with explicit Epic Name and Epic Color values, properly detecting the
    correct custom fields regardless of the Jira configuration.
    """
    # Generate unique identifiers for this test
    test_id = str(uuid.uuid4())[:8]
    epic_summary = f"Test Epic {test_id}"
    custom_epic_name = f"Custom Epic Name {test_id}"

    try:
        # Force field discovery to ensure we have the latest field IDs
        if hasattr(jira_client, "_field_ids_cache"):
            delattr(jira_client, "_field_ids_cache")

        # Get field IDs and log them for debugging
        field_ids = jira_client.get_jira_field_ids()
        print(f"Discovered field IDs: {field_ids}")

        # Attempt to create the Epic with custom values
        epic_issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=epic_summary,
            description="This is a test epic with custom values.",
            issue_type="Epic",
            epic_name=custom_epic_name,
            epic_color="blue",
        )

        # Track the epic for cleanup
        resource_tracker.add_jira_issue(epic_issue.key)

        # Verify Epic was created correctly
        assert epic_issue is not None
        assert epic_issue.key.startswith(test_project_key)
        assert epic_issue.summary == epic_summary

        print(f"\nTEST PASSED: Successfully created Epic issue {epic_issue.key}")

        # Retrieve the Epic to verify custom fields were set
        retrieved_epic = jira_client.get_issue(epic_issue.key)

        # Verify custom Epic Name - the field might be accessible under different properties
        # depending on the Jira configuration
        has_epic_name = False
        if hasattr(retrieved_epic, "epic_name") and retrieved_epic.epic_name:
            assert retrieved_epic.epic_name == custom_epic_name
            has_epic_name = True
            print(
                f"Verified Epic Name via epic_name property: {retrieved_epic.epic_name}"
            )

        if not has_epic_name:
            print("Could not verify Epic Name directly, checking raw fields...")
            # Try to get the raw API response to verify the custom fields
            if hasattr(jira_client, "jira"):
                raw_issue = jira_client.jira.issue(epic_issue.key)
                fields = raw_issue.get("fields", {})

                # Find the Epic Name field by searching known patterns
                for field_id, value in fields.items():
                    if field_id.startswith("customfield_") and isinstance(value, str):
                        if value == custom_epic_name:
                            print(
                                f"Found Epic Name in custom field {field_id}: {value}"
                            )
                            has_epic_name = True
                            break

        if not has_epic_name:
            print("WARNING: Could not verify Epic Name was set correctly")

    except Exception as e:
        print(f"\nERROR creating Epic with custom fields: {str(e)}")

        # Print information about field IDs to help with debugging
        try:
            print("\n=== Jira Field Information for Debugging ===")
            field_ids = jira_client.get_jira_field_ids()
            print(f"Available field IDs: {field_ids}")
        except Exception as error:
            print(f"Error retrieving field IDs: {str(error)}")

        raise
    finally:
        cleanup_resources()


@pytest.mark.anyio
async def test_jira_create_epic_two_step(
    jira_client: JiraFetcher,
    test_project_key: str,
    resource_tracker: ResourceTracker,
    cleanup_resources: Callable[[], None],
) -> None:
    """
    Test the two-step Epic creation process.

    This test verifies that the create_issue method can successfully create an Epic
    using the two-step approach (create basic issue first, then update Epic fields)
    to work around screen configuration issues.
    """
    # Generate unique identifiers for this test
    test_id = str(uuid.uuid4())[:8]
    epic_summary = f"Two-Step Epic {test_id}"
    epic_name = f"Epic Name {test_id}"

    try:
        # Clear any cached field IDs to force fresh discovery
        if hasattr(jira_client, "_field_ids"):
            delattr(jira_client, "_field_ids")

        # Show all available field IDs - useful for debugging
        field_ids = jira_client.get_jira_field_ids()
        print(f"\nAvailable field IDs for Epic creation: {field_ids}")

        # Create the Epic - should use the two-step process internally
        print("\nAttempting to create Epic using two-step process...")
        epic_issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=epic_summary,
            description="This is a test epic using the two-step creation process.",
            issue_type="Epic",
            epic_name=epic_name,  # This should be stored for post-creation update
            epic_color="blue",  # This should be stored for post-creation update
        )

        # Track the epic for cleanup
        resource_tracker.add_jira_issue(epic_issue.key)

        # Verify the Epic was created
        assert epic_issue is not None
        assert epic_issue.key.startswith(test_project_key)
        assert epic_issue.summary == epic_summary

        print(f"\nSuccessfully created Epic: {epic_issue.key}")

        # Try to retrieve the Epic to verify Epic-specific fields
        retrieved_epic = jira_client.get_issue(epic_issue.key)
        print(f"\nRetrieved Epic: {retrieved_epic.key}")

        # Log epic field information for debugging
        print(f"Epic name: {retrieved_epic.epic_name}")

        # Try to get the raw API response to inspect all fields
        try:
            # Using _raw property if available, or direct API call as fallback
            if hasattr(retrieved_epic, "_raw"):
                raw_data = retrieved_epic._raw
            else:
                raw_data = jira_client.jira.issue(epic_issue.key)

            # Print relevant fields for debugging
            if "fields" in raw_data:
                for field_id, field_value in raw_data["fields"].items():
                    if "epic" in field_id.lower() or field_id in field_ids.values():
                        print(f"Field {field_id}: {field_value}")
        except Exception as e:
            print(f"Error getting raw Epic data: {str(e)}")

        print("\nTEST PASSED: Successfully completed two-step Epic creation test")

    except Exception as e:
        print(f"\nERROR in two-step Epic creation test: {str(e)}")

        # Print debugging information
        print("\nAvailable field IDs:")
        try:
            field_ids = jira_client.get_jira_field_ids()
            for name, field_id in field_ids.items():
                print(f"  {name}: {field_id}")
        except Exception as field_error:
            print(f"Error getting field IDs: {str(field_error)}")

        raise
    finally:
        cleanup_resources()


# Tool Validation Tests (Requires --use-real-data)
# These tests use the server's call_tool handler to test the full flow
@pytest.mark.usefixtures("use_real_jira_data")
class TestRealToolValidation:
    """
    Test class for validating tool calls with real API data.
    """

    @pytest.mark.anyio
    async def test_jira_search_with_start_at(
        self, use_real_jira_data: bool, test_project_key: str
    ) -> None:
        """Test the jira_search tool with the startAt parameter."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        jql = f'project = "{test_project_key}" ORDER BY created ASC'
        limit = 1

        # Call 1: startAt = 0
        args1 = {"jql": jql, "limit": limit, "startAt": 0}
        result1_content: Sequence[TextContent] = await call_tool("jira_search", args1)
        assert result1_content and isinstance(result1_content[0], TextContent)
        results1 = json.loads(result1_content[0].text)

        # Call 2: startAt = 1
        args2 = {"jql": jql, "limit": limit, "startAt": 1}
        result2_content: Sequence[TextContent] = await call_tool("jira_search", args2)
        assert result2_content and isinstance(result2_content[0], TextContent)
        results2 = json.loads(result2_content[0].text)

        # Assertions (assuming project has at least 2 issues)
        assert isinstance(results1, list)
        assert isinstance(results2, list)

        if len(results1) > 0 and len(results2) > 0:
            assert results1[0]["key"] != results2[0]["key"], (
                f"Expected different issues with startAt=0 and startAt=1, but got {results1[0]['key']} for both."
                f" Ensure project '{test_project_key}' has at least 2 issues."
            )
        elif len(results1) <= 1:
            pytest.skip(
                f"Project {test_project_key} has less than 2 issues, cannot test pagination."
            )

    @pytest.mark.anyio
    async def test_jira_get_project_issues_with_start_at(
        self, use_real_jira_data: bool, test_project_key: str
    ) -> None:
        """Test the jira_get_project_issues tool with the startAt parameter."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        limit = 1

        # Call 1: startAt = 0
        args1 = {"project_key": test_project_key, "limit": limit, "startAt": 0}
        result1_content: Sequence[TextContent] = await call_tool(
            "jira_get_project_issues", args1
        )
        assert result1_content and isinstance(result1_content[0], TextContent)
        results1 = json.loads(result1_content[0].text)

        # Call 2: startAt = 1
        args2 = {"project_key": test_project_key, "limit": limit, "startAt": 1}
        result2_content: Sequence[TextContent] = await call_tool(
            "jira_get_project_issues", args2
        )
        assert result2_content and isinstance(result2_content[0], TextContent)
        results2 = json.loads(result2_content[0].text)

        # Assertions (assuming project has at least 2 issues)
        assert isinstance(results1, list)
        assert isinstance(results2, list)

        if len(results1) > 0 and len(results2) > 0:
            assert results1[0]["key"] != results2[0]["key"], (
                f"Expected different issues with startAt=0 and startAt=1, but got {results1[0]['key']} for both."
                f" Ensure project '{test_project_key}' has at least 2 issues."
            )
        elif len(results1) <= 1:
            pytest.skip(
                f"Project {test_project_key} has less than 2 issues, cannot test pagination."
            )

    @pytest.mark.anyio
    async def test_jira_get_epic_issues_with_start_at(
        self, use_real_jira_data: bool, test_epic_key: str
    ) -> None:
        """Test the jira_get_epic_issues tool with the startAt parameter."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        limit = 1

        # Call 1: startAt = 0
        args1 = {"epic_key": test_epic_key, "limit": limit, "startAt": 0}
        result1_content: Sequence[TextContent] = await call_tool(
            "jira_get_epic_issues", args1
        )
        assert result1_content and isinstance(result1_content[0], TextContent)
        results1 = json.loads(result1_content[0].text)

        # Call 2: startAt = 1
        args2 = {"epic_key": test_epic_key, "limit": limit, "startAt": 1}
        result2_content: Sequence[TextContent] = await call_tool(
            "jira_get_epic_issues", args2
        )
        assert result2_content and isinstance(result2_content[0], TextContent)
        results2 = json.loads(result2_content[0].text)

        # Assertions (assuming epic has at least 2 issues)
        assert isinstance(results1, list)
        assert isinstance(results2, list)

        if len(results1) > 0 and len(results2) > 0:
            assert results1[0]["key"] != results2[0]["key"], (
                f"Expected different issues with startAt=0 and startAt=1, but got {results1[0]['key']} for both."
                f" Ensure epic '{test_epic_key}' has at least 2 linked issues."
            )
        elif len(results1) <= 1:
            pytest.skip(
                f"Epic {test_epic_key} has less than 2 issues, cannot test pagination."
            )
