"""Attachment operations for Jira API."""

import logging
import os
from pathlib import Path
from typing import Any

from ..models.jira import JiraAttachment
from .client import JiraClient

# Configure logging
logger = logging.getLogger("mcp-jira")


class AttachmentsMixin(JiraClient):
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

        logger.info(
            f"Downloading attachments for {issue_key} to directory: {target_dir}"
        )

        # Create the target directory if it doesn't exist
        target_path = Path(target_dir)
        target_path.mkdir(parents=True, exist_ok=True)

        # Get the issue with attachments
        logger.info(f"Fetching issue {issue_key} with attachments")
        issue_data = self.jira.issue(issue_key, fields="attachment")

        if not issue_data or "fields" not in issue_data:
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
