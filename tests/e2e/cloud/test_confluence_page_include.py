"""get_page include param: inline comments, labels, views.

Regression for https://github.com/sooperset/mcp-atlassian/issues/1103
"""

from __future__ import annotations

import uuid

import pytest

from mcp_atlassian.confluence import ConfluenceFetcher

from .conftest import CloudInstanceInfo, CloudResourceTracker

pytestmark = pytest.mark.cloud_e2e


class TestGetPageIncludeEnrichments:
    """get_page include param inlines comments, labels, views.

    Regression for https://github.com/sooperset/mcp-atlassian/issues/1103
    """

    def test_include_comments(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Include comments test {uid}",
            body="<p>Testing include param.</p>",
            is_markdown=False,
        )
        resource_tracker.add_confluence_page(page.id)

        # Add a comment
        confluence_fetcher.add_comment(page.id, "Test comment for include")

        # Verify comments can be retrieved
        comments = confluence_fetcher.get_page_comments(page.id)
        assert len(comments) >= 1

    def test_include_labels(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Include labels test {uid}",
            body="<p>Testing labels include.</p>",
            is_markdown=False,
        )
        resource_tracker.add_confluence_page(page.id)

        # Add a label
        confluence_fetcher.add_page_label(page.id, "test-label")

        # Verify labels can be retrieved
        labels = confluence_fetcher.get_page_labels(page.id)
        assert len(labels) >= 1
