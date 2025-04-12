"""
Jira issue models.

This module provides Pydantic models for Jira issues.
"""

import logging
from typing import Any, Literal

from pydantic import Field

from ..base import ApiModel, TimestampMixin
from ..constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
    JIRA_DEFAULT_KEY,
)
from .comment import JiraComment
from .common import (
    JiraAttachment,
    JiraIssueType,
    JiraPriority,
    JiraStatus,
    JiraTimetracking,
    JiraUser,
)
from .project import JiraProject

logger = logging.getLogger(__name__)


class JiraIssue(ApiModel, TimestampMixin):
    """
    Model representing a Jira issue.

    This is a comprehensive model containing all the common fields
    for Jira issues and related metadata.
    """

    id: str = JIRA_DEFAULT_ID
    key: str = JIRA_DEFAULT_KEY
    summary: str = EMPTY_STRING
    description: str | None = None
    created: str = EMPTY_STRING
    updated: str = EMPTY_STRING
    status: JiraStatus | None = None
    issue_type: JiraIssueType | None = None
    priority: JiraPriority | None = None
    assignee: JiraUser | None = None
    reporter: JiraUser | None = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    comments: list[JiraComment] = Field(default_factory=list)
    attachments: list[JiraAttachment] = Field(default_factory=list)
    timetracking: JiraTimetracking | None = None
    url: str | None = None
    epic_key: str | None = None
    epic_name: str | None = None
    fix_versions: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    requested_fields: Literal["*all"] | list[str] | None = None
    project: JiraProject | None = None

    def __getattribute__(self, name: str) -> Any:
        """
        Custom attribute access to handle custom field access.

        This allows accessing custom fields by their name as if they were
        regular attributes of the JiraIssue class.

        Args:
            name: The attribute name to access

        Returns:
            The attribute value or custom field value
        """
        # First try to get the attribute normally
        try:
            return super().__getattribute__(name)
        except AttributeError:
            # If the attribute doesn't exist, check if it's a custom field
            try:
                custom_fields = super().__getattribute__("custom_fields")
                if name in custom_fields:
                    return custom_fields[name]
            except AttributeError:
                pass
            # Re-raise the original AttributeError
            raise

    @property
    def page_content(self) -> str | None:
        """
        Get the page content from the description.

        This is a convenience property for treating Jira issues as documentation pages.

        Returns:
            The description text or None
        """
        # Return description without modification for now
        # In the future, we could parse ADF content here
        return self.description

    @staticmethod
    def _find_custom_field_by_name(
        fields: dict[str, Any], name_patterns: list[str]
    ) -> Any:
        """
        Find a custom field by name patterns.

        Args:
            fields: The fields dictionary from the Jira API
            name_patterns: List of field name patterns to search for

        Returns:
            The custom field value or None
        """
        # This method is used to find commonly used custom fields
        # by looking for field names that match certain patterns
        custom_field_id = None

        # Loop through all fields to find matching custom field IDs
        for field_id, field_value in fields.items():
            # Skip non-custom fields (custom fields start with "customfield_")
            if not field_id.startswith("customfield_"):
                continue

            # Check if this field has a name that matches our patterns
            field_name = None
            if isinstance(field_value, dict) and "name" in field_value:
                field_name = field_value.get("name", "").lower()
            elif isinstance(field_value, dict) and "key" in field_value:
                field_name = field_value.get("key", "").lower()

            # Skip fields where we couldn't extract a name
            if not field_name:
                continue

            # Check against our patterns
            for pattern in name_patterns:
                if pattern.lower() in field_name:
                    custom_field_id = field_id
                    break

            # Break early if we found a match
            if custom_field_id:
                break

        # If we found a matching field ID, return its value
        if custom_field_id and custom_field_id in fields:
            return fields[custom_field_id]

        return None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraIssue":
        """
        Create a JiraIssue from a Jira API response.

        Args:
            data: The issue data from the Jira API
            **kwargs: Additional arguments to pass to the constructor

        Returns:
            A JiraIssue instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        fields = data.get("fields", {})
        if not isinstance(fields, dict):
            fields = {}

        # Get required simple fields
        issue_id = str(data.get("id", JIRA_DEFAULT_ID))
        key = str(data.get("key", JIRA_DEFAULT_KEY))
        summary = str(fields.get("summary", EMPTY_STRING))
        description = fields.get("description")

        # Timestamps
        created = str(fields.get("created", EMPTY_STRING))
        updated = str(fields.get("updated", EMPTY_STRING))

        # Extract assignee data
        assignee = None
        assignee_data = fields.get("assignee")
        if assignee_data:
            assignee = JiraUser.from_api_response(assignee_data)

        # Extract reporter data
        reporter = None
        reporter_data = fields.get("reporter")
        if reporter_data:
            reporter = JiraUser.from_api_response(reporter_data)

        # Extract status data
        status = None
        status_data = fields.get("status")
        if status_data:
            status = JiraStatus.from_api_response(status_data)

        # Extract issue type data
        issue_type = None
        issue_type_data = fields.get("issuetype")
        if issue_type_data:
            issue_type = JiraIssueType.from_api_response(issue_type_data)

        # Extract priority data
        priority = None
        priority_data = fields.get("priority")
        if priority_data:
            priority = JiraPriority.from_api_response(priority_data)

        # Extract project data
        project = None
        project_data = fields.get("project")
        if project_data:
            project = JiraProject.from_api_response(project_data)

        # Lists of strings
        labels = []
        if labels_data := fields.get("labels"):
            if isinstance(labels_data, list):
                labels = [str(label) for label in labels_data if label]

        components = []
        if components_data := fields.get("components"):
            if isinstance(components_data, list):
                components = [
                    str(comp.get("name", "")) if isinstance(comp, dict) else str(comp)
                    for comp in components_data
                    if comp
                ]

        fix_versions = []
        if fix_versions_data := fields.get("fixVersions"):
            if isinstance(fix_versions_data, list):
                fix_versions = [
                    str(version.get("name", ""))
                    if isinstance(version, dict)
                    else str(version)
                    for version in fix_versions_data
                    if version
                ]

        # Handling comments
        comments = []
        comments_field = fields.get("comment", {})
        if isinstance(comments_field, dict) and "comments" in comments_field:
            comments_data = comments_field["comments"]
            if isinstance(comments_data, list):
                comments = [
                    JiraComment.from_api_response(comment)
                    for comment in comments_data
                    if comment
                ]

        # Handling attachments
        attachments = []
        attachments_data = fields.get("attachment", [])
        if isinstance(attachments_data, list):
            attachments = [
                JiraAttachment.from_api_response(attachment)
                for attachment in attachments_data
                if attachment
            ]

        # Timetracking
        timetracking = None
        timetracking_data = fields.get("timetracking")
        if timetracking_data:
            timetracking = JiraTimetracking.from_api_response(timetracking_data)

        # URL
        url = data.get("self")  # API URL for the issue

        # Try to find epic fields (varies by Jira instance)
        epic_key = None
        epic_name = None

        # Check for "Epic Link" field
        epic_link = cls._find_custom_field_by_name(fields, ["epic link", "parent epic"])
        if isinstance(epic_link, str):
            epic_key = epic_link

        # Check for "Epic Name" field
        epic_name_value = cls._find_custom_field_by_name(fields, ["epic name"])
        if isinstance(epic_name_value, str):
            epic_name = epic_name_value

        # Store custom fields
        custom_fields = {}
        for field_id, field_value in fields.items():
            if field_id.startswith("customfield_"):
                # Extract custom field name if it's a nested object with a name
                if isinstance(field_value, dict) and "name" in field_value:
                    field_name = field_value.get("name", "")
                    if field_name:
                        # Use the field name as a key for easier access
                        custom_field_name = field_name.lower().replace(" ", "_")
                        custom_fields[custom_field_name] = field_value
                else:
                    # Use a shortened version of the ID as the key
                    short_id = field_id.replace("customfield_", "cf_")
                    custom_fields[short_id] = field_value

        # Create the issue instance with all the extracted data
        return cls(
            id=issue_id,
            key=key,
            summary=summary,
            description=description,
            created=created,
            updated=updated,
            status=status,
            issue_type=issue_type,
            priority=priority,
            assignee=assignee,
            reporter=reporter,
            project=project,
            labels=labels,
            components=components,
            comments=comments,
            attachments=attachments,
            timetracking=timetracking,
            url=url,
            epic_key=epic_key,
            epic_name=epic_name,
            fix_versions=fix_versions,
            custom_fields=custom_fields,
            requested_fields=kwargs.get("requested_fields"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "key": self.key,
            "summary": self.summary,
            "url": self.url,
        }

        # Add description if available
        if self.description:
            result["description"] = self.description

        # Add status
        if self.status:
            result["status"] = self.status.to_simplified_dict()
        else:
            result["status"] = {"name": "Unknown"}

        # Add issue type
        if self.issue_type:
            result["issue_type"] = self.issue_type.to_simplified_dict()
        else:
            result["issue_type"] = {"name": "Unknown"}

        # Add priority
        if self.priority:
            result["priority"] = self.priority.to_simplified_dict()

        # Add project info
        if self.project:
            result["project"] = self.project.to_simplified_dict()

        # Add assignee and reporter
        if self.assignee:
            result["assignee"] = self.assignee.to_simplified_dict()
        else:
            result["assignee"] = {"display_name": "Unassigned"}

        if self.reporter:
            result["reporter"] = self.reporter.to_simplified_dict()

        # Add lists
        if self.labels:
            result["labels"] = self.labels

        if self.components:
            result["components"] = self.components

        if self.fix_versions:
            result["fix_versions"] = self.fix_versions

        # Add epic fields
        if self.epic_key:
            result["epic_key"] = self.epic_key

        if self.epic_name:
            result["epic_name"] = self.epic_name

        # Add time tracking
        if self.timetracking:
            result["timetracking"] = self.timetracking.to_simplified_dict()

        # Add created and updated timestamps
        if self.created:
            result["created"] = self.created

        if self.updated:
            result["updated"] = self.updated

        # Add comments if requested
        if self.requested_fields == "*all" or (
            isinstance(self.requested_fields, list)
            and "comments" in self.requested_fields
        ):
            result["comments"] = [
                comment.to_simplified_dict() for comment in self.comments
            ]

        # Add attachments if requested
        if self.requested_fields == "*all" or (
            isinstance(self.requested_fields, list)
            and "attachments" in self.requested_fields
        ):
            result["attachments"] = [
                attachment.to_simplified_dict() for attachment in self.attachments
            ]

        return result
