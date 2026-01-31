"""Module for Confluence protocol definitions."""

from abc import abstractmethod
from typing import Any, Protocol


class AttachmentsOperationsProto(Protocol):
    """Protocol defining attachments operations interface for Confluence."""

    @abstractmethod
    def upload_attachment(
        self,
        content_id: str,
        file_path: str,
        comment: str | None = None,
        minor_edit: bool = True,
    ) -> dict[str, Any]:
        """
        Upload a single attachment to Confluence content.

        Args:
            content_id: The ID of the content (page/blog post) to attach the file to
            file_path: The path to the file to upload
            comment: Optional comment for the attachment
            minor_edit: Whether this is a minor edit (default: True)

        Returns:
            A dictionary with upload result information
        """

    @abstractmethod
    def upload_attachments(
        self,
        content_id: str,
        file_paths: list[str],
        comment: str | None = None,
        minor_edit: bool = True,
    ) -> dict[str, Any]:
        """
        Upload multiple attachments to Confluence content.

        Args:
            content_id: The ID of the content (page/blog post) to attach files to
            file_paths: List of paths to files to upload
            comment: Optional comment for the attachments
            minor_edit: Whether this is a minor edit (default: True)

        Returns:
            A dictionary with upload results
        """

    @abstractmethod
    def download_attachment(self, url: str, target_path: str) -> bool:
        """
        Download a Confluence attachment to the specified path.

        Args:
            url: The URL of the attachment to download
            target_path: The path where the attachment should be saved

        Returns:
            True if successful, False otherwise
        """

    @abstractmethod
    def download_content_attachments(
        self, content_id: str, target_dir: str
    ) -> dict[str, Any]:
        """
        Download all attachments for Confluence content.

        Args:
            content_id: The ID of the content (page/blog post)
            target_dir: The directory where attachments should be saved

        Returns:
            A dictionary with download results
        """

    @abstractmethod
    def get_content_attachments(
        self, content_id: str, start: int = 0, limit: int = 50
    ) -> dict[str, Any]:
        """
        Get list of attachments for Confluence content.

        Args:
            content_id: The ID of the content (page/blog post)
            start: Starting index for pagination (default: 0)
            limit: Maximum number of attachments to return (default: 50)

        Returns:
            A dictionary with attachment list and metadata
        """

    @abstractmethod
    def delete_attachment(self, attachment_id: str) -> dict[str, Any]:
        """
        Delete an attachment by ID.

        Args:
            attachment_id: The ID of the attachment to delete

        Returns:
            A dictionary with deletion result
        """
