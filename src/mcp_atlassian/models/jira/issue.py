"""
Jira issue models.

This module provides Pydantic models for Jira issues.
"""

import logging
import re
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

# Extended epic field name patterns to support more variations
EPIC_NAME_PATTERNS = [
    r"epic\s*name",
    r"epic[._-]?name",
    r"epicname",
]

EPIC_LINK_PATTERNS = [
    r"epic\s*link",
    r"epic[._-]?link",
    r"Parent Link",
    r"parent\s*link",
    r"epiclink",
]


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
    def _find_custom_field_in_api_response(
        fields: dict[str, Any], name_patterns: list[str]
    ) -> Any:
        """
        Find a custom field by name patterns in the raw API response.

        Used during object creation from API response to extract fields
        before the JiraIssue object is instantiated.

        Args:
            fields: The fields dictionary from the Jira API
            name_patterns: List of field name patterns to search for

        Returns:
            The custom field value or None
        """
        if not fields or not isinstance(fields, dict):
            return None

        # Normalize all patterns for easier matching
        normalized_patterns = []
        for pattern in name_patterns:
            norm_pattern = pattern.lower()
            norm_pattern = re.sub(r"[_\-\s]", "", norm_pattern)
            normalized_patterns.append(norm_pattern)

        custom_field_id = None

        # Check if fields has a names() method
        if hasattr(fields, "names") and callable(fields.names):
            try:
                names_dict = fields.names()
                if isinstance(names_dict, dict):
                    for field_id, field_name in names_dict.items():
                        field_name_norm = re.sub(r"[_\-\s]", "", field_name.lower())
                        for norm_pattern in normalized_patterns:
                            if norm_pattern in field_name_norm:
                                custom_field_id = field_id
                                break
                        if custom_field_id:
                            break
            except Exception:
                logger.debug("Error accessing names() method", exc_info=True)

        # Look at field metadata if name method didn't work
        if not custom_field_id:
            schema = fields.get("schema", {})
            if schema and isinstance(schema, dict) and "fields" in schema:
                schema_fields = schema["fields"]
                if isinstance(schema_fields, dict):
                    for field_id, field_info in schema_fields.items():
                        if not field_id.startswith("customfield_"):
                            continue

                        if isinstance(field_info, dict) and "name" in field_info:
                            field_name = field_info["name"].lower()
                            field_name_norm = re.sub(r"[_\-\s]", "", field_name)
                            for norm_pattern in normalized_patterns:
                                if norm_pattern in field_name_norm:
                                    custom_field_id = field_id
                                    break

                        if custom_field_id:
                            break

        # Try direct matching of field IDs for common epic fields
        if not custom_field_id:
            has_epic_link_pattern = any("epiclink" in p for p in normalized_patterns)
            has_epic_name_pattern = any("epicname" in p for p in normalized_patterns)

            if has_epic_link_pattern:
                for field_id in fields:
                    if field_id.startswith("customfield_") and field_id.endswith("14"):
                        custom_field_id = field_id
                        break
            elif has_epic_name_pattern:
                for field_id in fields:
                    if field_id.startswith("customfield_") and field_id.endswith("11"):
                        custom_field_id = field_id
                        break

        # Last attempt - look through all custom fields for names in their values
        if not custom_field_id:
            for field_id, field_value in fields.items():
                if not field_id.startswith("customfield_"):
                    continue

                field_name = None
                if isinstance(field_value, dict) and "name" in field_value:
                    field_name = field_value.get("name", "").lower()
                elif isinstance(field_value, dict) and "key" in field_value:
                    field_name = field_value.get("key", "").lower()

                if not field_name:
                    continue

                field_name_norm = re.sub(r"[_\-\s]", "", field_name)
                for norm_pattern in normalized_patterns:
                    if norm_pattern in field_name_norm:
                        custom_field_id = field_id
                        break

                if custom_field_id:
                    break

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
        epic_link = cls._find_custom_field_in_api_response(
            fields, ["epic link", "parent epic"]
        )
        if isinstance(epic_link, str):
            epic_key = epic_link

        # Check for "Epic Name" field
        epic_name_value = cls._find_custom_field_in_api_response(fields, ["epic name"])
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
                    # Use the original ID as the key (instead of shortened version)
                    custom_fields[field_id] = field_value

        # Handle requested_fields parameter
        requested_fields_param = kwargs.get("requested_fields")

        # Convert string requested_fields to list (except "*all")
        if isinstance(requested_fields_param, str) and requested_fields_param != "*all":
            requested_fields_param = requested_fields_param.split(",")
            # Strip whitespace from each field name
            requested_fields_param = [field.strip() for field in requested_fields_param]

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
            requested_fields=requested_fields_param,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "id": self.id,
            "key": self.key,
        }

        # Add summary by default unless explicitly filtering by requested_fields
        add_summary = True
        if (
            isinstance(self.requested_fields, list)
            and "summary" not in self.requested_fields
        ):
            add_summary = False

        if add_summary:
            result["summary"] = self.summary

        # Add URL if available
        if self.url:
            result["url"] = self.url

        # Add description if available, unless explicitly filtered
        add_description = True
        if (
            isinstance(self.requested_fields, list)
            and "description" not in self.requested_fields
        ):
            add_description = False

        if add_description and self.description:
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

        # Add priority if not explicitly filtered
        if self.priority and (
            not isinstance(self.requested_fields, list)
            or "priority" in self.requested_fields
        ):
            result["priority"] = self.priority.to_simplified_dict()

        # Add project info if not explicitly filtered
        if self.project and (
            not isinstance(self.requested_fields, list)
            or "project" in self.requested_fields
        ):
            result["project"] = self.project.to_simplified_dict()

        # Add assignee and reporter if not explicitly filtered
        add_assignee = (
            not isinstance(self.requested_fields, list)
            or "assignee" in self.requested_fields
        )
        if add_assignee:
            if self.assignee:
                result["assignee"] = self.assignee.to_simplified_dict()
            else:
                result["assignee"] = {"display_name": "Unassigned"}

        if self.reporter and (
            not isinstance(self.requested_fields, list)
            or "reporter" in self.requested_fields
        ):
            result["reporter"] = self.reporter.to_simplified_dict()

        # Add lists if not explicitly filtered
        if self.labels and (
            not isinstance(self.requested_fields, list)
            or "labels" in self.requested_fields
        ):
            result["labels"] = self.labels

        if self.components and (
            not isinstance(self.requested_fields, list)
            or "components" in self.requested_fields
        ):
            result["components"] = self.components

        if self.fix_versions and (
            not isinstance(self.requested_fields, list)
            or "fix_versions" in self.requested_fields
        ):
            result["fix_versions"] = self.fix_versions

        # Add epic fields if not explicitly filtered
        if self.epic_key and (
            not isinstance(self.requested_fields, list)
            or "epic_key" in self.requested_fields
        ):
            result["epic_key"] = self.epic_key

        if self.epic_name and (
            not isinstance(self.requested_fields, list)
            or "epic_name" in self.requested_fields
        ):
            result["epic_name"] = self.epic_name

        # Add time tracking only if explicitly requested
        add_timetracking = self.requested_fields == "*all" or (
            isinstance(self.requested_fields, list)
            and "timetracking" in self.requested_fields
        )
        if add_timetracking and self.timetracking:
            result["timetracking"] = self.timetracking.to_simplified_dict()

        # Add created and updated timestamps if not explicitly filtered
        if self.created and (
            not isinstance(self.requested_fields, list)
            or "created" in self.requested_fields
        ):
            result["created"] = self.created

        if self.updated and (
            not isinstance(self.requested_fields, list)
            or "updated" in self.requested_fields
        ):
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

        # Process custom fields
        if self.custom_fields:
            # Add custom fields if requested with "*all"
            if self.requested_fields == "*all":
                # Loop through custom fields and add all of them
                for field_id, field_value in self.custom_fields.items():
                    # Process the value to make it more user-friendly
                    processed_value = self._process_custom_field_value(field_value)

                    # Add with original ID only
                    result[field_id] = processed_value

            # Add specific requested custom fields
            elif isinstance(self.requested_fields, list):
                for field in self.requested_fields:
                    # Check for customfield_ format
                    if field.startswith("customfield_"):
                        # Try to find the field in custom_fields
                        if field in self.custom_fields:
                            value = self._process_custom_field_value(
                                self.custom_fields[field]
                            )
                            result[field] = value

                    # Check for cf_ format (for backward compatibility in requests)
                    elif field.startswith("cf_"):
                        full_id = "customfield_" + field[3:]  # Convert to full form

                        # Try to find the full version in custom_fields
                        if full_id in self.custom_fields:
                            value = self._process_custom_field_value(
                                self.custom_fields[full_id]
                            )
                            result[full_id] = value

        return result

    def _process_custom_field_value(self, field_value: Any) -> Any:
        """
        Process a custom field value for simplified dict output.

        Args:
            field_value: The value to process

        Returns:
            Processed value suitable for API response
        """
        if field_value is None or isinstance(field_value, str | int | float | bool):
            return field_value

        if isinstance(field_value, dict):
            if "value" in field_value:
                return field_value["value"]
            elif "name" in field_value:
                return field_value["name"]

        if isinstance(field_value, list):
            return [
                item.get("value", str(item)) if isinstance(item, dict) else str(item)
                for item in field_value
            ]

        return str(field_value)

    def _find_custom_field_in_issue(
        self, name: str, pattern: bool = False
    ) -> tuple[str | None, Any]:
        """
        Find a custom field by name or pattern in an instantiated JiraIssue.

        Used by instance methods like _get_epic_name and _get_epic_link
        to search through the custom_fields dictionary of an existing issue.

        Args:
            name: The name to search for
            pattern: If True, use regex pattern matching

        Returns:
            A tuple of (field_id, field_value) or (None, None) if not found
        """
        if not self.custom_fields:
            return None, None

        # Check if fields has a names() method (some implementations have this)
        if hasattr(self.custom_fields, "names") and callable(self.custom_fields.names):
            names_dict = self.custom_fields.names()
            if names_dict:
                for field_id, field_name in names_dict.items():
                    if (pattern and re.search(name, field_name, re.IGNORECASE)) or (
                        not pattern and field_name.lower() == name.lower()
                    ):
                        return field_id, self.custom_fields.get(field_id)

        # Check field metadata for name (custom fields usually have a name)
        for field_id, field_value in self.custom_fields.items():
            if not field_id.startswith("customfield_"):
                continue

            # Custom fields can have a schema with a name
            if isinstance(field_value, dict) and field_value.get("name"):
                field_name = field_value.get("name")
                if (pattern and re.search(name, field_name, re.IGNORECASE)) or (
                    not pattern and field_name.lower() == name.lower()
                ):
                    return field_id, field_value

        # Fallback: Directly look for keys that match the pattern
        if pattern:
            for field_id, field_value in self.custom_fields.items():
                if re.search(name, field_id, re.IGNORECASE):
                    return field_id, field_value

        return None, None

    def _get_epic_name(self) -> str | None:
        """Get the epic name from custom fields if available."""
        # Try each pattern in order
        for pattern in EPIC_NAME_PATTERNS:
            field_id, field_value = self._find_custom_field_in_issue(
                pattern, pattern=True
            )
            if field_id and field_value:
                if isinstance(field_value, dict):
                    return field_value.get("value") or field_value.get("name")
                return str(field_value)
        return None

    def _get_epic_link(self) -> str | None:
        """Get the epic link from custom fields if available."""
        # Try each pattern in order
        for pattern in EPIC_LINK_PATTERNS:
            field_id, field_value = self._find_custom_field_in_issue(
                pattern, pattern=True
            )
            if field_id and field_value:
                # Handle different possible value types
                if isinstance(field_value, dict):
                    return field_value.get("key") or field_value.get("value")
                return str(field_value)
        return None
