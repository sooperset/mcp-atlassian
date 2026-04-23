"""Attachment operations for Jira API."""

import logging
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from ..models.jira import JiraAttachment
from ..utils.io import validate_safe_path
from ..utils.media import ATTACHMENT_MAX_BYTES
from .client import JiraClient
from .protocols import AttachmentsOperationsProto

# Configure logging
logger = logging.getLogger("mcp-jira")


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

    def get_embedded_images(self, issue_key: str) -> dict[str, Any]:
        """Fetch images embedded in the rich text editor (description + comments).

        These are images pasted directly into Jira's editor that are NOT
        stored as formal attachments.  They are served via internal servlets
        like ``jeditor_file_provider`` and only appear as ``<img>`` tags in
        the rendered HTML.

        Args:
            issue_key: The Jira issue key (e.g., 'PROJ-123').

        Returns:
            A dictionary with:
                success (bool)
                issue_key (str)
                total (int)
                images (list[dict]): each dict has 'filename',
                    'content_type', 'size', 'data' (bytes), and 'source'
                failed (list[dict]): each dict has 'filename' and 'error'
        """
        logger.info(f"Fetching embedded images for {issue_key}")

        try:
            issue_data = self.jira.issue(
                issue_key,
                fields="description,comment",
                expand="renderedFields",
            )
        except Exception as e:
            logger.error(f"Error fetching issue {issue_key}: {e}")
            return {"success": False, "error": str(e)}

        if not isinstance(issue_data, dict):
            msg = f"Unexpected return type from jira.issue: {type(issue_data)}"
            logger.error(msg)
            raise TypeError(msg)

        rendered = issue_data.get("renderedFields") or {}
        base_url = self.config.url

        # Sammle URLs aus Description und Kommentaren
        image_urls: list[dict[str, str]] = []

        desc_html = rendered.get("description") or ""
        if desc_html:
            for entry in _extract_embedded_image_urls(desc_html, base_url):
                entry["source"] = "description"
                image_urls.append(entry)

        comment_field = rendered.get("comment")
        if isinstance(comment_field, dict):
            comments_list = comment_field.get("comments", [])
        elif isinstance(comment_field, list):
            comments_list = comment_field
        else:
            comments_list = []

        for comment in comments_list:
            if not isinstance(comment, dict):
                continue
            body_html = comment.get("body") or ""
            if body_html:
                comment_id = comment.get("id", "")
                for entry in _extract_embedded_image_urls(body_html, base_url):
                    entry["source"] = "comment"
                    entry["comment_id"] = str(comment_id)
                    image_urls.append(entry)

        if not image_urls:
            return {
                "success": True,
                "issue_key": issue_key,
                "total": 0,
                "images": [],
                "failed": [],
                "message": "No embedded images found",
            }

        # Lade jedes Bild herunter
        images: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for img_info in image_urls:
            url = img_info["url"]
            filename = img_info["filename"]

            data = self.fetch_attachment_content(url)
            if data is None:
                failed.append({"filename": filename, "error": "Fetch failed"})
                continue

            if len(data) > ATTACHMENT_MAX_BYTES:
                failed.append(
                    {
                        "filename": filename,
                        "error": (
                            f"Image is {len(data)} bytes which exceeds "
                            "the 50 MB inline limit."
                        ),
                    }
                )
                continue

            content_type = (
                mimetypes.guess_type(filename)[0] or "image/png"
            )
            images.append(
                {
                    "filename": filename,
                    "content_type": content_type,
                    "size": len(data),
                    "data": data,
                    "source": img_info.get("source", "unknown"),
                }
            )

        return {
            "success": True,
            "issue_key": issue_key,
            "total": len(image_urls),
            "images": images,
            "failed": failed,
        }


def _extract_embedded_image_urls(
    html: str, base_url: str
) -> list[dict[str, str]]:
    """Extract embedded image URLs from rendered HTML.

    Parses ``<img>`` tags, keeps only same-host URLs that are NOT formal
    attachment paths (``/secure/attachment/``, ``/rest/api/``), and returns
    a list of dicts with ``url`` and ``filename`` keys.

    Args:
        html: Rendered HTML string from Jira's ``renderedFields``.
        base_url: The Jira instance base URL for host comparison.

    Returns:
        List of ``{"url": ..., "filename": ...}`` dicts.
    """
    if not html:
        return []

    parsed_base = urlparse(base_url)
    base_host = parsed_base.hostname or ""

    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src or not isinstance(src, str):
            continue

        parsed_src = urlparse(src)
        src_host = parsed_src.hostname or ""

        # Nur gleicher Host — verhindert SSRF
        if src_host.lower() != base_host.lower():
            continue

        # Formale Attachment-URLs ausschliessen
        path_lower = parsed_src.path.lower()
        if "/secure/attachment/" in path_lower or "/rest/api/" in path_lower:
            continue

        # Deduplizierung
        if src in seen_urls:
            continue
        seen_urls.add(src)

        # Dateiname extrahieren: fileName-Query-Param oder URL-Pfad-Basename
        query_params = parse_qs(parsed_src.query)
        file_name_list = query_params.get("fileName", [])
        if file_name_list:
            filename = file_name_list[0]
        else:
            basename = os.path.basename(parsed_src.path)
            # Nur verwenden wenn es eine Dateiendung hat
            if basename and "." in basename:
                filename = basename
            else:
                filename = f"embedded_{len(results)}.png"

        results.append({"url": src, "filename": filename})

    return results
