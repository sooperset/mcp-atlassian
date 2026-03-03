"""Confluence Cloud-specific operation tests (single auth - basic)."""

from __future__ import annotations

import uuid

import pytest

from mcp_atlassian.confluence import ConfluenceFetcher

from .conftest import CloudInstanceInfo, CloudResourceTracker

pytestmark = pytest.mark.cloud_e2e


class TestConfluenceCloudBehavior:
    """Tests for Cloud-specific Confluence behavior."""

    def test_is_cloud(self, confluence_fetcher: ConfluenceFetcher) -> None:
        assert confluence_fetcher.config.is_cloud is True

    def test_wiki_prefix_in_url(self, cloud_instance: CloudInstanceInfo) -> None:
        """Cloud Confluence URL should contain /wiki."""
        assert "/wiki" in cloud_instance.confluence_url


class TestConfluenceCloudAnalytics:
    """Cloud-only Analytics API."""

    def test_get_page_views(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """get_page_views() should work on Cloud (not raise ValueError)."""
        result = confluence_fetcher.get_page_views(cloud_instance.test_page_id)
        assert result is not None
        assert result.page_id == cloud_instance.test_page_id


class TestConfluenceCloudStorageFormat:
    """Storage format content creation."""

    def test_create_storage_format_page(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        storage_content = (
            "<h1>Cloud E2E Storage Format Test</h1>"
            "<p>This page uses <strong>storage format</strong>.</p>"
            "<ul><li>Item 1</li><li>Item 2</li></ul>"
        )
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Storage Test {uid}",
            body=storage_content,
            is_markdown=False,
            content_representation="storage",
        )
        resource_tracker.add_confluence_page(page.id)
        assert page.id is not None


class TestConfluenceCloudPageHierarchy:
    """Page hierarchy (parent/child pages)."""

    def test_create_child_page(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        parent = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Parent Page {uid}",
            body="<p>Parent page.</p>",
        )
        resource_tracker.add_confluence_page(parent.id)

        child = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Child Page {uid}",
            body="<p>Child page.</p>",
            parent_id=parent.id,
        )
        resource_tracker.add_confluence_page(child.id)
        assert child.id is not None


class TestConfluenceCloudLabels:
    """Label operations on Cloud."""

    def test_add_label(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Label Test {uid}",
            body="<p>For label testing.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        labels = confluence_fetcher.add_page_label(page_id=page.id, name="e2e-test")
        assert labels is not None


class TestConfluenceCloudComments:
    """Comment operations on Cloud."""

    def test_add_and_get_comments(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Comment Test {uid}",
            body="<p>For comment testing.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        comment = confluence_fetcher.add_comment(
            page_id=page.id,
            content=f"Cloud E2E test comment {uid}",
        )
        assert comment is not None

        comments = confluence_fetcher.get_page_comments(page.id)
        assert len(comments) > 0
