"""Module for Confluence attachment operations."""

import logging
import os
from pathlib import Path
from typing import Any

from ..models.confluence import ConfluencePage
from .client import ConfluenceClient

logger = logging.getLogger("mcp-confluence")


class AttachmentsMixin(ConfluenceClient):
    """Mixin for Confluence attachment operations."""

    def upload_attachment(
        self,
        page_id: str,
        file_path: str,
        comment: str | None = None,
        minor_edit: bool = False,
    ) -> dict[str, Any]:
        """
        Upload a file attachment to a Confluence page.

        Args:
            page_id: The ID of the Confluence page
            file_path: Path to the file to upload
            comment: Optional comment for the attachment
            minor_edit: Whether this is a minor edit

        Returns:
            Dictionary containing attachment information

        Raises:
            FileNotFoundError: If the file doesn't exist
            Exception: If there is an error uploading the attachment
        """
        try:
            # Validate file exists
            if not Path(file_path).exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            # Get file name
            file_name = Path(file_path).name
            logger.info(f"Uploading attachment '{file_name}' to page {page_id}")

            # Prepare headers for file upload
            headers = {
                "X-Atlassian-Token": "no-check",  # Required for file uploads
            }

            # Prepare the file for upload
            with open(file_path, "rb") as file:
                files = {"file": (file_name, file)}

                # Prepare form data
                data = {}
                if comment:
                    data["comment"] = comment
                if minor_edit:
                    data["minorEdit"] = "true"

                # Upload the attachment
                endpoint = f"rest/api/content/{page_id}/child/attachment"
                response = self.confluence.post(
                    endpoint, files=files, data=data, headers=headers
                )

                if not isinstance(response, dict):
                    msg = f"Unexpected return value type from confluence upload: {type(response)}"
                    logger.error(msg)
                    raise TypeError(msg)

                logger.info(f"Successfully uploaded attachment: {file_name}")
                return response

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error uploading attachment: {str(e)}")
            raise Exception(f"Error uploading attachment: {str(e)}") from e

    def update_attachment(
        self,
        page_id: str,
        attachment_id: str,
        file_path: str,
        comment: str | None = None,
        minor_edit: bool = False,
    ) -> dict[str, Any]:
        """
        Update an existing attachment on a Confluence page.

        Args:
            page_id: The ID of the Confluence page
            attachment_id: The ID of the attachment to update
            file_path: Path to the new file
            comment: Optional comment for the update
            minor_edit: Whether this is a minor edit

        Returns:
            Dictionary containing updated attachment information

        Raises:
            FileNotFoundError: If the file doesn't exist
            Exception: If there is an error updating the attachment
        """
        try:
            # Validate file exists
            if not Path(file_path).exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            # Get file name
            file_name = Path(file_path).name
            logger.info(
                f"Updating attachment {attachment_id} with '{file_name}' on page {page_id}"
            )

            # Prepare headers for file upload
            headers = {
                "X-Atlassian-Token": "no-check",  # Required for file uploads
            }

            # Prepare the file for upload
            with open(file_path, "rb") as file:
                files = {"file": (file_name, file)}

                # Prepare form data
                data = {}
                if comment:
                    data["comment"] = comment
                if minor_edit:
                    data["minorEdit"] = "true"

                # Update the attachment
                endpoint = f"rest/api/content/{page_id}/child/attachment/{attachment_id}/data"
                response = self.confluence.post(
                    endpoint, files=files, data=data, headers=headers
                )

                if not isinstance(response, dict):
                    msg = f"Unexpected return value type from confluence update: {type(response)}"
                    logger.error(msg)
                    raise TypeError(msg)

                logger.info(f"Successfully updated attachment: {attachment_id}")
                return response

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error updating attachment: {str(e)}")
            raise Exception(f"Error updating attachment: {str(e)}") from e

    def get_attachments(
        self,
        page_id: str,
        start: int = 0,
        limit: int = 50,
        expand: str | None = None,
    ) -> dict[str, Any]:
        """
        Get attachments for a Confluence page.

        Args:
            page_id: The ID of the Confluence page
            start: Starting index for pagination
            limit: Maximum number of attachments to return
            expand: Optional fields to expand

        Returns:
            Dictionary containing attachment information

        Raises:
            Exception: If there is an error retrieving attachments
        """
        try:
            logger.info(f"Getting attachments for page {page_id}")

            # Prepare query parameters
            params = {
                "start": start,
                "limit": limit,
            }

            if expand:
                params["expand"] = expand

            # Get attachments
            endpoint = f"rest/api/content/{page_id}/child/attachment"
            response = self.confluence.get(endpoint, params=params)

            if not isinstance(response, dict):
                msg = f"Unexpected return value type from confluence get: {type(response)}"
                logger.error(msg)
                raise TypeError(msg)

            logger.info(
                f"Successfully retrieved {len(response.get('results', []))} attachments"
            )
            return response

        except Exception as e:
            logger.error(f"Error getting attachments: {str(e)}")
            raise Exception(f"Error getting attachments: {str(e)}") from e

    def get_attachment(
        self,
        page_id: str,
        attachment_id: str,
        expand: str | None = None,
    ) -> dict[str, Any]:
        """
        Get a specific attachment from a Confluence page.

        Args:
            page_id: The ID of the Confluence page
            attachment_id: The ID of the attachment
            expand: Optional fields to expand

        Returns:
            Dictionary containing attachment information

        Raises:
            Exception: If there is an error retrieving the attachment
        """
        try:
            logger.info(f"Getting attachment {attachment_id} from page {page_id}")

            # Prepare query parameters
            params = {}
            if expand:
                params["expand"] = expand

            # Get attachment
            endpoint = f"rest/api/content/{page_id}/child/attachment/{attachment_id}"
            response = self.confluence.get(endpoint, params=params)

            if not isinstance(response, dict):
                msg = f"Unexpected return value type from confluence get: {type(response)}"
                logger.error(msg)
                raise TypeError(msg)

            logger.info(f"Successfully retrieved attachment: {attachment_id}")
            return response

        except Exception as e:
            logger.error(f"Error getting attachment: {str(e)}")
            raise Exception(f"Error getting attachment: {str(e)}") from e

    def delete_attachment(
        self,
        page_id: str,
        attachment_id: str,
    ) -> dict[str, Any]:
        """
        Delete an attachment from a Confluence page.

        Args:
            page_id: The ID of the Confluence page
            attachment_id: The ID of the attachment to delete

        Returns:
            Dictionary containing deletion result

        Raises:
            Exception: If there is an error deleting the attachment
        """
        try:
            logger.info(f"Deleting attachment {attachment_id} from page {page_id}")

            # Delete attachment
            endpoint = f"rest/api/content/{page_id}/child/attachment/{attachment_id}"
            response = self.confluence.delete(endpoint)

            # Handle different response types for deletion
            if response is None:
                # Successful deletion might return None
                result = {"success": True, "message": "Attachment deleted successfully"}
            elif isinstance(response, dict):
                result = response
            else:
                result = {"success": True, "response": str(response)}

            logger.info(f"Successfully deleted attachment: {attachment_id}")
            return result

        except Exception as e:
            logger.error(f"Error deleting attachment: {str(e)}")
            raise Exception(f"Error deleting attachment: {str(e)}") from e

    def download_attachment(
        self,
        page_id: str,
        attachment_id: str,
        download_path: str | None = None,
    ) -> str:
        """
        Download an attachment from a Confluence page.

        Args:
            page_id: The ID of the Confluence page
            attachment_id: The ID of the attachment to download
            download_path: Optional path to save the file (defaults to current directory)

        Returns:
            Path to the downloaded file

        Raises:
            Exception: If there is an error downloading the attachment
        """
        try:
            logger.info(f"Downloading attachment {attachment_id} from page {page_id}")

            # First get attachment metadata to get the filename and download URL
            attachment_info = self.get_attachment(
                page_id, attachment_id, expand="version"
            )

            # Extract filename and download URL
            title = attachment_info.get("title", f"attachment_{attachment_id}")
            download_url = attachment_info.get("_links", {}).get("download")

            if not download_url:
                raise ValueError("No download URL found for attachment")

            # Prepare download path
            if download_path:
                # Use provided path
                if os.path.isdir(download_path):
                    file_path = os.path.join(download_path, title)
                else:
                    file_path = download_path
            else:
                # Use current directory with attachment title
                file_path = title

            # Download the file using the download URL
            # Note: download_url is relative, so we need to make a raw request
            response = self.confluence._session.get(
                f"{self.config.url}{download_url}", stream=True
            )
            response.raise_for_status()

            # Save the file
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Successfully downloaded attachment to: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Error downloading attachment: {str(e)}")
            raise Exception(f"Error downloading attachment: {str(e)}") from e

    def get_attachment_properties(
        self,
        page_id: str,
        attachment_id: str,
        start: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Get properties for a specific attachment.

        Args:
            page_id: The ID of the Confluence page
            attachment_id: The ID of the attachment
            start: Starting index for pagination
            limit: Maximum number of properties to return

        Returns:
            Dictionary containing attachment properties

        Raises:
            Exception: If there is an error retrieving properties
        """
        try:
            logger.info(f"Getting properties for attachment {attachment_id}")

            # Prepare query parameters
            params = {
                "start": start,
                "limit": limit,
            }

            # Get attachment properties
            endpoint = f"rest/api/content/{page_id}/child/attachment/{attachment_id}/property"
            response = self.confluence.get(endpoint, params=params)

            if not isinstance(response, dict):
                msg = f"Unexpected return value type from confluence get: {type(response)}"
                logger.error(msg)
                raise TypeError(msg)

            logger.info(
                f"Successfully retrieved {len(response.get('results', []))} properties"
            )
            return response

        except Exception as e:
            logger.error(f"Error getting attachment properties: {str(e)}")
            raise Exception(f"Error getting attachment properties: {str(e)}") from e
