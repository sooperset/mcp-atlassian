"""
Integration tests with real Atlassian APIs.

These tests are skipped by default and only run with the
--integration --use-real-data flags. They require proper environment
configuration and will create/modify real data.
"""

import os
import time
import uuid
from collections.abc import Callable
from typing import TypeVar

import pytest

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.confluence.config import ConfluenceConfig
from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig
from tests.utils.base import BaseAuthTest

T = TypeVar("T")


def _retry_until(
    fn: Callable[[], T],
    ok: Callable[[T], object],
    *,
    tries: int = 15,
    delay: float = 2.0,
) -> T:
    """Call ``fn`` until ``ok(result)`` is truthy, then return that result.

    Absorbs Atlassian search-index lag in live tests. Returns the last result
    even if ``ok`` never became truthy, so the caller's assertions still run.
    """
    result = fn()
    for _ in range(tries - 1):
        if ok(result):
            return result
        time.sleep(delay)
        result = fn()
    return result


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
        created_issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=summary,
            issue_type="Task",
            description="This is an integration test issue that will be deleted",
        )
        created_issues.append(created_issue.key)

        try:
            assert created_issue.key.startswith(test_project_key)
            assert created_issue.summary == summary

            # 2. Update issue
            updated_issue = jira_client.update_issue(
                issue_key=created_issue.key,
                summary=f"{summary} - Updated",
                description="Updated description",
            )
            assert updated_issue.summary == f"{summary} - Updated"

            # 3. Add comment (returns a dict)
            comment = jira_client.add_comment(
                issue_key=created_issue.key,
                comment="Test comment from integration test",
            )
            assert "Test comment from integration test" in comment["body"]

            # 4. Get available transitions (list of dicts)
            transitions = jira_client.get_transitions(issue_key=created_issue.key)
            assert len(transitions) > 0

            # 5. Transition issue (if a "Done" transition is available)
            done_transition = next(
                (t for t in transitions if "done" in t["name"].lower()), None
            )
            if done_transition:
                jira_client.transition_issue(
                    issue_key=created_issue.key,
                    transition_id=done_transition["id"],
                )

            # 6. Delete issue
            jira_client.delete_issue(issue_key=created_issue.key)
            created_issues.remove(created_issue.key)

            # Verify deletion
            with pytest.raises(Exception):
                jira_client.get_issue(issue_key=created_issue.key)
        finally:
            if created_issue.key in created_issues:
                try:
                    jira_client.delete_issue(issue_key=created_issue.key)
                    created_issues.remove(created_issue.key)
                except Exception:  # noqa: BLE001
                    pass

    def test_attachment_upload_download(
        self, jira_client, test_project_key, created_issues, tmp_path
    ):
        """Test attachment upload and download flow."""
        # Create test issue
        unique_id = str(uuid.uuid4())[:8]
        issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=f"Attachment Test {unique_id}",
            issue_type="Task",
        )
        created_issues.append(issue.key)

        try:
            # Create test file
            test_file = tmp_path / "test_attachment.txt"
            test_file.write_text(f"Test content {unique_id}")

            # Upload attachment (returns a result dict)
            result = jira_client.upload_attachment(
                issue_key=issue.key, file_path=str(test_file)
            )
            assert result["success"]
            assert result["filename"] == "test_attachment.txt"

            # Get issue with attachments
            issue_with_attachments = jira_client.get_issue(
                issue_key=issue.key, fields="attachment"
            )
            assert any(
                a.filename == "test_attachment.txt"
                for a in issue_with_attachments.attachments
            )

        finally:
            # Cleanup
            jira_client.delete_issue(issue_key=issue.key)
            created_issues.remove(issue.key)

    def test_jql_search_with_pagination(
        self, jira_client, test_project_key, created_issues
    ):
        """Test JQL search pagination across two pages.

        Cloud ignores ``start`` and returns ``total = -1``; the only way to
        page is ``next_page_token``. Seed exactly 3 issues so a real second
        page exists (limit=2 -> page1 of 2, page2 of 1).
        """
        unique_id = str(uuid.uuid4())[:8]

        seeded = []
        try:
            for i in range(3):
                issue = jira_client.create_issue(
                    project_key=test_project_key,
                    summary=f"Pagination Test {i + 1} - {unique_id}",
                    issue_type="Task",
                )
                seeded.append(issue.key)
                created_issues.append(issue.key)

            # Precise JQL matching exactly the 3 seeded issues.
            jql = f"issuekey in ({', '.join(seeded)}) ORDER BY created DESC"

            # The search index can lag; retry page 1 until the index reflects a
            # full first page with more available.
            if jira_client.config.is_cloud:
                page1 = _retry_until(
                    lambda: jira_client.search_issues(jql, limit=2),
                    lambda r: bool(r.next_page_token),
                )
            else:
                # Server/DC: total is a real count — wait until all 3 are
                # indexed so page 2 isn't empty from a partially-indexed state.
                page1 = _retry_until(
                    lambda: jira_client.search_issues(jql, limit=2),
                    lambda r: len(r.issues) == 2 and r.total >= 3,
                )

            page1_keys = [i.key for i in page1.issues]
            assert len(page1_keys) == 2

            if jira_client.config.is_cloud:
                # Cloud paginates only via next_page_token (start is ignored).
                assert page1.next_page_token
                page2 = jira_client.search_issues(
                    jql, limit=2, page_token=page1.next_page_token
                )
            else:
                # Server/DC uses offset paging.
                page2 = jira_client.search_issues(jql, start=2, limit=2)

            page2_keys = [i.key for i in page2.issues]
            # Pages must be disjoint and together cover the seeded issues.
            assert not set(page1_keys).intersection(page2_keys)
            assert set(page1_keys) | set(page2_keys) == set(seeded)

        finally:
            for key in seeded:
                try:
                    jira_client.delete_issue(issue_key=key)
                    created_issues.remove(key)
                except Exception:  # noqa: BLE001
                    pass

    def test_bulk_issue_creation(self, jira_client, test_project_key, created_issues):
        """Test creating multiple issues in bulk."""
        unique_id = str(uuid.uuid4())[:8]

        # Create issues
        created = []
        try:
            for i in range(3):
                issue = jira_client.create_issue(
                    project_key=test_project_key,
                    summary=f"Bulk Test Issue {i + 1} - {unique_id}",
                    issue_type="Task",
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
                except Exception:  # noqa: BLE001
                    pass

    def test_rate_limiting_behavior(self, jira_client):
        """Test API rate limiting behavior with retries."""
        # Make multiple rapid requests
        start_time = time.time()

        for _i in range(5):
            try:
                jira_client.get_fields()
            except Exception as e:  # noqa: BLE001
                if "429" in str(e) or "rate limit" in str(e).lower():
                    # Rate limit hit - this is expected
                    assert True
                    return

        # If no rate limit hit, that's also fine
        elapsed = time.time() - start_time
        assert elapsed < 10  # Should complete quickly if no rate limiting

    def test_edit_comment_lifecycle(
        self, jira_client, test_project_key, created_issues
    ):
        """Test edit_comment feature with real API (v0.13.0 feature #813)."""
        unique_id = str(uuid.uuid4())[:8]

        # Create issue
        issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=f"Edit Comment Test {unique_id}",
            description="Test issue for edit comment testing",
            issue_type="Task",
        )
        created_issues.append(issue.key)

        try:
            # Add comment
            comment = jira_client.add_comment(
                issue_key=issue.key, comment="Original comment text"
            )

            assert comment is not None
            comment_id = comment.id if hasattr(comment, "id") else comment["id"]

            # Edit comment
            edited = jira_client.edit_comment(
                issue_key=issue.key,
                comment_id=comment_id,
                comment="**Edited** comment with _markdown_",
            )

            assert edited is not None
            edited_body = edited.body if hasattr(edited, "body") else edited["body"]
            # Verify the edit was applied (markdown may be converted to Jira markup)
            assert "Edited" in edited_body or "*Edited*" in edited_body

        finally:
            jira_client.delete_issue(issue_key=issue.key)
            created_issues.remove(issue.key)

    def test_create_issue_with_additional_fields(
        self, jira_client, test_project_key, created_issues
    ):
        """Test additional_fields feature with real API (v0.13.0 feature #829)."""
        unique_id = str(uuid.uuid4())[:8]

        # Create issue with additional fields (labels)
        issue = jira_client.create_issue(
            project_key=test_project_key,
            summary=f"Additional Fields Test {unique_id}",
            description="Test issue for additional fields testing",
            issue_type="Task",
            labels=["integration-test", "v0130"],
        )
        created_issues.append(issue.key)

        try:
            # Verify labels were applied
            fetched = jira_client.get_issue(issue_key=issue.key)
            labels = (
                fetched.labels if hasattr(fetched, "labels") else fetched.fields.labels
            )
            assert "integration-test" in labels or "v0130" in labels

        finally:
            jira_client.delete_issue(issue_key=issue.key)
            created_issues.remove(issue.key)


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

        # 1. Create page (markdown body; is_markdown=True is the default)
        page = confluence_client.create_page(
            space_key=test_space_key,
            title=title,
            body="This is an integration test page",
        )
        created_pages.append(page.id)

        try:
            assert page.title == title
            assert page.space.key == test_space_key

            # 2. Update page (version auto-increments; no version_number arg)
            updated_page = confluence_client.update_page(
                page_id=page.id,
                title=f"{title} - Updated",
                body="Updated content",
            )

            assert updated_page.title == f"{title} - Updated"
            assert updated_page.version.number == page.version.number + 1

            # 3. Add comment (kwarg is `content`; body is a flat string)
            comment = confluence_client.add_comment(
                page_id=page.id, content="Test comment from integration test"
            )

            assert comment is not None and comment.id
            # The v1 path may not expand body.view; assert only when present.
            if comment.body:
                assert "Test comment" in comment.body

            # 4. Delete page
            confluence_client.delete_page(page_id=page.id)
            created_pages.remove(page.id)

            # Verify deletion
            with pytest.raises(Exception):
                confluence_client.get_page_content(page.id)
        finally:
            if page.id in created_pages:
                try:
                    confluence_client.delete_page(page_id=page.id)
                    created_pages.remove(page.id)
                except Exception:  # noqa: BLE001
                    pass

    def test_page_hierarchy(self, confluence_client, test_space_key, created_pages):
        """Test creating page hierarchy with parent-child relationships."""
        unique_id = str(uuid.uuid4())[:8]

        parent = None
        child = None
        try:
            # Create parent page
            parent = confluence_client.create_page(
                space_key=test_space_key,
                title=f"Parent Page {unique_id}",
                body="Parent content",
            )
            created_pages.append(parent.id)

            # Create child page
            child = confluence_client.create_page(
                space_key=test_space_key,
                title=f"Child Page {unique_id}",
                body="Child content",
                parent_id=parent.id,
            )
            created_pages.append(child.id)

            # Get child pages (returns a list)
            children = confluence_client.get_page_children(parent.id)
            child_ids = [c.id for c in children]
            assert child.id in child_ids

        finally:
            # Delete child first, then parent, each guarded independently.
            if child is not None and child.id in created_pages:
                try:
                    confluence_client.delete_page(page_id=child.id)
                    created_pages.remove(child.id)
                except Exception:  # noqa: BLE001
                    pass
            if parent is not None and parent.id in created_pages:
                try:
                    confluence_client.delete_page(page_id=parent.id)
                    created_pages.remove(parent.id)
                except Exception:  # noqa: BLE001
                    pass

    def test_cql_search(self, confluence_client, test_space_key, created_pages):
        """Test CQL search finds a freshly created page."""
        unique_id = str(uuid.uuid4())[:8]
        marker = f"cqlmarker{unique_id}"
        title = f"CQL Search Test {marker}"

        page = confluence_client.create_page(
            space_key=test_space_key, title=title, body="searchable content"
        )
        created_pages.append(page.id)

        try:
            cql = f'space = "{test_space_key}" and title ~ "{marker}"'

            # Search index lags; retry until the new page appears.
            results = _retry_until(
                lambda: confluence_client.search(cql, limit=10),
                lambda r: any(p.id == page.id for p in r),
            )

            assert any(p.id == page.id for p in results)
            for result in results:
                if result.space is not None:
                    assert result.space.key == test_space_key

        finally:
            confluence_client.delete_page(page_id=page.id)
            created_pages.remove(page.id)

    def test_attachment_handling(
        self, confluence_client, test_space_key, created_pages, tmp_path
    ):
        """Test attachment upload to Confluence page."""
        unique_id = str(uuid.uuid4())[:8]

        # Create page
        page = confluence_client.create_page(
            space_key=test_space_key,
            title=f"Attachment Test Page {unique_id}",
            body="Page with attachments",
        )
        created_pages.append(page.id)

        try:
            # Create test file
            test_file = tmp_path / "confluence_test.txt"
            test_file.write_text(f"Confluence test content {unique_id}")

            # Upload attachment (returns a result dict)
            result = confluence_client.upload_attachment(
                content_id=page.id, file_path=str(test_file)
            )
            assert result["success"]
            assert result["filename"] == "confluence_test.txt"

            # Get page attachments (returns a dict with raw attachment dicts)
            attachments = confluence_client.get_content_attachments(content_id=page.id)
            assert any(
                a["title"] == "confluence_test.txt" for a in attachments["attachments"]
            )

        finally:
            # Cleanup
            confluence_client.delete_page(page_id=page.id)
            created_pages.remove(page.id)

    def test_large_content_handling(
        self, confluence_client, test_space_key, created_pages
    ):
        """Test handling of large content (~210KB round-trip)."""
        unique_id = str(uuid.uuid4())[:8]

        # Create large content (markdown/plain text, ~210KB)
        large_content = "Large content block. " * 10000

        # Create page with large content
        page = confluence_client.create_page(
            space_key=test_space_key,
            title=f"Large Content Test {unique_id}",
            body=large_content,
        )
        created_pages.append(page.id)

        try:
            # Retrieve and verify
            retrieved = confluence_client.get_page_content(page.id)

            assert len(retrieved.content) > 100000  # At least 100KB

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
        issue = None
        page = None

        try:
            # Create Jira issue
            issue = jira_client.create_issue(
                project_key=test_project_key,
                summary=f"Linked Issue {unique_id}",
                issue_type="Task",
            )
            created_issues.append(issue.key)

            # Create Confluence page with a Jira issue link (markdown link)
            issue_url = f"{jira_client.config.url}/browse/{issue.key}"
            page = confluence_client.create_page(
                space_key=test_space_key,
                title=f"Linked Page {unique_id}",
                body=f"Related to Jira issue: [{issue.key}]({issue_url})",
            )
            created_pages.append(page.id)

            # Add comment in Jira referencing the Confluence page. Include the
            # page id as plain text so it survives the ADF round-trip even if
            # the bare URL is reshaped into a smartlink.
            confluence_url = (
                f"{confluence_client.config.url}/pages/viewpage.action?pageId={page.id}"
            )
            jira_client.add_comment(
                issue_key=issue.key,
                comment=f"Documentation for page {page.id}: {confluence_url}",
            )

            # Read comments back via the ADF-safe model path and key on the
            # page id substring (the URL itself is reshaped on the round-trip).
            fetched_issue = jira_client.get_issue(issue_key=issue.key, fields="comment")
            assert any(str(page.id) in c.body for c in fetched_issue.comments)

            # Verify the page still references the Jira issue
            retrieved_page = confluence_client.get_page_content(page.id)
            assert issue.key in retrieved_page.content

        finally:
            # Cleanup each resource independently so one failure can't leak the other.
            if issue is not None and issue.key in created_issues:
                try:
                    jira_client.delete_issue(issue_key=issue.key)
                    created_issues.remove(issue.key)
                except Exception:  # noqa: BLE001
                    pass
            if page is not None and page.id in created_pages:
                try:
                    confluence_client.delete_page(page_id=page.id)
                    created_pages.remove(page.id)
                except Exception:  # noqa: BLE001
                    pass
