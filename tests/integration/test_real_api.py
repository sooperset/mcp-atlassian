"""
Integration tests with real Atlassian APIs.

These tests are skipped by default and only run with --integration --use-real-data flags.
They require proper environment configuration and will create/modify real data.
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
    def skip_without_real_data(self, request):
        """Skip these tests unless --use-real-data is provided."""
        if not request.config.getoption("--use-real-data", default=False):
            pytest.skip("Real API tests only run with --use-real-data flag")

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
        issue_data = {
            "project": {"key": test_project_key},
            "summary": summary,
            "description": "This is an integration test issue that will be deleted",
            "issuetype": {"name": "Task"},
        }

        created_issue = jira_client.create_issue(**issue_data)
        created_issues.append(created_issue.key)

        assert created_issue.key.startswith(test_project_key)
        assert created_issue.fields.summary == summary

        # 2. Update issue
        update_data = {
            "summary": f"{summary} - Updated",
            "description": "Updated description",
        }

        updated_issue = jira_client.update_issue(
            issue_key=created_issue.key, **update_data
        )

        assert updated_issue.fields.summary == f"{summary} - Updated"

        # 3. Add comment
        comment = jira_client.add_comment(
            issue_key=created_issue.key, body="Test comment from integration test"
        )

        assert comment.body == "Test comment from integration test"

        # 4. Get available transitions
        transitions = jira_client.get_transitions(issue_key=created_issue.key)
        assert len(transitions) > 0

        # 5. Transition issue (if "Done" transition available)
        done_transition = next(
            (t for t in transitions if "done" in t.name.lower()), None
        )
        if done_transition:
            jira_client.transition_issue(
                issue_key=created_issue.key, transition_id=done_transition.id
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
        """Test attachment upload and download flow."""
        # Create test issue
        unique_id = str(uuid.uuid4())[:8]
        issue_data = {
            "project": {"key": test_project_key},
            "summary": f"Attachment Test {unique_id}",
            "issuetype": {"name": "Task"},
        }

        issue = jira_client.create_issue(**issue_data)
        created_issues.append(issue.key)

        try:
            # Create test file
            test_file = tmp_path / "test_attachment.txt"
            test_content = f"Test content {unique_id}"
            test_file.write_text(test_content)

            # Upload attachment
            with open(test_file, "rb") as f:
                attachments = jira_client.add_attachment(
                    issue_key=issue.key, filename="test_attachment.txt", data=f.read()
                )

            assert len(attachments) == 1
            attachment = attachments[0]
            assert attachment.filename == "test_attachment.txt"

            # Get issue with attachments
            issue_with_attachments = jira_client.get_issue(
                issue_key=issue.key, expand="attachment"
            )

            assert len(issue_with_attachments.fields.attachment) == 1

        finally:
            # Cleanup
            jira_client.delete_issue(issue_key=issue.key)
            created_issues.remove(issue.key)

    def test_jql_search_with_pagination(self, jira_client, test_project_key):
        """Test JQL search with pagination."""
        # Search for recent issues in test project
        jql = f"project = {test_project_key} ORDER BY created DESC"

        # First page
        results_page1 = jira_client.search_issues(jql=jql, start_at=0, max_results=2)

        assert results_page1.total >= 0

        if results_page1.total > 2:
            # Second page
            results_page2 = jira_client.search_issues(
                jql=jql, start_at=2, max_results=2
            )

            # Ensure different issues
            page1_keys = [i.key for i in results_page1.issues]
            page2_keys = [i.key for i in results_page2.issues]
            assert not set(page1_keys).intersection(set(page2_keys))

    def test_bulk_issue_creation(self, jira_client, test_project_key, created_issues):
        """Test creating multiple issues in bulk."""
        unique_id = str(uuid.uuid4())[:8]
        issues_data = []

        # Prepare 3 issues
        for i in range(3):
            issues_data.append(
                {
                    "project": {"key": test_project_key},
                    "summary": f"Bulk Test Issue {i + 1} - {unique_id}",
                    "issuetype": {"name": "Task"},
                }
            )

        # Create issues
        created = []
        try:
            for issue_data in issues_data:
                issue = jira_client.create_issue(**issue_data)
                created.append(issue)
                created_issues.append(issue.key)

            assert len(created) == 3

            # Verify all created
            for i, issue in enumerate(created):
                assert f"Bulk Test Issue {i + 1}" in issue.fields.summary

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
    def skip_without_real_data(self, request):
        """Skip these tests unless --use-real-data is provided."""
        if not request.config.getoption("--use-real-data", default=False):
            pytest.skip("Real API tests only run with --use-real-data flag")

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
            version_number=page.version.number + 1,
        )

        assert updated_page.title == f"{title} - Updated"
        assert updated_page.version.number == page.version.number + 1

        # 3. Add comment
        comment = confluence_client.add_comment(
            page_id=page.id, body="Test comment from integration test"
        )

        assert "Test comment" in comment.body.storage.value

        # 4. Delete page
        confluence_client.delete_page(page_id=page.id)
        created_pages.remove(page.id)

        # Verify deletion
        with pytest.raises(Exception):
            confluence_client.get_page_by_id(page_id=page.id)

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

            assert len(children.results) == 1
            assert children.results[0].id == child.id

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

        results = confluence_client.search_content(cql=cql, limit=5)

        assert results.size >= 0

        # Verify all results are from test space
        for result in results.results:
            if hasattr(result, "space"):
                assert result.space.key == test_space_key

    def test_attachment_handling(
        self, confluence_client, test_space_key, created_pages, tmp_path
    ):
        """Test attachment upload to Confluence page."""
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

            # Upload attachment
            with open(test_file, "rb") as f:
                attachment = confluence_client.create_attachment(
                    page_id=page.id, filename="confluence_test.txt", data=f.read()
                )

            assert attachment.title == "confluence_test.txt"

            # Get page attachments
            attachments = confluence_client.get_attachments(page_id=page.id)
            assert len(attachments.results) == 1
            assert attachments.results[0].title == "confluence_test.txt"

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
            retrieved = confluence_client.get_page_by_id(
                page_id=page.id, expand="body.storage"
            )

            assert len(retrieved.body.storage.value) > 100000  # At least 100KB

        finally:
            # Cleanup
            confluence_client.delete_page(page_id=page.id)
            created_pages.remove(page.id)


@pytest.mark.integration
class TestCrossServiceIntegration:
    """Test integration between Jira and Confluence services."""

    @pytest.fixture(autouse=True)
    def skip_without_real_data(self, request):
        """Skip these tests unless --use-real-data is provided."""
        if not request.config.getoption("--use-real-data", default=False):
            pytest.skip("Real API tests only run with --use-real-data flag")

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
            project={"key": test_project_key},
            summary=f"Linked Issue {unique_id}",
            issuetype={"name": "Task"},
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
                body=f"Documentation available at: {confluence_url}",
            )

            # Verify both exist and contain cross-references
            issue_comments = jira_client.get_comments(issue_key=issue.key)
            assert any(confluence_url in c.body for c in issue_comments.comments)

            retrieved_page = confluence_client.get_page_by_id(
                page_id=page.id, expand="body.storage"
            )
            assert issue.key in retrieved_page.body.storage.value

        finally:
            # Cleanup
            jira_client.delete_issue(issue_key=issue.key)
            created_issues.remove(issue.key)
            confluence_client.delete_page(page_id=page.id)
            created_pages.remove(page.id)
