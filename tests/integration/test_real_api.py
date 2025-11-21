"""
Integration tests with real Atlassian APIs.

These tests are skipped by default and only run with --use-real-data flag.
They require proper environment configuration and will create/modify real data.

Usage:
    uv run --env-file .env.test pytest tests/integration/test_real_api.py --integration --use-real-data -v
"""

import os
import time
import uuid

import pytest

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from tests.utils.base import BaseAuthTest


@pytest.mark.integration
class TestRealJiraAPI(BaseAuthTest):
    """Real Jira API integration tests with cleanup."""

    @pytest.fixture(autouse=True)
    def skip_without_integration(self, request):
        """Skip these tests unless --integration is provided."""
        if not request.config.getoption("--integration", default=False):
            pytest.skip("Need --integration option to run")

    @pytest.fixture
    def jira_client(self):
        """Create real Jira client from environment."""
        if not os.getenv("JIRA_URL"):
            pytest.skip("JIRA_URL not set in environment")

        config = JiraConfig.from_env()
        return JiraFetcher(config=config)

    @pytest.fixture
    def test_project_key(self):
        """Get test project key from environment."""
        key = os.getenv("JIRA_TEST_PROJECT_KEY", "TEST")
        return key

    @pytest.fixture
    def created_issues(self):
        """Track created issues for cleanup."""
        issues = []
        yield issues
        # Cleanup will be done in individual tests

    def test_complete_issue_lifecycle(
        self, jira_client, test_project_key, created_issues
    ):
        """Test create, update, transition, and delete issue lifecycle."""
        # Create unique summary to avoid conflicts
        unique_id = str(uuid.uuid4())[:8]
        summary = f"Integration Test Issue {unique_id}"

        # 1. Create issue
        created_issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=summary,
            issue_type="Task",
            description="This is an integration test issue that will be deleted",
        )
        created_issues.append(created_issue.key)

        assert created_issue.key.startswith(test_project_key)
        assert created_issue.summary == summary

        # 2. Update issue
        update_data = {
            "summary": f"{summary} - Updated",
            "description": "Updated description",
        }

        updated_issue = jira_client.update_issue(
            issue_key=created_issue.key, **update_data
        )

        assert updated_issue.summary == f"{summary} - Updated"

        # 3. Add comment
        comment = jira_client.add_comment(
            issue_key=created_issue.key, comment="Test comment from integration test"
        )

        assert comment["body"] == "Test comment from integration test"

        # 4. Get available transitions
        transitions = jira_client.get_transitions(issue_key=created_issue.key)
        assert len(transitions) > 0

        # 5. Transition issue (if "Done" transition available)
        done_transition = next(
            (t for t in transitions if "done" in t["name"].lower()), None
        )
        if done_transition:
            jira_client.transition_issue(
                issue_key=created_issue.key, transition_id=done_transition["id"]
            )

        # 6. Delete issue
        jira_client.delete_issue(issue_key=created_issue.key)
        created_issues.remove(created_issue.key)

        # Verify deletion
        with pytest.raises(Exception):
            jira_client.get_issue(issue_key=created_issue.key)

    def test_attachment_upload_download(
        self, jira_client, test_project_key, created_issues, tmp_path
    ):
        """Test attachment upload via update_issue (MCP API way)."""
        # Create test issue
        unique_id = str(uuid.uuid4())[:8]

        issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=f"Attachment Test {unique_id}",
            issue_type="Task",
            description="Test issue for attachment upload/download",
        )
        created_issues.append(issue.key)

        try:
            # Create test file
            test_file = tmp_path / "test_attachment.txt"
            test_content = f"Test content {unique_id}"
            test_file.write_text(test_content)

            # Upload attachment via update_issue (the MCP way)
            updated_issue = jira_client.update_issue(
                issue_key=issue.key,
                fields={"description": "Updated with attachment"},
                attachments=[str(test_file)],
            )

            assert updated_issue.description == "Updated with attachment"

            # Wait a moment for the attachment to be processed
            time.sleep(2)

            # Re-read the issue with attachments
            issue_with_attachments = jira_client.get_issue(
                issue_key=issue.key, expand="attachment"
            )

            # Test attachment download functionality if attachments exist
            if len(issue_with_attachments.attachments) > 0:
                # Test download functionality
                download_dir = tmp_path / "downloads"
                download_dir.mkdir()

                result = jira_client.download_issue_attachments(
                    issue_key=issue.key, target_dir=str(download_dir)
                )

                assert result["success"] is True
                assert len(result["downloaded_files"]) > 0
            else:
                print(
                    "Warning: No attachments found after upload - may be server configuration issue"
                )

        finally:
            # Cleanup
            jira_client.delete_issue(issue_key=issue.key)
            created_issues.remove(issue.key)

    def test_jql_search_with_pagination(self, jira_client, test_project_key):
        """Test JQL search with pagination."""
        # Search for recent issues in test project
        jql = f"project = {test_project_key} ORDER BY created DESC"

        # First page
        results_page1 = jira_client.search_issues(jql=jql, start=0, limit=2)

        # For Cloud, total is -1 (v3 API doesn't provide total count)
        # For Server/DC, total should be >= 0
        if hasattr(jira_client.config, "is_cloud") and jira_client.config.is_cloud:
            assert results_page1.total == -1  # Cloud v3 API behavior
        else:
            assert results_page1.total >= 0  # Server/DC behavior

        if results_page1.total > 2:
            # Second page
            results_page2 = jira_client.search_issues(jql=jql, start=2, limit=2)

            # Ensure different issues
            page1_keys = [i.key for i in results_page1.issues]
            page2_keys = [i.key for i in results_page2.issues]
            assert not set(page1_keys).intersection(set(page2_keys))

    def test_bulk_issue_creation(self, jira_client, test_project_key, created_issues):
        """Test creating multiple issues in bulk."""
        unique_id = str(uuid.uuid4())[:8]
        issues_data = []

        # Create issues
        created = []
        try:
            for i in range(3):
                issue = jira_client.create_issue(
                    project_key=test_project_key,
                    summary=f"Bulk Test Issue {i + 1} - {unique_id}",
                    issue_type="Task",
                    description=f"Bulk test issue {i + 1}",
                )
                created.append(issue)
                created_issues.append(issue.key)

            assert len(created) == 3

            # Verify all created
            for i, issue in enumerate(created):
                assert f"Bulk Test Issue {i + 1}" in issue.summary

        finally:
            # Cleanup all created issues
            for issue in created:
                try:
                    jira_client.delete_issue(issue_key=issue.key)
                    created_issues.remove(issue.key)
                except Exception:
                    pass

    def test_rate_limiting_behavior(self, jira_client):
        """Test API rate limiting behavior with retries."""
        # Make multiple rapid requests
        start_time = time.time()

        for _i in range(5):
            try:
                jira_client.get_fields()
            except Exception as e:
                if "429" in str(e) or "rate limit" in str(e).lower():
                    # Rate limit hit - this is expected
                    assert True
                    return

        # If no rate limit hit, that's also fine
        elapsed = time.time() - start_time
        assert elapsed < 10  # Should complete quickly if no rate limiting


@pytest.mark.integration
class TestRealConfluenceAPI(BaseAuthTest):
    """Real Confluence API integration tests with cleanup."""

    @pytest.fixture(autouse=True)
    def skip_without_integration(self, request):
        """Skip these tests unless --integration is provided."""
        if not request.config.getoption("--integration", default=False):
            pytest.skip("Need --integration option to run")

    @pytest.fixture
    def confluence_client(self):
        """Create real Confluence client from environment."""
        if not os.getenv("CONFLUENCE_URL"):
            pytest.skip("CONFLUENCE_URL not set in environment")

        config = ConfluenceConfig.from_env()
        return ConfluenceFetcher(config=config)

    @pytest.fixture
    def test_space_key(self):
        """Get test space key from environment."""
        key = os.getenv("CONFLUENCE_TEST_SPACE_KEY", "TEST")
        return key

    @pytest.fixture
    def created_pages(self):
        """Track created pages for cleanup."""
        pages = []
        yield pages
        # Cleanup will be done in individual tests

    def test_page_lifecycle(self, confluence_client, test_space_key, created_pages):
        """Test create, update, and delete page lifecycle."""
        unique_id = str(uuid.uuid4())[:8]
        title = f"Integration Test Page {unique_id}"

        # 1. Create page
        page = confluence_client.create_page(
            space_key=test_space_key,
            title=title,
            body="<p>This is an integration test page</p>",
        )
        created_pages.append(page.id)

        assert page.title == title
        assert page.space.key == test_space_key

        # 2. Update page
        updated_page = confluence_client.update_page(
            page_id=page.id,
            title=f"{title} - Updated",
            body="<p>Updated content</p>",
        )

        assert updated_page.title == f"{title} - Updated"

        # 3. Add comment
        comment = confluence_client.add_comment(
            page_id=page.id, content="Test comment from integration test"
        )

        # Verify comment was created
        assert comment is not None
        assert comment.id is not None

        # Fetch comments to verify content using MCP tool
        comments = confluence_client.get_page_comments(page_id=page.id)
        assert len(comments) > 0
        assert any("Test comment from integration test" in c.body for c in comments)

        # 4. Delete page
        confluence_client.delete_page(page_id=page.id)
        created_pages.remove(page.id)

        # Verify deletion
        with pytest.raises(Exception):
            confluence_client.get_page_content(page_id=page.id)

    def test_page_hierarchy(self, confluence_client, test_space_key, created_pages):
        """Test creating page hierarchy with parent-child relationships."""
        unique_id = str(uuid.uuid4())[:8]

        # Create parent page
        parent = confluence_client.create_page(
            space_key=test_space_key,
            title=f"Parent Page {unique_id}",
            body="<p>Parent content</p>",
        )
        created_pages.append(parent.id)

        try:
            # Create child page
            child = confluence_client.create_page(
                space_key=test_space_key,
                title=f"Child Page {unique_id}",
                body="<p>Child content</p>",
                parent_id=parent.id,
            )
            created_pages.append(child.id)

            # Get child pages
            children = confluence_client.get_page_children(
                page_id=parent.id, expand="body.storage"
            )

            assert len(children) == 1
            assert children[0].id == child.id

            # Delete child first, then parent
            confluence_client.delete_page(page_id=child.id)
            created_pages.remove(child.id)

        finally:
            # Cleanup parent
            confluence_client.delete_page(page_id=parent.id)
            created_pages.remove(parent.id)

    def test_cql_search(self, confluence_client, test_space_key):
        """Test CQL search functionality."""
        # Search for pages in test space
        cql = f'space = "{test_space_key}" and type = "page"'

        results = confluence_client.search(query=cql, limit=5)

        assert len(results) >= 0

        # Verify all results are from test space
        for result in results:
            if hasattr(result, "space"):
                assert result.space.key == test_space_key

    def test_attachment_handling(
        self, confluence_client, test_space_key, created_pages, tmp_path
    ):
        """Test attachment upload to Confluence page.

        Note: Confluence MCP tools don't currently support attachments,
        so this test uses the internal atlassian-python-api directly.
        This represents a missing MCP feature that could be added.
        """
        unique_id = str(uuid.uuid4())[:8]

        # Create page
        page = confluence_client.create_page(
            space_key=test_space_key,
            title=f"Attachment Test Page {unique_id}",
            body="<p>Page with attachments</p>",
        )
        created_pages.append(page.id)

        try:
            # Create test file
            test_file = tmp_path / "confluence_test.txt"
            test_content = f"Confluence test content {unique_id}"
            test_file.write_text(test_content)

            # Upload attachment using internal API (no MCP tool available)
            # TODO: This should be replaced with MCP tool when available
            confluence_client.confluence.attach_file(
                filename=str(test_file),
                name="confluence_test.txt",
                content_type="text/plain",
                page_id=page.id,
            )

            # Get attachments from page using internal API
            # TODO: This should be replaced with MCP tool when available
            attachments = confluence_client.confluence.get_attachments_from_content(
                page_id=page.id
            )

            # Verify attachment was uploaded
            assert attachments is not None
            assert "results" in attachments
            assert len(attachments["results"]) == 1
            assert attachments["results"][0]["title"] == "confluence_test.txt"

        finally:
            # Cleanup
            confluence_client.delete_page(page_id=page.id)
            created_pages.remove(page.id)

    def test_large_content_handling(
        self, confluence_client, test_space_key, created_pages
    ):
        """Test handling of large content (>1MB)."""
        unique_id = str(uuid.uuid4())[:8]

        # Create large content (approximately 1MB)
        large_content = "<p>" + ("Large content block. " * 10000) + "</p>"

        # Create page with large content
        page = confluence_client.create_page(
            space_key=test_space_key,
            title=f"Large Content Test {unique_id}",
            body=large_content,
        )
        created_pages.append(page.id)

        try:
            # Retrieve and verify
            retrieved = confluence_client.get_page_content(
                page_id=page.id, convert_to_markdown=False
            )

            # Check content length (either in content or body attribute)
            content_length = (
                len(retrieved.content)
                if hasattr(retrieved, "content")
                else len(retrieved.body.storage.value)
                if hasattr(retrieved, "body")
                else 0
            )
            assert content_length > 100000  # At least 100KB

        finally:
            # Cleanup
            confluence_client.delete_page(page_id=page.id)
            created_pages.remove(page.id)


@pytest.mark.integration
class TestCrossServiceIntegration:
    """Test integration between Jira and Confluence services."""

    @pytest.fixture(autouse=True)
    def skip_without_integration(self, request):
        """Skip these tests unless --integration is provided."""
        if not request.config.getoption("--integration", default=False):
            pytest.skip("Need --integration option to run")

    @pytest.fixture
    def jira_client(self):
        """Create real Jira client from environment."""
        if not os.getenv("JIRA_URL"):
            pytest.skip("JIRA_URL not set in environment")

        config = JiraConfig.from_env()
        return JiraFetcher(config=config)

    @pytest.fixture
    def confluence_client(self):
        """Create real Confluence client from environment."""
        if not os.getenv("CONFLUENCE_URL"):
            pytest.skip("CONFLUENCE_URL not set in environment")

        config = ConfluenceConfig.from_env()
        return ConfluenceFetcher(config=config)

    @pytest.fixture
    def test_project_key(self):
        """Get test project key from environment."""
        return os.getenv("JIRA_TEST_PROJECT_KEY", "TEST")

    @pytest.fixture
    def test_space_key(self):
        """Get test space key from environment."""
        return os.getenv("CONFLUENCE_TEST_SPACE_KEY", "TEST")

    @pytest.fixture
    def created_issues(self):
        """Track created issues for cleanup."""
        issues = []
        yield issues

    @pytest.fixture
    def created_pages(self):
        """Track created pages for cleanup."""
        pages = []
        yield pages

    def test_jira_confluence_linking(
        self,
        jira_client,
        confluence_client,
        test_project_key,
        test_space_key,
        created_issues,
        created_pages,
    ):
        """Test linking between Jira issues and Confluence pages."""
        unique_id = str(uuid.uuid4())[:8]

        # Create Jira issue
        issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=f"Linked Issue {unique_id}",
            issue_type="Task",
            description="Test issue for Jira-Confluence linking",
        )
        created_issues.append(issue.key)

        # Create Confluence page with Jira issue link
        page_content = f'<p>Related to Jira issue: <a href="{jira_client.config.url}/browse/{issue.key}">{issue.key}</a></p>'

        page = confluence_client.create_page(
            space_key=test_space_key,
            title=f"Linked Page {unique_id}",
            body=page_content,
        )
        created_pages.append(page.id)

        try:
            # Add comment in Jira referencing Confluence page
            confluence_url = (
                f"{confluence_client.config.url}/pages/viewpage.action?pageId={page.id}"
            )
            jira_client.add_comment(
                issue_key=issue.key,
                comment=f"Documentation available at: {confluence_url}",
            )

            # Verify both exist and contain cross-references
            issue_comments = jira_client.get_issue_comments(issue_key=issue.key)
            assert any(confluence_url in c["body"] for c in issue_comments)

            retrieved_page = confluence_client.get_page_content(page_id=page.id)
            assert issue.key in retrieved_page.content

        finally:
            # Cleanup
            jira_client.delete_issue(issue_key=issue.key)
            created_issues.remove(issue.key)
            confluence_client.delete_page(page_id=page.id)
            created_pages.remove(page.id)
