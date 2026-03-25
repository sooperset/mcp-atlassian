"""E2E tests for Confluence page metadata fields (upstream #607)."""

from __future__ import annotations

import uuid

import pytest

from mcp_atlassian.confluence import ConfluenceFetcher

from .conftest import CloudInstanceInfo, CloudResourceTracker

pytestmark = pytest.mark.cloud_e2e


class TestConfluencePageMetadata:
    """Page metadata fields (created, updated, author) are populated.

    Regression for https://github.com/sooperset/mcp-atlassian/issues/607
    Root cause: get_page_content() missing 'history' in expand params.
    Fix: add 'history' to expand string in pages.py lines 66 and 75.
    Branch sits here until fix is implemented — test currently FAILS.
    """

    def test_page_has_created_date(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Metadata Test {uid}",
            body="<p>Testing metadata retrieval.</p>",
            is_markdown=False,
        )
        resource_tracker.add_confluence_page(page.id)
        fetched = confluence_fetcher.get_page_content(page.id)
        assert fetched.created, "created date is empty — 'history' missing from expand"

    def test_page_has_last_modified(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Modified Test {uid}",
            body="<p>Testing metadata retrieval.</p>",
            is_markdown=False,
        )
        resource_tracker.add_confluence_page(page.id)
        fetched = confluence_fetcher.get_page_content(page.id)
        assert fetched.updated, "updated date is empty — 'history' missing from expand"

    def test_page_has_author(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Author Test {uid}",
            body="<p>Testing author retrieval.</p>",
            is_markdown=False,
        )
        resource_tracker.add_confluence_page(page.id)
        fetched = confluence_fetcher.get_page_content(page.id)
        assert fetched.author is not None, "author is None — not returned by API"
