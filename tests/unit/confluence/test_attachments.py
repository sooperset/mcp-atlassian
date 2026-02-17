"""Tests for the Confluence attachments module."""

import os
import tempfile
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from mcp_atlassian.confluence.attachments import AttachmentsMixin

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
            # Changed from .post to .put to match implementation
            attachments_mixin.confluence._session.put.side_effect = raise_error
        else:
            mock_response.json.return_value = response_data
            mock_response.raise_for_status.return_value = None
            # Changed from .post to .put to match implementation
            attachments_mixin.confluence._session.put.return_value = mock_response

        return mock_response

    # Tests for upload_attachment method

    def test_upload_attachment_success(self, attachments_mixin: AttachmentsMixin):
        """Test successful attachment upload."""
        # Mock the REST API call
        self._mock_rest_api_upload(attachments_mixin)

        # Mock file operations
        with (
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
            # Changed from .post to .put to match implementation
            attachments_mixin.confluence._session.put.assert_called_once()
            call_args = attachments_mixin.confluence._session.put.call_args

            # Check URL
            assert "/rest/api/content/123456/child/attachment" in call_args[0][0]

            # Check headers include X-Atlassian-Token
            assert call_args[1]["headers"]["X-Atlassian-Token"] == "nocheck"

            # Check minorEdit was passed in data
            assert call_args[1]["data"]["minorEdit"] == "false"
            # Note: comment is now in files dict as multipart form data, not in data dict

    def test_upload_attachment_relative_path(self, attachments_mixin: AttachmentsMixin):
        """Test attachment upload with a relative path."""
        # Mock the REST API call
        self._mock_rest_api_upload(attachments_mixin)

        # Mock file operations
        with (
            patch("os.path.exists") as mock_exists,
            patch("os.path.getsize") as mock_getsize,
            patch("os.path.isabs") as mock_isabs,
            patch("os.path.abspath") as mock_abspath,
            patch("os.path.basename") as mock_basename,
            patch("builtins.open", mock_open(read_data=b"test content")),
        ):
            mock_exists.return_value = True
            mock_getsize.return_value = 100
            mock_isabs.return_value = False
            mock_abspath.return_value = "/absolute/path/test_file.txt"
            mock_basename.return_value = "test_file.txt"

            # Call the method with a relative path
            result = attachments_mixin.upload_attachment("123456", "test_file.txt")

            # Assertions
            assert result["success"] is True
            mock_isabs.assert_called_once_with("test_file.txt")
            mock_abspath.assert_called_once_with("test_file.txt")

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

            # Assertions
            assert result["success"] is False
            # When direct API fails, we get generic failure message
            assert "Failed to upload attachment" in result["error"]

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
        ):
            mock_exists.return_value = False  # File doesn't exist after write

            result = attachments_mixin.download_attachment(
                "https://test.url/attachment", "/tmp/test_file.txt"
            )
            assert result is False

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
        with patch.object(
            attachments_mixin,
            "get_content_attachments",
            return_value={"success": False, "error": "API Error"},
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
