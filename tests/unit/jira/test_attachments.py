"""Tests for the Jira attachments module."""

from unittest.mock import MagicMock, mock_open, patch

from mcp_atlassian.jira.attachments import AttachmentsMixin
from mcp_atlassian.jira.config import JiraConfig

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

    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Create a mock Jira client
        with (
            patch("mcp_atlassian.jira.client.Jira"),
            patch("mcp_atlassian.jira.client.configure_ssl_verification"),
        ):
            config = JiraConfig(
                url="https://test.atlassian.net",
                auth_type="basic",
                username="test_username",
                api_token="test_token",
            )
            self.client = AttachmentsMixin(config=config)
            self.client.jira = MagicMock()
            self.client.jira._session = MagicMock()

    def test_download_attachment_success(self):
        """Test successful attachment download."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status = MagicMock()
        self.client.jira._session.get.return_value = mock_response

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
            result = self.client.download_attachment(
                "https://test.url/attachment", "/tmp/test_file.txt"
            )

            # Assertions
            assert result is True
            self.client.jira._session.get.assert_called_once_with(
                "https://test.url/attachment", stream=True
            )
            mock_file.assert_called_once_with("/tmp/test_file.txt", "wb")
            mock_file().write.assert_called_once_with(b"test content")
            mock_makedirs.assert_called_once()

    def test_download_attachment_relative_path(self):
        """Test attachment download with a relative path."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status = MagicMock()
        self.client.jira._session.get.return_value = mock_response

        # Mock file operations and os.path.abspath
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
            result = self.client.download_attachment(
                "https://test.url/attachment", "test_file.txt"
            )

            # Assertions
            assert result is True
            mock_isabs.assert_called_once_with("test_file.txt")
            mock_abspath.assert_called_once_with("test_file.txt")
            mock_file.assert_called_once_with("/absolute/path/test_file.txt", "wb")

    def test_download_attachment_no_url(self):
        """Test attachment download with no URL."""
        result = self.client.download_attachment("", "/tmp/test_file.txt")
        assert result is False

    def test_download_attachment_http_error(self):
        """Test attachment download with an HTTP error."""
        # Mock the response to raise an HTTP error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        self.client.jira._session.get.return_value = mock_response

        result = self.client.download_attachment(
            "https://test.url/attachment", "/tmp/test_file.txt"
        )
        assert result is False

    def test_download_attachment_file_write_error(self):
        """Test attachment download with a file write error."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status = MagicMock()
        self.client.jira._session.get.return_value = mock_response

        # Mock file operations to raise an exception during write
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("os.makedirs") as mock_makedirs,
        ):
            mock_file().write.side_effect = OSError("Write error")

            result = self.client.download_attachment(
                "https://test.url/attachment", "/tmp/test_file.txt"
            )
            assert result is False

    def test_download_attachment_file_not_created(self):
        """Test attachment download when file is not created."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status = MagicMock()
        self.client.jira._session.get.return_value = mock_response

        # Mock file operations
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("os.path.exists") as mock_exists,
            patch("os.makedirs") as mock_makedirs,
        ):
            mock_exists.return_value = False  # File doesn't exist after write

            result = self.client.download_attachment(
                "https://test.url/attachment", "/tmp/test_file.txt"
            )
            assert result is False

    def test_download_issue_attachments_success(self):
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
        self.client.jira.issue.return_value = mock_issue

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
                self.client, "download_attachment", return_value=True
            ) as mock_download,
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                side_effect=[mock_attachment1, mock_attachment2],
            ),
        ):
            result = self.client.download_issue_attachments(
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

    def test_download_issue_attachments_relative_path(self):
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
        self.client.jira.issue.return_value = mock_issue

        # Mock attachment
        mock_attachment = MagicMock()
        mock_attachment.filename = "test1.txt"
        mock_attachment.url = "https://test.url/attachment1"
        mock_attachment.size = 100

        # Mock path operations
        with (
            patch.object(
                self.client, "download_attachment", return_value=True
            ) as mock_download,
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                return_value=mock_attachment,
            ),
            patch("os.path.isabs") as mock_isabs,
            patch("os.path.abspath") as mock_abspath,
        ):
            mock_isabs.return_value = False
            mock_abspath.return_value = "/absolute/path/attachments"

            result = self.client.download_issue_attachments("TEST-123", "attachments")

            # Assertions
            assert result["success"] is True
            mock_isabs.assert_called_once_with("attachments")
            mock_abspath.assert_called_once_with("attachments")

    def test_download_issue_attachments_no_attachments(self):
        """Test download when issue has no attachments."""
        # Mock the issue data with no attachments
        mock_issue = {"fields": {"attachment": []}}
        self.client.jira.issue.return_value = mock_issue

        with patch("pathlib.Path.mkdir") as mock_mkdir:
            result = self.client.download_issue_attachments(
                "TEST-123", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is True
            assert "No attachments found" in result["message"]
            assert len(result["downloaded"]) == 0
            assert len(result["failed"]) == 0
            mock_mkdir.assert_called_once()

    def test_download_issue_attachments_issue_not_found(self):
        """Test download when issue cannot be retrieved."""
        self.client.jira.issue.return_value = None

        result = self.client.download_issue_attachments("TEST-123", "/tmp/attachments")

        # Assertions
        assert result["success"] is False
        assert "Could not retrieve issue" in result["error"]

    def test_download_issue_attachments_no_fields(self):
        """Test download when issue has no fields."""
        # Mock the issue data with no fields
        mock_issue = {}  # Missing 'fields' key
        self.client.jira.issue.return_value = mock_issue

        result = self.client.download_issue_attachments("TEST-123", "/tmp/attachments")

        # Assertions
        assert result["success"] is False
        assert "Could not retrieve issue" in result["error"]

    def test_download_issue_attachments_some_failures(self):
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
        self.client.jira.issue.return_value = mock_issue

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
                self.client, "download_attachment", side_effect=[True, False]
            ) as mock_download,
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch(
                "mcp_atlassian.models.jira.JiraAttachment.from_api_response",
                side_effect=[mock_attachment1, mock_attachment2],
            ),
        ):
            result = self.client.download_issue_attachments(
                "TEST-123", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is True
            assert len(result["downloaded"]) == 1
            assert len(result["failed"]) == 1
            assert result["downloaded"][0]["filename"] == "test1.txt"
            assert result["failed"][0]["filename"] == "test2.txt"
            assert mock_download.call_count == 2

    def test_download_issue_attachments_missing_url(self):
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
        self.client.jira.issue.return_value = mock_issue

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
        ):
            result = self.client.download_issue_attachments(
                "TEST-123", "/tmp/attachments"
            )

            # Assertions
            assert result["success"] is True
            assert len(result["downloaded"]) == 0
            assert len(result["failed"]) == 1
            assert result["failed"][0]["filename"] == "test1.txt"
            assert "No URL available" in result["failed"][0]["error"]

    # Tests for upload_attachment method

    def test_upload_attachment_success(self):
        """Test successful attachment upload."""
        # Mock the Jira API response
        mock_attachment_response = {
            "id": "12345",
            "filename": "test_file.txt",
            "size": 100,
        }
        self.client.jira.add_attachment.return_value = mock_attachment_response

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
            result = self.client.upload_attachment(
                "TEST-123", "/absolute/path/test_file.txt"
            )

            # Assertions
            assert result["success"] is True
            assert result["issue_key"] == "TEST-123"
            assert result["filename"] == "test_file.txt"
            assert result["size"] == 100
            assert result["id"] == "12345"
            self.client.jira.add_attachment.assert_called_once_with(
                issue_key="TEST-123", filename="/absolute/path/test_file.txt"
            )

    def test_upload_attachment_relative_path(self):
        """Test attachment upload with a relative path."""
        # Mock the Jira API response
        mock_attachment_response = {
            "id": "12345",
            "filename": "test_file.txt",
            "size": 100,
        }
        self.client.jira.add_attachment.return_value = mock_attachment_response

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
            result = self.client.upload_attachment("TEST-123", "test_file.txt")

            # Assertions
            assert result["success"] is True
            mock_isabs.assert_called_once_with("test_file.txt")
            mock_abspath.assert_called_once_with("test_file.txt")
            self.client.jira.add_attachment.assert_called_once_with(
                issue_key="TEST-123", filename="/absolute/path/test_file.txt"
            )

    def test_upload_attachment_no_issue_key(self):
        """Test attachment upload with no issue key."""
        result = self.client.upload_attachment("", "/path/to/file.txt")

        # Assertions
        assert result["success"] is False
        assert "No issue key provided" in result["error"]
        self.client.jira.add_attachment.assert_not_called()

    def test_upload_attachment_no_file_path(self):
        """Test attachment upload with no file path."""
        result = self.client.upload_attachment("TEST-123", "")

        # Assertions
        assert result["success"] is False
        assert "No file path provided" in result["error"]
        self.client.jira.add_attachment.assert_not_called()

    def test_upload_attachment_file_not_found(self):
        """Test attachment upload when file doesn't exist."""
        # Mock file operations
        with (
            patch("os.path.exists") as mock_exists,
            patch("os.path.isabs") as mock_isabs,
            patch("os.path.abspath") as mock_abspath,
            patch("builtins.open", mock_open(read_data=b"test content")),
        ):
            mock_exists.return_value = False
            mock_isabs.return_value = True
            mock_abspath.return_value = "/absolute/path/test_file.txt"

            result = self.client.upload_attachment(
                "TEST-123", "/absolute/path/test_file.txt"
            )

            # Assertions
            assert result["success"] is False
            assert "File not found" in result["error"]
            self.client.jira.add_attachment.assert_not_called()

    def test_upload_attachment_api_error(self):
        """Test attachment upload with an API error."""
        # Mock the Jira API to raise an exception
        self.client.jira.add_attachment.side_effect = Exception("API Error")

        # Mock file operations
        with (
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

            result = self.client.upload_attachment(
                "TEST-123", "/absolute/path/test_file.txt"
            )

            # Assertions
            assert result["success"] is False
            assert "API Error" in result["error"]

    def test_upload_attachment_no_response(self):
        """Test attachment upload when API returns no response."""
        # Mock the Jira API to return None
        self.client.jira.add_attachment.return_value = None

        # Mock file operations
        with (
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

            result = self.client.upload_attachment(
                "TEST-123", "/absolute/path/test_file.txt"
            )

            # Assertions
            assert result["success"] is False
            assert "Failed to upload attachment" in result["error"]

    # Tests for upload_attachments method

    def test_upload_attachments_success(self):
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
            self.client, "upload_attachment", side_effect=mock_results
        ) as mock_upload:
            # Call the method
            result = self.client.upload_attachments("TEST-123", file_paths)

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

    def test_upload_attachments_mixed_results(self):
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
            self.client, "upload_attachment", side_effect=mock_results
        ) as mock_upload:
            # Call the method
            result = self.client.upload_attachments("TEST-123", file_paths)

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

    def test_upload_attachments_empty_list(self):
        """Test upload with an empty list of file paths."""
        # Call the method with an empty list
        result = self.client.upload_attachments("TEST-123", [])

        # Assertions
        assert result["success"] is False
        assert "No file paths provided" in result["error"]

    def test_upload_attachments_no_issue_key(self):
        """Test upload with no issue key provided."""
        # Call the method with no issue key
        result = self.client.upload_attachments("", ["/path/to/file.txt"])

        # Assertions
        assert result["success"] is False
        assert "No issue key provided" in result["error"]
