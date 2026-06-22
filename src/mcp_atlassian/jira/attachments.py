"""Attachment operations for Jira API."""

import io
import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

from ..models.jira import JiraAttachment
from ..utils.io import validate_safe_path
from ..utils.media import ATTACHMENT_MAX_BYTES, get_image_dimensions
from .client import JiraClient
from .protocols import AttachmentsOperationsProto

# Configure logging
logger = logging.getLogger("mcp-jira")

# Jira Cloud's attachment-content endpoint redirects to the Media Services
# download URL (e.g. ``https://api.media.atlassian.com/file/{uuid}/binary``).
# The media file UUID is the path segment after ``/file/``. Match on this
# fragment only — the host varies (api.media.atlassian.com, api-gev2.*, and
# Forge outbound proxies all appear), so anchoring on the host is fragile.
_MEDIA_FILE_UUID_RE = re.compile(
    r"/file/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


class AttachmentsMixin(JiraClient, AttachmentsOperationsProto):
    """Mixin for Jira attachment operations."""

    def download_attachment(self, url: str, target_path: str) -> bool:
        """
        Download a Jira attachment to the specified path.

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

            # Use the Jira session to download the file
            response = self.jira._session.get(url, stream=True)
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

    def fetch_attachment_content(self, url: str) -> bytes | None:
        """
        Fetch attachment content into memory.

        Args:
            url: The URL of the attachment to download

        Returns:
            The raw bytes of the attachment, or None on failure
        """
        if not url:
            logger.error("No URL provided for attachment fetch")
            return None

        try:
            logger.info(f"Fetching attachment from {url}")
            response = self.jira._session.get(url, stream=True)
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

    def get_issue_attachments(self, issue_key: str) -> list[JiraAttachment]:
        """Return attachment metadata for a Jira issue without downloading.

        Args:
            issue_key: The Jira issue key (e.g., 'PROJ-123').

        Returns:
            A list of JiraAttachment instances.
        """
        logger.info(f"Fetching attachment metadata for {issue_key}")
        issue_data = self.jira.issue(issue_key, fields="attachment")

        if not isinstance(issue_data, dict):
            msg = f"Unexpected return value type from `jira.issue`: {type(issue_data)}"
            logger.error(msg)
            raise TypeError(msg)

        if "fields" not in issue_data:
            logger.error(f"Could not retrieve issue {issue_key}")
            return []

        attachment_data = issue_data.get("fields", {}).get("attachment", [])
        return [
            JiraAttachment.from_api_response(item)
            for item in attachment_data
            if isinstance(item, dict)
        ]

    def get_issue_attachment_contents(self, issue_key: str) -> dict[str, Any]:
        """
        Fetch all attachment contents for a Jira issue into memory.

        Unlike download_issue_attachments, this method does not write to
        the filesystem.  Each attachment is returned as raw bytes so the
        caller (e.g. the MCP server layer) can serialise them however it
        needs (base64 embedded resources, etc.).

        Args:
            issue_key: The Jira issue key (e.g., 'PROJ-123')

        Returns:
            A dictionary with:
                success (bool)
                issue_key (str)
                total (int)
                attachments (list[dict]): each dict has 'filename',
                    'content_type', 'size', and 'data' (bytes)
                failed (list[dict]): each dict has 'filename' and 'error'
        """
        logger.info(f"Fetching attachment contents for {issue_key}")

        issue_data = self.jira.issue(issue_key, fields="attachment")

        if not isinstance(issue_data, dict):
            msg = f"Unexpected return value type from `jira.issue`: {type(issue_data)}"
            logger.error(msg)
            raise TypeError(msg)

        if "fields" not in issue_data:
            logger.error(f"Could not retrieve issue {issue_key}")
            return {
                "success": False,
                "error": f"Could not retrieve issue {issue_key}",
            }

        attachment_data = issue_data.get("fields", {}).get("attachment", [])

        if not attachment_data:
            return {
                "success": True,
                "message": f"No attachments found for issue {issue_key}",
                "attachments": [],
                "failed": [],
            }

        attachments: list[JiraAttachment] = []
        for item in attachment_data:
            if isinstance(item, dict):
                attachments.append(JiraAttachment.from_api_response(item))

        if not attachments:
            return {
                "success": True,
                "message": f"No attachments found for issue {issue_key}",
                "attachments": [],
                "failed": [],
            }

        fetched: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for attachment in attachments:
            if not attachment.url:
                logger.warning(f"No URL for attachment {attachment.filename}")
                failed.append(
                    {"filename": attachment.filename, "error": "No URL available"}
                )
                continue

            if attachment.size > ATTACHMENT_MAX_BYTES:
                logger.warning(
                    f"Skipping attachment {attachment.filename}: "
                    f"{attachment.size} bytes exceeds 50 MB limit"
                )
                failed.append(
                    {
                        "filename": attachment.filename,
                        "error": (
                            f"Attachment '{attachment.filename}' is "
                            f"{attachment.size} bytes which exceeds "
                            "the 50 MB inline limit. Retrieve it "
                            "directly from Jira."
                        ),
                    }
                )
                continue

            data = self.fetch_attachment_content(attachment.url)
            if data is not None:
                content_type = (
                    attachment.content_type
                    or mimetypes.guess_type(attachment.filename)[0]
                    or "application/octet-stream"
                )
                fetched.append(
                    {
                        "filename": attachment.filename,
                        "content_type": content_type,
                        "size": len(data),
                        "data": data,
                    }
                )
            else:
                failed.append(
                    {"filename": attachment.filename, "error": "Fetch failed"}
                )

        return {
            "success": True,
            "issue_key": issue_key,
            "total": len(attachments),
            "attachments": fetched,
            "failed": failed,
        }

    def download_issue_attachments(
        self, issue_key: str, target_dir: str
    ) -> dict[str, Any]:
        """
        Download all attachments for a Jira issue.

        Args:
            issue_key: The Jira issue key (e.g., 'PROJ-123')
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
            f"Downloading attachments for {issue_key} to directory: {target_dir}"
        )

        # Create the target directory if it doesn't exist
        target_path = Path(target_dir)
        target_path.mkdir(parents=True, exist_ok=True)

        # Get the issue with attachments
        logger.info(f"Fetching issue {issue_key} with attachments")
        issue_data = self.jira.issue(issue_key, fields="attachment")

        if not isinstance(issue_data, dict):
            msg = f"Unexpected return value type from `jira.issue`: {type(issue_data)}"
            logger.error(msg)
            raise TypeError(msg)

        if "fields" not in issue_data:
            logger.error(f"Could not retrieve issue {issue_key}")
            return {"success": False, "error": f"Could not retrieve issue {issue_key}"}

        # Process attachments
        attachments = []
        results = []

        # Extract attachments from the API response
        attachment_data = issue_data.get("fields", {}).get("attachment", [])

        if not attachment_data:
            return {
                "success": True,
                "message": f"No attachments found for issue {issue_key}",
                "downloaded": [],
                "failed": [],
            }

        # Create JiraAttachment objects for each attachment
        for attachment in attachment_data:
            if isinstance(attachment, dict):
                attachments.append(JiraAttachment.from_api_response(attachment))

        # Download each attachment
        downloaded = []
        failed = []

        for attachment in attachments:
            if not attachment.url:
                logger.warning(f"No URL for attachment {attachment.filename}")
                failed.append(
                    {"filename": attachment.filename, "error": "No URL available"}
                )
                continue

            # Create a safe filename
            safe_filename = Path(attachment.filename).name
            file_path = target_path / safe_filename

            # Download the attachment
            success = self.download_attachment(attachment.url, str(file_path))

            if success:
                downloaded.append(
                    {
                        "filename": attachment.filename,
                        "path": str(file_path),
                        "size": attachment.size,
                    }
                )
            else:
                failed.append(
                    {"filename": attachment.filename, "error": "Download failed"}
                )

        return {
            "success": True,
            "issue_key": issue_key,
            "total": len(attachments),
            "downloaded": downloaded,
            "failed": failed,
        }

    def upload_attachment(self, issue_key: str, file_path: str) -> dict[str, Any]:
        """
        Upload a single attachment to a Jira issue.

        Args:
            issue_key: The Jira issue key (e.g., 'PROJ-123')
            file_path: The path to the file to upload

        Returns:
            A dictionary with upload result information
        """
        if not issue_key:
            logger.error("No issue key provided for attachment upload")
            return {"success": False, "error": "No issue key provided"}

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

            logger.info(f"Uploading attachment from {file_path} to issue {issue_key}")

            # Use the Jira API to upload the file
            filename = os.path.basename(file_path)
            with open(file_path, "rb") as file:
                attachment = self.jira.add_attachment(
                    issue_key=issue_key, filename=file_path
                )

            if attachment:
                file_size = os.path.getsize(file_path)
                logger.info(
                    f"Successfully uploaded attachment {filename} to {issue_key} (size: {file_size} bytes)"
                )
                return {
                    "success": True,
                    "issue_key": issue_key,
                    "filename": filename,
                    "size": file_size,
                    "id": attachment.get("id")
                    if isinstance(attachment, dict)
                    else None,
                }
            else:
                logger.error(f"Failed to upload attachment {filename} to {issue_key}")
                return {
                    "success": False,
                    "error": f"Failed to upload attachment {filename} to {issue_key}",
                }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error uploading attachment: {error_msg}")
            return {"success": False, "error": error_msg}

    def upload_attachments(
        self, issue_key: str, file_paths: list[str]
    ) -> dict[str, Any]:
        """
        Upload multiple attachments to a Jira issue.

        Args:
            issue_key: The Jira issue key (e.g., 'PROJ-123')
            file_paths: List of paths to files to upload

        Returns:
            A dictionary with upload results
        """
        if not issue_key:
            logger.error("No issue key provided for attachment upload")
            return {"success": False, "error": "No issue key provided"}

        if not file_paths:
            logger.error("No file paths provided for attachment upload")
            return {"success": False, "error": "No file paths provided"}

        logger.info(f"Uploading {len(file_paths)} attachments to issue {issue_key}")

        # Upload each attachment
        uploaded = []
        failed = []

        for file_path in file_paths:
            result = self.upload_attachment(issue_key, file_path)

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
            "issue_key": issue_key,
            "total": len(file_paths),
            "uploaded": uploaded,
            "failed": failed,
        }

    @staticmethod
    def _extract_attachment_id(response: Any) -> str | None:
        """Extract the attachment id from a Jira attachments API response.

        The ``issue/{key}/attachments`` endpoint returns a list of attachment
        objects, but some code paths/mocks return a single dict. Handle both.

        Args:
            response: The raw response from the attachments endpoint.

        Returns:
            The attachment id as a string, or None if it cannot be determined.
        """
        item: Any = None
        if isinstance(response, list) and response:
            item = response[0]
        elif isinstance(response, dict):
            item = response
        if isinstance(item, dict):
            attachment_id = item.get("id")
            return str(attachment_id) if attachment_id is not None else None
        return None

    def upload_attachment_content(
        self, issue_key: str, filename: str, content: bytes
    ) -> dict[str, Any]:
        """
        Upload an attachment to a Jira issue from in-memory bytes.

        Unlike :meth:`upload_attachment`, this does not require filesystem
        access, so it works for remote/stdio servers and for content the LLM
        generates inline (passed as base64 by the server layer).

        Args:
            issue_key: The Jira issue key (e.g., 'PROJ-123')
            filename: The name to give the attachment in Jira
            content: The raw bytes of the file to upload

        Returns:
            A dictionary with upload result information
        """
        if not issue_key:
            logger.error("No issue key provided for attachment upload")
            return {"success": False, "error": "No issue key provided"}

        if not filename:
            logger.error("No filename provided for attachment upload")
            return {"success": False, "error": "No filename provided"}

        if len(content) > ATTACHMENT_MAX_BYTES:
            msg = (
                f"Attachment '{filename}' is {len(content)} bytes which "
                "exceeds the 50 MB limit."
            )
            logger.error(msg)
            return {"success": False, "error": msg}

        try:
            safe_filename = os.path.basename(filename)
            logger.info(
                f"Uploading in-memory attachment '{safe_filename}' "
                f"({len(content)} bytes) to issue {issue_key}"
            )
            # A named buffer makes requests send the correct multipart filename.
            buffer = io.BytesIO(content)
            buffer.name = safe_filename
            response = self.jira.add_attachment_object(issue_key, buffer)

            result: dict[str, Any] = {
                "success": True,
                "issue_key": issue_key,
                "filename": safe_filename,
                "size": len(content),
                "id": self._extract_attachment_id(response),
            }
            # Surface pixel dimensions for images so callers embedding the
            # attachment inline (ADF media nodes) can size it correctly.
            dimensions = get_image_dimensions(content)
            if dimensions is not None:
                result["width"], result["height"] = dimensions
            return result
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error uploading attachment: {error_msg}")
            return {"success": False, "error": error_msg}

    def delete_attachment(self, attachment_id: str) -> dict[str, Any]:
        """
        Delete a Jira attachment by its ID.

        Args:
            attachment_id: The numeric ID of the attachment to delete

        Returns:
            A dictionary describing the result of the deletion
        """
        if not attachment_id:
            logger.error("No attachment ID provided for deletion")
            return {"success": False, "error": "No attachment ID provided"}

        try:
            logger.info(f"Deleting attachment {attachment_id}")
            self.jira.remove_attachment(attachment_id)
            return {
                "success": True,
                "attachment_id": attachment_id,
                "message": f"Attachment {attachment_id} deleted successfully",
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error deleting attachment {attachment_id}: {error_msg}")
            return {
                "success": False,
                "attachment_id": attachment_id,
                "error": error_msg,
            }

    def upload_attachment_from_path(
        self, issue_key: str, file_path: str
    ) -> dict[str, Any]:
        """
        Upload a local file to a Jira issue, returning a reliable attachment id.

        Reads the file into memory and delegates to
        :meth:`upload_attachment_content`, so the returned ``id`` is correct
        (the legacy :meth:`upload_attachment` cannot report it because the
        attachments endpoint returns a list).

        Any absolute path is accepted (e.g. screenshots under ``/tmp`` or
        ``/var/folders``); unlike the download helpers this read is not
        confined to the working directory, since uploading is an explicit,
        operator-initiated action.

        Args:
            issue_key: The Jira issue key (e.g., 'PROJ-123')
            file_path: Path to the local file to upload

        Returns:
            A dictionary with upload result information
        """
        if not file_path:
            logger.error("No file path provided for attachment upload")
            return {"success": False, "error": "No file path provided"}

        try:
            if not os.path.isabs(file_path):
                file_path = os.path.abspath(file_path)
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return {"success": False, "error": f"File not found: {file_path}"}
            with open(file_path, "rb") as fh:
                content = fh.read()
            return self.upload_attachment_content(
                issue_key, os.path.basename(file_path), content
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error uploading attachment from path: {error_msg}")
            return {"success": False, "error": error_msg}

    @staticmethod
    def _extract_media_file_uuid(text: str | None) -> str | None:
        """Return the media file UUID from a media-download URL, if present."""
        if not text:
            return None
        match = _MEDIA_FILE_UUID_RE.search(text)
        return match.group(1) if match else None

    def get_attachment_media_id(self, attachment_id: str) -> str | None:
        """
        Resolve the Media Services file UUID for an uploaded attachment.

        Inline ADF ``media`` nodes require the Media Services UUID, which
        differs from the REST attachment id. Jira Cloud exposes it only
        indirectly: the ``attachment/content/{id}`` endpoint redirects to the
        media download URL (``.../file/{uuid}/binary``), and the UUID is the
        ``/file/`` path segment.

        Resolution is attempted in two passes:

        1. Fast path — request the endpoint *without* following the redirect
           and read the UUID from the ``Location`` header. This is the
           documented single-hop behaviour.
        2. Fallback — when the first ``Location`` is not the media URL (e.g.
           behind the OAuth gateway ``api.atlassian.com/ex/jira/{cloudId}``, a
           corporate proxy, or a multi-hop redirect), follow the whole chain
           and scan every hop's URL for the ``/file/{uuid}`` fragment.
           ``requests`` strips the ``Authorization`` header on cross-host
           redirects, so following to the media host leaks no credentials.

        Args:
            attachment_id: The REST attachment id returned when uploading

        Returns:
            The media UUID string, or None if it cannot be resolved
        """
        if not attachment_id:
            return None

        url = self.jira.resource_url(
            f"attachment/content/{attachment_id}", api_version="3"
        )

        # --- Pass 1: documented single-hop redirect (no follow). ---
        first_status: int | str = "unknown"
        first_location = ""
        try:
            response = self.jira._session.get(url, allow_redirects=False, stream=True)
            first_status = getattr(response, "status_code", "unknown")
            first_location = response.headers.get("Location", "")
            response.close()
            media_id = self._extract_media_file_uuid(first_location)
            if media_id:
                return media_id
        except Exception as e:
            logger.error(
                f"Error resolving media id for attachment {attachment_id}: {str(e)}"
            )
            return None

        # --- Pass 2: follow the full redirect chain and scan each hop. ---
        try:
            followed = self.jira._session.get(url, allow_redirects=True, stream=True)
            candidates: list[str] = []
            for hop in followed.history or []:
                candidates.append(hop.headers.get("Location", ""))
                candidates.append(getattr(hop, "url", "") or "")
            candidates.append(getattr(followed, "url", "") or "")
            followed.close()
            for candidate in candidates:
                media_id = self._extract_media_file_uuid(candidate)
                if media_id:
                    return media_id
        except Exception as e:
            logger.error(
                f"Error resolving media id for attachment {attachment_id} "
                f"via the redirect chain: {str(e)}"
            )
            return None

        logger.error(
            "Could not resolve the media id for attachment %s: the "
            "attachment-content endpoint returned HTTP %s and no hop exposed a "
            "'/file/{uuid}' media URL (first-hop Location: %s). The instance "
            "likely routes attachment content through a gateway/proxy that "
            "hides the media URL.",
            attachment_id,
            first_status,
            (first_location[:120] or "<none>"),
        )
        return None
