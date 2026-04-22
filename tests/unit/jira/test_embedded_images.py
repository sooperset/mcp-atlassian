"""Tests for embedded image extraction from Jira rich text editor fields."""

from unittest.mock import MagicMock

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.attachments import (
    AttachmentsMixin,
    _extract_embedded_image_urls,
)

# ---------------------------------------------------------------------------
# Tests for _extract_embedded_image_urls()
# ---------------------------------------------------------------------------


class TestExtractEmbeddedImageUrls:
    """Tests for the private URL extraction helper."""

    BASE_URL = "https://jira.example.com"

    def test_jeditor_url_extracted(self) -> None:
        html = (
            '<span class="image-wrap">'
            '<img src="https://jira.example.com/plugins/servlet/'
            'jeditor_file_provider?imgId=abc123&amp;fileName=screenshot.png"'
            ' class="je-pasted-image" width="800">'
            "</span>"
        )
        result = _extract_embedded_image_urls(html, self.BASE_URL)
        assert len(result) == 1
        assert result[0]["filename"] == "screenshot.png"
        assert "jeditor_file_provider" in result[0]["url"]

    def test_ckupload_url_extracted(self) -> None:
        html = (
            '<img src="https://jira.example.com/plugins/servlet/'
            'ckupload/pastedImage.png">'
        )
        result = _extract_embedded_image_urls(html, self.BASE_URL)
        assert len(result) == 1
        assert result[0]["filename"] == "pastedImage.png"

    def test_external_urls_filtered(self) -> None:
        html = (
            '<img src="https://external-site.com/image.png">'
            '<img src="https://jira.example.com/plugins/servlet/'
            'jeditor_file_provider?imgId=1&amp;fileName=local.png">'
        )
        result = _extract_embedded_image_urls(html, self.BASE_URL)
        assert len(result) == 1
        assert result[0]["filename"] == "local.png"

    def test_formal_attachment_urls_excluded(self) -> None:
        html = (
            '<img src="https://jira.example.com/secure/attachment/'
            '12345/screenshot.png">'
            '<img src="https://jira.example.com/rest/api/2/attachment/'
            'content/67890">'
        )
        result = _extract_embedded_image_urls(html, self.BASE_URL)
        assert len(result) == 0

    def test_empty_html(self) -> None:
        assert _extract_embedded_image_urls("", self.BASE_URL) == []

    def test_no_images_in_html(self) -> None:
        html = "<p>Just some text without images</p>"
        assert _extract_embedded_image_urls(html, self.BASE_URL) == []

    def test_mixed_content(self) -> None:
        """Embedded images kept, external and formal excluded."""
        html = (
            '<p>Description</p>'
            '<img src="https://external.com/img.png">'
            '<img src="https://jira.example.com/secure/attachment/1/a.png">'
            '<img src="https://jira.example.com/plugins/servlet/'
            'jeditor_file_provider?imgId=x&amp;fileName=pasted.png">'
        )
        result = _extract_embedded_image_urls(html, self.BASE_URL)
        assert len(result) == 1
        assert result[0]["filename"] == "pasted.png"

    def test_duplicate_urls_deduplicated(self) -> None:
        url = (
            "https://jira.example.com/plugins/servlet/"
            "jeditor_file_provider?imgId=1&fileName=dup.png"
        )
        html = f'<img src="{url}"><img src="{url}">'
        result = _extract_embedded_image_urls(html, self.BASE_URL)
        assert len(result) == 1

    def test_filename_fallback_to_path_basename(self) -> None:
        html = (
            '<img src="https://jira.example.com/plugins/servlet/'
            'ckupload/my_screenshot.png">'
        )
        result = _extract_embedded_image_urls(html, self.BASE_URL)
        assert result[0]["filename"] == "my_screenshot.png"

    def test_filename_fallback_to_generated_name(self) -> None:
        html = (
            '<img src="https://jira.example.com/plugins/servlet/'
            'jeditor_file_provider?imgId=abc">'
        )
        result = _extract_embedded_image_urls(html, self.BASE_URL)
        assert result[0]["filename"] == "embedded_0.png"

    def test_img_without_src_skipped(self) -> None:
        html = '<img alt="no source">'
        assert _extract_embedded_image_urls(html, self.BASE_URL) == []


# ---------------------------------------------------------------------------
# Tests for AttachmentsMixin.get_embedded_images()
# ---------------------------------------------------------------------------


class TestGetEmbeddedImages:
    """Tests for the get_embedded_images mixin method."""

    @pytest.fixture
    def attachments_mixin(self, jira_fetcher: JiraFetcher) -> AttachmentsMixin:
        attachments_mixin = jira_fetcher
        attachments_mixin.jira = MagicMock()
        attachments_mixin.jira._session = MagicMock()
        return attachments_mixin

    def test_no_embedded_images(
        self, attachments_mixin: AttachmentsMixin
    ) -> None:
        attachments_mixin.jira.issue.return_value = {
            "fields": {"description": "plain text", "comment": {"comments": []}},
            "renderedFields": {
                "description": "<p>plain text</p>",
                "comment": {"comments": []},
            },
        }
        result = attachments_mixin.get_embedded_images("PROJ-1")
        assert result["success"] is True
        assert result["total"] == 0
        assert result["images"] == []

    def test_embedded_image_from_description(
        self, attachments_mixin: AttachmentsMixin
    ) -> None:
        base_url = attachments_mixin.config.url
        img_url = (
            f"{base_url}/plugins/servlet/jeditor_file_provider"
            "?imgId=abc&fileName=shot.png"
        )
        attachments_mixin.jira.issue.return_value = {
            "fields": {"description": "text", "comment": {"comments": []}},
            "renderedFields": {
                "description": f'<p><img src="{img_url}"></p>',
                "comment": {"comments": []},
            },
        }
        # Simuliere erfolgreichen Download
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        attachments_mixin.fetch_attachment_content = MagicMock(
            return_value=fake_png
        )

        result = attachments_mixin.get_embedded_images("PROJ-1")

        assert result["success"] is True
        assert result["total"] == 1
        assert len(result["images"]) == 1
        assert result["images"][0]["filename"] == "shot.png"
        assert result["images"][0]["source"] == "description"
        assert result["images"][0]["data"] == fake_png

    def test_embedded_image_from_comment(
        self, attachments_mixin: AttachmentsMixin
    ) -> None:
        base_url = attachments_mixin.config.url
        img_url = (
            f"{base_url}/plugins/servlet/jeditor_file_provider"
            "?imgId=xyz&fileName=comment_img.png"
        )
        attachments_mixin.jira.issue.return_value = {
            "fields": {"description": "", "comment": {"comments": []}},
            "renderedFields": {
                "description": "",
                "comment": {
                    "comments": [
                        {
                            "id": "12345",
                            "body": f'<p><img src="{img_url}"></p>',
                        }
                    ]
                },
            },
        }
        fake_png = b"\x89PNG" + b"\x00" * 50
        attachments_mixin.fetch_attachment_content = MagicMock(
            return_value=fake_png
        )

        result = attachments_mixin.get_embedded_images("PROJ-2")

        assert result["success"] is True
        assert len(result["images"]) == 1
        assert result["images"][0]["source"] == "comment"
        assert result["images"][0]["filename"] == "comment_img.png"

    def test_fetch_failure_recorded(
        self, attachments_mixin: AttachmentsMixin
    ) -> None:
        base_url = attachments_mixin.config.url
        img_url = (
            f"{base_url}/plugins/servlet/jeditor_file_provider"
            "?imgId=fail&fileName=broken.png"
        )
        attachments_mixin.jira.issue.return_value = {
            "fields": {},
            "renderedFields": {
                "description": f'<img src="{img_url}">',
                "comment": {"comments": []},
            },
        }
        attachments_mixin.fetch_attachment_content = MagicMock(
            return_value=None
        )

        result = attachments_mixin.get_embedded_images("PROJ-3")

        assert result["success"] is True
        assert result["total"] == 1
        assert len(result["images"]) == 0
        assert len(result["failed"]) == 1
        assert result["failed"][0]["filename"] == "broken.png"

    def test_oversized_image_skipped(
        self, attachments_mixin: AttachmentsMixin
    ) -> None:
        base_url = attachments_mixin.config.url
        img_url = (
            f"{base_url}/plugins/servlet/jeditor_file_provider"
            "?imgId=big&fileName=huge.png"
        )
        attachments_mixin.jira.issue.return_value = {
            "fields": {},
            "renderedFields": {
                "description": f'<img src="{img_url}">',
                "comment": {"comments": []},
            },
        }
        # 51 MB
        oversized_data = b"\x00" * (51 * 1024 * 1024)
        attachments_mixin.fetch_attachment_content = MagicMock(
            return_value=oversized_data
        )

        result = attachments_mixin.get_embedded_images("PROJ-4")

        assert result["success"] is True
        assert len(result["images"]) == 0
        assert len(result["failed"]) == 1
        assert "50 MB" in result["failed"][0]["error"]

    def test_api_error_returns_failure(
        self, attachments_mixin: AttachmentsMixin
    ) -> None:
        attachments_mixin.jira.issue.side_effect = Exception("API down")

        result = attachments_mixin.get_embedded_images("PROJ-5")

        assert result["success"] is False
        assert "API down" in result["error"]
