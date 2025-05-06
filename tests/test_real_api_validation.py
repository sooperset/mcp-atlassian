"""
Test file for validating the refactored FastMCP tools with real API data.

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
from fastmcp import Client
from fastmcp.client import FastMCPTransport
from mcp.types import TextContent

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.comments import CommentsMixin as ConfluenceCommentsMixin
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.confluence.labels import LabelsMixin as ConfluenceLabelsMixin
from mcp_atlassian.confluence.pages import PagesMixin
from mcp_atlassian.confluence.search import SearchMixin as ConfluenceSearchMixin
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.jira.links import LinksMixin
from mcp_atlassian.models.confluence import (
    ConfluenceComment,
    ConfluenceLabel,
    ConfluencePage,
)
from mcp_atlassian.models.jira import JiraIssueLinkType
from mcp_atlassian.servers import main_mcp


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
            for issue_key, comment_id in self.jira_comments:
                try:
                    jira_client.delete_comment(issue_key, comment_id)
                    print(f"Deleted Jira comment {comment_id} from issue {issue_key}")
                except Exception as e:
                    print(f"Failed to delete Jira comment {comment_id}: {e}")

            for issue_key in self.jira_issues:
                try:
                    jira_client.delete_issue(issue_key)
                    print(f"Deleted Jira issue {issue_key}")
                except Exception as e:
                    print(f"Failed to delete Jira issue {issue_key}: {e}")

        if confluence_client:
            for comment_id in self.confluence_comments:
                try:
                    confluence_client.delete_comment(comment_id)
                    print(f"Deleted Confluence comment {comment_id}")
                except Exception as e:
                    print(f"Failed to delete Confluence comment {comment_id}: {e}")

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
def test_board_id() -> str:
    """Get test Jira board ID from environment."""
    board_id = os.environ.get("JIRA_TEST_BOARD_ID")
    if not board_id:
        pytest.skip("JIRA_TEST_BOARD_ID environment variable not set")
    return board_id


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


@pytest.fixture(scope="class")
async def api_validation_client():
    """Provides a FastMCP client connected to the main server for tool calls."""
    transport = FastMCPTransport(main_mcp)
    client = Client(transport=transport)
    async with client as connected_client:
        yield connected_client


async def call_tool(
    client: Client, tool_name: str, arguments: dict
) -> list[TextContent]:
    """Helper function to call tools via the client."""
    return await client.call_tool(tool_name, arguments)


class TestRealJiraValidation:
    """
    Test class for validating Jira models with real API data.

    These tests will be skipped if:
    1. The --use-real-data flag is not passed to pytest
    2. The required Jira environment variables are not set
    """

    @pytest.mark.anyio
    async def test_get_issue(self, use_real_jira_data, api_validation_client):
        """Test that get_issue returns a proper JiraIssue model."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        issue_key = os.environ.get("JIRA_TEST_ISSUE_KEY", "TES-143")

        result_content = await call_tool(
            api_validation_client, "jira_get_issue", {"issue_key": issue_key}
        )

        assert result_content and isinstance(result_content[0], TextContent)
        issue_data = json.loads(result_content[0].text)

        assert isinstance(issue_data, dict)
        assert issue_data.get("key") == issue_key
        assert "id" in issue_data
        assert "summary" in issue_data

    @pytest.mark.anyio
    async def test_search_issues(self, use_real_jira_data, api_validation_client):
        """Test that search_issues returns JiraIssue models."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        jql = 'project = "TES" ORDER BY created DESC'
        result_content = await call_tool(
            api_validation_client, "jira_search", {"jql": jql, "limit": 5}
        )

        assert result_content and isinstance(result_content[0], TextContent)
        search_data = json.loads(result_content[0].text)

        assert isinstance(search_data, dict)
        assert "issues" in search_data
        assert isinstance(search_data["issues"], list)
        assert len(search_data["issues"]) > 0

        for issue_dict in search_data["issues"]:
            assert isinstance(issue_dict, dict)
            assert "key" in issue_dict
            assert "id" in issue_dict
            assert "summary" in issue_dict

    @pytest.mark.anyio
    async def test_get_issue_comments(self, use_real_jira_data, api_validation_client):
        """Test that issue comments are properly converted to JiraComment models."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        issue_key = os.environ.get("JIRA_TEST_ISSUE_KEY", "TES-143")

        result_content = await call_tool(
            api_validation_client,
            "jira_get_issue",
            {"issue_key": issue_key, "fields": "comment", "comment_limit": 5},
        )
        issue_data = json.loads(result_content[0].text)

        for comment in issue_data["comments"]:
            assert isinstance(comment, dict)
            assert "body" in comment or "author" in comment


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

        config = ConfluenceConfig.from_env()
        pages_client = PagesMixin(config=config)

        page = pages_client.get_page_content(test_page_id)

        assert isinstance(page, ConfluencePage)
        assert page.id == test_page_id
        assert page.title is not None
        assert page.content is not None

        assert page.space is not None
        assert page.space.key is not None

        assert page.content_format in ["storage", "view", "markdown"]

    def test_get_page_comments(self, use_real_confluence_data, test_page_id):
        """Test that page comments are properly converted to ConfluenceComment models."""
        if not use_real_confluence_data:
            pytest.skip("Real Confluence data testing is disabled")

        config = ConfluenceConfig.from_env()
        comments_client = ConfluenceCommentsMixin(config=config)

        comments = comments_client.get_page_comments(test_page_id)

        if len(comments) == 0:
            pytest.skip("Test page has no comments")

        for comment in comments:
            assert isinstance(comment, ConfluenceComment)
            assert comment.id is not None
            assert comment.body is not None

    def test_get_page_labels(self, use_real_confluence_data, test_page_id):
        """Test that page labels are properly converted to ConfluenceLabel models."""
        if not use_real_confluence_data:
            pytest.skip("Real Confluence data testing is disabled")

        config = ConfluenceConfig.from_env()
        labels_client = ConfluenceLabelsMixin(config=config)

        labels = labels_client.get_page_labels(test_page_id)

        if len(labels) == 0:
            pytest.skip("Test page has no labels")

        for label in labels:
            assert isinstance(label, ConfluenceLabel)
            assert label.id is not None
            assert label.name is not None

    def test_search_content(self, use_real_confluence_data):
        """Test that search returns ConfluencePage models."""
        if not use_real_confluence_data:
            pytest.skip("Real Confluence data testing is disabled")

        config = ConfluenceConfig.from_env()
        search_client = ConfluenceSearchMixin(config=config)

        cql = 'type = "page" ORDER BY created DESC'
        results = search_client.search(cql, limit=5)

        assert len(results) > 0
        for page in results:
            assert isinstance(page, ConfluencePage)
            assert page.id is not None
            assert page.title is not None


@pytest.mark.anyio
async def test_jira_get_issue(jira_client: JiraFetcher, test_issue_key: str) -> None:
    """Test retrieving an issue from Jira."""
    issue = jira_client.get_issue(test_issue_key)

    assert issue is not None
    assert issue.key == test_issue_key
    assert hasattr(issue, "fields") or hasattr(issue, "summary")


@pytest.mark.anyio
async def test_jira_get_issue_with_fields(
    jira_client: JiraFetcher, test_issue_key: str
) -> None:
    """Test retrieving a Jira issue with specific fields."""
    full_issue = jira_client.get_issue(test_issue_key)
    assert full_issue is not None

    limited_issue = jira_client.get_issue(
        test_issue_key, fields="summary,description,customfield_*"
    )

    assert limited_issue is not None
    assert limited_issue.key == test_issue_key
    assert limited_issue.summary is not None

    full_data = full_issue.to_simplified_dict()
    limited_data = limited_issue.to_simplified_dict()

    assert "key" in full_data and "key" in limited_data
    assert "id" in full_data and "id" in limited_data
    assert "summary" in full_data and "summary" in limited_data

    assert "description" in limited_data

    custom_fields_found = False
    for field in limited_data:
        if field.startswith("customfield_"):
            custom_fields_found = True
            break

    if "assignee" in full_data and "assignee" not in limited_data:
        assert "assignee" not in limited_data
    if "status" in full_data and "status" not in limited_data:
        assert "status" not in limited_data

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
    issues = jira_client.get_epic_issues(test_epic_key)

    assert isinstance(issues, list)

    if issues:
        for issue in issues:
            assert hasattr(issue, "key")
            assert hasattr(issue, "id")


@pytest.mark.anyio
async def test_confluence_get_page_content(
    confluence_client: ConfluenceFetcher, test_page_id: str
) -> None:
    """Test retrieving a page from Confluence."""
    page = confluence_client.get_page_content(test_page_id)

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
    test_id = str(uuid.uuid4())[:8]
    summary = f"Test Issue (API Validation) {test_id}"
    description = "This is a test issue created by the API validation tests. It should be automatically deleted."

    try:
        issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=summary,
            description=description,
            issue_type="Task",
        )

        resource_tracker.add_jira_issue(issue.key)

        assert issue is not None
        assert issue.key.startswith(test_project_key)
        assert issue.summary == summary

        retrieved_issue = jira_client.get_issue(issue.key)
        assert retrieved_issue is not None
        assert retrieved_issue.key == issue.key
        assert retrieved_issue.summary == summary
    finally:
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
    test_id = str(uuid.uuid4())[:8]
    subtask_summary = f"Subtask Test Issue {test_id}"

    try:
        parent_issue_key = test_issue_key

        subtask_issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=subtask_summary,
            description=f"This is a test subtask linked to parent {parent_issue_key} and epic {test_epic_key}",
            issue_type="Subtask",
            parent=parent_issue_key,
            epic_link=test_epic_key,
        )

        resource_tracker.add_jira_issue(subtask_issue.key)

        assert subtask_issue is not None
        assert subtask_issue.key.startswith(test_project_key)
        assert subtask_issue.summary == subtask_summary

        retrieved_subtask = jira_client.get_issue(subtask_issue.key)
        assert retrieved_subtask is not None
        assert retrieved_subtask.key == subtask_issue.key

        if hasattr(retrieved_subtask, "fields"):
            if hasattr(retrieved_subtask.fields, "parent"):
                assert retrieved_subtask.fields.parent.key == parent_issue_key

            field_ids = jira_client.get_field_ids_to_epic()
            epic_link_field = field_ids.get("epic_link") or field_ids.get("Epic Link")

            if epic_link_field and hasattr(retrieved_subtask.fields, epic_link_field):
                epic_key = getattr(retrieved_subtask.fields, epic_link_field)
                assert epic_key == test_epic_key

        print(
            f"\nCreated subtask {subtask_issue.key} under parent {parent_issue_key} and epic {test_epic_key}"
        )

    finally:
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
    test_id = str(uuid.uuid4())[:8]
    task_summary = f"Task with Parent Test {test_id}"

    try:
        parent_issue_key = test_epic_key

        try:
            task_issue = jira_client.create_issue(
                project_key=test_project_key,
                summary=task_summary,
                description=f"This is a test task linked to parent {parent_issue_key}",
                issue_type="Task",
                parent=parent_issue_key,
            )

            resource_tracker.add_jira_issue(task_issue.key)

            assert task_issue is not None
            assert task_issue.key.startswith(test_project_key)
            assert task_issue.summary == task_summary

            retrieved_task = jira_client.get_issue(task_issue.key)
            assert retrieved_task is not None
            assert retrieved_task.key == task_issue.key

            if hasattr(retrieved_task, "fields"):
                if hasattr(retrieved_task.fields, "parent"):
                    assert retrieved_task.fields.parent.key == parent_issue_key

            print(f"\nCreated task {task_issue.key} with parent {parent_issue_key}")

        except Exception as e:
            if "hierarchy" in str(e).lower():
                pytest.skip(
                    f"Parent-child relationship not allowed by Jira configuration: {str(e)}"
                )
            else:
                raise

    finally:
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
        epic_issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=epic_summary,
            description="This is a test epic for validating Epic creation functionality.",
            issue_type="Epic",
        )

        resource_tracker.add_jira_issue(epic_issue.key)

        assert epic_issue is not None
        assert epic_issue.key.startswith(test_project_key)
        assert epic_issue.summary == epic_summary

        print(f"\nTEST PASSED: Successfully created Epic issue {epic_issue.key}")

        retrieved_epic = jira_client.get_issue(epic_issue.key)
        assert retrieved_epic is not None
        assert retrieved_epic.key == epic_issue.key
        assert retrieved_epic.summary == epic_summary

    except Exception as e:
        print(f"\nERROR creating Epic: {str(e)}")

        try:
            print("\n=== Jira Field Information for Debugging ===")
            field_ids = jira_client.get_field_ids_to_epic()
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
        comment = jira_client.add_comment(
            issue_key=test_issue_key, comment=comment_text
        )

        if hasattr(comment, "id"):
            resource_tracker.add_jira_comment(test_issue_key, comment.id)
        elif isinstance(comment, dict) and "id" in comment:
            resource_tracker.add_jira_comment(test_issue_key, comment["id"])

        assert comment is not None

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

    timestamp = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    content = f"""
    <h1>Test Page</h1>
    <p>This is a test page created by the API validation tests at {timestamp}.</p>
    <p>It should be automatically deleted after the test.</p>
    """

    try:
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

        page_id = page.id
        resource_tracker.add_confluence_page(page_id)

        assert page is not None
        assert page.title == title

        retrieved_page = confluence_client.get_page_content(page_id)
        assert retrieved_page is not None
    finally:
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
    test_id = str(uuid.uuid4())[:8]
    title = f"Update Test Page {test_id}"
    content = f"<p>Initial content {test_id}</p>"

    try:
        page = confluence_client.create_page(
            space_key=test_space_key, title=title, body=content
        )

        page_id = page.id
        resource_tracker.add_confluence_page(page_id)

        now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        updated_content = f"<p>Updated content {test_id} at {now}</p>"

        updated_page = confluence_client.update_page(
            page_id=page_id, title=title, body=updated_content
        )

        assert updated_page is not None

        # ======= TextContent Validation (prevents issue #97) =======
        # Import TextContent class to test directly
        from mcp.types import TextContent

        print("Testing TextContent validation to prevent issue #97")

        try:
            _ = TextContent(text="This should fail without type field")
            raise AssertionError(
                "TextContent creation without 'type' field should fail but didn't"
            )
        except Exception as e:
            print(f"Correctly got error: {str(e)}")
            assert "type" in str(e), "Error should mention missing 'type' field"

        valid_content = TextContent(
            type="text", text="This should work with type field"
        )
        assert valid_content.type == "text", "TextContent should have type='text'"
        assert valid_content.text == "This should work with type field", (
            "TextContent text should match"
        )

        print("TextContent validation succeeded - 'type' field is properly required")

    finally:
        cleanup_resources()


@pytest.mark.anyio
async def test_confluence_add_page_label(
    confluence_client: ConfluenceFetcher,
    resource_tracker: ResourceTracker,
    test_space_key: str,
    cleanup_resources: Callable[[], None],
) -> None:
    """Test adding a label to a page in Confluence"""
    test_id = str(uuid.uuid4())[:8]
    title = f"Update Test Page {test_id}"
    content = f"<p>Initial content {test_id}</p>"

    try:
        page = confluence_client.create_page(
            space_key=test_space_key, title=title, body=content
        )

        page_id = page.id
        resource_tracker.add_confluence_page(page_id)

        name = "test"
        updated_labels = confluence_client.add_page_label(page_id=page_id, name=name)

        assert updated_labels is not None
    finally:
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
    test_id = str(uuid.uuid4())[:8]
    summary = f"Transition Test Issue {test_id}"

    try:
        issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=summary,
            description="Test issue for transition testing",
            issue_type="Task",
        )

        resource_tracker.add_jira_issue(issue.key)

        transitions = jira_client.get_transitions(issue.key)
        assert transitions is not None
        assert len(transitions) > 0

        transition_id = None
        for transition in transitions:
            if hasattr(transition, "name") and "progress" in transition.name.lower():
                transition_id = transition.id
                break

        if not transition_id and transitions:
            transition_id = (
                transitions[0].id
                if hasattr(transitions[0], "id")
                else transitions[0]["id"]
            )

        assert transition_id is not None

        transition_result = jira_client.transition_issue(
            issue_key=issue.key, transition_id=transition_id
        )

        if transition_result is not None:
            assert transition_result, (
                "Transition should return a truthy value if successful"
            )

        updated_issue = jira_client.get_issue(issue.key)

        if hasattr(updated_issue, "status") and hasattr(updated_issue.status, "name"):
            status_name = updated_issue.status.name
        else:
            status_name = updated_issue["fields"]["status"]["name"]

        assert "to do" not in status_name.lower()
    finally:
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
    test_id = str(uuid.uuid4())[:8]
    epic_summary = f"Test Epic {test_id}"
    custom_epic_name = f"Custom Epic Name {test_id}"

    try:
        field_ids = jira_client.get_field_ids_to_epic()
        jira_client._field_ids_cache = None
        print(f"Discovered field IDs: {field_ids}")

        epic_issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=epic_summary,
            description="This is a test epic with custom values.",
            issue_type="Epic",
            epic_name=custom_epic_name,
            epic_color="blue",
        )
        jira_client._field_ids_cache = None

        resource_tracker.add_jira_issue(epic_issue.key)
        jira_client._field_ids_cache = None

        assert epic_issue is not None
        assert epic_issue.key.startswith(test_project_key)
        assert epic_issue.summary == epic_summary

        print(f"\nTEST PASSED: Successfully created Epic issue {epic_issue.key}")

        retrieved_epic = jira_client.get_issue(epic_issue.key)
        jira_client._field_ids_cache = None

        has_epic_name = False
        if hasattr(retrieved_epic, "epic_name") and retrieved_epic.epic_name:
            assert retrieved_epic.epic_name == custom_epic_name
            has_epic_name = True
            print(
                f"Verified Epic Name via epic_name property: {retrieved_epic.epic_name}"
            )

        if not has_epic_name:
            print("Could not verify Epic Name directly, checking raw fields...")
            if hasattr(jira_client, "jira"):
                raw_issue = jira_client.jira.issue(epic_issue.key)
                fields = raw_issue.get("fields", {})

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

        try:
            print("\n=== Jira Field Information for Debugging ===")
            field_ids = jira_client.get_field_ids_to_epic()
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
    test_id = str(uuid.uuid4())[:8]
    epic_summary = f"Two-Step Epic {test_id}"
    epic_name = f"Epic Name {test_id}"

    try:
        field_ids = jira_client.get_field_ids_to_epic()
        jira_client._field_ids_cache = None
        print(f"\nAvailable field IDs for Epic creation: {field_ids}")

        print("\nAttempting to create Epic using two-step process...")
        epic_issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=epic_summary,
            description="This is a test epic using the two-step creation process.",
            issue_type="Epic",
            epic_name=epic_name,  # This should be stored for post-creation update
            epic_color="blue",  # This should be stored for post-creation update
        )
        jira_client._field_ids_cache = None

        resource_tracker.add_jira_issue(epic_issue.key)
        jira_client._field_ids_cache = None

        assert epic_issue is not None
        assert epic_issue.key.startswith(test_project_key)
        assert epic_issue.summary == epic_summary

        print(f"\nSuccessfully created Epic: {epic_issue.key}")

        retrieved_epic = jira_client.get_issue(epic_issue.key)
        jira_client._field_ids_cache = None
        print(f"\nRetrieved Epic: {retrieved_epic.key}")

        print(f"Epic name: {retrieved_epic.epic_name}")

        try:
            if hasattr(retrieved_epic, "_raw"):
                raw_data = retrieved_epic._raw
            else:
                raw_data = jira_client.jira.issue(epic_issue.key)

            if "fields" in raw_data:
                for field_id, field_value in raw_data["fields"].items():
                    if "epic" in field_id.lower() or field_id in field_ids.values():
                        print(f"Field {field_id}: {field_value}")
        except Exception as e:
            print(f"Error getting raw Epic data: {str(e)}")

        print("\nTEST PASSED: Successfully completed two-step Epic creation test")

    except Exception as e:
        print(f"\nERROR in two-step Epic creation test: {str(e)}")

        print("\nAvailable field IDs:")
        try:
            field_ids = jira_client.get_field_ids_to_epic()
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

        args1 = {"jql": jql, "limit": limit, "startAt": 0}
        result1_content: Sequence[TextContent] = await call_tool(
            api_validation_client, "jira_search", args1
        )
        assert result1_content and isinstance(result1_content[0], TextContent)
        results1 = json.loads(result1_content[0].text)

        args2 = {"jql": jql, "limit": limit, "startAt": 1}
        result2_content: Sequence[TextContent] = await call_tool(
            api_validation_client, "jira_search", args2
        )
        assert result2_content and isinstance(result2_content[0], TextContent)
        results2 = json.loads(result2_content[0].text)

        assert isinstance(results1.get("issues"), list)
        assert isinstance(results2.get("issues"), list)

        if len(results1["issues"]) > 0 and len(results2["issues"]) > 0:
            assert results1["issues"][0]["key"] != results2["issues"][0]["key"], (
                f"Expected different issues with startAt=0 and startAt=1, but got {results1['issues'][0]['key']} for both."
                f" Ensure project '{test_project_key}' has at least 2 issues."
            )
        elif len(results1["issues"]) <= 1:
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

        args1 = {"project_key": test_project_key, "limit": limit, "startAt": 0}
        result1_content = list(
            await call_tool(api_validation_client, "jira_get_project_issues", args1)
        )
        assert isinstance(result1_content[0], TextContent)
        results1 = json.loads(result1_content[0].text)

        args2 = {"project_key": test_project_key, "limit": limit, "startAt": 1}
        result2_content = list(
            await call_tool(api_validation_client, "jira_get_project_issues", args2)
        )
        assert isinstance(result2_content[0], TextContent)
        results2 = json.loads(result2_content[0].text)

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

        args1 = {"epic_key": test_epic_key, "limit": limit, "startAt": 0}
        result1_content: Sequence[TextContent] = await call_tool(
            api_validation_client, "jira_get_epic_issues", args1
        )
        assert result1_content and isinstance(result1_content[0], TextContent)
        results1 = json.loads(result1_content[0].text)

        args2 = {"epic_key": test_epic_key, "limit": limit, "startAt": 1}
        result2_content: Sequence[TextContent] = await call_tool(
            api_validation_client, "jira_get_epic_issues", args2
        )
        assert result2_content and isinstance(result2_content[0], TextContent)
        results2 = json.loads(result2_content[0].text)

        assert isinstance(results1.get("issues"), list)
        assert isinstance(results2.get("issues"), list)

        if len(results1["issues"]) > 0 and len(results2["issues"]) > 0:
            assert results1["issues"][0]["key"] != results2["issues"][0]["key"], (
                f"Expected different issues with startAt=0 and startAt=1, but got {results1['issues'][0]['key']} for both."
                f" Ensure epic '{test_epic_key}' has at least 2 linked issues."
            )
        elif len(results1["issues"]) <= 1:
            pytest.skip(
                f"Epic {test_epic_key} has less than 2 issues, cannot test pagination."
            )

    @pytest.mark.anyio
    async def test_jira_get_issue_includes_comments(
        self, use_real_jira_data: bool, test_issue_key: str
    ) -> None:
        """Test that jira_get_issue includes comments when comment_limit > 0."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        result = await call_tool(
            api_validation_client,
            "jira_get_issue",
            {"issue_key": test_issue_key, "comment_limit": 10},
        )

        assert isinstance(result, dict)
        assert "comments" in result
        assert isinstance(result["comments"], list)

        result_without_comments = await call_tool(
            api_validation_client,
            "jira_get_issue",
            {"issue_key": test_issue_key, "comment_limit": 10, "fields": "summary"},
        )

        assert isinstance(result_without_comments, dict)
        assert "comments" not in result_without_comments

    @pytest.mark.anyio
    async def test_jira_get_link_types_tool(
        self, use_real_jira_data: bool, api_validation_client: Client
    ) -> None:
        """Test the jira_get_link_types tool."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        try:
            result_content = list(
                await call_tool(api_validation_client, "jira_get_link_types", {})
            )
        except LookupError:
            pytest.skip("Server context not available for call_tool")

        assert isinstance(result_content[0], TextContent)
        link_types = json.loads(result_content[0].text)

        assert isinstance(link_types, list)
        assert len(link_types) > 0

        first_link = link_types[0]
        assert "id" in first_link
        assert "name" in first_link
        assert "inward" in first_link
        assert "outward" in first_link

    @pytest.mark.anyio
    async def test_jira_create_issue_link_tool(
        self, use_real_jira_data: bool, test_project_key: str, api_validation_client
    ) -> None:
        """Test the jira_create_issue_link and jira_remove_issue_link tools."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        test_id = str(uuid.uuid4())[:8]

        issue1_args = {
            "project_key": test_project_key,
            "summary": f"Link Test Source {test_id}",
            "description": "Test issue for link testing via tool",
            "issue_type": "Task",
        }
        issue1_content: Sequence[TextContent] = await call_tool(
            api_validation_client, "jira/create_issue", issue1_args
        )
        assert issue1_content and isinstance(issue1_content[0], TextContent)
        issue1_data = json.loads(issue1_content[0].text)
        issue1_key = issue1_data["key"]

        issue2_args = {
            "project_key": test_project_key,
            "summary": f"Link Test Target {test_id}",
            "description": "Test issue for link testing via tool",
            "issue_type": "Task",
        }
        issue2_content: Sequence[TextContent] = await call_tool(
            api_validation_client, "jira/create_issue", issue2_args
        )
        assert issue2_content and isinstance(issue2_content[0], TextContent)
        issue2_data = json.loads(issue2_content[0].text)
        issue2_key = issue2_data["key"]

        try:
            link_types_content: Sequence[TextContent] = await call_tool(
                api_validation_client, "jira/get_link_types", {}
            )
            assert link_types_content and isinstance(link_types_content[0], TextContent)
            link_types = json.loads(link_types_content[0].text)

            link_type_name = None
            for lt in link_types:
                if "relate" in lt["name"].lower():
                    link_type_name = lt["name"]
                    break

            # If no "relates to" type found, use the first available type
            if not link_type_name:
                link_type_name = link_types[0]["name"]

            link_args = {
                "link_type": link_type_name,
                "inward_issue_key": issue1_key,
                "outward_issue_key": issue2_key,
                "comment": f"Test link created by API validation test {test_id}",
            }
            link_content: Sequence[TextContent] = await call_tool(
                api_validation_client, "jira/create_issue_link", link_args
            )

            assert link_content and isinstance(link_content[0], TextContent)
            link_result = json.loads(link_content[0].text)
            assert link_result["success"] is True

            issue_content: Sequence[TextContent] = await call_tool(
                api_validation_client,
                "jira/get_issue",
                {"issue_key": issue1_key, "fields": "issuelinks"},
            )
            assert issue_content and isinstance(issue_content[0], TextContent)
            issue_data = json.loads(issue_content[0].text)

            link_id = None
            if "issuelinks" in issue_data:
                for link in issue_data["issuelinks"]:
                    if link.get("outwardIssue", {}).get("key") == issue2_key:
                        link_id = link.get("id")
                        break

            # If we found a link ID, test removing it
            if link_id:
                remove_args = {"link_id": link_id}
                remove_content: Sequence[TextContent] = await call_tool(
                    api_validation_client, "jira/remove_issue_link", remove_args
                )

                assert remove_content and isinstance(remove_content[0], TextContent)
                remove_result = json.loads(remove_content[0].text)
                assert remove_result["success"] is True
                assert remove_result["link_id"] == link_id

        finally:
            await call_tool(
                api_validation_client, "jira/delete_issue", {"issue_key": issue1_key}
            )
            await call_tool(
                api_validation_client, "jira/delete_issue", {"issue_key": issue2_key}
            )


@pytest.mark.anyio
async def test_jira_get_issue_link_types(jira_client: JiraFetcher) -> None:
    """Test retrieving issue link types from Jira."""
    links_client = LinksMixin(config=jira_client.config)

    link_types = links_client.get_issue_link_types()

    # An empty list is a valid response if no link types are configured or accessible
    assert isinstance(link_types, list)

    # If the list is not empty, check the structure of the first element
    if link_types:
        first_link = link_types[0]
        assert isinstance(first_link, JiraIssueLinkType)
        assert first_link.id is not None
        assert first_link.name is not None
        assert first_link.inward is not None
        assert first_link.outward is not None


@pytest.mark.anyio
async def test_jira_create_and_remove_issue_link(
    jira_client: JiraFetcher,
    test_project_key: str,
    resource_tracker: ResourceTracker,
    cleanup_resources: Callable[[], None],
) -> None:
    """Test creating and removing a link between two Jira issues."""
    test_id = str(uuid.uuid4())[:8]
    summary1 = f"Link Test Issue 1 {test_id}"
    summary2 = f"Link Test Issue 2 {test_id}"

    try:
        issue1 = jira_client.create_issue(
            project_key=test_project_key,
            summary=summary1,
            description="First test issue for link testing",
            issue_type="Task",
        )

        issue2 = jira_client.create_issue(
            project_key=test_project_key,
            summary=summary2,
            description="Second test issue for link testing",
            issue_type="Task",
        )

        resource_tracker.add_jira_issue(issue1.key)
        resource_tracker.add_jira_issue(issue2.key)

        links_client = LinksMixin(config=jira_client.config)

        link_types = links_client.get_issue_link_types()
        assert len(link_types) > 0

        link_type_name = None
        for lt in link_types:
            if "relate" in lt.name.lower():
                link_type_name = lt.name
                break

        # If no "Relates" type found, use the first available type
        if not link_type_name:
            link_type_name = link_types[0].name

        link_data = {
            "type": {"name": link_type_name},
            "inwardIssue": {"key": issue1.key},
            "outwardIssue": {"key": issue2.key},
            "comment": {"body": f"Test link created by API validation test {test_id}"},
        }

        link_result = links_client.create_issue_link(link_data)

        assert link_result is not None
        assert link_result["success"] is True
        assert link_result["inward_issue"] == issue1.key
        assert link_result["outward_issue"] == issue2.key

        raw_issue = jira_client.jira.issue(issue1.key, fields="issuelinks")

        link_id = None
        if hasattr(raw_issue, "fields") and hasattr(raw_issue.fields, "issuelinks"):
            for link in raw_issue.fields.issuelinks:
                if (
                    hasattr(link, "outwardIssue")
                    and link.outwardIssue.key == issue2.key
                ):
                    link_id = link.id
                    break

        # Skip link removal test if we couldn't find the link ID
        if not link_id:
            pytest.skip("Could not find link ID for removal test")

        remove_result = links_client.remove_issue_link(link_id)

        assert remove_result is not None
        assert remove_result["success"] is True
        assert remove_result["link_id"] == link_id

    finally:
        # Clean up resources even if the test fails
        cleanup_resources()

    @pytest.mark.anyio
    async def test_regression_jira_create_additional_fields_string(
        self,
        use_real_jira_data: bool,
        test_project_key: str,
        resource_tracker: ResourceTracker,
        cleanup_resources: Callable[[], None],
    ) -> None:
        """Test jira_create_issue with additional_fields passed as a JSON string."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        test_id = str(uuid.uuid4())[:8]
        summary = f"Regression Test (JSON String Fields) {test_id}"
        additional_fields_str = '{"priority": {"name": "High"}, "labels": ["regression-test", "json-string"]}'

        created_issue_key = None
        try:
            create_args = {
                "project_key": test_project_key,
                "summary": summary,
                "issue_type": "Task",
                "additional_fields": additional_fields_str,
            }
            create_result_content: Sequence[TextContent] = await call_tool(
                api_validation_client, "jira/create_issue", create_args
            )
            assert create_result_content and isinstance(
                create_result_content[0], TextContent
            )
            created_issue_data = json.loads(create_result_content[0].text)
            created_issue_key = created_issue_data["key"]

            get_args = {
                "issue_key": created_issue_key,
                "fields": "summary,priority,labels",
            }
            get_result_content: Sequence[TextContent] = await call_tool(
                api_validation_client, "jira/get_issue", get_args
            )
            assert get_result_content and isinstance(get_result_content[0], TextContent)
            fetched_issue_data = json.loads(get_result_content[0].text)

            assert "priority" in fetched_issue_data, (
                "Priority field missing in fetched issue"
            )
            assert isinstance(fetched_issue_data["priority"], dict), (
                "Priority should be a dict"
            )
            assert fetched_issue_data["priority"].get("name") == "High", (
                "Priority was not set correctly"
            )
            assert "labels" in fetched_issue_data, (
                "Labels field missing in fetched issue"
            )
            assert isinstance(fetched_issue_data["labels"], list), (
                "Labels should be a list"
            )
            assert set(fetched_issue_data["labels"]) == {
                "regression-test",
                "json-string",
            }, "Labels were not set correctly"

        finally:
            cleanup_resources()

    @pytest.mark.anyio
    async def test_regression_jira_update_fields_string(
        self,
        use_real_jira_data: bool,
        test_project_key: str,
        api_validation_client,
        resource_tracker: ResourceTracker,
        cleanup_resources: Callable[[], None],
    ) -> None:
        """Test jira_update_issue with 'fields' passed as a JSON string."""
        if not use_real_jira_data:
            pytest.skip("Real Jira data testing is disabled")

        test_id = str(uuid.uuid4())[:8]
        initial_summary = f"Regression Update Test Initial {test_id}"
        updated_summary = f"Regression Update Test UPDATED {test_id}"

        created_issue_key = None
        try:
            create_args = {
                "project_key": test_project_key,
                "summary": initial_summary,
                "issue_type": "Task",
            }
            create_result_content: Sequence[TextContent] = await call_tool(
                api_validation_client, "jira/create_issue", create_args
            )
            created_issue_key = json.loads(create_result_content[0].text)["key"]
            resource_tracker.add_jira_issue(created_issue_key)

            update_fields_str = f'{{"summary": "{updated_summary}", "labels": ["regression-update", "json-string"]}}'
            update_args = {
                "issue_key": created_issue_key,
                "fields": update_fields_str,
            }
            update_result_content: Sequence[TextContent] = await call_tool(
                api_validation_client, "jira/update_issue", update_args
            )
            assert update_result_content and isinstance(
                update_result_content[0], TextContent
            )
            update_result_data = json.loads(update_result_content[0].text)
            assert update_result_data.get("success"), "Update did not succeed"

            get_args = {"issue_key": created_issue_key, "fields": "summary,labels"}
            get_result_content: Sequence[TextContent] = await call_tool(
                api_validation_client, "jira/get_issue", get_args
            )
            assert get_result_content and isinstance(get_result_content[0], TextContent)
            fetched_issue_data = json.loads(get_result_content[0].text)

            assert fetched_issue_data["summary"] == updated_summary, (
                "Summary was not updated correctly"
            )
            assert set(fetched_issue_data["labels"]) == {
                "regression-update",
                "json-string",
            }, "Labels were not updated correctly"

        finally:
            cleanup_resources()
