"""Module for Jira issue link operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from ..models.jira import JiraIssueLinkType
from ..utils.decorators import handle_auth_errors
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class LinksMixin(JiraClient):
    """Mixin for Jira issue link operations."""

    @handle_auth_errors("Jira API")
    def get_issue_link_types(self) -> list[JiraIssueLinkType]:
        """
        Get all available issue link types.

        Returns:
            List of JiraIssueLinkType objects

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails
                with the Jira API (401/403)
            Exception: If there is an error retrieving issue link types
        """
        try:
            link_types_response = self.jira.get("rest/api/2/issueLinkType")
            if not isinstance(link_types_response, dict):
                msg = (
                    "Unexpected return value type from "
                    f"`jira.get`: {type(link_types_response)}"
                )
                logger.error(msg)
                raise TypeError(msg)

            link_types_data = link_types_response.get("issueLinkTypes", [])

            return [
                JiraIssueLinkType.from_api_response(link_type)
                for link_type in link_types_data
            ]
        except HTTPError:
            raise  # let decorator handle auth errors
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Error getting issue link types: {error_msg}",
                exc_info=True,
            )
            raise Exception(f"Error getting issue link types: {error_msg}") from e

    @handle_auth_errors("Jira API")
    def create_issue_link(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a link between two issues.

        Args:
            data: A dictionary containing the link data with the
                following structure:
                {
                    "type": {"name": "Duplicate" },
                    "inwardIssue": { "key": "ISSUE-1"},
                    "outwardIssue": {"key": "ISSUE-2"},
                    "comment": {
                        "body": "Linked related issue!",
                        "visibility": {
                            "type": "group",
                            "value": "jira-software-users"
                        }
                    }
                }

        Returns:
            Dictionary with the created link information

        Raises:
            ValueError: If required fields are missing
            MCPAtlassianAuthenticationError: If authentication fails
                with the Jira API (401/403)
            Exception: If there is an error creating the issue link
        """
        # Validate required fields
        if not data.get("type"):
            raise ValueError("Link type is required")
        if not data.get("inwardIssue") or not data["inwardIssue"].get("key"):
            raise ValueError("Inward issue key is required")
        if not data.get("outwardIssue") or not data["outwardIssue"].get("key"):
            raise ValueError("Outward issue key is required")

        try:
            # Create the issue link
            self.jira.create_issue_link(data)

            # Return a response with the link information
            inward = data["inwardIssue"]["key"]
            outward = data["outwardIssue"]["key"]
            return {
                "success": True,
                "message": (f"Link created between {inward} and {outward}"),
                "link_type": data["type"]["name"],
                "inward_issue": inward,
                "outward_issue": outward,
            }
        except HTTPError:
            raise  # let decorator handle auth errors
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Error creating issue link: {error_msg}",
                exc_info=True,
            )
            raise Exception(f"Error creating issue link: {error_msg}") from e

    @handle_auth_errors("Jira API")
    def create_remote_issue_link(
        self, issue_key: str, link_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Create a remote issue link (web link or Confluence link).

        Args:
            issue_key: The key of the issue (e.g., 'PROJ-123')
            link_data: Remote link data dict with structure:
                {
                    "object": {
                        "url": "https://example.com/page",
                        "title": "Example Page",
                        "summary": "Optional description",
                        "icon": {
                            "url16x16": "https://example.com/icon16.png",
                            "title": "Icon Title"
                        }
                    },
                    "relationship": "causes"
                }

        Returns:
            Dictionary with the created remote link information

        Raises:
            ValueError: If required fields are missing
            MCPAtlassianAuthenticationError: If authentication fails
                with the Jira API (401/403)
            Exception: If there is an error creating the link
        """
        # Validate required fields
        if not issue_key:
            raise ValueError("Issue key is required")
        if not link_data.get("object"):
            raise ValueError("Link object is required")
        if not link_data["object"].get("url"):
            raise ValueError("URL is required in link object")
        if not link_data["object"].get("title"):
            raise ValueError("Title is required in link object")

        try:
            # Cloud uses v3 API, Server/DC uses v2 API
            if self.config.is_cloud:
                endpoint = f"rest/api/3/issue/{issue_key}/remotelink"
            else:
                endpoint = f"rest/api/2/issue/{issue_key}/remotelink"
            self.jira.post(endpoint, json=link_data)

            return {
                "success": True,
                "message": (f"Remote link created for issue {issue_key}"),
                "issue_key": issue_key,
                "link_title": link_data["object"]["title"],
                "link_url": link_data["object"]["url"],
                "relationship": link_data.get("relationship", ""),
            }
        except HTTPError:
            raise  # let decorator handle auth errors
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Error creating remote issue link: {error_msg}",
                exc_info=True,
            )
            raise Exception(f"Error creating remote issue link: {error_msg}") from e

    @handle_auth_errors("Jira API")
    def remove_issue_link(self, link_id: str) -> dict[str, Any]:
        """
        Remove a link between two issues.

        Args:
            link_id: The ID of the link to remove

        Returns:
            Dictionary with the result of the operation

        Raises:
            ValueError: If link_id is empty
            MCPAtlassianAuthenticationError: If authentication fails
                with the Jira API (401/403)
            Exception: If there is an error removing the issue link
        """
        # Validate input
        if not link_id:
            raise ValueError("Link ID is required")

        try:
            self.jira.remove_issue_link(link_id)

            return {
                "success": True,
                "message": (f"Link with ID {link_id} has been removed"),
                "link_id": link_id,
            }
        except HTTPError:
            raise  # let decorator handle auth errors
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Error removing issue link: {error_msg}",
                exc_info=True,
            )
            raise Exception(f"Error removing issue link: {error_msg}") from e
