"""Attachment operations for Confluence API."""

import logging
import os
from pathlib import Path
from typing import Any

from ..models.confluence import ConfluenceAttachment
from ..utils.io import validate_safe_path
from ..utils.urls import resolve_relative_url
from .client import ConfluenceClient
from .protocols import AttachmentsOperationsProto
from .v2_adapter import ConfluenceV2Adapter

# Configure logging
logger = logging.getLogger("mcp-confluence")


class AttachmentsMixin(ConfluenceClient, AttachmentsOperationsProto):
    """Mixin for Confluence attachment operations."""

    @property
    def _v2_adapter(self) -> ConfluenceV2Adapter | None:
        """Get v2 API adapter for OAuth authentication.

        Returns:
            ConfluenceV2Adapter instance if OAuth is configured, None otherwise
        """
        if self.config.auth_type == "oauth" and self.config.is_cloud:
            return ConfluenceV2Adapter(
                session=self.confluence._session, base_url=self.confluence.url
            )
        return None

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
            content_id: The Confluence content ID
            file_path: The path to the file to upload
            comment: Optional comment for the attachment
            minor_edit: Whether this is a minor edit (default: True)

        Returns:
            A dictionary with upload result information
        """
        if not content_id:
            logger.error("No content ID provided for attachment upload")
            return {"success": False, "error": "No content ID provided"}

        if not file_path:
            logger.error("No file path provided for attachment upload")
            return {"success": False, "error": "No file path provided"}

        try:
            # Convert to absolute path if relative
            if not os.path.isabs(file_path):
                file_path = os.path.abspath(file_path)

            # Check if file exists
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return {"success": False, "error": f"File not found: {file_path}"}

            logger.info(
                f"Uploading attachment from {file_path} to content {content_id} (minor_edit={minor_edit})"
            )

            # Use direct REST API call to support minorEdit parameter
            filename = os.path.basename(file_path)
            attachment = self._upload_attachment_direct(
                content_id, file_path, filename, comment, minor_edit
            )

            if attachment:
                file_size = os.path.getsize(file_path)
                logger.info(
                    f"Successfully uploaded attachment {filename} to content {content_id} (size: {file_size} bytes)"
                )
                return {
                    "success": True,
                    "content_id": content_id,
                    "filename": filename,
                    "size": file_size,
                    "id": attachment.get("id")
                    if isinstance(attachment, dict)
                    else None,
                }
            else:
                logger.error(
                    f"Failed to upload attachment {filename} to content {content_id}"
                )
                return {
                    "success": False,
                    "error": f"Failed to upload attachment {filename} to content {content_id}",
                }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error uploading attachment: {error_msg}")
            return {"success": False, "error": error_msg}

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
            content_id: The Confluence content ID
            file_paths: List of paths to files to upload
            comment: Optional comment for the attachments
            minor_edit: Whether this is a minor edit (default: True)

        Returns:
            A dictionary with upload results
        """
        if not content_id:
            logger.error("No content ID provided for attachment upload")
            return {"success": False, "error": "No content ID provided"}

        if not file_paths:
            logger.error("No file paths provided for attachment upload")
            return {"success": False, "error": "No file paths provided"}

        logger.info(f"Uploading {len(file_paths)} attachments to content {content_id}")

        # Upload each attachment
        uploaded = []
        failed = []

        for file_path in file_paths:
            result = self.upload_attachment(content_id, file_path, comment, minor_edit)

            if result.get("success"):
                uploaded.append(
                    {
                        "filename": result.get("filename"),
                        "size": result.get("size"),
                        "id": result.get("id"),
                    }
                )
            else:
                failed.append(
                    {
                        "filename": os.path.basename(file_path),
                        "error": result.get("error"),
                    }
                )

        return {
            "success": True,
            "content_id": content_id,
            "total": len(file_paths),
            "uploaded": uploaded,
            "failed": failed,
        }

    def fetch_attachment_content(self, url: str) -> bytes | None:
        """Fetch attachment content into memory.

        Args:
            url: The URL of the attachment to download.

        Returns:
            The raw bytes of the attachment, or None on failure.
        """
        if not url:
            logger.error("No URL provided for attachment fetch")
            return None

        try:
            logger.info(f"Fetching attachment from {url}")
            response = self.confluence._session.get(url, stream=True)
            response.raise_for_status()

            chunks: list[bytes] = []
            for chunk in response.iter_content(chunk_size=8192):
                chunks.append(chunk)

            data = b"".join(chunks)
            logger.info(
                f"Successfully fetched attachment from {url} (size: {len(data)} bytes)"
            )
            return data

        except Exception as e:
            logger.error(f"Error fetching attachment: {str(e)}")
            return None

    def download_attachment(self, url: str, target_path: str) -> bool:
        """
        Download a Confluence attachment to the specified path.

        Args:
            url: The URL of the attachment to download
            target_path: The path where the attachment should be saved

        Returns:
            True if successful, False otherwise
        """
        if not url:
            logger.error("No URL provided for attachment download")
            return False

        try:
            # Convert to absolute path if relative
            if not os.path.isabs(target_path):
                target_path = os.path.abspath(target_path)

            # Guard against path traversal (resolves symlinks)
            validate_safe_path(target_path)

            logger.info(f"Downloading attachment from {url} to {target_path}")

            # Create the directory if it doesn't exist
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            # Use the Confluence session to download the file
            response = self.confluence._session.get(url, stream=True)
            response.raise_for_status()

            # Write the file to disk
            with open(target_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Verify the file was created
            if os.path.exists(target_path):
                file_size = os.path.getsize(target_path)
                logger.info(
                    f"Successfully downloaded attachment to {target_path} (size: {file_size} bytes)"
                )
                return True
            else:
                logger.error(f"File was not created at {target_path}")
                return False

        except Exception as e:
            logger.error(f"Error downloading attachment: {str(e)}")
            return False

    def download_content_attachments(
        self, content_id: str, target_dir: str
    ) -> dict[str, Any]:
        """
        Download all attachments for Confluence content.

        Args:
            content_id: The Confluence content ID
            target_dir: The directory where attachments should be saved

        Returns:
            A dictionary with download results
        """
        # Convert to absolute path if relative
        if not os.path.isabs(target_dir):
            target_dir = os.path.abspath(target_dir)

        # Guard against path traversal (resolves symlinks)
        validate_safe_path(target_dir)

        logger.info(
            f"Downloading attachments for content {content_id} to directory: {target_dir}"
        )

        # Create the target directory if it doesn't exist
        target_path = Path(target_dir)
        target_path.mkdir(parents=True, exist_ok=True)

        # Get the attachments
        logger.info(f"Fetching attachments for content {content_id}")
        attachments_result = self.get_content_attachments(content_id)

        if not attachments_result.get("success"):
            return attachments_result

        attachment_data = attachments_result.get("attachments", [])

        if not attachment_data:
            return {
                "success": True,
                "message": f"No attachments found for content {content_id}",
                "downloaded": [],
                "failed": [],
            }

        # Create ConfluenceAttachment objects for each attachment
        attachments = []
        for attachment in attachment_data:
            if isinstance(attachment, dict):
                attachments.append(ConfluenceAttachment.from_api_response(attachment))

        # Download each attachment
        downloaded = []
        failed = []

        for attachment in attachments:
            if not attachment.download_url:
                logger.warning(f"No download URL for attachment {attachment.title}")
                failed.append(
                    {
                        "filename": attachment.title,
                        "error": "No download URL available",
                    }
                )
                continue

            # Create a safe filename
            safe_filename = Path(attachment.title).name
            file_path = target_path / safe_filename

            # Prepend base URL if download URL is relative
            download_url = resolve_relative_url(
                attachment.download_url, self.config.url
            )

            # Download the attachment
            success = self.download_attachment(download_url, str(file_path))

            if success:
                downloaded.append(
                    {
                        "filename": attachment.title,
                        "path": str(file_path),
                        "size": attachment.file_size,
                    }
                )
            else:
                failed.append(
                    {"filename": attachment.title, "error": "Download failed"}
                )

        return {
            "success": True,
            "content_id": content_id,
            "total": len(attachments),
            "downloaded": downloaded,
            "failed": failed,
        }

    def get_content_attachments(
        self,
        content_id: str,
        start: int = 0,
        limit: int = 50,
        filename: str | None = None,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Get all attachments for Confluence content.

        Args:
            content_id: The Confluence content ID
            start: Starting index for pagination
            limit: Maximum number of results to return
            filename: Optional filename filter (exact match)
            media_type: Optional MIME type filter (exact match)

        Returns:
            A dictionary with attachment information
        """
        if not content_id:
            logger.error("No content ID provided for getting attachments")
            return {"success": False, "error": "No content ID provided"}

        try:
            logger.info(f"Fetching attachments for content {content_id}")

            # Use v2 API for OAuth authentication, v1 API for token/basic auth
            v2_adapter = self._v2_adapter
            if v2_adapter:
                logger.debug(
                    f"Using v2 API for OAuth authentication to get attachments for '{content_id}'"
                )
                # V2 API supports server-side filtering
                response = v2_adapter.get_page_attachments(
                    page_id=content_id,
                    start=start,
                    limit=limit,
                    filename=filename,
                    media_type=media_type,
                )
            else:
                logger.debug(
                    f"Using v1 API for token/basic authentication to get attachments for '{content_id}'"
                )
                # V1 API doesn't support filtering - fetch all, then filter client-side
                response = self.confluence.get_attachments_from_content(
                    content_id, start=start, limit=limit
                )

            attachments = response.get("results", [])
            total = response.get("size", 0)

            # Apply client-side filtering for V1 API when filters are specified
            if not v2_adapter and (filename or media_type):
                filtered = []
                for att in attachments:
                    # Filter by filename (exact match)
                    if filename and att.get("title") != filename:
                        continue
                    # Filter by media_type (exact match)
                    if media_type and att.get("mediaType") != media_type:
                        continue
                    filtered.append(att)

                attachments = filtered
                total = len(filtered)
                logger.debug(
                    f"Client-side filtering: {len(filtered)} of {response.get('size', 0)} attachments matched"
                )

            logger.info(
                f"Retrieved {len(attachments)} attachments for content {content_id}"
            )

            return {
                "success": True,
                "content_id": content_id,
                "attachments": attachments,
                "total": total,
                "start": start,
                "limit": limit,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error getting attachments: {error_msg}")
            return {"success": False, "error": error_msg}

    def _upload_attachment_direct(
        self,
        content_id: str,
        file_path: str,
        filename: str,
        comment: str | None,
        minor_edit: bool,
    ) -> dict[str, Any] | None:
        """
        Upload attachment using direct REST API call.

        This method uses the Confluence REST API directly to support
        the minorEdit parameter, which is not available in the
        atlassian-python-api library's attach_file() method.

        Args:
            content_id: The Confluence content ID
            file_path: Full path to the file
            filename: Name of the file
            comment: Optional comment for the attachment
            minor_edit: Whether this is a minor edit

        Returns:
            Attachment metadata dict if successful, None otherwise
        """
        try:
            # Build the API endpoint URL
            base_url = self.config.url.rstrip("/")
            url = f"{base_url}/rest/api/content/{content_id}/child/attachment"

            # Prepare headers (X-Atlassian-Token required for file uploads)
            headers = {"X-Atlassian-Token": "nocheck"}

            # Prepare multipart form data
            files = {"file": (filename, open(file_path, "rb"))}

            # Comment must be sent with text/plain content-type for proper encoding
            if comment:
                files["comment"] = (None, comment, "text/plain; charset=utf-8")

            data = {}
            if minor_edit is not None:
                data["minorEdit"] = str(minor_edit).lower()

            # Use PUT to support creating new versions of existing attachments
            # PUT will create a new attachment if it doesn't exist, OR create a new
            # version if an attachment with the same filename already exists
            response = self.confluence._session.put(
                url, headers=headers, files=files, data=data
            )
            response.raise_for_status()

            # Parse response
            result = response.json()

            # Return first result if it's a list
            if isinstance(result, dict) and "results" in result:
                results = result.get("results", [])
                return results[0] if results else result
            return result

        except Exception as e:
            logger.error(f"Direct API upload failed: {e}")
            return None
        finally:
            # Close file handles (only for actual file objects, not text fields like comment)
            if "files" in locals() and "file" in files:
                file_tuple = files["file"]
                if len(file_tuple) >= 2 and hasattr(file_tuple[1], "close"):
                    file_tuple[1].close()

    def delete_attachment(self, attachment_id: str) -> dict[str, Any]:
        """
        Delete an attachment by ID.

        Args:
            attachment_id: The Confluence attachment ID

        Returns:
            A dictionary with deletion result
        """
        if not attachment_id:
            logger.error("No attachment ID provided for deletion")
            return {"success": False, "error": "No attachment ID provided"}

        try:
            logger.info(f"Deleting attachment {attachment_id}")

            # Use v2 API for OAuth authentication, v1 API for token/basic auth
            v2_adapter = self._v2_adapter
            if v2_adapter:
                logger.debug(
                    f"Using v2 API for OAuth authentication to delete attachment '{attachment_id}'"
                )
                v2_adapter.delete_attachment(attachment_id)
            else:
                logger.debug(
                    f"Using v1 API for token/basic authentication to delete attachment '{attachment_id}'"
                )
                # Use v1 API endpoint for deletion
                base_url = self.config.url.rstrip("/")
                url = f"{base_url}/rest/api/content/{attachment_id}"
                response = self.confluence._session.delete(url)
                response.raise_for_status()

            logger.info(f"Successfully deleted attachment {attachment_id}")

            return {
                "success": True,
                "attachment_id": attachment_id,
                "message": "Attachment deleted successfully",
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error deleting attachment: {error_msg}")
            return {"success": False, "error": error_msg}
