"""Confluence DC-specific operation tests (single auth - basic)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

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


class TestConfluenceDCAttachments:
    """Attachment upload/versioning through the fetcher API."""

    def test_upload_attachment_creates_new_version(
        self,
        confluence_fetcher: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
        tmp_path: Path,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Attachment Test {uid}",
            body="<p>For attachment upload testing.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        attachment_path = tmp_path / f"dc upload {uid} & notes #1.txt"
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


class TestConfluenceDCPageLayout:
    """Page width and table layout handling."""

    def test_markdown_table_layout_and_page_width(
        self,
        confluence_fetcher: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Layout Test {uid}",
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


class TestConfluenceDCCopyAndRestrictions:
    """Page copy and restriction operations."""

    def test_copy_page(
        self,
        confluence_fetcher: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        source = confluence_fetcher.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Copy Source {uid}",
            body=f"<p>DC copy source {uid}</p>",
            is_markdown=False,
            content_representation="storage",
        )
        resource_tracker.add_confluence_page(source.id)

        copied = confluence_fetcher.copy_page(
            source_page_id=source.id,
            destination_space_key=dc_instance.space_key,
            new_title=f"E2E Copy Target {uid}",
        )
        resource_tracker.add_confluence_page(copied.id)

        assert copied.id != source.id
        assert copied.title == f"E2E Copy Target {uid}"
        copied_raw = confluence_fetcher.get_page_content(
            copied.id,
            convert_to_markdown=False,
        )
        assert f"DC copy source {uid}" in (copied_raw.content or "")

    def test_set_and_get_page_restrictions(
        self,
        confluence_fetcher: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Restrictions Test {uid}",
            body="<p>Restriction test.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        try:
            result = confluence_fetcher.set_page_restrictions(
                page.id,
                read_users=[dc_instance.admin_username],
                edit_users=[dc_instance.admin_username],
            )
            assert result["read"]["users"] == [dc_instance.admin_username]
            assert result["update"]["users"] == [dc_instance.admin_username]

            restrictions = confluence_fetcher.get_page_restrictions(page.id)
            assert dc_instance.admin_username in restrictions["read"]["users"]
            assert dc_instance.admin_username in restrictions["update"]["users"]
        finally:
            confluence_fetcher.set_page_restrictions(page.id)


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

    def test_add_and_get_inline_comments(
        self,
        confluence_fetcher: ConfluenceFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        anchor = f"inline anchor {uid}"
        page = confluence_fetcher.create_page(
            space_key=dc_instance.space_key,
            title=f"E2E Inline Comment Test {uid}",
            body=f"<p>Before {anchor} after.</p>",
            is_markdown=False,
            content_representation="storage",
        )
        resource_tracker.add_confluence_page(page.id)

        comment = confluence_fetcher.add_inline_comment(
            page_id=page.id,
            content=f"E2E inline test comment {uid}",
            text_selection=anchor,
        )
        assert comment is not None
        assert comment.location == "inline"

        comments = confluence_fetcher.get_inline_comments(page.id)
        assert any(inline_comment.id == comment.id for inline_comment in comments)
