"""Confluence Cloud-specific operation tests (single auth - basic)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

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


class TestConfluenceCloudAttachments:
    """Attachment upload/versioning through the fetcher API."""

    def test_upload_attachment_creates_new_version(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
        tmp_path: Path,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Attachment Test {uid}",
            body="<p>For attachment upload testing.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        attachment_path = tmp_path / f"cloud upload {uid} & notes #1.txt"
        attachment_path.write_text(f"first upload {uid}", encoding="utf-8")

        first = confluence_fetcher.upload_attachment(
            content_id=page.id,
            file_path=str(attachment_path),
            comment="first upload",
        )
        assert first["success"] is True
        assert first["filename"] == attachment_path.name
        assert first["id"]

        attachment_path.write_text(f"second upload {uid}", encoding="utf-8")
        second = confluence_fetcher.upload_attachment(
            content_id=page.id,
            file_path=str(attachment_path),
            comment="second upload",
        )
        assert second["success"] is True
        assert second["id"] == first["id"]

        attachments = confluence_fetcher.get_content_attachments(
            content_id=page.id,
            filename=attachment_path.name,
        )
        matching = [
            attachment
            for attachment in attachments["attachments"]
            if attachment["title"] == attachment_path.name
        ]
        assert len(matching) == 1
        if "version" in matching[0]:
            assert matching[0]["version"]["number"] >= 2


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

        children = []
        for _ in range(6):
            children = confluence_fetcher.get_page_children(
                page_id=parent.id,
                include_folders=False,
            )
            if any(page.id == child.id for page in children):
                break
            time.sleep(2)

        assert any(page.id == child.id for page in children)


class TestConfluenceCloudPageLayout:
    """Page width and table layout handling."""

    def test_markdown_table_layout_and_page_width(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Layout Test {uid}",
            body="| Alpha | Beta |\n| --- | --- |\n| one | two |",
            page_width="full-width",
            table_layout="full-width",
        )
        resource_tracker.add_confluence_page(page.id)

        assert page.page_width == "full-width"

        raw_page = confluence_fetcher.confluence.get_page_by_id(
            page.id,
            expand="body.storage,version",
        )
        storage_body = raw_page["body"]["storage"]["value"]
        assert 'data-layout="full-width"' in storage_body
        assert 'data-table-width="1800"' in storage_body


class TestConfluenceCloudCopyAndRestrictions:
    """Page copy and restriction operations."""

    def test_copy_page(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        source = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Copy Source {uid}",
            body=f"<p>Cloud copy source {uid}</p>",
            is_markdown=False,
            content_representation="storage",
        )
        resource_tracker.add_confluence_page(source.id)

        copied = confluence_fetcher.copy_page(
            source_page_id=source.id,
            destination_space_key=cloud_instance.space_key,
            new_title=f"Cloud E2E Copy Target {uid}",
        )
        resource_tracker.add_confluence_page(copied.id)

        assert copied.id != source.id
        assert copied.title == f"Cloud E2E Copy Target {uid}"
        copied_raw = confluence_fetcher.get_page_content(
            copied.id,
            convert_to_markdown=False,
        )
        assert f"Cloud copy source {uid}" in (copied_raw.content or "")

    def test_set_and_get_page_restrictions(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Restrictions Test {uid}",
            body="<p>Restriction test.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        current_user = confluence_fetcher.confluence.get(
            f"{confluence_fetcher._v1_rest_base_url()}/rest/api/user/current",
            absolute=True,
        )
        account_id = current_user.get("accountId")
        if not account_id:
            pytest.skip("Current Cloud user response did not include accountId")

        try:
            result = confluence_fetcher.set_page_restrictions(
                page.id,
                read_users=[account_id],
                edit_users=[account_id],
            )
            assert result["read"]["users"] == [account_id]
            assert result["update"]["users"] == [account_id]

            restrictions = confluence_fetcher.get_page_restrictions(page.id)
            assert account_id in restrictions["read"]["users"]
            assert account_id in restrictions["update"]["users"]
        finally:
            confluence_fetcher.set_page_restrictions(page.id)


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

    def test_add_and_get_inline_comments(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        anchor = f"cloud inline anchor {uid}"
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Inline Comment Test {uid}",
            body=f"<p>Before {anchor} after.</p>",
            is_markdown=False,
            content_representation="storage",
        )
        resource_tracker.add_confluence_page(page.id)

        comment = confluence_fetcher.add_inline_comment(
            page_id=page.id,
            content=f"Cloud E2E inline test comment {uid}",
            text_selection=anchor,
        )
        assert comment is not None
        assert comment.location == "inline"

        comments = confluence_fetcher.get_inline_comments(page.id)
        assert any(inline_comment.id == comment.id for inline_comment in comments)
