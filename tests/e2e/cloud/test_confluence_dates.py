"""E2E tests for Confluence page date fields (upstream #965)."""

from __future__ import annotations

import uuid

import pytest

from mcp_atlassian.confluence import ConfluenceFetcher

from .conftest import CloudInstanceInfo, CloudResourceTracker

pytestmark = pytest.mark.cloud_e2e


class TestConfluencePageDateFields:
    """ConfluencePage.created and .updated fields are always empty.

    Regression for https://github.com/sooperset/mcp-atlassian/issues/965
    Same root cause as #607: 'history' not included in expand params.
    Test FAILS until history is added to expand in pages.py.
    """

    def test_page_created_date_populated(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Date fields test {uid}",
            body="<p>Testing date fields.</p>",
            is_markdown=False,
        )
        resource_tracker.add_confluence_page(page.id)
        fetched = confluence_fetcher.get_page_content(page.id)
        assert fetched.created, (
            "ConfluencePage.created is empty — 'history' missing from expand params"
        )

    def test_page_updated_date_populated(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Updated date test {uid}",
            body="<p>Testing updated date field.</p>",
            is_markdown=False,
        )
        resource_tracker.add_confluence_page(page.id)
        fetched = confluence_fetcher.get_page_content(page.id)
        assert fetched.updated, (
            "ConfluencePage.updated is empty — 'history' missing from expand params"
        )
