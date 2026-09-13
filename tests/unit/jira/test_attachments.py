"""Tests for the Jira attachments module."""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.attachments import AttachmentsMixin

# Test scenarios for AttachmentsMixin
#
# 1. Single Attachment Download (download_attachment method):
#    - Success case: Downloads attachment correctly with proper HTTP response
#    - Path handling: Converts relative path to absolute path
#    - Error cases:
#      - No URL provided
#      - HTTP error during download
#      - File write error
#      - File not created after write operation
#
# 2. Issue Attachments Download (download_issue_attachments method):
#    - Success case: Downloads all attachments for an issue
#    - Path handling: Converts relative target directory to absolute path
#    - Edge cases:
#      - Issue has no attachments
#      - Issue not found
#      - Issue has no fields
#      - Some attachments fail to download
#      - Attachment has missing URL
#
# 3. Single Attachment Upload (upload_attachment method):
#    - Success case: Uploads file correctly
#    - Path handling: Converts relative file path to absolute path
#    - Error cases:
#      - No issue key provided
#      - No file path provided
#      - File not found
#      - API error during upload
#      - No response from API
#
# 4. Multiple Attachments Upload (upload_attachments method):
#    - Success case: Uploads multiple files correctly
#    - Partial success: Some files upload successfully, others fail
#    - Error cases:
#      - Empty list of file paths
#      - No issue key provided


class TestAttachmentsMixin:
    """Tests for the AttachmentsMixin class."""

    @pytest.fixture
    def attachments_mixin(self, jira_fetcher: JiraFetcher) -> AttachmentsMixin:
        """Set up test fixtures before each test method."""
        # Create a mock Jira client
        attachments_mixin = jira_fetcher
        attachments_mixin.jira = MagicMock()
        attachments_mixin.jira._session = MagicMock()
        return attachments_mixin

    def test_download_attachment_success(self, attachments_mixin: AttachmentsMixin):
        """Test successful attachment download."""
        import os

        # Mock the response
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status = MagicMock()
        attachments_mixin.jira._session.get.return_value = mock_response

        # A subdirectory of CWD (downloads may not land in the CWD root itself).
        download_path = "/tmp/downloads/test_file.txt"
        expected_path = os.path.abspath(download_path)

        # Mock file operations
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("os.path.exists") as mock_exists,
            patch("os.path.getsize") as mock_getsize,
            patch("os.makedirs") as mock_makedirs,
            patch("os.getcwd", return_value="/tmp"),
        ):
            mock_exists.return_value = True
            mock_getsize.return_value = 12  # Length of "test content"

            # Call the method
            result = attachments_mixin.download_attachment(
                "https://test.url/attachment", download_path
            )

            # Assertions
            assert result is True
            attachments_mixin.jira._session.get.assert_called_once_with(
                "https://test.url/attachment", stream=True
            )
            mock_file.assert_called_once_with(expected_path, "wb")
            mock_file().write.assert_called_once_with(b"test content")
            mock_makedirs.assert_called_once()

    def test_download_attachment_relative_path(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test attachment download with a relative path."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status = MagicMock()
        attachments_mixin.jira._session.get.return_value = mock_response

        # Mock file operations and os.path.abspath
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("os.path.exists") as mock_exists,
            patch("os.path.getsize") as mock_getsize,
            patch("os.makedirs") as mock_makedirs,
            patch("os.path.abspath") as mock_abspath,
            patch("os.path.isabs") as mock_isabs,
            patch("os.getcwd", return_value="/absolute/path"),
            patch("mcp_atlassian.jira.attachments.validate_safe_path"),
        ):
            mock_exists.return_value = True
            mock_getsize.return_value = 12
            mock_isabs.return_value = False
            # Target a subdirectory (downloads may not land in the CWD root itself).
            mock_abspath.side_effect = lambda p: (
                "/absolute/path/downloads/test_file.txt"
                if p == "downloads/test_file.txt"
                else p
            )

            # Call the method with a relative path
            result = attachments_mixin.download_attachment(
                "https://test.url/attachment", "downloads/test_file.txt"
            )

            # Assertions
            assert result is True
            mock_isabs.assert_any_call("downloads/test_file.txt")
            mock_abspath.assert_any_call("downloads/test_file.txt")
            mock_file.assert_called_once_with(
                "/absolute/path/downloads/test_file.txt", "wb"
            )

    def test_download_attachment_no_url(self, attachments_mixin: AttachmentsMixin):
        """Test attachment download with no URL."""
        result = attachments_mixin.download_attachment("", "/tmp/test_file.txt")
        assert result is False

    def test_download_attachment_http_error(self, attachments_mixin: AttachmentsMixin):
        """Test attachment download with an HTTP error."""
        # Mock the response to raise an HTTP error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        attachments_mixin.jira._session.get.return_value = mock_response

        result = attachments_mixin.download_attachment(
            "https://test.url/attachment", "/tmp/test_file.txt"
        )
        assert result is False

    def test_download_attachment_file_write_error(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test attachment download with a file write error."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status = MagicMock()
        attachments_mixin.jira._session.get.return_value = mock_response

        # Mock file operations to raise an exception during write
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("os.makedirs") as mock_makedirs,
        ):
            mock_file().write.side_effect = OSError("Write error")

            result = attachments_mixin.download_attachment(
                "https://test.url/attachment", "/tmp/test_file.txt"
            )
            assert result is False

    def test_download_attachment_file_not_created(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test attachment download when file is not created."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status = MagicMock()
        attachments_mixin.jira._session.get.return_value = mock_response

        # Mock file operations
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("os.path.exists") as mock_exists,
            patch("os.makedirs") as mock_makedirs,
        ):
            mock_exists.return_value = False  # File doesn't exist after write

            result = attachments_mixin.download_attachment(
                "https://test.url/attachment", "/tmp/test_file.txt"
            )
            assert result is False

    def test_download_issue_attachments_success(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test successful download of all issue attachments."""
        # Mock the issue data
        mock_issue = {
            "fields": {
                "attachment": [
                    {
                        "filename": "test1.txt",
                        "content": "https://test.url/attachment1",
                        "size": 100,
                    },
                    {
                        "filename": "test2.txt",
                        "content": "https://test.url/attachment2",
                        "size": 200,
                    },
                ]
            }
        }
        attachments_mixin.jira.issue.return_value = mock_issue

        # Mock JiraAttachment.from_api_response
        mock_attachment1 = MagicMock()
        mock_attachment1.filename = "test1.txt"
        mock_attachment1.url = "https://test.url/attachment1"
        mock_attachment1.size = 100

        mock_attachment2 = MagicMock()
        mock_attachment2.filename = "test2.txt"
        mock_attachment2.url = "https://test.url/attachment2"
        mock_attachment2.size = 200

        # Mock the download_attachment method
        with (
            patch.object(
                attachments_mixin, "download_attachment", return_value=True
            ) as mock_download,
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                side_effect=[mock_attachment1, mock_attachment2],
            ),
            patch("os.getcwd", return_value="/tmp"),
        ):
            result = attachments_mixin.download_issue_attachments(
                "TEST-123", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is True
            assert len(result["downloaded"]) == 2
            assert len(result["failed"]) == 0
            assert result["total"] == 2
            assert result["issue_key"] == "TEST-123"
            assert mock_download.call_count == 2
            mock_mkdir.assert_called_once()

    def test_download_issue_attachments_relative_path(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test download issue attachments with a relative path."""
        # Mock the issue data
        mock_issue = {
            "fields": {
                "attachment": [
                    {
                        "filename": "test1.txt",
                        "content": "https://test.url/attachment1",
                        "size": 100,
                    }
                ]
            }
        }
        attachments_mixin.jira.issue.return_value = mock_issue

        # Mock attachment
        mock_attachment = MagicMock()
        mock_attachment.filename = "test1.txt"
        mock_attachment.url = "https://test.url/attachment1"
        mock_attachment.size = 100

        # Mock path operations
        with (
            patch.object(
                attachments_mixin, "download_attachment", return_value=True
            ) as mock_download,
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                return_value=mock_attachment,
            ),
            patch("os.path.isabs") as mock_isabs,
            patch("os.path.abspath") as mock_abspath,
            patch("os.getcwd", return_value="/absolute/path"),
            patch("mcp_atlassian.jira.attachments.validate_safe_path"),
        ):
            mock_isabs.return_value = False
            mock_abspath.return_value = "/absolute/path/attachments"

            result = attachments_mixin.download_issue_attachments(
                "TEST-123", "attachments"
            )

            # Assertions
            assert result["success"] is True
            mock_isabs.assert_called_once_with("attachments")
            mock_abspath.assert_called_once_with("attachments")

    def test_download_issue_attachments_no_attachments(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test download when issue has no attachments."""
        # Mock the issue data with no attachments
        mock_issue = {"fields": {"attachment": []}}
        attachments_mixin.jira.issue.return_value = mock_issue

        with (
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch("os.getcwd", return_value="/tmp"),
        ):
            result = attachments_mixin.download_issue_attachments(
                "TEST-123", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is True
            assert "No attachments found" in result["message"]
            assert len(result["downloaded"]) == 0
            assert len(result["failed"]) == 0
            mock_mkdir.assert_called_once()

    def test_download_issue_attachments_issue_not_found(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test download when issue cannot be retrieved."""
        attachments_mixin.jira.issue.return_value = None

        with (
            patch("os.getcwd", return_value="/tmp"),
            pytest.raises(
                TypeError,
                match="Unexpected return value type from `jira.issue`: <class 'NoneType'>",
            ),
        ):
            attachments_mixin.download_issue_attachments("TEST-123", "/tmp/attachments")

    def test_download_issue_attachments_no_fields(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test download when issue has no fields."""
        # Mock the issue data with no fields
        mock_issue = {}  # Missing 'fields' key
        attachments_mixin.jira.issue.return_value = mock_issue

        with patch("os.getcwd", return_value="/tmp"):
            result = attachments_mixin.download_issue_attachments(
                "TEST-123", "/tmp/attachments"
            )

        # Assertions
        assert result["success"] is False
        assert "Could not retrieve issue" in result["error"]

    def test_download_issue_attachments_some_failures(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test download when some attachments fail to download."""
        # Mock the issue data
        mock_issue = {
            "fields": {
                "attachment": [
                    {
                        "filename": "test1.txt",
                        "content": "https://test.url/attachment1",
                        "size": 100,
                    },
                    {
                        "filename": "test2.txt",
                        "content": "https://test.url/attachment2",
                        "size": 200,
                    },
                ]
            }
        }
        attachments_mixin.jira.issue.return_value = mock_issue

        # Mock attachments
        mock_attachment1 = MagicMock()
        mock_attachment1.filename = "test1.txt"
        mock_attachment1.url = "https://test.url/attachment1"
        mock_attachment1.size = 100

        mock_attachment2 = MagicMock()
        mock_attachment2.filename = "test2.txt"
        mock_attachment2.url = "https://test.url/attachment2"
        mock_attachment2.size = 200

        # Mock the download_attachment method to succeed for first attachment and fail for second
        with (
            patch.object(
                attachments_mixin, "download_attachment", side_effect=[True, False]
            ) as mock_download,
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                side_effect=[mock_attachment1, mock_attachment2],
            ),
            patch("os.getcwd", return_value="/tmp"),
        ):
            result = attachments_mixin.download_issue_attachments(
                "TEST-123", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is True
            assert len(result["downloaded"]) == 1
            assert len(result["failed"]) == 1
            assert result["downloaded"][0]["filename"] == "test1.txt"
            assert result["failed"][0]["filename"] == "test2.txt"
            assert mock_download.call_count == 2

    def test_download_issue_attachments_missing_url(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test download when an attachment has no URL."""
        # Mock the issue data
        mock_issue = {
            "fields": {
                "attachment": [
                    {
                        "filename": "test1.txt",
                        "content": "https://test.url/attachment1",
                        "size": 100,
                    }
                ]
            }
        }
        attachments_mixin.jira.issue.return_value = mock_issue

        # Mock attachment with no URL
        mock_attachment = MagicMock()
        mock_attachment.filename = "test1.txt"
        mock_attachment.url = None  # No URL
        mock_attachment.size = 100

        # Mock path operations
        with (
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                return_value=mock_attachment,
            ),
            patch("os.getcwd", return_value="/tmp"),
        ):
            result = attachments_mixin.download_issue_attachments(
                "TEST-123", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is True
            assert len(result["downloaded"]) == 0
            assert len(result["failed"]) == 1
            assert result["failed"][0]["filename"] == "test1.txt"
            assert "No URL available" in result["failed"][0]["error"]

    # Tests for upload_attachment method

    def test_upload_attachment_success(self, attachments_mixin: AttachmentsMixin):
        """Test successful attachment upload."""
        # Mock the Jira API response
        mock_attachment_response = {
            "id": "12345",
            "filename": "test_file.txt",
            "size": 100,
        }
        attachments_mixin.jira.add_attachment.return_value = mock_attachment_response

        # Mock file operations
        with (
            # Pin the workspace so the absolute path resolves inside it — keeps
            # validate_safe_path passing deterministically across Python versions
            # (mocking os.path.abspath does not reach pathlib.Path.resolve on 3.13).
            patch("os.getcwd", return_value="/absolute/path"),
            patch("os.path.exists") as mock_exists,
            patch("os.path.getsize") as mock_getsize,
            patch("os.path.isabs") as mock_isabs,
            patch("os.path.abspath") as mock_abspath,
            patch("os.path.basename") as mock_basename,
            patch("builtins.open", mock_open(read_data=b"test content")),
        ):
            mock_exists.return_value = True
            mock_getsize.return_value = 100
            mock_isabs.return_value = True
            mock_abspath.return_value = "/absolute/path/test_file.txt"
            mock_basename.return_value = "test_file.txt"

            # Call the method
            result = attachments_mixin.upload_attachment(
                "TEST-123", "/absolute/path/test_file.txt"
            )

            # Assertions
            assert result["success"] is True
            assert result["issue_key"] == "TEST-123"
            assert result["filename"] == "test_file.txt"
            assert result["size"] == 100
            assert result["id"] == "12345"
            attachments_mixin.jira.add_attachment.assert_called_once_with(
                issue_key="TEST-123", filename="/absolute/path/test_file.txt"
            )

    def test_upload_attachment_relative_path(
        self, attachments_mixin: AttachmentsMixin, tmp_path: Path
    ):
        """A relative path inside the workspace resolves and uploads."""
        mock_attachment_response = {
            "id": "12345",
            "filename": "test_file.txt",
            "size": 100,
        }
        attachments_mixin.jira.add_attachment.return_value = mock_attachment_response

        (tmp_path / "test_file.txt").write_bytes(b"test content")
        resolved = str((tmp_path / "test_file.txt").resolve())

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = attachments_mixin.upload_attachment("TEST-123", "test_file.txt")

        assert result["success"] is True
        attachments_mixin.jira.add_attachment.assert_called_once_with(
            issue_key="TEST-123", filename=resolved
        )

    def test_upload_attachment_no_issue_key(self, attachments_mixin: AttachmentsMixin):
        """Test attachment upload with no issue key."""
        result = attachments_mixin.upload_attachment("", "/path/to/file.txt")

        # Assertions
        assert result["success"] is False
        assert "No issue key provided" in result["error"]
        attachments_mixin.jira.add_attachment.assert_not_called()

    def test_upload_attachment_no_file_path(self, attachments_mixin: AttachmentsMixin):
        """Test attachment upload with no file path."""
        result = attachments_mixin.upload_attachment("TEST-123", "")

        # Assertions
        assert result["success"] is False
        assert "No file path provided" in result["error"]
        attachments_mixin.jira.add_attachment.assert_not_called()

    def test_upload_attachment_file_not_found(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test attachment upload when file doesn't exist."""
        # Mock file operations
        with (
            patch("os.getcwd", return_value="/absolute/path"),
            patch("os.path.exists") as mock_exists,
            patch("os.path.isabs") as mock_isabs,
            patch("os.path.abspath") as mock_abspath,
            patch("builtins.open", mock_open(read_data=b"test content")),
        ):
            mock_exists.return_value = False
            mock_isabs.return_value = True
            mock_abspath.return_value = "/absolute/path/test_file.txt"

            result = attachments_mixin.upload_attachment(
                "TEST-123", "/absolute/path/test_file.txt"
            )

            # Assertions
            assert result["success"] is False
            assert "File not found" in result["error"]
            attachments_mixin.jira.add_attachment.assert_not_called()

    def test_upload_attachment_api_error(self, attachments_mixin: AttachmentsMixin):
        """Test attachment upload with an API error."""
        # Mock the Jira API to raise an exception
        attachments_mixin.jira.add_attachment.side_effect = Exception("API Error")

        # Mock file operations
        with (
            patch("os.getcwd", return_value="/absolute/path"),
            patch("os.path.exists") as mock_exists,
            patch("os.path.isabs") as mock_isabs,
            patch("os.path.abspath") as mock_abspath,
            patch("os.path.basename") as mock_basename,
            patch("builtins.open", mock_open(read_data=b"test content")),
        ):
            mock_exists.return_value = True
            mock_isabs.return_value = True
            mock_abspath.return_value = "/absolute/path/test_file.txt"
            mock_basename.return_value = "test_file.txt"

            result = attachments_mixin.upload_attachment(
                "TEST-123", "/absolute/path/test_file.txt"
            )

            # Assertions
            assert result["success"] is False
            assert "API Error" in result["error"]

    def test_upload_attachment_no_response(self, attachments_mixin: AttachmentsMixin):
        """Test attachment upload when API returns no response."""
        # Mock the Jira API to return None
        attachments_mixin.jira.add_attachment.return_value = None

        # Mock file operations
        with (
            patch("os.getcwd", return_value="/absolute/path"),
            patch("os.path.exists") as mock_exists,
            patch("os.path.isabs") as mock_isabs,
            patch("os.path.abspath") as mock_abspath,
            patch("os.path.basename") as mock_basename,
            patch("builtins.open", mock_open(read_data=b"test content")),
        ):
            mock_exists.return_value = True
            mock_isabs.return_value = True
            mock_abspath.return_value = "/absolute/path/test_file.txt"
            mock_basename.return_value = "test_file.txt"

            result = attachments_mixin.upload_attachment(
                "TEST-123", "/absolute/path/test_file.txt"
            )

            # Assertions
            assert result["success"] is False
            assert "Failed to upload attachment" in result["error"]

    # Tests for upload_attachments method

    # Tests for upload_attachment_from_content method

    def test_upload_attachment_from_content_success(
        self, attachments_mixin: AttachmentsMixin
    ):
        """In-memory upload posts multipart content without touching the disk."""
        attachments_mixin.jira.resource_url.return_value = (
            "https://test.atlassian.net/rest/api/2/issue"
        )
        attachments_mixin.jira.no_check_headers = {"X-Atlassian-Token": "no-check"}
        attachments_mixin.jira.post.return_value = [
            {"id": "12345", "filename": "test_file.txt", "size": 12}
        ]

        result = attachments_mixin.upload_attachment_from_content(
            "TEST-123", "test_file.txt", b"test content"
        )

        assert result["success"] is True
        assert result["issue_key"] == "TEST-123"
        assert result["filename"] == "test_file.txt"
        assert result["size"] == 12
        assert result["id"] == "12345"
        attachments_mixin.jira.post.assert_called_once_with(
            "https://test.atlassian.net/rest/api/2/issue/TEST-123/attachments",
            headers={"X-Atlassian-Token": "no-check"},
            files={"file": ("test_file.txt", b"test content")},
        )
        attachments_mixin.jira.add_attachment.assert_not_called()

    def test_upload_attachment_from_content_dict_response(
        self, attachments_mixin: AttachmentsMixin
    ):
        """A bare dict response (not wrapped in a list) is handled."""
        attachments_mixin.jira.resource_url.return_value = "https://test.url/issue"
        attachments_mixin.jira.no_check_headers = {}
        attachments_mixin.jira.post.return_value = {"id": "999"}

        result = attachments_mixin.upload_attachment_from_content(
            "TEST-123", "a.txt", b"x"
        )

        assert result["success"] is True
        assert result["id"] == "999"

    def test_upload_attachment_from_content_no_issue_key(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Upload without an issue key fails."""
        result = attachments_mixin.upload_attachment_from_content("", "a.txt", b"x")

        assert result["success"] is False
        assert "No issue key provided" in result["error"]

    def test_upload_attachment_from_content_no_filename(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Upload without a filename fails."""
        result = attachments_mixin.upload_attachment_from_content("TEST-123", "", b"x")

        assert result["success"] is False
        assert "No filename provided" in result["error"]

    def test_upload_attachment_from_content_empty_content(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Empty bytes are rejected instead of creating a 0-byte attachment."""
        result = attachments_mixin.upload_attachment_from_content(
            "TEST-123", "empty.txt", b""
        )

        assert result["success"] is False
        assert "No file content provided" in result["error"]

    def test_upload_attachments_from_content_missing_content_key(
        self, attachments_mixin: AttachmentsMixin
    ):
        """A descriptor without 'content' fails instead of uploading b''."""
        result = attachments_mixin.upload_attachments_from_content(
            "TEST-123", [{"filename": "a.txt"}]
        )

        assert result["success"] is False
        assert result["failed"][0]["filename"] == "a.txt"
        assert "No file content provided" in result["failed"][0]["error"]

    def test_upload_attachment_from_content_api_error(
        self, attachments_mixin: AttachmentsMixin
    ):
        """An API failure is reported, not raised."""
        attachments_mixin.jira.resource_url.return_value = "https://test.url/issue"
        attachments_mixin.jira.no_check_headers = {}
        attachments_mixin.jira.post.side_effect = Exception("API error")

        result = attachments_mixin.upload_attachment_from_content(
            "TEST-123", "a.txt", b"x"
        )

        assert result["success"] is False
        assert "API error" in result["error"]

    def test_upload_attachment_from_content_empty_response(
        self, attachments_mixin: AttachmentsMixin
    ):
        """An empty API response is reported as a failure."""
        attachments_mixin.jira.resource_url.return_value = "https://test.url/issue"
        attachments_mixin.jira.no_check_headers = {}
        attachments_mixin.jira.post.return_value = None

        result = attachments_mixin.upload_attachment_from_content(
            "TEST-123", "a.txt", b"x"
        )

        assert result["success"] is False
        assert "Failed to upload attachment a.txt" in result["error"]

    # Tests for upload_attachments_from_content method

    def test_upload_attachments_from_content_mixed_results(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Batch upload reports successes and failures in the shared shape."""
        attachments_mixin.jira.resource_url.return_value = "https://test.url/issue"
        attachments_mixin.jira.no_check_headers = {}
        attachments_mixin.jira.post.side_effect = [
            [{"id": "1"}],
            Exception("API error"),
        ]

        result = attachments_mixin.upload_attachments_from_content(
            "TEST-123",
            [
                {"filename": "ok.txt", "content": b"ok"},
                {"filename": "bad.txt", "content": b"bad"},
            ],
        )

        assert result["success"] is True
        assert result["total"] == 2
        assert len(result["uploaded"]) == 1
        assert result["uploaded"][0]["filename"] == "ok.txt"
        assert len(result["failed"]) == 1
        assert result["failed"][0]["filename"] == "bad.txt"
        assert "API error" in result["failed"][0]["error"]

    def test_upload_attachments_from_content_empty_list(
        self, attachments_mixin: AttachmentsMixin
    ):
        """An empty batch fails without calling the API."""
        result = attachments_mixin.upload_attachments_from_content("TEST-123", [])

        assert result["success"] is False
        assert "No attachment content provided" in result["error"]

    def test_upload_attachments_from_content_no_issue_key(
        self, attachments_mixin: AttachmentsMixin
    ):
        """A batch without an issue key fails."""
        result = attachments_mixin.upload_attachments_from_content(
            "", [{"filename": "a.txt", "content": b"x"}]
        )

        assert result["success"] is False
        assert "No issue key provided" in result["error"]

    def test_upload_attachments_success(self, attachments_mixin: AttachmentsMixin):
        """Test successful upload of multiple attachments."""
        # Set up mock for upload_attachment method to simulate successful uploads
        file_paths = [
            "/path/to/file1.txt",
            "/path/to/file2.pdf",
            "/path/to/file3.jpg",
        ]

        # Create mock successful results for each file
        mock_results = [
            {
                "success": True,
                "issue_key": "TEST-123",
                "filename": f"file{i + 1}.{ext}",
                "size": 100 * (i + 1),
                "id": f"id{i + 1}",
            }
            for i, ext in enumerate(["txt", "pdf", "jpg"])
        ]

        with patch.object(
            attachments_mixin, "upload_attachment", side_effect=mock_results
        ) as mock_upload:
            # Call the method
            result = attachments_mixin.upload_attachments("TEST-123", file_paths)

            # Assertions
            assert result["success"] is True
            assert result["issue_key"] == "TEST-123"
            assert result["total"] == 3
            assert len(result["uploaded"]) == 3
            assert len(result["failed"]) == 0

            # Check that upload_attachment was called for each file
            assert mock_upload.call_count == 3
            mock_upload.assert_any_call("TEST-123", "/path/to/file1.txt")
            mock_upload.assert_any_call("TEST-123", "/path/to/file2.pdf")
            mock_upload.assert_any_call("TEST-123", "/path/to/file3.jpg")

            # Verify uploaded files details
            assert result["uploaded"][0]["filename"] == "file1.txt"
            assert result["uploaded"][1]["filename"] == "file2.pdf"
            assert result["uploaded"][2]["filename"] == "file3.jpg"
            assert result["uploaded"][0]["size"] == 100
            assert result["uploaded"][1]["size"] == 200
            assert result["uploaded"][2]["size"] == 300
            assert result["uploaded"][0]["id"] == "id1"
            assert result["uploaded"][1]["id"] == "id2"
            assert result["uploaded"][2]["id"] == "id3"

    def test_upload_attachments_mixed_results(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test upload of multiple attachments with mixed success and failure."""
        # Set up mock for upload_attachment method to simulate mixed results
        file_paths = [
            "/path/to/file1.txt",  # Will succeed
            "/path/to/file2.pdf",  # Will fail
            "/path/to/file3.jpg",  # Will succeed
        ]

        # Create mock results with mixed success/failure
        mock_results = [
            {
                "success": True,
                "issue_key": "TEST-123",
                "filename": "file1.txt",
                "size": 100,
                "id": "id1",
            },
            {"success": False, "error": "File not found: /path/to/file2.pdf"},
            {
                "success": True,
                "issue_key": "TEST-123",
                "filename": "file3.jpg",
                "size": 300,
                "id": "id3",
            },
        ]

        with patch.object(
            attachments_mixin, "upload_attachment", side_effect=mock_results
        ) as mock_upload:
            # Call the method
            result = attachments_mixin.upload_attachments("TEST-123", file_paths)

            # Assertions
            assert (
                result["success"] is True
            )  # Overall success is True even with partial failures
            assert result["issue_key"] == "TEST-123"
            assert result["total"] == 3
            assert len(result["uploaded"]) == 2
            assert len(result["failed"]) == 1

            # Check that upload_attachment was called for each file
            assert mock_upload.call_count == 3

            # Verify uploaded files details
            assert result["uploaded"][0]["filename"] == "file1.txt"
            assert result["uploaded"][1]["filename"] == "file3.jpg"
            assert result["uploaded"][0]["size"] == 100
            assert result["uploaded"][1]["size"] == 300
            assert result["uploaded"][0]["id"] == "id1"
            assert result["uploaded"][1]["id"] == "id3"

            # Verify failed file details
            assert result["failed"][0]["filename"] == "file2.pdf"
            assert "File not found" in result["failed"][0]["error"]

    def test_upload_attachments_all_fail(self, attachments_mixin: AttachmentsMixin):
        """Report failure when no attachment is uploaded."""
        with patch.object(
            attachments_mixin,
            "upload_attachment",
            return_value={"success": False, "error": "File not found"},
        ):
            result = attachments_mixin.upload_attachments(
                "TEST-123", ["/path/to/file1.txt", "/path/to/file2.txt"]
            )

        assert result["success"] is False
        assert result["uploaded"] == []
        assert len(result["failed"]) == 2

    def test_upload_attachments_empty_list(self, attachments_mixin: AttachmentsMixin):
        """Test upload with an empty list of file paths."""
        # Call the method with an empty list
        result = attachments_mixin.upload_attachments("TEST-123", [])

        # Assertions
        assert result["success"] is False
        assert "No file paths provided" in result["error"]

    def test_upload_attachments_no_issue_key(self, attachments_mixin: AttachmentsMixin):
        """Test upload with no issue key provided."""
        # Call the method with no issue key
        result = attachments_mixin.upload_attachments("", ["/path/to/file.txt"])

        # Assertions
        assert result["success"] is False
        assert "No issue key provided" in result["error"]

    # Tests for fetch_attachment_content method

    def test_fetch_attachment_content_success(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test successful in-memory attachment fetch."""
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_response.raise_for_status = MagicMock()
        attachments_mixin.jira._session.get.return_value = mock_response

        result = attachments_mixin.fetch_attachment_content(
            "https://test.url/attachment"
        )

        assert result == b"chunk1chunk2"
        attachments_mixin.jira._session.get.assert_called_once_with(
            "https://test.url/attachment", stream=True
        )

    def test_fetch_attachment_content_no_url(self, attachments_mixin: AttachmentsMixin):
        """Test fetch with no URL returns None."""
        result = attachments_mixin.fetch_attachment_content("")
        assert result is None

    def test_fetch_attachment_content_http_error(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test fetch with an HTTP error returns None."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        attachments_mixin.jira._session.get.return_value = mock_response

        result = attachments_mixin.fetch_attachment_content(
            "https://test.url/attachment"
        )
        assert result is None

    # Tests for get_issue_attachment_contents method

    def test_get_issue_attachment_contents_success(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test successful in-memory fetch of all issue attachments."""
        mock_issue = {
            "fields": {
                "attachment": [
                    {
                        "filename": "test1.txt",
                        "content": "https://test.url/attachment1",
                        "size": 100,
                        "mimeType": "text/plain",
                    },
                    {
                        "filename": "test2.png",
                        "content": "https://test.url/attachment2",
                        "size": 200,
                        "mimeType": "image/png",
                    },
                ]
            }
        }
        attachments_mixin.jira.issue.return_value = mock_issue

        mock_attachment1 = MagicMock()
        mock_attachment1.filename = "test1.txt"
        mock_attachment1.url = "https://test.url/attachment1"
        mock_attachment1.content_type = "text/plain"
        mock_attachment1.size = 100

        mock_attachment2 = MagicMock()
        mock_attachment2.filename = "test2.png"
        mock_attachment2.url = "https://test.url/attachment2"
        mock_attachment2.content_type = "image/png"
        mock_attachment2.size = 200

        with (
            patch.object(
                attachments_mixin,
                "fetch_attachment_content",
                side_effect=[b"content1", b"image_data"],
            ) as mock_fetch,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                side_effect=[mock_attachment1, mock_attachment2],
            ),
        ):
            result = attachments_mixin.get_issue_attachment_contents("TEST-123")

            assert result["success"] is True
            assert result["issue_key"] == "TEST-123"
            assert result["total"] == 2
            assert len(result["attachments"]) == 2
            assert len(result["failed"]) == 0
            assert result["attachments"][0]["filename"] == "test1.txt"
            assert result["attachments"][0]["data"] == b"content1"
            assert result["attachments"][0]["content_type"] == "text/plain"
            assert result["attachments"][1]["filename"] == "test2.png"
            assert result["attachments"][1]["data"] == b"image_data"
            assert mock_fetch.call_count == 2

    def test_get_issue_attachment_contents_no_attachments(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test fetch when issue has no attachments."""
        mock_issue = {"fields": {"attachment": []}}
        attachments_mixin.jira.issue.return_value = mock_issue

        result = attachments_mixin.get_issue_attachment_contents("TEST-123")

        assert result["success"] is True
        assert "No attachments found" in result["message"]
        assert len(result["attachments"]) == 0
        assert len(result["failed"]) == 0

    def test_get_issue_attachment_contents_issue_not_found(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test fetch when issue returns unexpected type."""
        attachments_mixin.jira.issue.return_value = None

        with pytest.raises(
            TypeError,
            match="Unexpected return value type from `jira.issue`: <class 'NoneType'>",
        ):
            attachments_mixin.get_issue_attachment_contents("TEST-123")

    def test_get_issue_attachment_contents_no_fields(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test fetch when issue has no fields."""
        mock_issue = {}
        attachments_mixin.jira.issue.return_value = mock_issue

        result = attachments_mixin.get_issue_attachment_contents("TEST-123")

        assert result["success"] is False
        assert "Could not retrieve issue" in result["error"]

    def test_get_issue_attachment_contents_some_failures(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test fetch when some attachments fail."""
        mock_issue = {
            "fields": {
                "attachment": [
                    {
                        "filename": "good.txt",
                        "content": "https://test.url/good",
                        "size": 100,
                    },
                    {
                        "filename": "bad.txt",
                        "content": "https://test.url/bad",
                        "size": 200,
                    },
                ]
            }
        }
        attachments_mixin.jira.issue.return_value = mock_issue

        mock_attachment1 = MagicMock()
        mock_attachment1.filename = "good.txt"
        mock_attachment1.url = "https://test.url/good"
        mock_attachment1.content_type = "text/plain"
        mock_attachment1.size = 100

        mock_attachment2 = MagicMock()
        mock_attachment2.filename = "bad.txt"
        mock_attachment2.url = "https://test.url/bad"
        mock_attachment2.content_type = "text/plain"
        mock_attachment2.size = 200

        with (
            patch.object(
                attachments_mixin,
                "fetch_attachment_content",
                side_effect=[b"good_data", None],
            ),
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                side_effect=[mock_attachment1, mock_attachment2],
            ),
        ):
            result = attachments_mixin.get_issue_attachment_contents("TEST-123")

            assert result["success"] is True
            assert len(result["attachments"]) == 1
            assert len(result["failed"]) == 1
            assert result["attachments"][0]["filename"] == "good.txt"
            assert result["failed"][0]["filename"] == "bad.txt"

    def test_get_issue_attachment_contents_missing_url(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test fetch when an attachment has no URL."""
        mock_issue = {
            "fields": {
                "attachment": [
                    {
                        "filename": "no_url.txt",
                        "size": 100,
                    }
                ]
            }
        }
        attachments_mixin.jira.issue.return_value = mock_issue

        mock_attachment = MagicMock()
        mock_attachment.filename = "no_url.txt"
        mock_attachment.url = None
        mock_attachment.content_type = None

        with patch(
            "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
            return_value=mock_attachment,
        ):
            result = attachments_mixin.get_issue_attachment_contents("TEST-123")

            assert result["success"] is True
            assert len(result["attachments"]) == 0
            assert len(result["failed"]) == 1
            assert "No URL available" in result["failed"][0]["error"]

    # Tests for 50MB attachment size limit

    def test_get_issue_attachment_contents_skips_oversized(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Attachment with size > 50MB in metadata is skipped before download."""
        mock_issue = {
            "fields": {
                "attachment": [
                    {
                        "filename": "huge.bin",
                        "content": "https://test.url/huge",
                        "size": 60 * 1024 * 1024,  # 60 MB
                    }
                ]
            }
        }
        attachments_mixin.jira.issue.return_value = mock_issue

        mock_attachment = MagicMock()
        mock_attachment.filename = "huge.bin"
        mock_attachment.url = "https://test.url/huge"
        mock_attachment.size = 60 * 1024 * 1024
        mock_attachment.content_type = "application/octet-stream"

        with (
            patch.object(
                attachments_mixin,
                "fetch_attachment_content",
            ) as mock_fetch,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                return_value=mock_attachment,
            ),
        ):
            result = attachments_mixin.get_issue_attachment_contents("TEST-123")

            # fetch_attachment_content should NOT be called for oversized file
            mock_fetch.assert_not_called()
            assert len(result["attachments"]) == 0
            assert len(result["failed"]) == 1
            assert "50 MB" in result["failed"][0]["error"]

    def test_get_issue_attachment_contents_allows_zero_size(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Attachment with size=0 (metadata missing) still gets downloaded."""
        mock_issue = {
            "fields": {
                "attachment": [
                    {
                        "filename": "unknown.bin",
                        "content": "https://test.url/unknown",
                    }
                ]
            }
        }
        attachments_mixin.jira.issue.return_value = mock_issue

        mock_attachment = MagicMock()
        mock_attachment.filename = "unknown.bin"
        mock_attachment.url = "https://test.url/unknown"
        mock_attachment.size = 0
        mock_attachment.content_type = "application/octet-stream"

        with (
            patch.object(
                attachments_mixin,
                "fetch_attachment_content",
                return_value=b"data",
            ) as mock_fetch,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                return_value=mock_attachment,
            ),
        ):
            result = attachments_mixin.get_issue_attachment_contents("TEST-123")

            mock_fetch.assert_called_once()
            assert len(result["attachments"]) == 1
            assert len(result["failed"]) == 0

    def test_get_issue_attachment_contents_allows_small(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Attachment with size < 50MB gets downloaded normally."""
        mock_issue = {
            "fields": {
                "attachment": [
                    {
                        "filename": "small.txt",
                        "content": "https://test.url/small",
                        "size": 1024,
                    }
                ]
            }
        }
        attachments_mixin.jira.issue.return_value = mock_issue

        mock_attachment = MagicMock()
        mock_attachment.filename = "small.txt"
        mock_attachment.url = "https://test.url/small"
        mock_attachment.size = 1024
        mock_attachment.content_type = "text/plain"

        with (
            patch.object(
                attachments_mixin,
                "fetch_attachment_content",
                return_value=b"small content",
            ) as mock_fetch,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                return_value=mock_attachment,
            ),
        ):
            result = attachments_mixin.get_issue_attachment_contents("TEST-123")

            mock_fetch.assert_called_once()
            assert len(result["attachments"]) == 1
            assert len(result["failed"]) == 0

    def test_get_issue_attachment_contents_mixed_sizes(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Mix of large and small attachments — only large ones skipped."""
        mock_issue = {
            "fields": {
                "attachment": [
                    {
                        "filename": "small.txt",
                        "content": "https://test.url/small",
                        "size": 1024,
                    },
                    {
                        "filename": "huge.bin",
                        "content": "https://test.url/huge",
                        "size": 60 * 1024 * 1024,
                    },
                    {
                        "filename": "medium.txt",
                        "content": "https://test.url/medium",
                        "size": 10 * 1024 * 1024,
                    },
                ]
            }
        }
        attachments_mixin.jira.issue.return_value = mock_issue

        mock_small = MagicMock()
        mock_small.filename = "small.txt"
        mock_small.url = "https://test.url/small"
        mock_small.size = 1024
        mock_small.content_type = "text/plain"

        mock_huge = MagicMock()
        mock_huge.filename = "huge.bin"
        mock_huge.url = "https://test.url/huge"
        mock_huge.size = 60 * 1024 * 1024
        mock_huge.content_type = "application/octet-stream"

        mock_medium = MagicMock()
        mock_medium.filename = "medium.txt"
        mock_medium.url = "https://test.url/medium"
        mock_medium.size = 10 * 1024 * 1024
        mock_medium.content_type = "text/plain"

        with (
            patch.object(
                attachments_mixin,
                "fetch_attachment_content",
                side_effect=[b"small data", b"medium data"],
            ) as mock_fetch,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                side_effect=[mock_small, mock_huge, mock_medium],
            ),
        ):
            result = attachments_mixin.get_issue_attachment_contents("TEST-123")

            # Only small and medium should be fetched
            assert mock_fetch.call_count == 2
            assert len(result["attachments"]) == 2
            assert len(result["failed"]) == 1
            assert result["failed"][0]["filename"] == "huge.bin"
            assert "50 MB" in result["failed"][0]["error"]
            filenames = [a["filename"] for a in result["attachments"]]
            assert "small.txt" in filenames
            assert "medium.txt" in filenames

    # Tests for path traversal rejection (PR #949 security hardening)

    @pytest.mark.parametrize(
        "malicious_path",
        [
            # Absolute paths that resolve outside cwd
            "/etc/passwd",
            "/tmp/evil/file.txt",
            "/var/log/secrets.txt",
        ],
        ids=[
            "absolute-etc-passwd",
            "absolute-tmp-evil",
            "absolute-var-log",
        ],
    )
    def test_download_attachment_rejects_path_traversal(
        self,
        attachments_mixin: AttachmentsMixin,
        malicious_path: str,
    ):
        """Regression: path traversal in attachment filenames must be rejected.

        The guard in download_attachment checks that the resolved absolute path
        is within cwd via ``Path(target_path).is_relative_to(cwd)``.  Paths
        outside cwd trigger a ValueError which is caught internally, causing
        the method to return False.
        """
        with patch("os.getcwd", return_value="/safe/working/dir"):
            result = attachments_mixin.download_attachment(
                "https://test.url/attachment",
                malicious_path,
            )
            assert result is False

    @pytest.mark.parametrize(
        "relative_path",
        [
            "../../../etc/passwd",
            "normal/../../../etc/shadow",
        ],
        ids=[
            "relative-traversal-etc-passwd",
            "relative-traversal-nested",
        ],
    )
    def test_download_attachment_rejects_relative_path_traversal(
        self,
        attachments_mixin: AttachmentsMixin,
        relative_path: str,
    ):
        """Regression: relative paths that resolve outside cwd are rejected.

        When a relative path is given, os.path.abspath resolves it.  If the
        resolved path escapes cwd, the guard rejects it and returns False.
        """
        import os

        cwd = os.getcwd()
        with patch("os.getcwd", return_value=cwd):
            result = attachments_mixin.download_attachment(
                "https://test.url/attachment",
                relative_path,
            )
            # The relative path resolves outside cwd (it traverses up)
            resolved = os.path.abspath(relative_path)
            if not Path(resolved).is_relative_to(cwd):
                assert result is False

    @pytest.mark.parametrize(
        "malicious_dir",
        [
            "/etc",
            "/tmp/evil",
            "/var/log",
        ],
        ids=[
            "absolute-etc",
            "absolute-tmp-evil",
            "absolute-var-log",
        ],
    )
    def test_download_issue_attachments_rejects_path_traversal(
        self,
        attachments_mixin: AttachmentsMixin,
        malicious_dir: str,
    ):
        """Regression: path traversal in target_dir must raise ValueError.

        Unlike download_attachment (which catches the error internally),
        download_issue_attachments lets the ValueError propagate.
        """
        with (
            patch("os.getcwd", return_value="/safe/working/dir"),
            pytest.raises(ValueError, match="Path traversal detected"),
        ):
            attachments_mixin.download_issue_attachments(
                "TEST-123",
                malicious_dir,
            )

    def test_get_issue_attachments_metadata(self, attachments_mixin: AttachmentsMixin):
        """get_issue_attachments returns JiraAttachment list without downloading."""
        attachments_mixin.jira.issue.return_value = {
            "fields": {
                "attachment": [
                    {
                        "id": "101",
                        "filename": "photo.png",
                        "size": 1024,
                        "mimeType": "image/png",
                        "content": "https://jira.example.com/att/101",
                    },
                    {
                        "id": "102",
                        "filename": "report.pdf",
                        "size": 2048,
                        "mimeType": "application/pdf",
                        "content": "https://jira.example.com/att/102",
                    },
                ]
            }
        }

        from mcp_atlassian.models.jira import JiraAttachment

        result = attachments_mixin.get_issue_attachments("TEST-123")
        assert len(result) == 2
        assert all(isinstance(a, JiraAttachment) for a in result)
        assert result[0].filename == "photo.png"
        assert result[0].content_type == "image/png"
        assert result[1].filename == "report.pdf"
        # No download calls should have been made
        attachments_mixin.jira._session.get.assert_not_called()


class TestUploadPathTraversalRegression:
    """Regression — upload-side attachment path traversal / arbitrary file read.

    Covers GHSA-wm45, vc25, 93xw, 6cr4, f4p7, f6pj, 2xj6, mrq8, wv8v, p6hp, h7wj,
    mfv2, f26r, 9547, cc5h (read half), and the 6vmq download-overwrite variant.

    The download side gained ``validate_safe_path`` (CVE-2026-27825), but the
    upload path used to feed any caller-supplied ``file_path`` to the API after
    only an ``os.path.exists`` check, so a path outside the workspace was read and
    exfiltrated. These tests assert the secure outcome: a traversal/absolute path
    never reaches the upload sink.

    Assertions target the *sink* (``add_attachment`` not called), not an exception
    type, because ``upload_attachment`` wraps its body in ``except Exception`` and
    returns an error dict — so the fix may reject by raising or by returning a dict,
    and either way the secret must never reach the API.
    """

    @pytest.fixture
    def attachments_mixin(self, jira_fetcher: JiraFetcher) -> AttachmentsMixin:
        """AttachmentsMixin with a mocked Jira client (Cloud by default)."""
        mixin = jira_fetcher
        mixin.jira = MagicMock()
        mixin.jira._session = MagicMock()
        return mixin

    @pytest.mark.security_regression
    @pytest.mark.parametrize("attack", ["absolute_outside_cwd", "relative_traversal"])
    def test_upload_attachment_does_not_read_outside_workspace(
        self,
        attachments_mixin: AttachmentsMixin,
        tmp_path: Path,
        attack: str,
    ) -> None:
        """A file_path resolving outside the workspace must not reach the API."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        secret = tmp_path / "secret.txt"  # sibling of workspace -> outside it
        secret.write_bytes(b"SECRET-EXFIL")
        malicious = str(secret) if attack == "absolute_outside_cwd" else "../secret.txt"

        with patch("os.getcwd", return_value=str(workspace)):
            attachments_mixin.upload_attachment("PROJ-1", malicious)

        attachments_mixin.jira.add_attachment.assert_not_called()

    @pytest.mark.security_regression
    def test_upload_attachments_list_does_not_read_outside_workspace(
        self,
        attachments_mixin: AttachmentsMixin,
        tmp_path: Path,
    ) -> None:
        """The list/confused-deputy path (update_issue -> upload_attachments)."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_bytes(b"SECRET-EXFIL")

        with patch("os.getcwd", return_value=str(workspace)):
            attachments_mixin.upload_attachments("PROJ-1", [str(secret)])

        attachments_mixin.jira.add_attachment.assert_not_called()

    @pytest.mark.security_regression
    def test_download_into_cwd_module_is_rejected(
        self,
        attachments_mixin: AttachmentsMixin,
        tmp_path: Path,
    ) -> None:
        """Downloading onto a source file inside CWD must be confined/rejected."""
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"import os; os.system('id')\n"]
        mock_response.raise_for_status = MagicMock()
        attachments_mixin.jira._session.get.return_value = mock_response

        with (
            patch("builtins.open", mock_open()),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=27),
            patch("os.makedirs"),
            patch("os.getcwd", return_value=str(tmp_path)),
        ):
            result = attachments_mixin.download_attachment(
                "https://test.url/evil",
                "important_module.py",  # relative -> resolves inside CWD
            )

        assert result is False, (
            "download targeting the CWD (where Python imports modules) must be "
            "confined to a dedicated directory, not allowed to overwrite source files"
        )


class TestDeleteAttachment:
    """Tests for deleting a Jira attachment by id."""

    @pytest.fixture
    def attachments_mixin(self, jira_fetcher):
        return jira_fetcher

    def test_delete_attachment_success(self, attachments_mixin):
        """A successful deletion reports the id it removed."""
        attachments_mixin.jira.remove_attachment = MagicMock(return_value=None)

        result = attachments_mixin.delete_attachment("10001")

        assert result["success"] is True
        assert result["attachment_id"] == "10001"
        attachments_mixin.jira.remove_attachment.assert_called_once_with("10001")

    def test_delete_attachment_without_id(self, attachments_mixin):
        """A missing id is rejected before any API call."""
        attachments_mixin.jira.remove_attachment = MagicMock()

        result = attachments_mixin.delete_attachment("")

        assert result["success"] is False
        assert "No attachment ID provided" in result["error"]
        attachments_mixin.jira.remove_attachment.assert_not_called()

    def test_delete_attachment_api_error(self, attachments_mixin):
        """An API failure surfaces as a failed result, not an exception."""
        attachments_mixin.jira.remove_attachment = MagicMock(
            side_effect=Exception("403 Forbidden")
        )

        result = attachments_mixin.delete_attachment("10001")

        assert result["success"] is False
        assert result["attachment_id"] == "10001"
        assert "403 Forbidden" in result["error"]


class TestGetAttachmentMediaId:
    """Tests for resolving the Media Services UUID of an attachment."""

    MEDIA_UUID = "0e4b3f6a-1c2d-4e5f-8a9b-0c1d2e3f4a5b"
    MEDIA_URL = f"https://api.media.atlassian.com/file/{MEDIA_UUID}/binary"

    @pytest.fixture
    def attachments_mixin(self, jira_fetcher):
        jira_fetcher.jira.resource_url = MagicMock(
            return_value="https://example.atlassian.net/rest/api/3/attachment/content/1"
        )
        jira_fetcher.jira.url = "https://example.atlassian.net"
        return jira_fetcher

    @staticmethod
    def _response(status_code=302, location="", url=""):
        response = MagicMock()
        response.status_code = status_code
        response.headers = {"Location": location} if location else {}
        response.url = url
        response.history = []
        response.close = MagicMock()
        return response

    def test_resolves_from_first_hop_location(self, attachments_mixin):
        """The documented single-hop redirect is read straight off Location."""
        session = MagicMock()
        session.get.return_value = self._response(location=self.MEDIA_URL)
        attachments_mixin.jira._session = session

        assert attachments_mixin.get_attachment_media_id("1") == self.MEDIA_UUID
        # Only the fast path runs; the redirect chain is never followed.
        assert session.get.call_count == 1
        assert session.get.call_args.kwargs["allow_redirects"] is False

    def test_follows_redirect_chain_when_first_hop_is_a_gateway(
        self, attachments_mixin
    ):
        """A gateway or proxy hop hides the media URL until the chain is walked."""
        gateway = self._response(
            location="https://api.atlassian.com/ex/jira/cloud-id/secure/attachment/1"
        )
        hop = MagicMock()
        hop.headers = {"Location": self.MEDIA_URL}
        hop.url = "https://api.atlassian.com/ex/jira/cloud-id/secure/attachment/1"
        followed = self._response(status_code=200, url=self.MEDIA_URL)
        followed.history = [hop]

        session = MagicMock()
        session.get.side_effect = [gateway, followed]
        attachments_mixin.jira._session = session

        assert attachments_mixin.get_attachment_media_id("1") == self.MEDIA_UUID
        assert session.get.call_count == 2
        assert session.get.call_args.kwargs["allow_redirects"] is True

    def test_falls_back_to_chain_when_the_fast_path_raises(self, attachments_mixin):
        """A failure on the fast path does not abort resolution."""
        followed = self._response(status_code=200, url=self.MEDIA_URL)
        session = MagicMock()
        session.get.side_effect = [Exception("boom"), followed]
        attachments_mixin.jira._session = session

        assert attachments_mixin.get_attachment_media_id("1") == self.MEDIA_UUID

    def test_builds_an_absolute_url_from_a_relative_resource(self, attachments_mixin):
        """Some library versions return a relative resource_url; requests needs
        an absolute one or it raises MissingSchema."""
        attachments_mixin.jira.resource_url = MagicMock(
            return_value="rest/api/3/attachment/content/1"
        )
        session = MagicMock()
        session.get.return_value = self._response(location=self.MEDIA_URL)
        attachments_mixin.jira._session = session

        attachments_mixin.get_attachment_media_id("1")

        assert session.get.call_args.args[0] == (
            "https://example.atlassian.net/rest/api/3/attachment/content/1"
        )

    def test_returns_none_when_no_hop_exposes_a_media_url(self, attachments_mixin):
        """An instance that hides the media URL resolves to None, not a crash."""
        first = self._response(location="https://example.atlassian.net/elsewhere")
        followed = self._response(
            status_code=200, url="https://example.atlassian.net/elsewhere"
        )
        session = MagicMock()
        session.get.side_effect = [first, followed]
        attachments_mixin.jira._session = session

        assert attachments_mixin.get_attachment_media_id("1") is None

    def test_returns_none_without_an_attachment_id(self, attachments_mixin):
        """A missing id short-circuits before any request."""
        session = MagicMock()
        attachments_mixin.jira._session = session

        assert attachments_mixin.get_attachment_media_id("") is None
        session.get.assert_not_called()

    def test_redirect_chain_errors_are_not_swallowed(self, attachments_mixin):
        """A hard failure surfaces its real cause instead of a vague None."""
        session = MagicMock()
        session.get.side_effect = [
            Exception("first"),
            ValueError("Redirect blocked (SSRF): internal host"),
        ]
        attachments_mixin.jira._session = session

        with pytest.raises(ValueError, match="Redirect blocked"):
            attachments_mixin.get_attachment_media_id("1")

    @pytest.mark.parametrize(
        "text,expected",
        [
            (f"https://api.media.atlassian.com/file/{MEDIA_UUID}/binary", MEDIA_UUID),
            (f"https://proxy.internal/pass/file/{MEDIA_UUID}/image", MEDIA_UUID),
            ("https://api.media.atlassian.com/file/not-a-uuid/binary", None),
            ("https://example.atlassian.net/secure/attachment/1/shot.png", None),
            ("", None),
            (None, None),
        ],
    )
    def test_media_uuid_extraction_is_host_agnostic(self, text, expected):
        """The UUID is matched on the /file/ fragment, whatever the host is."""
        assert AttachmentsMixin._extract_media_file_uuid(text) == expected
