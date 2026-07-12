"""Confluence Cloud-specific operation tests (single auth - basic)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest
import requests

from mcp_atlassian.confluence import ConfluenceFetcher

from .conftest import CloudInstanceInfo, CloudResourceTracker

pytestmark = pytest.mark.cloud_e2e


def _get_cloud_account_id(cloud_instance: CloudInstanceInfo) -> str:
    """Return the current Atlassian account ID from Jira Cloud."""
    response = requests.get(
        f"{cloud_instance.jira_url}/rest/api/3/myself",
        auth=(cloud_instance.username, cloud_instance.api_token),
        timeout=15,
    )
    response.raise_for_status()
    return str(response.json()["accountId"])


def _get_cloud_space_id(cloud_instance: CloudInstanceInfo) -> str:
    """Return the numeric Confluence space ID for the configured space key."""
    response = requests.get(
        f"{cloud_instance.confluence_url}/api/v2/spaces",
        params={"keys": cloud_instance.space_key, "limit": "1"},
        auth=(cloud_instance.username, cloud_instance.api_token),
        timeout=15,
    )
    response.raise_for_status()
    for space in response.json().get("results", []):
        if space.get("key") == cloud_instance.space_key:
            return str(space["id"])
    raise AssertionError(f"Space {cloud_instance.space_key} not found")


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


class TestConfluenceCloudPermissions:
    """Cloud-only permission inspection APIs."""

    def test_check_content_permissions(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        account_id = _get_cloud_account_id(cloud_instance)

        result = confluence_fetcher.check_content_permissions(
            content_id=cloud_instance.test_page_id,
            user_identifier=account_id,
            operation="read",
        )

        assert result["hasPermission"] is True

    def test_get_space_permissions(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        space_id = _get_cloud_space_id(cloud_instance)

        result = confluence_fetcher.get_space_permissions(space_id=space_id, limit=1)

        assert isinstance(result.get("results"), list)


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


class TestConfluenceCloudPageSubtype:
    """Cloud page subtype operations."""

    def test_create_live_doc_page(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        """Create a Live Doc and expose its subtype in the returned model."""
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Live Doc Test {uid}",
            body="<p>Created as a Live Doc.</p>",
            is_markdown=False,
            content_representation="storage",
            subtype="live",
        )
        resource_tracker.add_confluence_page(page.id)

        assert page.subtype == "live"
        assert page.to_simplified_dict()["subtype"] == "live"

    def test_markdown_task_lists_use_confluence_storage_macros(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Task List {uid}",
            body="- [ ] Todo item\n- [x] Done item",
        )
        resource_tracker.add_confluence_page(page.id)

        raw_page = confluence_fetcher.confluence.get_page_by_id(
            page.id,
            expand="body.storage",
        )
        storage_body = raw_page["body"]["storage"]["value"]
        assert "<ac:task-list>" in storage_body
        assert "<ac:task-status>incomplete</ac:task-status>" in storage_body
        assert "<ac:task-status>complete</ac:task-status>" in storage_body


class TestConfluenceCloudTemplates:
    """Cloud page template operations."""

    def test_page_template_workflow(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        marker = f"template-marker-{uid}"
        created_template = confluence_fetcher.confluence.create_or_update_template(
            name=f"Cloud E2E Template {uid}",
            body={
                "storage": {
                    "value": f"<h1>Template E2E</h1><p>{marker}</p>",
                    "representation": "storage",
                }
            },
            description="Temporary MCP template test",
            space=cloud_instance.space_key,
        )
        template_id = str(created_template["templateId"])

        try:
            templates = confluence_fetcher.list_page_templates(
                space_key=cloud_instance.space_key,
                limit=200,
            )
            assert any(
                str(template.get("templateId")) == template_id for template in templates
            )

            template = confluence_fetcher.get_page_template(template_id)
            template_body = template["body"]["storage"]["value"]
            assert marker in template_body

            page = confluence_fetcher.create_page_from_template(
                space_key=cloud_instance.space_key,
                title=f"Cloud E2E Template Page {uid}",
                template_id=template_id,
            )
            resource_tracker.add_confluence_page(str(page["id"]))

            raw_page = confluence_fetcher.confluence.get_page_by_id(
                str(page["id"]),
                expand="body.storage",
            )
            assert marker in raw_page["body"]["storage"]["value"]
        finally:
            confluence_fetcher.confluence.remove_template(template_id)


class TestConfluenceCloudAttachments:
    """Attachment upload/versioning through the fetcher API."""

    def test_upload_attachment_creates_new_version(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
        workspace_tmp_path: Path,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Attachment Test {uid}",
            body="<p>For attachment upload testing.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        attachment_path = workspace_tmp_path / f"cloud upload {uid} & notes #1.txt"
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

    def test_reply_to_comment_preserves_body(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        """Cloud replies retain their body in the page comment thread."""
        uid = uuid.uuid4().hex[:8]
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Reply Test {uid}",
            body="<p>For reply testing.</p>",
        )
        resource_tracker.add_confluence_page(page.id)

        parent = confluence_fetcher.add_comment(
            page_id=page.id,
            content=f"Cloud E2E parent comment {uid}",
        )
        assert parent is not None

        reply = confluence_fetcher.reply_to_comment(
            comment_id=parent.id,
            content=f"Cloud E2E reply body {uid}",
        )
        assert reply is not None

        comments = confluence_fetcher.get_page_comments(page.id)
        assert any(
            f"Cloud E2E reply body {uid}" in comment.body for comment in comments
        )

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


class TestConfluenceDateLozenge:
    """Date lozenges in storage format are preserved in page content.

    Regression for https://github.com/sooperset/mcp-atlassian/issues/897
    """

    def test_date_lozenge_preserved_in_page_content(
        self,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        storage_body = '<p>Meeting date: <time datetime="2026-02-04" /></p>'
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Cloud E2E Date Lozenge Test {uid}",
            body=storage_body,
            is_markdown=False,
            content_representation="storage",
        )
        resource_tracker.add_confluence_page(page.id)
        fetched = confluence_fetcher.get_page_content(page.id)
        content = fetched.content or ""
        assert "2026-02-04" in content, (
            f"Date lozenge value missing from content. Got: {content[:500]}"
        )
