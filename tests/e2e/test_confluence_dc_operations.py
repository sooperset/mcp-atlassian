"""Confluence DC-specific operation tests (single auth - basic)."""

from __future__ import annotations

import uuid

import pytest

from mcp_atlassian.confluence import ConfluenceFetcher

from .conftest import DCInstanceInfo, DCResourceTracker

pytestmark = pytest.mark.dc_e2e


class TestConfluenceDCBehavior:
    """Tests for DC-specific Confluence behavior."""

    def test_is_not_cloud(self, confluence_fetcher: ConfluenceFetcher) -> None:
        assert confluence_fetcher.config.is_cloud is False

    def test_no_wiki_prefix(self, dc_instance: DCInstanceInfo) -> None:
        """DC Confluence URL should not have /wiki prefix."""
        assert "/wiki" not in dc_instance.confluence_url


class TestConfluenceDCStorageFormat:
    """Storage format content creation."""

    def test_create_storage_format_page(
        self,
        confluence_fetcher: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        storage_content = (
            "<h1>E2E Storage Format Test</h1>"
            "<p>This page uses <strong>storage format</strong>.</p>"
            "<ul><li>Item 1</li><li>Item 2</li></ul>"
        )
        page = confluence_fetcher.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Storage Test {uid}",
            body=storage_content,
        )
        resource_tracker.add_confluence_page(page.id)
        assert page.id is not None


class TestConfluenceDCPageHierarchy:
    """Page hierarchy (parent/child pages)."""

    def test_create_child_page(
        self,
        confluence_fetcher: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        parent = confluence_fetcher.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Parent Page {uid}",
            body="<p>Parent page.</p>",
        )
        resource_tracker.add_confluence_page(parent.id)

        child = confluence_fetcher.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Child Page {uid}",
            body="<p>Child page.</p>",
            parent_id=parent.id,
        )
        resource_tracker.add_confluence_page(child.id)
        assert child.id is not None


class TestConfluenceDCLabels:
    """Label operations."""

    def test_add_label(
        self,
        confluence_fetcher: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Label Test {uid}",
            body="<p>For label testing.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        labels = confluence_fetcher.add_page_label(page_id=page.id, name="e2e-test")
        assert labels is not None


class TestConfluenceDCComments:
    """Comment operations."""

    def test_add_and_get_comments(
        self,
        confluence_fetcher: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Comment Test {uid}",
            body="<p>For comment testing.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        comment = confluence_fetcher.add_comment(
            page_id=page.id,
            content=f"E2E test comment {uid}",
        )
        assert comment is not None

        comments = confluence_fetcher.get_page_comments(page.id)
        assert len(comments) > 0
