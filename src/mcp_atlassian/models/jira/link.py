"""
Jira issue link models.

This module provides Pydantic models for Jira issue links and link types.
"""

import logging
from typing import Any

from ..base import ApiModel
from ..constants import EMPTY_STRING, JIRA_DEFAULT_ID, UNKNOWN
from .common import JiraIssueType, JiraPriority, JiraStatus

logger = logging.getLogger(__name__)


class JiraIssueLinkType(ApiModel):
    """
    Model representing a Jira issue link type.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = UNKNOWN
    inward: str = EMPTY_STRING
    outward: str = EMPTY_STRING
    self_url: str | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraIssueLinkType":
        """
        Create a JiraIssueLinkType from a Jira API response.

        Args:
            data: The issue link type data from the Jira API

        Returns:
            A JiraIssueLinkType instance
        """
        if not data:
            return cls()

        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        link_type_id = data.get("id", JIRA_DEFAULT_ID)
        if link_type_id is not None:
            link_type_id = str(link_type_id)

        return cls(
            id=link_type_id,
            name=str(data.get("name", UNKNOWN)),
            inward=str(data.get("inward", EMPTY_STRING)),
            outward=str(data.get("outward", EMPTY_STRING)),
            self_url=data.get("self"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "name": self.name,
            "inward": self.inward,
            "outward": self.outward,
        }

        if self.self_url:
            result["self"] = self.self_url

        return result


class JiraLinkedIssueFields(ApiModel):
    """
    Model representing the fields of a linked issue.
    """

    summary: str = EMPTY_STRING
    status: JiraStatus | None = None
    priority: JiraPriority | None = None
    issuetype: JiraIssueType | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraLinkedIssueFields":
        """
        Create a JiraLinkedIssueFields from a Jira API response.

        Args:
            data: The linked issue fields data from the Jira API

        Returns:
            A JiraLinkedIssueFields instance
        """
        if not data:
            return cls()

        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Extract status data
        status = None
        status_data = data.get("status")
        if status_data:
            status = JiraStatus.from_api_response(status_data)

        # Extract priority data
        priority = None
        priority_data = data.get("priority")
        if priority_data:
            priority = JiraPriority.from_api_response(priority_data)

        # Extract issue type data
        issuetype = None
        issuetype_data = data.get("issuetype")
        if issuetype_data:
            issuetype = JiraIssueType.from_api_response(issuetype_data)

        return cls(
            summary=str(data.get("summary", EMPTY_STRING)),
            status=status,
            priority=priority,
            issuetype=issuetype,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "summary": self.summary,
        }

        if self.status:
            result["status"] = self.status.to_simplified_dict()

        if self.priority:
            result["priority"] = self.priority.to_simplified_dict()

        if self.issuetype:
            result["issuetype"] = self.issuetype.to_simplified_dict()

        return result


class JiraLinkedIssue(ApiModel):
    """
    Model representing a linked issue in Jira.
    """

    id: str = JIRA_DEFAULT_ID
    key: str = EMPTY_STRING
    self_url: str | None = None
    fields: JiraLinkedIssueFields | None = None

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraLinkedIssue":
        """
        Create a JiraLinkedIssue from a Jira API response.

        Args:
            data: The linked issue data from the Jira API

        Returns:
            A JiraLinkedIssue instance
        """
        if not data:
            return cls()

        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Extract fields data
        fields = None
        fields_data = data.get("fields")
        if fields_data:
            fields = JiraLinkedIssueFields.from_api_response(fields_data)

        # Ensure ID is a string
        issue_id = data.get("id", JIRA_DEFAULT_ID)
        if issue_id is not None:
            issue_id = str(issue_id)

        return cls(
            id=issue_id,
            key=str(data.get("key", EMPTY_STRING)),
            self_url=data.get("self"),
            fields=fields,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "key": self.key,
        }

        if self.self_url:
            result["self"] = self.self_url

        if self.fields:
            result["fields"] = self.fields.to_simplified_dict()

        return result


class JiraIssueLink(ApiModel):
    """
    Model representing a link between two Jira issues.
    """

    id: str = JIRA_DEFAULT_ID
    type: JiraIssueLinkType | None = None
    inward_issue: JiraLinkedIssue | None = None
    outward_issue: JiraLinkedIssue | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraIssueLink":
        """
        Create a JiraIssueLink from a Jira API response.

        Args:
            data: The issue link data from the Jira API

        Returns:
            A JiraIssueLink instance
        """
        if not data:
            return cls()

        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Extract link type data
        link_type = None
        type_data = data.get("type")
        if type_data:
            link_type = JiraIssueLinkType.from_api_response(type_data)

        # Extract inward issue data
        inward_issue = None
        inward_issue_data = data.get("inwardIssue")
        if inward_issue_data:
            inward_issue = JiraLinkedIssue.from_api_response(inward_issue_data)

        # Extract outward issue data
        outward_issue = None
        outward_issue_data = data.get("outwardIssue")
        if outward_issue_data:
            outward_issue = JiraLinkedIssue.from_api_response(outward_issue_data)

        # Ensure ID is a string
        link_id = data.get("id", JIRA_DEFAULT_ID)
        if link_id is not None:
            link_id = str(link_id)

        return cls(
            id=link_id,
            type=link_type,
            inward_issue=inward_issue,
            outward_issue=outward_issue,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
        }

        if self.type:
            result["type"] = self.type.to_simplified_dict()

        if self.inward_issue:
            result["inward_issue"] = self.inward_issue.to_simplified_dict()

        if self.outward_issue:
            result["outward_issue"] = self.outward_issue.to_simplified_dict()

        return result
