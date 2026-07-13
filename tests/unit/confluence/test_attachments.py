"""Tests for the Confluence attachments module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, mock_open, patch

import pytest
from mcp.types import EmbeddedResource, TextContent

from mcp_atlassian.confluence.attachments import AttachmentsMixin
from mcp_atlassian.confluence.config import ConfluenceConfig

# Test scenarios for AttachmentsMixin
#
# 1. Single Attachment Upload (upload_attachment method):
#    - Success case: Uploads attachment correctly
#    - Path handling: Converts relative path to absolute path
#    - Error cases:
#      - No content ID provided
#      - No file path provided
#      - File not found
#      - API error during upload
#
# 2. Multiple Attachments Upload (upload_attachments method):
#    - Success case: Uploads multiple files correctly
#    - Partial success: Some files upload successfully, others fail
#    - Error cases:
#      - Empty list of file paths
#      - No content ID provided
#
# 3. Single Attachment Download (download_attachment method):
#    - Success case: Downloads attachment correctly with proper HTTP response
#    - Path handling: Converts relative path to absolute path
#    - Error cases:
#      - No URL provided
#      - HTTP error during download
#      - File write error
#      - File not created after write operation
#
# 4. Content Attachments Download (download_content_attachments method):
#    - Success case: Downloads all attachments for content
#    - Path handling: Converts relative target directory to absolute path
#    - Edge cases:
#      - Content has no attachments
#      - API error retrieving attachments
#      - Some attachments fail to download
#      - Attachment has missing download URL
#
# 5. Get Content Attachments (get_content_attachments method):
#    - Success case: Retrieves all attachments for content
#    - Pagination: Handles paginated results
#    - Error cases:
#      - No content ID provided
#      - API error retrieving attachments
#      - Empty results


class TestAttachmentsMixin:
    """Tests for the AttachmentsMixin class."""

    @pytest.fixture
    def attachments_mixin(self, confluence_client) -> AttachmentsMixin:
        """Create an AttachmentsMixin instance for testing."""
        # AttachmentsMixin inherits from ConfluenceClient, so we need to create it properly
        with patch(
            "mcp_atlassian.confluence.attachments.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = AttachmentsMixin()
            # Copy the necessary attributes from our mocked client
            mixin.confluence = confluence_client.confluence
            mixin.config = confluence_client.config
            mixin.preprocessor = confluence_client.preprocessor
            return mixin

    def _mock_rest_api_upload(
        self, attachments_mixin, response_data=None, raise_error=None
    ):
        """Helper to mock the direct REST API upload call.

        Args:
            attachments_mixin: The mixin fixture
            response_data: Dict to return from API (default: successful attachment)
            raise_error: Exception to raise from API call (default: None)

        Returns:
            The mock response object
        """
        if response_data is None:
            response_data = {
                "results": [
                    {
                        "id": "att12345",
                        "type": "attachment",
                        "title": "test_file.txt",
                        "extensions": {"mediaType": "text/plain", "fileSize": 100},
                        "_links": {
                            "download": "/download/attachments/123/test_file.txt"
                        },
                        "version": {"number": 1},
                    }
                ]
            }

        mock_response = Mock()
        if raise_error:
            attachments_mixin.confluence._session.post.side_effect = raise_error
        else:
            mock_response.status_code = 200
            mock_response.json.return_value = response_data
            mock_response.raise_for_status.return_value = None
            attachments_mixin.confluence._session.post.return_value = mock_response

        return mock_response

    # Tests for upload_attachment method

    def test_upload_attachment_success(self, attachments_mixin: AttachmentsMixin):
        """Test successful attachment upload."""
        # Mock the REST API call
        self._mock_rest_api_upload(attachments_mixin)

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
                "123456",
                "/absolute/path/test_file.txt",
                comment="Test comment",
                minor_edit=False,
            )

            # Assertions
            assert result["success"] is True
            assert result["content_id"] == "123456"
            assert result["filename"] == "test_file.txt"
            assert result["size"] == 100
            assert result["id"] == "att12345"

            # Verify the REST API was called with correct parameters
            attachments_mixin.confluence._session.post.assert_called_once()
            call_args = attachments_mixin.confluence._session.post.call_args

            # Check URL
            assert "/rest/api/content/123456/child/attachment" in call_args[0][0]

            # Check headers include X-Atlassian-Token with correct value (hyphen required
            # by Confluence Server/DC to bypass XSRF validation)
            assert call_args[1]["headers"]["X-Atlassian-Token"] == "no-check"

            # Check minorEdit was passed in data
            assert call_args[1]["data"]["minorEdit"] == "false"
            # Note: comment is now in files dict as multipart form data, not in data dict

    def _capture_upload_url(self, attachments_mixin, config_url: str) -> str:
        """Run an upload with the given config URL and return the request URL.

        Sets ``config.url`` (which drives ``is_cloud``), performs an upload with
        all file I/O mocked, and returns the URL passed to ``session.post``.
        """
        attachments_mixin.config.url = config_url
        self._mock_rest_api_upload(attachments_mixin)

        with (
            patch("os.getcwd", return_value="/absolute/path"),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=100),
            patch("os.path.isabs", return_value=True),
            patch("os.path.abspath", return_value="/absolute/path/test_file.txt"),
            patch("os.path.basename", return_value="test_file.txt"),
            patch("builtins.open", mock_open(read_data=b"test content")),
        ):
            attachments_mixin.upload_attachment(
                "123456", "/absolute/path/test_file.txt"
            )

        return attachments_mixin.confluence._session.post.call_args[0][0]

    def test_upload_attachment_cloud_adds_wiki_prefix(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Cloud bare site URL gets the /wiki prefix (otherwise the call 404s)."""
        url = self._capture_upload_url(attachments_mixin, "https://test.atlassian.net")

        assert (
            url == "https://test.atlassian.net/wiki"
            "/rest/api/content/123456/child/attachment"
        )

    def test_upload_attachment_cloud_no_double_wiki_prefix(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Cloud URL already ending in /wiki must not become /wiki/wiki."""
        url = self._capture_upload_url(
            attachments_mixin, "https://test.atlassian.net/wiki"
        )

        assert "/wiki/wiki" not in url
        assert (
            url == "https://test.atlassian.net/wiki"
            "/rest/api/content/123456/child/attachment"
        )

    def test_upload_attachment_server_dc_no_wiki_prefix(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Server/DC URLs are unchanged — no /wiki prefix is added."""
        url = self._capture_upload_url(
            attachments_mixin, "https://confluence.example.com"
        )

        assert "/wiki" not in url
        assert (
            url == "https://confluence.example.com"
            "/rest/api/content/123456/child/attachment"
        )

    def test_upload_attachment_relative_path(
        self, attachments_mixin: AttachmentsMixin, tmp_path: Path
    ):
        """A relative path inside the workspace resolves and uploads."""
        self._mock_rest_api_upload(attachments_mixin)

        (tmp_path / "test_file.txt").write_bytes(b"test content")

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = attachments_mixin.upload_attachment("123456", "test_file.txt")

        assert result["success"] is True
        attachments_mixin.confluence._session.post.assert_called_once()

    def test_upload_attachment_no_content_id(self, attachments_mixin: AttachmentsMixin):
        """Test attachment upload with no content ID."""
        result = attachments_mixin.upload_attachment("", "/path/to/file.txt")

        # Assertions
        assert result["success"] is False
        assert "No content ID provided" in result["error"]
        # Should not call API at all
        attachments_mixin.confluence._session.post.assert_not_called()

    def test_upload_attachment_no_file_path(self, attachments_mixin: AttachmentsMixin):
        """Test attachment upload with no file path."""
        result = attachments_mixin.upload_attachment("123456", "")

        # Assertions
        assert result["success"] is False
        assert "No file path provided" in result["error"]
        # Should not call API at all
        attachments_mixin.confluence._session.post.assert_not_called()

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
        ):
            mock_exists.return_value = False
            mock_isabs.return_value = True
            mock_abspath.return_value = "/absolute/path/test_file.txt"

            result = attachments_mixin.upload_attachment(
                "123456", "/absolute/path/test_file.txt"
            )

            # Assertions
            assert result["success"] is False
            assert "File not found" in result["error"]
            # Should not call API if file doesn't exist
            attachments_mixin.confluence._session.post.assert_not_called()

    def test_upload_attachment_api_error(self, attachments_mixin: AttachmentsMixin):
        """Test attachment upload with an API error."""
        # Mock the REST API to raise an exception
        from requests.exceptions import HTTPError

        self._mock_rest_api_upload(
            attachments_mixin, raise_error=HTTPError("API Error")
        )

        # Mock file operations
        with (
            patch("os.getcwd", return_value="/absolute/path"),
            patch("os.path.exists") as mock_exists,
            patch("os.path.isabs") as mock_isabs,
            patch("os.path.abspath") as mock_abspath,
            patch("os.path.basename") as mock_basename,
            patch("os.path.getsize") as mock_getsize,
            patch("builtins.open", mock_open(read_data=b"test content")),
        ):
            mock_exists.return_value = True
            mock_isabs.return_value = True
            mock_abspath.return_value = "/absolute/path/test_file.txt"
            mock_basename.return_value = "test_file.txt"
            mock_getsize.return_value = 100

            result = attachments_mixin.upload_attachment(
                "123456", "/absolute/path/test_file.txt"
            )

            # Assertions: exception is caught by upload_attachment and returned as failure dict
            assert result["success"] is False
            assert "API Error" in result["error"]

    def test_upload_attachment_versioning_fallback(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test that re-uploading an existing file triggers the versioning fallback.

        On Confluence Server/DC, uploading a file with the same name as an existing
        attachment returns HTTP 400 with 'same file name' in the body. The code must
        then GET the existing attachment ID and POST to /child/attachment/{id}/data
        to create a new version.
        """
        filename = "test file & notes #1.txt"
        updated_attachment = {
            "id": "att12345",
            "type": "attachment",
            "title": filename,
            "extensions": {"mediaType": "text/plain", "fileSize": 200},
            "_links": {"download": f"/download/attachments/123/{filename}"},
            "version": {"number": 2},
        }

        # First POST returns 400 "same file name"
        conflict_response = Mock()
        conflict_response.status_code = 400
        conflict_response.text = (
            f"Attachment with same file name already exists: {filename}"
        )

        # GET list returns existing attachment
        list_response = Mock()
        list_response.status_code = 200
        list_response.raise_for_status.return_value = None
        list_response.json.return_value = {"results": [{"id": "att12345"}]}

        # Second POST (to /data endpoint) returns the updated attachment
        update_response = Mock()
        update_response.status_code = 200
        update_response.raise_for_status.return_value = None
        update_response.json.return_value = updated_attachment

        attachments_mixin.confluence._session.post.side_effect = [
            conflict_response,
            update_response,
        ]
        attachments_mixin.confluence._session.get.return_value = list_response

        with (
            patch("os.getcwd", return_value="/absolute/path"),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=200),
            patch("os.path.isabs", return_value=True),
            patch("os.path.abspath", return_value=f"/absolute/path/{filename}"),
            patch("os.path.basename", return_value=filename),
            patch("builtins.open", mock_open(read_data=b"updated content")),
        ):
            result = attachments_mixin.upload_attachment(
                "123456", f"/absolute/path/{filename}"
            )

        assert result["success"] is True
        assert result["filename"] == filename

        # Verify the lookup URL escapes query-special filename characters.
        list_call_url = attachments_mixin.confluence._session.get.call_args[0][0]
        assert "filename=test%20file%20%26%20notes%20%231.txt" in list_call_url

        # Verify the versioning POST was made to the /data endpoint
        assert attachments_mixin.confluence._session.post.call_count == 2
        second_call_url = attachments_mixin.confluence._session.post.call_args_list[1][
            0
        ][0]
        assert "/child/attachment/att12345/data" in second_call_url

    # Tests for upload_attachments method

    def test_upload_attachments_success(self, attachments_mixin: AttachmentsMixin):
        """Test successful upload of multiple attachments."""
        file_paths = [
            "/path/to/file1.txt",
            "/path/to/file2.pdf",
            "/path/to/file3.jpg",
        ]

        # Create mock successful results for each file
        mock_results = [
            {
                "success": True,
                "content_id": "123456",
                "filename": f"file{i + 1}.{ext}",
                "size": 100 * (i + 1),
                "id": f"att{i + 1}",
            }
            for i, ext in enumerate(["txt", "pdf", "jpg"])
        ]

        with patch.object(
            attachments_mixin, "upload_attachment", side_effect=mock_results
        ) as mock_upload:
            # Call the method
            result = attachments_mixin.upload_attachments("123456", file_paths)

            # Assertions
            assert result["success"] is True
            assert result["content_id"] == "123456"
            assert result["total"] == 3
            assert len(result["uploaded"]) == 3
            assert len(result["failed"]) == 0

            # Check that upload_attachment was called for each file
            assert mock_upload.call_count == 3
            # Calls are made with positional args, not keyword args
            mock_upload.assert_any_call("123456", "/path/to/file1.txt", None, True)  # noqa: FBT003
            mock_upload.assert_any_call("123456", "/path/to/file2.pdf", None, True)  # noqa: FBT003
            mock_upload.assert_any_call("123456", "/path/to/file3.jpg", None, True)  # noqa: FBT003

            # Verify uploaded files details
            assert result["uploaded"][0]["filename"] == "file1.txt"
            assert result["uploaded"][1]["filename"] == "file2.pdf"
            assert result["uploaded"][2]["filename"] == "file3.jpg"

    def test_upload_attachments_mixed_results(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test upload of multiple attachments with mixed success and failure."""
        file_paths = [
            "/path/to/file1.txt",  # Will succeed
            "/path/to/file2.pdf",  # Will fail
            "/path/to/file3.jpg",  # Will succeed
        ]

        # Create mock results with mixed success/failure
        mock_results = [
            {
                "success": True,
                "content_id": "123456",
                "filename": "file1.txt",
                "size": 100,
                "id": "att1",
            },
            {"success": False, "error": "File not found: /path/to/file2.pdf"},
            {
                "success": True,
                "content_id": "123456",
                "filename": "file3.jpg",
                "size": 300,
                "id": "att3",
            },
        ]

        with patch.object(
            attachments_mixin, "upload_attachment", side_effect=mock_results
        ) as mock_upload:
            # Call the method
            result = attachments_mixin.upload_attachments("123456", file_paths)

            # Assertions
            assert result["success"] is True
            assert result["content_id"] == "123456"
            assert result["total"] == 3
            assert len(result["uploaded"]) == 2
            assert len(result["failed"]) == 1
            assert mock_upload.call_count == 3

            # Verify failed file details
            assert result["failed"][0]["filename"] == "file2.pdf"
            assert "File not found" in result["failed"][0]["error"]

    def test_upload_attachments_empty_list(self, attachments_mixin: AttachmentsMixin):
        """Test upload with an empty list of file paths."""
        result = attachments_mixin.upload_attachments("123456", [])

        # Assertions
        assert result["success"] is False
        assert "No file paths provided" in result["error"]

    def test_upload_attachments_no_content_id(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test upload with no content ID provided."""
        result = attachments_mixin.upload_attachments("", ["/path/to/file.txt"])

        # Assertions
        assert result["success"] is False
        assert "No content ID provided" in result["error"]

    # Tests for upload_attachment_from_content method

    def test_upload_attachment_from_content_success(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test successful in-memory attachment upload (no filesystem access)."""
        self._mock_rest_api_upload(attachments_mixin)

        result = attachments_mixin.upload_attachment_from_content(
            "123456",
            "test_file.txt",
            b"test content",
            comment="Test comment",
            minor_edit=False,
        )

        assert result["success"] is True
        assert result["content_id"] == "123456"
        assert result["filename"] == "test_file.txt"
        assert result["size"] == len(b"test content")
        assert result["id"] == "att12345"

        # The REST API must be called without ever touching the filesystem
        attachments_mixin.confluence._session.post.assert_called_once()
        call_args = attachments_mixin.confluence._session.post.call_args
        assert "/rest/api/content/123456/child/attachment" in call_args[0][0]
        assert call_args[1]["headers"]["X-Atlassian-Token"] == "no-check"
        assert call_args[1]["data"]["minorEdit"] == "false"
        # The raw bytes are sent directly as the multipart file payload
        assert call_args[1]["files"]["file"] == ("test_file.txt", b"test content")

    def test_upload_attachment_from_content_no_content_id(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test in-memory upload with no content ID."""
        result = attachments_mixin.upload_attachment_from_content(
            "", "test_file.txt", b"data"
        )

        assert result["success"] is False
        assert "No content ID provided" in result["error"]
        attachments_mixin.confluence._session.post.assert_not_called()

    def test_upload_attachment_from_content_no_filename(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test in-memory upload with no filename."""
        result = attachments_mixin.upload_attachment_from_content("123456", "", b"data")

        assert result["success"] is False
        assert "No filename provided" in result["error"]
        attachments_mixin.confluence._session.post.assert_not_called()

    def test_upload_attachment_from_content_api_error(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test in-memory upload surfaces API errors as a failure result."""
        from requests.exceptions import HTTPError

        self._mock_rest_api_upload(
            attachments_mixin, raise_error=HTTPError("API Error")
        )

        result = attachments_mixin.upload_attachment_from_content(
            "123456", "test_file.txt", b"data"
        )

        assert result["success"] is False
        assert "API Error" in result["error"]

    def test_upload_attachment_from_content_versioning_fallback(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test in-memory upload can update an existing attachment version."""
        filename = "test file & notes #1.txt"
        updated_attachment = {
            "id": "att12345",
            "type": "attachment",
            "title": filename,
            "extensions": {"mediaType": "text/plain", "fileSize": 200},
            "_links": {"download": f"/download/attachments/123/{filename}"},
            "version": {"number": 2},
        }

        conflict_response = Mock()
        conflict_response.status_code = 400
        conflict_response.text = (
            f"Attachment with same file name already exists: {filename}"
        )

        list_response = Mock()
        list_response.status_code = 200
        list_response.raise_for_status.return_value = None
        list_response.json.return_value = {"results": [{"id": "att12345"}]}

        update_response = Mock()
        update_response.status_code = 200
        update_response.raise_for_status.return_value = None
        update_response.json.return_value = updated_attachment

        attachments_mixin.confluence._session.post.side_effect = [
            conflict_response,
            update_response,
        ]
        attachments_mixin.confluence._session.get.return_value = list_response

        result = attachments_mixin.upload_attachment_from_content(
            "123456",
            filename,
            b"updated content",
        )

        assert result["success"] is True
        assert result["filename"] == filename
        assert result["id"] == "att12345"

        list_call_url = attachments_mixin.confluence._session.get.call_args[0][0]
        assert "filename=test%20file%20%26%20notes%20%231.txt" in list_call_url

        assert attachments_mixin.confluence._session.post.call_count == 2
        second_call = attachments_mixin.confluence._session.post.call_args_list[1]
        assert "/child/attachment/att12345/data" in second_call[0][0]
        assert second_call[1]["files"]["file"] == (filename, b"updated content")

    # Tests for download_attachment method

    def test_download_attachment_success(self, attachments_mixin: AttachmentsMixin):
        """Test successful attachment download."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status = MagicMock()
        attachments_mixin.confluence._session.get.return_value = mock_response

        # Use platform-independent temp path for cross-platform testing
        test_path = os.path.join(tempfile.gettempdir(), "test_file.txt")

        # Mock file operations
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("os.path.exists") as mock_exists,
            patch("os.path.getsize") as mock_getsize,
            patch("os.makedirs") as mock_makedirs,
            patch("mcp_atlassian.confluence.attachments.validate_safe_path"),
        ):
            mock_exists.return_value = True
            mock_getsize.return_value = 12  # Length of "test content"

            # Call the method
            result = attachments_mixin.download_attachment(
                "https://test.url/attachment", test_path
            )

            # Assertions
            assert result is True
            attachments_mixin.confluence._session.get.assert_called_once_with(
                "https://test.url/attachment", stream=True
            )
            # Path should remain unchanged since it's already absolute
            mock_file.assert_called_once_with(test_path, "wb")
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
        attachments_mixin.confluence._session.get.return_value = mock_response

        # Mock file operations
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("os.path.exists") as mock_exists,
            patch("os.path.getsize") as mock_getsize,
            patch("os.makedirs") as mock_makedirs,
            patch("os.path.abspath") as mock_abspath,
            patch("os.path.isabs") as mock_isabs,
            patch("mcp_atlassian.confluence.attachments.validate_safe_path"),
        ):
            mock_exists.return_value = True
            mock_getsize.return_value = 12
            mock_isabs.return_value = False
            mock_abspath.return_value = "/absolute/path/test_file.txt"

            # Call the method with a relative path
            result = attachments_mixin.download_attachment(
                "https://test.url/attachment", "test_file.txt"
            )

            # Assertions
            assert result is True
            mock_isabs.assert_called_once_with("test_file.txt")
            mock_abspath.assert_called_once_with("test_file.txt")
            mock_file.assert_called_once_with("/absolute/path/test_file.txt", "wb")

    def test_download_attachment_no_url(self, attachments_mixin: AttachmentsMixin):
        """Test attachment download with no URL."""
        result = attachments_mixin.download_attachment("", "/tmp/test_file.txt")
        assert result is False

    def test_download_attachment_http_error(self, attachments_mixin: AttachmentsMixin):
        """Test attachment download with an HTTP error."""
        # Mock the response to raise an HTTP error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        attachments_mixin.confluence._session.get.return_value = mock_response

        with patch("mcp_atlassian.confluence.attachments.validate_safe_path"):
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
        attachments_mixin.confluence._session.get.return_value = mock_response

        # Mock file operations to raise an exception during write
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("os.makedirs") as mock_makedirs,
            patch("mcp_atlassian.confluence.attachments.validate_safe_path"),
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
        attachments_mixin.confluence._session.get.return_value = mock_response

        # Mock file operations
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("os.path.exists") as mock_exists,
            patch("os.makedirs") as mock_makedirs,
            patch("mcp_atlassian.confluence.attachments.validate_safe_path"),
        ):
            mock_exists.return_value = False  # File doesn't exist after write

            result = attachments_mixin.download_attachment(
                "https://test.url/attachment", "/tmp/test_file.txt"
            )
            assert result is False

    # Tests for fetch_attachment_content method

    def test_fetch_attachment_content_success(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test successful in-memory attachment fetch returns bytes."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_content.return_value = [b"hello ", b"world"]
        attachments_mixin.confluence._session.get.return_value = mock_response

        result = attachments_mixin.fetch_attachment_content(
            "https://test.atlassian.net/download/att123"
        )

        assert result == b"hello world"
        attachments_mixin.confluence._session.get.assert_called_once_with(
            "https://test.atlassian.net/download/att123", stream=True
        )

    def test_fetch_attachment_content_empty_url(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test fetch_attachment_content returns None for empty URL."""
        assert attachments_mixin.fetch_attachment_content("") is None
        attachments_mixin.confluence._session.get.assert_not_called()

    def test_fetch_attachment_content_http_error(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test fetch_attachment_content returns None on HTTP error."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        attachments_mixin.confluence._session.get.return_value = mock_response

        result = attachments_mixin.fetch_attachment_content(
            "https://test.atlassian.net/download/att123"
        )
        assert result is None

    def test_fetch_attachment_content_network_exception(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test fetch_attachment_content returns None on network exception."""
        attachments_mixin.confluence._session.get.side_effect = ConnectionError(
            "Connection refused"
        )

        result = attachments_mixin.fetch_attachment_content(
            "https://test.atlassian.net/download/att123"
        )
        assert result is None

    def test_fetch_attachment_content_streaming(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test fetch_attachment_content reads in chunks via streaming."""
        chunks = [b"chunk1", b"chunk2", b"chunk3"]
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_content.return_value = chunks
        attachments_mixin.confluence._session.get.return_value = mock_response

        result = attachments_mixin.fetch_attachment_content(
            "https://test.atlassian.net/download/att123"
        )

        assert result == b"chunk1chunk2chunk3"
        mock_response.iter_content.assert_called_once_with(chunk_size=8192)

    # Tests for download_content_attachments method

    def test_download_content_attachments_success(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test successful download of all content attachments."""
        # Mock the get_content_attachments response
        mock_attachments = [
            {
                "id": "att1",
                "title": "test1.txt",
                "extensions": {"fileSize": 100},
                "_links": {"download": "/download/test1.txt"},
            },
            {
                "id": "att2",
                "title": "test2.txt",
                "extensions": {"fileSize": 200},
                "_links": {"download": "/download/test2.txt"},
            },
        ]

        # Mock ConfluenceAttachment.from_api_response
        mock_attachment1 = MagicMock()
        mock_attachment1.title = "test1.txt"
        mock_attachment1.download_url = "/download/test1.txt"
        mock_attachment1.file_size = 100

        mock_attachment2 = MagicMock()
        mock_attachment2.title = "test2.txt"
        mock_attachment2.download_url = "/download/test2.txt"
        mock_attachment2.file_size = 200

        # Mock methods
        with (
            patch.object(
                attachments_mixin,
                "get_content_attachments",
                return_value={"success": True, "attachments": mock_attachments},
            ) as mock_get,
            patch.object(
                attachments_mixin, "download_attachment", return_value=True
            ) as mock_download,
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch(
                "mcp_atlassian.models.confluence.ConfluenceAttachment.from_api_response",
                side_effect=[mock_attachment1, mock_attachment2],
            ),
            patch("mcp_atlassian.confluence.attachments.validate_safe_path"),
        ):
            result = attachments_mixin.download_content_attachments(
                "123456", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is True
            assert len(result["downloaded"]) == 2
            assert len(result["failed"]) == 0
            assert result["total"] == 2
            assert result["content_id"] == "123456"
            assert mock_download.call_count == 2
            mock_mkdir.assert_called_once()

    def test_download_content_attachments_relative_path(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test download content attachments with a relative path."""
        # Mock the get_content_attachments response
        mock_attachments = [
            {
                "id": "att1",
                "title": "test1.txt",
                "_links": {"download": "/download/test1.txt"},
            }
        ]

        # Mock attachment
        mock_attachment = MagicMock()
        mock_attachment.title = "test1.txt"
        mock_attachment.download_url = "/download/test1.txt"
        mock_attachment.file_size = 100

        # Mock path operations
        with (
            patch.object(
                attachments_mixin,
                "get_content_attachments",
                return_value={"success": True, "attachments": mock_attachments},
            ),
            patch.object(attachments_mixin, "download_attachment", return_value=True),
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch(
                "mcp_atlassian.models.confluence.ConfluenceAttachment.from_api_response",
                return_value=mock_attachment,
            ),
            patch("os.path.isabs") as mock_isabs,
            patch("os.path.abspath") as mock_abspath,
            patch("mcp_atlassian.confluence.attachments.validate_safe_path"),
        ):
            mock_isabs.return_value = False
            mock_abspath.return_value = "/absolute/path/attachments"

            result = attachments_mixin.download_content_attachments(
                "123456", "attachments"
            )

            # Assertions
            assert result["success"] is True
            mock_isabs.assert_called_once_with("attachments")
            mock_abspath.assert_called_once_with("attachments")

    def test_download_content_attachments_no_attachments(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test download when content has no attachments."""
        # Mock the get_content_attachments response with empty list
        with (
            patch.object(
                attachments_mixin,
                "get_content_attachments",
                return_value={"success": True, "attachments": []},
            ),
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch("mcp_atlassian.confluence.attachments.validate_safe_path"),
        ):
            result = attachments_mixin.download_content_attachments(
                "123456", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is True
            assert "No attachments found" in result["message"]
            assert len(result["downloaded"]) == 0
            assert len(result["failed"]) == 0
            mock_mkdir.assert_called_once()

    def test_download_content_attachments_api_error(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test download when API error occurs retrieving attachments."""
        # Mock the get_content_attachments to return error
        with (
            patch.object(
                attachments_mixin,
                "get_content_attachments",
                return_value={"success": False, "error": "API Error"},
            ),
            patch("mcp_atlassian.confluence.attachments.validate_safe_path"),
        ):
            result = attachments_mixin.download_content_attachments(
                "123456", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is False
            assert "API Error" in result["error"]

    def test_download_content_attachments_some_failures(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test download when some attachments fail to download."""
        # Mock the get_content_attachments response
        mock_attachments = [
            {
                "id": "att1",
                "title": "test1.txt",
                "_links": {"download": "/download/test1.txt"},
            },
            {
                "id": "att2",
                "title": "test2.txt",
                "_links": {"download": "/download/test2.txt"},
            },
        ]

        # Mock attachments
        mock_attachment1 = MagicMock()
        mock_attachment1.title = "test1.txt"
        mock_attachment1.download_url = "/download/test1.txt"
        mock_attachment1.file_size = 100

        mock_attachment2 = MagicMock()
        mock_attachment2.title = "test2.txt"
        mock_attachment2.download_url = "/download/test2.txt"
        mock_attachment2.file_size = 200

        # Mock the download_attachment method to succeed for first and fail for second
        with (
            patch.object(
                attachments_mixin,
                "get_content_attachments",
                return_value={"success": True, "attachments": mock_attachments},
            ),
            patch.object(
                attachments_mixin, "download_attachment", side_effect=[True, False]
            ) as mock_download,
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch(
                "mcp_atlassian.models.confluence.ConfluenceAttachment.from_api_response",
                side_effect=[mock_attachment1, mock_attachment2],
            ),
            patch("mcp_atlassian.confluence.attachments.validate_safe_path"),
        ):
            result = attachments_mixin.download_content_attachments(
                "123456", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is True
            assert len(result["downloaded"]) == 1
            assert len(result["failed"]) == 1
            assert result["downloaded"][0]["filename"] == "test1.txt"
            assert result["failed"][0]["filename"] == "test2.txt"
            assert mock_download.call_count == 2

    def test_download_content_attachments_missing_url(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test download when an attachment has no download URL."""
        # Mock the get_content_attachments response
        mock_attachments = [
            {"id": "att1", "title": "test1.txt"}  # Missing _links
        ]

        # Mock attachment with no URL
        mock_attachment = MagicMock()
        mock_attachment.title = "test1.txt"
        mock_attachment.download_url = None  # No URL
        mock_attachment.file_size = 100

        # Mock methods
        with (
            patch.object(
                attachments_mixin,
                "get_content_attachments",
                return_value={"success": True, "attachments": mock_attachments},
            ),
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch(
                "mcp_atlassian.models.confluence.ConfluenceAttachment.from_api_response",
                return_value=mock_attachment,
            ),
            patch("mcp_atlassian.confluence.attachments.validate_safe_path"),
        ):
            result = attachments_mixin.download_content_attachments(
                "123456", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is True
            assert len(result["downloaded"]) == 0
            assert len(result["failed"]) == 1
            assert result["failed"][0]["filename"] == "test1.txt"
            assert "No download URL available" in result["failed"][0]["error"]

    # Tests for get_content_attachments method

    def test_get_content_attachments_success(self, attachments_mixin: AttachmentsMixin):
        """Test successful retrieval of content attachments."""
        # Mock the Confluence API response
        mock_api_response = {
            "results": [
                {
                    "id": "att1",
                    "type": "attachment",
                    "title": "test1.txt",
                    "extensions": {"mediaType": "text/plain", "fileSize": 100},
                },
                {
                    "id": "att2",
                    "type": "attachment",
                    "title": "test2.pdf",
                    "extensions": {"mediaType": "application/pdf", "fileSize": 200},
                },
            ],
            "start": 0,
            "limit": 50,
            "size": 2,
        }
        attachments_mixin.confluence.get_attachments_from_content.return_value = (
            mock_api_response
        )

        # Call the method
        result = attachments_mixin.get_content_attachments("123456")

        # Assertions
        assert result["success"] is True
        assert result["content_id"] == "123456"
        assert len(result["attachments"]) == 2
        assert result["total"] == 2
        attachments_mixin.confluence.get_attachments_from_content.assert_called_once_with(
            "123456", start=0, limit=50
        )

    def test_get_content_attachments_with_pagination(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test retrieval with custom pagination parameters."""
        # Mock the Confluence API response
        mock_api_response = {
            "results": [{"id": "att1", "title": "test1.txt"}],
            "start": 25,
            "limit": 25,
            "size": 1,
        }
        attachments_mixin.confluence.get_attachments_from_content.return_value = (
            mock_api_response
        )

        # Call the method with custom pagination
        result = attachments_mixin.get_content_attachments("123456", start=25, limit=25)

        # Assertions
        assert result["success"] is True
        attachments_mixin.confluence.get_attachments_from_content.assert_called_once_with(
            "123456", start=25, limit=25
        )

    def test_get_content_attachments_empty_results(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test retrieval when no attachments exist."""
        # Mock the Confluence API response with empty results
        mock_api_response = {"results": [], "start": 0, "limit": 50, "size": 0}
        attachments_mixin.confluence.get_attachments_from_content.return_value = (
            mock_api_response
        )

        # Call the method
        result = attachments_mixin.get_content_attachments("123456")

        # Assertions
        assert result["success"] is True
        assert len(result["attachments"]) == 0
        assert result["total"] == 0

    def test_get_content_attachments_no_content_id(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test retrieval with no content ID."""
        result = attachments_mixin.get_content_attachments("")

        # Assertions
        assert result["success"] is False
        assert "No content ID provided" in result["error"]
        attachments_mixin.confluence.get_attachments_from_content.assert_not_called()

    def test_get_content_attachments_api_error(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test retrieval when API error occurs."""
        # Mock the Confluence API to raise an exception
        attachments_mixin.confluence.get_attachments_from_content.side_effect = (
            Exception("API Error")
        )

        # Call the method
        result = attachments_mixin.get_content_attachments("123456")

        # Assertions
        assert result["success"] is False
        assert "API Error" in result["error"]

    def test_get_content_attachments_v2_oauth(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test getting attachments using v2 API (OAuth)."""
        # Mock config URL to be cloud (contains .atlassian.net) and OAuth
        with patch.object(
            attachments_mixin.config, "url", "https://test.atlassian.net/wiki"
        ):
            attachments_mixin.config.auth_type = "oauth"

            # Mock the v2 API method
            mock_v2_get = Mock(
                return_value={
                    "results": [
                        {"id": "att1", "title": "file1.txt", "type": "attachment"},
                        {"id": "att2", "title": "file2.pdf", "type": "attachment"},
                    ],
                    "size": 2,
                    "start": 0,
                    "limit": 50,
                }
            )

            with patch(
                "mcp_atlassian.confluence.attachments.ConfluenceV2Adapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.get_page_attachments = mock_v2_get
                mock_adapter_class.return_value = mock_adapter

                # Call the method
                result = attachments_mixin.get_content_attachments("123456")

                # Assertions
                assert result["success"] is True
                assert result["content_id"] == "123456"
                assert len(result["attachments"]) == 2
                assert result["total"] == 2
                # Updated to include filename and media_type parameters added during UAT
                mock_v2_get.assert_called_once_with(
                    page_id="123456",
                    start=0,
                    limit=50,
                    filename=None,
                    media_type=None,
                )

    def test_get_content_attachments_v2_with_pagination(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test v2 API pagination parameters are passed correctly."""
        # Mock config URL to be cloud and OAuth
        with patch.object(
            attachments_mixin.config, "url", "https://test.atlassian.net/wiki"
        ):
            attachments_mixin.config.auth_type = "oauth"

            mock_v2_get = Mock(
                return_value={
                    "results": [],
                    "size": 0,
                    "start": 25,
                    "limit": 10,
                }
            )

            with patch(
                "mcp_atlassian.confluence.attachments.ConfluenceV2Adapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.get_page_attachments = mock_v2_get
                mock_adapter_class.return_value = mock_adapter

                # Call with custom pagination
                result = attachments_mixin.get_content_attachments(
                    "123456", start=25, limit=10
                )

                # Assertions
                assert result["success"] is True
                assert result["start"] == 25
                assert result["limit"] == 10
                # Updated to include filename and media_type parameters added during UAT
                mock_v2_get.assert_called_once_with(
                    page_id="123456",
                    start=25,
                    limit=10,
                    filename=None,
                    media_type=None,
                )

    def test_get_content_attachments_v2_error(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test error handling when v2 API fails."""
        # Mock config URL to be cloud and OAuth
        with patch.object(
            attachments_mixin.config, "url", "https://test.atlassian.net/wiki"
        ):
            attachments_mixin.config.auth_type = "oauth"

            with patch(
                "mcp_atlassian.confluence.attachments.ConfluenceV2Adapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.get_page_attachments.side_effect = ValueError(
                    "Page not found"
                )
                mock_adapter_class.return_value = mock_adapter

                # Call the method
                result = attachments_mixin.get_content_attachments("999999")

                # Assertions
                assert result["success"] is False
                assert "Page not found" in result["error"]

    # Delete attachment tests
    def test_delete_attachment_success_v1(self, attachments_mixin: AttachmentsMixin):
        """Test successful deletion using v1 API (non-OAuth)."""
        # Ensure non-OAuth (v1 path)
        attachments_mixin.config.auth_type = "basic"

        # Mock the session delete call
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        attachments_mixin.confluence._session.delete.return_value = mock_response

        # Call the method
        result = attachments_mixin.delete_attachment("att123")

        # Assertions
        assert result["success"] is True
        assert result["attachment_id"] == "att123"
        assert "deleted successfully" in result["message"]
        attachments_mixin.confluence._session.delete.assert_called_once()

    def _capture_delete_url(self, attachments_mixin, config_url: str) -> str:
        """Run a v1 delete with the given config URL and return the request URL."""
        attachments_mixin.config.auth_type = "basic"  # force v1 path
        attachments_mixin.config.url = config_url

        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        attachments_mixin.confluence._session.delete.return_value = mock_response

        attachments_mixin.delete_attachment("att123")

        return attachments_mixin.confluence._session.delete.call_args[0][0]

    def test_delete_attachment_v1_cloud_adds_wiki_prefix(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Cloud bare site URL gets the /wiki prefix on the v1 delete endpoint."""
        url = self._capture_delete_url(attachments_mixin, "https://test.atlassian.net")

        assert url == "https://test.atlassian.net/wiki/rest/api/content/att123"

    def test_delete_attachment_v1_cloud_no_double_wiki_prefix(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Cloud URL already ending in /wiki must not become /wiki/wiki."""
        url = self._capture_delete_url(
            attachments_mixin, "https://test.atlassian.net/wiki"
        )

        assert "/wiki/wiki" not in url
        assert url == "https://test.atlassian.net/wiki/rest/api/content/att123"

    def test_delete_attachment_v1_server_dc_no_wiki_prefix(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Server/DC URLs are unchanged — no /wiki prefix is added."""
        url = self._capture_delete_url(
            attachments_mixin, "https://confluence.example.com"
        )

        assert "/wiki" not in url
        assert url == "https://confluence.example.com/rest/api/content/att123"

    def test_delete_attachment_success_v2(self, attachments_mixin: AttachmentsMixin):
        """Test successful deletion using v2 API (OAuth)."""
        # Mock config URL to be cloud and OAuth
        with patch.object(
            attachments_mixin.config, "url", "https://test.atlassian.net/wiki"
        ):
            attachments_mixin.config.auth_type = "oauth"

            with patch(
                "mcp_atlassian.confluence.attachments.ConfluenceV2Adapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.delete_attachment.return_value = None
                mock_adapter_class.return_value = mock_adapter

                # Call the method
                result = attachments_mixin.delete_attachment("att456")

                # Assertions
                assert result["success"] is True
                assert result["attachment_id"] == "att456"
                assert "deleted successfully" in result["message"]
                mock_adapter.delete_attachment.assert_called_once_with("att456")

    def test_delete_attachment_no_id(self, attachments_mixin: AttachmentsMixin):
        """Test deletion fails when no attachment ID is provided."""
        result = attachments_mixin.delete_attachment("")

        assert result["success"] is False
        assert "No attachment ID provided" in result["error"]

    def test_delete_attachment_v1_http_error(self, attachments_mixin: AttachmentsMixin):
        """Test deletion fails with HTTP error using v1 API."""
        # Ensure non-OAuth (v1 path)
        attachments_mixin.config.auth_type = "basic"

        # Mock session delete to raise HTTPError
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        attachments_mixin.confluence._session.delete.return_value = mock_response

        # Call the method
        result = attachments_mixin.delete_attachment("att999")

        # Assertions
        assert result["success"] is False
        assert "404 Not Found" in result["error"]

    def test_delete_attachment_v2_error(self, attachments_mixin: AttachmentsMixin):
        """Test deletion fails when v2 adapter raises error."""
        # Mock config URL to be cloud and OAuth
        with patch.object(
            attachments_mixin.config, "url", "https://test.atlassian.net/wiki"
        ):
            attachments_mixin.config.auth_type = "oauth"

            with patch(
                "mcp_atlassian.confluence.attachments.ConfluenceV2Adapter"
            ) as mock_adapter_class:
                mock_adapter = Mock()
                mock_adapter.delete_attachment.side_effect = ValueError(
                    "Attachment not found"
                )
                mock_adapter_class.return_value = mock_adapter

                # Call the method
                result = attachments_mixin.delete_attachment("att999")

                # Assertions
                assert result["success"] is False
                assert "Attachment not found" in result["error"]

    def test_delete_attachment_v1_network_error(
        self, attachments_mixin: AttachmentsMixin
    ):
        """Test deletion handles network errors gracefully."""
        # Ensure non-OAuth (v1 path)
        attachments_mixin.config.auth_type = "basic"

        # Mock session delete to raise connection error
        attachments_mixin.confluence._session.delete.side_effect = Exception(
            "Connection timeout"
        )

        # Call the method
        result = attachments_mixin.delete_attachment("att789")

        # Assertions
        assert result["success"] is False
        assert "Connection timeout" in result["error"]


class TestDownloadAttachmentServerTool:
    """Tests for the server-level download_attachment tool (EmbeddedResource return)."""

    @pytest.mark.asyncio
    async def test_returns_embedded_resource_on_success(self):
        mock_fetcher = MagicMock()
        mock_fetcher._v2_adapter = None
        mock_fetcher.config.url = "https://test.atlassian.net/wiki"

        meta_resp = MagicMock()
        meta_resp.json.return_value = {
            "title": "report.pdf",
            "_links": {"download": "/download/report.pdf"},
            "extensions": {"mediaType": "application/pdf", "fileSize": 100},
        }
        meta_resp.raise_for_status.return_value = None
        mock_fetcher.confluence._session.get.return_value = meta_resp

        mock_fetcher.fetch_attachment_content.return_value = b"pdf content"

        with patch(
            "mcp_atlassian.servers.confluence.get_confluence_fetcher",
            AsyncMock(return_value=mock_fetcher),
        ):
            from mcp_atlassian.servers.confluence import (
                download_attachment as server_download_attachment,
            )

            result = await server_download_attachment(
                ctx=MagicMock(), attachment_id="att123456"
            )

        assert isinstance(result, EmbeddedResource)
        assert result.resource.mimeType == "application/pdf"
        assert result.resource.blob

    @pytest.mark.asyncio
    async def test_returns_text_on_missing_download_url(self):
        mock_fetcher = MagicMock()
        mock_fetcher._v2_adapter = None
        mock_fetcher.config.url = "https://test.atlassian.net/wiki"

        meta_resp = MagicMock()
        meta_resp.json.return_value = {
            "title": "report.pdf",
            "_links": {},
            "extensions": {"mediaType": "application/pdf", "fileSize": 100},
        }
        meta_resp.raise_for_status.return_value = None
        mock_fetcher.confluence._session.get.return_value = meta_resp

        with patch(
            "mcp_atlassian.servers.confluence.get_confluence_fetcher",
            AsyncMock(return_value=mock_fetcher),
        ):
            from mcp_atlassian.servers.confluence import (
                download_attachment as server_download_attachment,
            )

            result = await server_download_attachment(
                ctx=MagicMock(), attachment_id="att123456"
            )

        assert isinstance(result, TextContent)
        data = json.loads(result.text)
        assert data["success"] is False
        assert "download URL" in data["error"]

    @pytest.mark.asyncio
    async def test_returns_text_on_size_exceeded(self):
        mock_fetcher = MagicMock()
        mock_fetcher._v2_adapter = None
        mock_fetcher.config.url = "https://test.atlassian.net/wiki"

        meta_resp = MagicMock()
        meta_resp.json.return_value = {
            "title": "huge.bin",
            "_links": {"download": "/download/huge.bin"},
            "extensions": {
                "mediaType": "application/octet-stream",
                "fileSize": 60 * 1024 * 1024,
            },
        }
        meta_resp.raise_for_status.return_value = None
        mock_fetcher.confluence._session.get.return_value = meta_resp

        with patch(
            "mcp_atlassian.servers.confluence.get_confluence_fetcher",
            AsyncMock(return_value=mock_fetcher),
        ):
            from mcp_atlassian.servers.confluence import (
                download_attachment as server_download_attachment,
            )

            result = await server_download_attachment(
                ctx=MagicMock(), attachment_id="att_huge"
            )

        assert isinstance(result, TextContent)
        data = json.loads(result.text)
        assert data["success"] is False
        assert "50 MB" in data["error"]

    @pytest.mark.asyncio
    async def test_returns_text_on_exception(self):
        mock_fetcher = MagicMock()
        mock_fetcher._v2_adapter = None
        mock_fetcher.config.url = "https://test.atlassian.net/wiki"
        mock_fetcher.confluence._session.get.side_effect = Exception("Connection error")

        with patch(
            "mcp_atlassian.servers.confluence.get_confluence_fetcher",
            AsyncMock(return_value=mock_fetcher),
        ):
            from mcp_atlassian.servers.confluence import (
                download_attachment as server_download_attachment,
            )

            result = await server_download_attachment(
                ctx=MagicMock(), attachment_id="att123456"
            )

        assert isinstance(result, TextContent)
        data = json.loads(result.text)
        assert data["success"] is False
        assert "Connection error" in data["error"]


class TestDownloadContentAttachmentsServerTool:
    """Tests for the server-level download_content_attachments tool (EmbeddedResource return)."""

    @pytest.mark.asyncio
    async def test_returns_summary_plus_embedded_resources(self):
        mock_fetcher = MagicMock()
        mock_fetcher.config.url = "https://test.atlassian.net/wiki"
        mock_fetcher.get_content_attachments.return_value = {
            "success": True,
            "attachments": [
                {
                    "id": "att1",
                    "title": "file1.txt",
                    "extensions": {"mediaType": "text/plain", "fileSize": 12},
                    "_links": {"download": "/download/file1.txt"},
                }
            ],
        }

        mock_fetcher.fetch_attachment_content.return_value = b"hello world!"

        with patch(
            "mcp_atlassian.servers.confluence.get_confluence_fetcher",
            AsyncMock(return_value=mock_fetcher),
        ):
            from mcp_atlassian.servers.confluence import (
                download_content_attachments as server_download_content,
            )

            results = await server_download_content(
                ctx=MagicMock(), content_id="123456"
            )

        assert len(results) == 2
        assert isinstance(results[0], TextContent)
        summary = json.loads(results[0].text)
        assert summary["success"] is True
        assert summary["downloaded"] == 1
        assert isinstance(results[1], EmbeddedResource)
        assert results[1].resource.mimeType == "text/plain"

    @pytest.mark.asyncio
    async def test_returns_text_when_no_attachments(self):
        mock_fetcher = MagicMock()
        mock_fetcher.get_content_attachments.return_value = {
            "success": True,
            "attachments": [],
        }

        with patch(
            "mcp_atlassian.servers.confluence.get_confluence_fetcher",
            AsyncMock(return_value=mock_fetcher),
        ):
            from mcp_atlassian.servers.confluence import (
                download_content_attachments as server_download_content,
            )

            results = await server_download_content(
                ctx=MagicMock(), content_id="123456"
            )

        assert len(results) == 1
        assert isinstance(results[0], TextContent)
        summary = json.loads(results[0].text)
        assert summary["success"] is True
        assert "No attachments" in summary["message"]

    @pytest.mark.asyncio
    async def test_returns_error_text_on_api_failure(self):
        mock_fetcher = MagicMock()
        mock_fetcher.get_content_attachments.return_value = {
            "success": False,
            "error": "API error occurred",
        }

        with patch(
            "mcp_atlassian.servers.confluence.get_confluence_fetcher",
            AsyncMock(return_value=mock_fetcher),
        ):
            from mcp_atlassian.servers.confluence import (
                download_content_attachments as server_download_content,
            )

            results = await server_download_content(
                ctx=MagicMock(), content_id="123456"
            )

        assert len(results) == 1
        assert isinstance(results[0], TextContent)
        data = json.loads(results[0].text)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_skips_attachment_over_size_limit(self):
        mock_fetcher = MagicMock()
        mock_fetcher.config.url = "https://test.atlassian.net/wiki"
        mock_fetcher.get_content_attachments.return_value = {
            "success": True,
            "attachments": [
                {
                    "id": "att_big",
                    "title": "huge.bin",
                    "extensions": {
                        "mediaType": "application/octet-stream",
                        "fileSize": 60 * 1024 * 1024,
                    },
                    "_links": {"download": "/download/huge.bin"},
                }
            ],
        }

        with patch(
            "mcp_atlassian.servers.confluence.get_confluence_fetcher",
            AsyncMock(return_value=mock_fetcher),
        ):
            from mcp_atlassian.servers.confluence import (
                download_content_attachments as server_download_content,
            )

            results = await server_download_content(
                ctx=MagicMock(), content_id="123456"
            )

        assert len(results) == 1
        assert isinstance(results[0], TextContent)
        summary = json.loads(results[0].text)
        assert summary["downloaded"] == 0
        assert len(summary["failed"]) == 1
        assert "50 MB" in summary["failed"][0]["error"]


class TestConfluenceAttachmentPathTraversal:
    """Security regression tests for path traversal in Confluence attachments."""

    @pytest.fixture
    def confluence_mixin(self) -> AttachmentsMixin:
        """Create an AttachmentsMixin for path traversal testing."""
        with patch(
            "mcp_atlassian.confluence.attachments.ConfluenceClient.__init__"
        ) as mock_init:
            mock_init.return_value = None
            mixin = AttachmentsMixin()
            mixin.confluence = MagicMock()
            mixin.config = MagicMock()
            mixin.config.url = "https://test.atlassian.net/wiki"
            mixin.config.auth_type = "basic"
            mixin.preprocessor = MagicMock()
            return mixin

    def test_download_attachment_absolute_etc_passwd(
        self, confluence_mixin: AttachmentsMixin
    ) -> None:
        """download_attachment rejects absolute path /etc/passwd."""
        result = confluence_mixin.download_attachment(
            "https://example.com/file", "/etc/passwd"
        )
        assert result is False

    def test_download_attachment_relative_traversal(
        self, confluence_mixin: AttachmentsMixin
    ) -> None:
        """download_attachment rejects relative path traversal."""
        result = confluence_mixin.download_attachment(
            "https://example.com/file", "../../../etc/passwd"
        )
        assert result is False

    def test_download_content_attachments_absolute_escape(
        self, confluence_mixin: AttachmentsMixin
    ) -> None:
        """download_content_attachments rejects directory escape."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            confluence_mixin.download_content_attachments("12345", "/etc")

    # --- Upload-side path traversal regression -----------------------------------
    # The download tests above cover the CVE-2026-27825 fix. The upload path used to
    # feed any caller-supplied file_path to the sink after only an os.path.exists
    # check. These tests assert the secure outcome — the sink is never reached with
    # a path outside the workspace.
    # Covers GHSA-wm45, vc25, 93xw, 6cr4, f4p7, f6pj, mrq8, wv8v, p6hp, h7wj, mfv2,
    # f26r, 9547, cc5h (read half). Asserts on the sink (not an exception type)
    # because upload_attachment wraps its body in except Exception -> error dict.

    @pytest.mark.security_regression
    @pytest.mark.parametrize("attack", ["absolute_outside_cwd", "relative_traversal"])
    def test_upload_attachment_does_not_read_outside_workspace(
        self,
        confluence_mixin: AttachmentsMixin,
        tmp_path: Path,
        attack: str,
    ) -> None:
        """A file_path resolving outside the workspace must not reach the sink."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        secret = tmp_path / "secret.txt"  # sibling of workspace -> outside it
        secret.write_bytes(b"SECRET-EXFIL")
        malicious = str(secret) if attack == "absolute_outside_cwd" else "../secret.txt"

        confluence_mixin._upload_attachment_direct = MagicMock(return_value={"id": "1"})

        with patch("os.getcwd", return_value=str(workspace)):
            confluence_mixin.upload_attachment("123456", malicious)

        confluence_mixin._upload_attachment_direct.assert_not_called()


class TestResolveAttachmentDownloadUrl:
    """Tests for AttachmentsMixin._resolve_attachment_download_url.

    Covers the CONFLUENCE_ATTACHMENT_DOWNLOAD_USE_V1 Cloud workaround: when
    enabled, the (removed) legacy /download/attachments/... link is rewritten to
    the v1 REST endpoint; otherwise the original link is preserved.
    """

    def _make_mixin(
        self, *, use_v1: bool | None, url: str = "https://example.atlassian.net/wiki"
    ) -> AttachmentsMixin:
        with patch(
            "mcp_atlassian.confluence.attachments.ConfluenceClient.__init__",
            return_value=None,
        ):
            mixin = AttachmentsMixin()
        config = ConfluenceConfig(url=url, auth_type="basic")
        config.attachment_download_use_v1 = use_v1
        mixin.config = config
        return mixin

    def test_v1_enabled_builds_rest_endpoint(self) -> None:
        mixin = self._make_mixin(use_v1=True)
        url = mixin._resolve_attachment_download_url(
            "/download/attachments/123/foo.png?version=1&api=v2",
            attachment_id="att999",
        )
        assert url == (
            "https://example.atlassian.net/wiki"
            "/rest/api/content/123/child/attachment/att999/download?version=1"
        )

    def test_v1_preserves_only_version_param(self) -> None:
        # The v1 download endpoint documents only ``version``; keep that (so a
        # version-specific link doesn't fall back to latest) and drop the other
        # legacy query params (cacheVersion / api / ...).
        mixin = self._make_mixin(use_v1=True)
        url = mixin._resolve_attachment_download_url(
            "/download/attachments/123/foo.png?version=3&cacheVersion=1&api=v2",
            attachment_id="att999",
        )
        assert url.endswith("/att999/download?version=3")
        assert "cacheVersion" not in url
        assert "api=v2" not in url

    def test_v1_handles_relative_url_without_leading_slash(self) -> None:
        mixin = self._make_mixin(use_v1=True)
        url = mixin._resolve_attachment_download_url(
            "download/attachments/123/foo.png?version=2",
            attachment_id="att999",
        )
        assert url.endswith(
            "/rest/api/content/123/child/attachment/att999/download?version=2"
        )

    def test_v1_enabled_uses_explicit_content_id(self) -> None:
        mixin = self._make_mixin(use_v1=True)
        url = mixin._resolve_attachment_download_url(
            "/download/attachments/123/foo.png",
            attachment_id="att999",
            content_id="555",
        )
        assert "/rest/api/content/555/child/attachment/att999/download" in url

    def test_disabled_returns_legacy_link(self) -> None:
        mixin = self._make_mixin(use_v1=False)
        url = mixin._resolve_attachment_download_url(
            "/download/attachments/123/foo.png", attachment_id="att999"
        )
        assert "/download/attachments/123/" in url
        assert "/child/attachment/" not in url

    def test_missing_attachment_id_falls_back_to_legacy(self) -> None:
        mixin = self._make_mixin(use_v1=True)
        url = mixin._resolve_attachment_download_url(
            "/download/attachments/123/foo.png", attachment_id=None
        )
        assert "/download/attachments/123/" in url
        assert "/child/attachment/" not in url

    def test_auto_cloud_uses_v1(self) -> None:
        mixin = self._make_mixin(use_v1=None)
        url = mixin._resolve_attachment_download_url(
            "/download/attachments/123/foo.png", attachment_id="att999"
        )
        assert "/rest/api/content/123/child/attachment/att999/download" in url

    def test_auto_cloud_adds_wiki_prefix_for_bare_site_url(self) -> None:
        mixin = self._make_mixin(use_v1=None, url="https://example.atlassian.net")
        url = mixin._resolve_attachment_download_url(
            "/download/attachments/123/foo.png", attachment_id="att999"
        )
        assert url == (
            "https://example.atlassian.net/wiki"
            "/rest/api/content/123/child/attachment/att999/download"
        )

    def test_auto_server_dc_returns_legacy(self) -> None:
        mixin = self._make_mixin(use_v1=None, url="https://confluence.example.com")
        url = mixin._resolve_attachment_download_url(
            "/download/attachments/123/foo.png", attachment_id="att999"
        )
        assert "/child/attachment/" not in url
