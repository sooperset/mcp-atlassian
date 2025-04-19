"""Module for Jira issue link operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from ..exceptions import MCPAtlassianAuthenticationError
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class LinksMixin(JiraClient):
    """Mixin for Jira issue link operations."""

    def create_issue_link(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a link between two issues.

        Args:
            data: A dictionary containing the link data with the following structure:
                {
                    "type": {"name": "Duplicate" },  # Link type name (e.g., "Duplicate", "Blocks", "Relates to")
                    "inwardIssue": { "key": "ISSUE-1"},  # The issue that is the source of the link
                    "outwardIssue": {"key": "ISSUE-2"},  # The issue that is the target of the link
                    "comment": {  # Optional comment to add to the link
                        "body": "Linked related issue!",
                        "visibility": {  # Optional visibility settings
                            "type": "group",
                            "value": "jira-software-users"
                        }
                    }
                }

        Returns:
            Dictionary with the created link information

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails with the Jira API (401/403)
            Exception: If there is an error creating the issue link
        """
        try:
            # Validate required fields
            if not data.get("type"):
                raise ValueError("Link type is required")
            if not data.get("inwardIssue") or not data["inwardIssue"].get("key"):
                raise ValueError("Inward issue key is required")
            if not data.get("outwardIssue") or not data["outwardIssue"].get("key"):
                raise ValueError("Outward issue key is required")

            # Create the issue link
            result = self.jira.create_issue_link(data)

            # Return a response with the link information
            response = {
                "success": True,
                "message": f"Link created between {data['inwardIssue']['key']} and {data['outwardIssue']['key']}",
                "link_type": data["type"]["name"],
                "inward_issue": data["inwardIssue"]["key"],
                "outward_issue": data["outwardIssue"]["key"],
            }

            return response

        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code in [
                401,
                403,
            ]:
                error_msg = (
                    f"Authentication failed for Jira API ({http_err.response.status_code}). "
                    "Token may be expired or invalid. Please verify credentials."
                )
                logger.error(error_msg)
                raise MCPAtlassianAuthenticationError(error_msg) from http_err
            else:
                logger.error(f"HTTP error during API call: {http_err}", exc_info=True)
                raise Exception(f"Error creating issue link: {http_err}") from http_err
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error creating issue link: {error_msg}", exc_info=True)
            raise Exception(f"Error creating issue link: {error_msg}") from e

    def remove_issue_link(self, link_id: str) -> dict[str, Any]:
        """
        Remove a link between two issues.

        Args:
            link_id: The ID of the link to remove

        Returns:
            Dictionary with the result of the operation

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails with the Jira API (401/403)
            Exception: If there is an error removing the issue link
        """
        try:
            # Validate input
            if not link_id:
                raise ValueError("Link ID is required")

            # Remove the issue link
            self.jira.remove_issue_link(link_id)

            # Return a response indicating success
            response = {
                "success": True,
                "message": f"Link with ID {link_id} has been removed",
                "link_id": link_id,
            }

            return response

        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code in [
                401,
                403,
            ]:
                error_msg = (
                    f"Authentication failed for Jira API ({http_err.response.status_code}). "
                    "Token may be expired or invalid. Please verify credentials."
                )
                logger.error(error_msg)
                raise MCPAtlassianAuthenticationError(error_msg) from http_err
            else:
                logger.error(f"HTTP error during API call: {http_err}", exc_info=True)
                raise Exception(f"Error removing issue link: {http_err}") from http_err
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error removing issue link: {error_msg}", exc_info=True)
            raise Exception(f"Error removing issue link: {error_msg}") from e
