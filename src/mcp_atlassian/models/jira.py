"""
Pydantic models for Jira API responses.

This module provides type-safe models for working with Jira API data,
including user information, issues, projects, and search results.

Key models:
- JiraIssue: Comprehensive model for Jira issues with all standard fields
- JiraUser: User account information
- JiraProject: Project metadata and configuration
- JiraSearchResult: Container for Jira search (JQL) results
- JiraTransition: Issue workflow transitions
- JiraWorklog: Time tracking entries

Usage examples:

    # Get a typed issue model
    from mcp_atlassian.jira import JiraClient

    client = JiraClient.from_env()
    issue = client.get_issue("PROJECT-123")

    # Access typed properties with auto-completion
    print(f"Issue {issue.key}: {issue.summary}")
    print(f"Status: {issue.status.name}")
    print(f"Assignee: {issue.assignee.display_name if issue.assignee else 'Unassigned'}")

    # All models support conversion from/to API responses
    custom_issue = JiraIssue.from_api_response(api_data)
    simplified = custom_issue.to_simplified_dict()
"""

import logging
import warnings
from typing import Any

from pydantic import Field, model_validator

from .base import ApiModel, TimestampMixin
from .constants import (
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
    JIRA_DEFAULT_KEY,
    JIRA_DEFAULT_PROJECT,
    NONE_VALUE,
    UNASSIGNED,
    UNKNOWN,
)

logger = logging.getLogger(__name__)


class JiraUser(ApiModel):
    """
    Model representing a Jira user.
    """

    account_id: str | None = None
    display_name: str = UNASSIGNED
    email: str | None = None
    active: bool = True
    avatar_url: str | None = None
    time_zone: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraUser":
        """
        Create a JiraUser from a Jira API response.

        Args:
            data: The user data from the Jira API

        Returns:
            A JiraUser instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        avatar_url = None
        if avatars := data.get("avatarUrls"):
            if isinstance(avatars, dict):
                # Get the largest available avatar (48x48)
                avatar_url = avatars.get("48x48")
            else:
                logger.debug(f"Unexpected avatar data format: {type(avatars)}")

        return cls(
            account_id=data.get("accountId"),
            display_name=str(data.get("displayName", UNASSIGNED)),
            email=data.get("emailAddress"),
            active=bool(data.get("active", True)),
            avatar_url=avatar_url,
            time_zone=data.get("timeZone"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {
            "display_name": self.display_name,
            "name": self.display_name,  # Add name for backward compatibility
            "email": self.email,
            "avatar_url": self.avatar_url,
        }


class JiraStatusCategory(ApiModel):
    """
    Model representing a Jira status category.
    """

    id: int = 0
    key: str = EMPTY_STRING
    name: str = UNKNOWN
    color_name: str = EMPTY_STRING

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraStatusCategory":
        """
        Create a JiraStatusCategory from a Jira API response.

        Args:
            data: The status category data from the Jira API

        Returns:
            A JiraStatusCategory instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Safely get and convert fields, handling potential type mismatches
        id_value = data.get("id", 0)
        try:
            # Ensure id is an integer
            id_value = int(id_value) if id_value is not None else 0
        except (ValueError, TypeError):
            id_value = 0

        return cls(
            id=id_value,
            key=str(data.get("key", EMPTY_STRING)),
            name=str(data.get("name", UNKNOWN)),
            color_name=str(data.get("colorName", EMPTY_STRING)),
        )


class JiraStatus(ApiModel):
    """
    Model representing a Jira issue status.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = UNKNOWN
    description: str | None = None
    icon_url: str | None = None
    category: JiraStatusCategory | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraStatus":
        """
        Create a JiraStatus from a Jira API response.

        Args:
            data: The status data from the Jira API

        Returns:
            A JiraStatus instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        category = None
        category_data = data.get("statusCategory")
        if category_data:
            category = JiraStatusCategory.from_api_response(category_data)

        # Ensure ID is a string (API sometimes returns integers)
        status_id = data.get("id", JIRA_DEFAULT_ID)
        if status_id is not None:
            status_id = str(status_id)

        return cls(
            id=status_id,
            name=str(data.get("name", UNKNOWN)),
            description=data.get("description"),
            icon_url=data.get("iconUrl"),
            category=category,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "name": self.name,
        }

        if self.category:
            result["category"] = self.category.name
            result["color"] = self.category.color_name

        return result


class JiraIssueType(ApiModel):
    """
    Model representing a Jira issue type.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = UNKNOWN
    description: str | None = None
    icon_url: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraIssueType":
        """
        Create a JiraIssueType from a Jira API response.

        Args:
            data: The issue type data from the Jira API

        Returns:
            A JiraIssueType instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Ensure ID is a string
        issue_type_id = data.get("id", JIRA_DEFAULT_ID)
        if issue_type_id is not None:
            issue_type_id = str(issue_type_id)

        return cls(
            id=issue_type_id,
            name=str(data.get("name", UNKNOWN)),
            description=data.get("description"),
            icon_url=data.get("iconUrl"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {"name": self.name, "icon_url": self.icon_url}


class JiraPriority(ApiModel):
    """
    Model representing a Jira priority.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = NONE_VALUE
    description: str | None = None
    icon_url: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraPriority":
        """
        Create a JiraPriority from a Jira API response.

        Args:
            data: The priority data from the Jira API

        Returns:
            A JiraPriority instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Ensure ID is a string
        priority_id = data.get("id", JIRA_DEFAULT_ID)
        if priority_id is not None:
            priority_id = str(priority_id)

        return cls(
            id=priority_id,
            name=str(data.get("name", NONE_VALUE)),
            description=data.get("description"),
            icon_url=data.get("iconUrl"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        return {"name": self.name, "icon_url": self.icon_url}


class JiraComment(ApiModel, TimestampMixin):
    """
    Model representing a Jira issue comment.
    """

    id: str = JIRA_DEFAULT_ID
    body: str = EMPTY_STRING
    created: str = EMPTY_STRING
    updated: str = EMPTY_STRING
    author: JiraUser | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraComment":
        """
        Create a JiraComment from a Jira API response.

        Args:
            data: The comment data from the Jira API

        Returns:
            A JiraComment instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Ensure ID is a string
        comment_id = data.get("id", JIRA_DEFAULT_ID)
        if comment_id is not None:
            comment_id = str(comment_id)

        # Extract author information
        author = None
        if author_data := data.get("author"):
            author = JiraUser.from_api_response(author_data)

        return cls(
            id=comment_id,
            body=str(data.get("body", EMPTY_STRING)),
            created=data.get("created", EMPTY_STRING),
            updated=data.get("updated", EMPTY_STRING),
            author=author,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {"body": self.body, "created": self.format_timestamp(self.created)}

        if self.author:
            result["author"] = self.author.display_name

        return result


class JiraAttachment(ApiModel):
    """
    Model representing a Jira issue attachment.

    This model contains information about files attached to Jira issues,
    including the filename, size, content type, and download URL.
    """

    id: str = JIRA_DEFAULT_ID
    filename: str = EMPTY_STRING
    size: int = 0
    content_type: str | None = None
    created: str = EMPTY_STRING
    author: JiraUser | None = None
    url: str | None = None
    thumbnail_url: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraAttachment":
        """
        Create a JiraAttachment from a Jira API response.

        Args:
            data: The attachment data from the Jira API

        Returns:
            A JiraAttachment instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        # Ensure ID is a string
        attachment_id = data.get("id", JIRA_DEFAULT_ID)
        if attachment_id is not None:
            attachment_id = str(attachment_id)

        # Extract author information
        author = None
        if author_data := data.get("author"):
            author = JiraUser.from_api_response(author_data)

        return cls(
            id=attachment_id,
            filename=str(data.get("filename", EMPTY_STRING)),
            size=int(data.get("size", 0)),
            content_type=data.get("mimeType"),
            created=data.get("created", EMPTY_STRING),
            author=author,
            url=data.get("content"),
            thumbnail_url=data.get("thumbnail"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to simplified dictionary for API response."""
        result = {
            "filename": self.filename,
            "size": self.size,
            "created": self.created,
            "url": self.url,
        }

        if self.content_type:
            result["content_type"] = self.content_type

        if self.author:
            result["author"] = self.author.display_name

        if self.thumbnail_url:
            result["thumbnail_url"] = self.thumbnail_url

        return result


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
    url: str | None = None
    epic_key: str | None = None
    epic_name: str | None = None
    fix_versions: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    requested_fields: str | list[str] | None = None

    def __getattribute__(self, name: str) -> Any:
        """
        Override attribute access to prioritize model properties over custom fields.

        This fixes issues with test assertions by ensuring that when we access attributes
        like `issue.key`, we get the model property instead of a custom field with the same name.
        """
        try:
            # First try to get the attribute from the model
            return super().__getattribute__(name)
        except AttributeError:
            # If not found in model, check custom fields
            try:
                custom_fields = super().__getattribute__("custom_fields")
                if name in custom_fields:
                    return custom_fields[name]
            except AttributeError:
                pass
            # Propagate the original error
            raise

    @property
    def page_content(self) -> str | None:
        """
        Alias for description to maintain compatibility with tests.

        Deprecated: Use 'description' instead.
        """
        warnings.warn(
            "The 'page_content' property is deprecated. Use 'description' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.description

    @staticmethod
    def _find_custom_field_by_name(
        fields: dict[str, Any], name_patterns: list[str]
    ) -> Any:
        """
        Find a custom field value by searching through field names.

        Since Jira instances can have different custom field IDs for the same
        field, this method dynamically discovers fields by their names using
        two simple but effective strategies:

        1. Search in field metadata (schema) by name - most accurate when available
        2. Search using the fields' names() method (if available) - most flexible

        This approach is advantageous over hardcoded custom field IDs because:
        - It adapts to different Jira instances with varying field configurations
        - It works even when custom field IDs change in Jira updates
        - It doesn't require manual configuration or updates when field IDs change

        Args:
            fields: The fields dictionary from Jira API response
            name_patterns: List of name patterns to match against field names

        Returns:
            The value of the first matching field, or None if not found
        """
        if not fields or not isinstance(fields, dict):
            return None

        # STRATEGY 1: Try to find a matching name in field metadata
        meta_fields = fields.get("schema", {}).get("fields", {})
        if isinstance(meta_fields, dict):
            for field_id, field_meta in meta_fields.items():
                if not isinstance(field_meta, dict):
                    continue

                field_name = field_meta.get("name", "").lower()
                for pattern in name_patterns:
                    pattern_lower = pattern.lower()
                    # Try direct match
                    if pattern_lower in field_name:
                        return fields.get(field_id)
                    # Try without spaces or hyphens
                    normalized_pattern = pattern_lower.replace(" ", "").replace("-", "")
                    normalized_field_name = field_name.replace(" ", "").replace("-", "")
                    if normalized_pattern in normalized_field_name:
                        return fields.get(field_id)

        # STRATEGY 2: Try to get field names from the fields collection if available
        if hasattr(fields, "names") and callable(getattr(fields, "names", None)):
            try:
                field_names = fields.names()
                if isinstance(field_names, dict):
                    for field_id, field_name in field_names.items():
                        if field_id in fields and fields[field_id] is not None:
                            field_name_lower = str(field_name).lower()
                            for pattern in name_patterns:
                                pattern_lower = pattern.lower()
                                # Try direct match
                                if pattern_lower in field_name_lower:
                                    return fields[field_id]
                                # Try normalized match
                                normalized_pattern = pattern_lower.replace(
                                    " ", ""
                                ).replace("-", "")
                                normalized_field_name = field_name_lower.replace(
                                    " ", ""
                                ).replace("-", "")
                                if normalized_pattern in normalized_field_name:
                                    return fields[field_id]
            except Exception:
                # Ignore any errors from names() method
                logger.debug("Error accessing field names method")
                pass

        return None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraIssue":
        """
        Create a JiraIssue from a Jira API response.

        Args:
            data: The issue data from the Jira API
            **kwargs: Additional context parameters, including:
                - base_url: Base URL for constructing the issue URL
                - requested_fields: List of fields that were requested (if any)

        Returns:
            A JiraIssue instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance with the key
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            # Extract key if possible, otherwise return empty instance
            key = data if isinstance(data, str) else None
            return cls(key=key) if key else cls()

        # Use empty dict if fields doesn't exist or is not a dict
        fields = data.get("fields", {})
        if not isinstance(fields, dict):
            logger.debug(f"Fields is not a dict, using empty dict: {type(fields)}")
            fields = {}

        # Store requested fields if provided and normalize format
        requested_fields = kwargs.get("requested_fields")

        # Handle different formats of requested_fields
        if requested_fields is not None:
            if isinstance(requested_fields, str) and requested_fields != "*all":
                # Convert comma-separated string to list
                requested_fields = [
                    field.strip() for field in requested_fields.split(",")
                ]
            elif isinstance(requested_fields, list | tuple | set):
                # Keep as-is for collections, but convert to list for consistency
                requested_fields = list(requested_fields)
            elif requested_fields == "*all":
                # Keep "*all" as a string to signal all fields should be included
                requested_fields = "*all"
            elif requested_fields == ["*all"]:
                # Handle the case where it's in a list
                requested_fields = "*all"

        # Extract custom fields - any field beginning with "customfield_"
        custom_fields = {}
        for key, value in fields.items():
            if key.startswith("customfield_"):
                custom_fields[key] = value

        # Process status
        status = None
        status_data = fields.get("status")
        if status_data:
            status = JiraStatus.from_api_response(status_data)

        # Process issue type
        issue_type = None
        issuetype_data = fields.get("issuetype")
        if issuetype_data:
            issue_type = JiraIssueType.from_api_response(issuetype_data)

        # Process priority
        priority = None
        priority_data = fields.get("priority")
        if priority_data:
            priority = JiraPriority.from_api_response(priority_data)

        # Process assignee
        assignee = None
        assignee_data = fields.get("assignee")
        if assignee_data:
            assignee = JiraUser.from_api_response(assignee_data)

        # Process reporter
        reporter = None
        reporter_data = fields.get("reporter")
        if reporter_data:
            reporter = JiraUser.from_api_response(reporter_data)

        # Process components - ensure they're dictionaries with 'name' keys
        components = []
        components_data = fields.get("components", [])
        if isinstance(components_data, list):
            for c in components_data:
                if isinstance(c, dict) and "name" in c:
                    components.append(c.get("name"))

        # Process comments
        comments = []
        comment_data = fields.get("comment", {})
        if isinstance(comment_data, dict) and "comments" in comment_data:
            comments_list = comment_data.get("comments", [])
            if isinstance(comments_list, list):
                comments = [JiraComment.from_api_response(c) for c in comments_list]

        # Process attachments
        attachments = []
        attachments_data = fields.get("attachment", [])
        if isinstance(attachments_data, list):
            for attachment in attachments_data:
                if isinstance(attachment, dict):
                    attachments.append(JiraAttachment.from_api_response(attachment))

        # Extract fixVersions safely
        fix_versions = []
        fix_versions_data = fields.get("fixVersions", [])
        if isinstance(fix_versions_data, list):
            for version in fix_versions_data:
                if isinstance(version, dict) and "name" in version:
                    fix_versions.append(version.get("name"))

        # Construct URL if base_url is provided
        url = None
        base_url = kwargs.get("base_url")
        if base_url and data.get("key"):
            url = f"{base_url}/browse/{data.get('key')}"

        # Ensure all string fields are properly converted
        issue_id = (
            str(data.get("id", JIRA_DEFAULT_ID))
            if data.get("id") is not None
            else JIRA_DEFAULT_ID
        )
        key = (
            str(data.get("key", JIRA_DEFAULT_KEY))
            if data.get("key") is not None
            else JIRA_DEFAULT_KEY
        )
        summary = (
            str(fields.get("summary", EMPTY_STRING))
            if fields.get("summary") is not None
            else EMPTY_STRING
        )
        description = (
            str(fields.get("description", ""))
            if fields.get("description") is not None
            else None
        )
        created = (
            str(fields.get("created", EMPTY_STRING))
            if fields.get("created") is not None
            else EMPTY_STRING
        )
        updated = (
            str(fields.get("updated", EMPTY_STRING))
            if fields.get("updated") is not None
            else EMPTY_STRING
        )

        # Extract labels safely
        labels = []
        labels_data = fields.get("labels", [])
        if isinstance(labels_data, list):
            labels = [str(label) for label in labels_data if label is not None]

        # Extract epic information dynamically
        epic_key = cls._find_custom_field_by_name(
            fields, ["Epic Link", "epic-link", "epiclink"]
        )
        epic_name = cls._find_custom_field_by_name(
            fields, ["Epic Name", "epic-name", "epicname"]
        )

        # Extract all fields that aren't explicitly processed into custom_fields
        known_fields = {
            "summary",
            "description",
            "status",
            "issuetype",
            "priority",
            "assignee",
            "reporter",
            "components",
            "comment",
            "attachment",
            "fixVersions",
            "labels",
            "created",
            "updated",
            "duedate",
            "resolutiondate",
            "resolution",
            "project",
            "parent",
            "subtasks",
            "timetracking",
            "security",
            "worklog",  # Add worklog to known_fields to prevent conflicts
        }

        # First create field_map, which should exclude Jira model property names
        field_map = {}
        model_property_names = {
            "id",
            "key",
            "summary",
            "description",
            "created",
            "updated",
            "status",
            "issue_type",
            "priority",
            "assignee",
            "reporter",
            "labels",
            "components",
            "comments",
            "attachments",
            "url",
            "epic_key",
            "epic_name",
            "fix_versions",
            "custom_fields",
            "requested_fields",
            "page_content",
        }

        for field, value in fields.items():
            if field not in known_fields and not field.startswith("customfield_"):
                # Never add fields that would overwrite JiraIssue model properties
                if field not in model_property_names:
                    field_map[field] = value

        # Now merge field_map into custom_fields
        custom_fields.update(field_map)

        # Create the issue instance
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
            labels=labels,
            components=components,
            comments=comments,
            attachments=attachments,
            url=url,
            epic_key=epic_key,
            epic_name=epic_name,
            fix_versions=fix_versions,
            custom_fields=custom_fields,
            requested_fields=requested_fields,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """
        Convert to a simplified dictionary representation.
        - If fields="*all", all fields are included
        - If specific fields are requested, only those are included
        - If no fields specified, essential fields are included by default
        """
        # Always include id and key
        result: dict[str, Any] = {
            "id": self.id,
            "key": self.key,
        }

        # Define essential fields (same as default in API definition)
        essential_fields = [
            "summary",
            "description",
            "status",
            "assignee",
            "reporter",
            "priority",
            "created",
            "updated",
            "issuetype",
        ]

        # Case 1: "*all" was explicitly requested - include everything
        if self.requested_fields == "*all":
            # Add all standard fields
            result.update(
                {
                    "summary": self.summary,
                    "description": self.description,
                    "created": self.format_timestamp(self.created),
                    "updated": self.format_timestamp(self.updated),
                    "status": self.status.to_simplified_dict() if self.status else None,
                    "issue_type": self.issue_type.to_simplified_dict()
                    if self.issue_type
                    else None,
                    "priority": self.priority.to_simplified_dict()
                    if self.priority
                    else None,
                    "assignee": self.assignee.to_simplified_dict()
                    if self.assignee
                    else None,
                    "reporter": self.reporter.to_simplified_dict()
                    if self.reporter
                    else None,
                    "labels": self.labels,
                    "components": self.components,
                    "comments": [
                        comment.to_simplified_dict() for comment in self.comments
                    ],
                    "attachments": [
                        attachment.to_simplified_dict()
                        for attachment in self.attachments
                    ],
                    "url": self.url,
                    "epic_key": self.epic_key,
                    "epic_name": self.epic_name,
                    "fix_versions": self.fix_versions,
                }
            )

            # Add all custom fields
            for field_id, value in self.custom_fields.items():
                result[field_id] = value

        # Case 2: Specific fields were requested
        elif self.requested_fields:
            field_mapping = {
                "summary": lambda: self.summary,
                "description": lambda: self.description,
                "created": lambda: self.format_timestamp(self.created),
                "updated": lambda: self.format_timestamp(self.updated),
                "status": lambda: self.status.to_simplified_dict()
                if self.status
                else None,
                "issuetype": lambda: self.issue_type.to_simplified_dict()
                if self.issue_type
                else None,
                "issue_type": lambda: self.issue_type.to_simplified_dict()
                if self.issue_type
                else None,
                "priority": lambda: self.priority.to_simplified_dict()
                if self.priority
                else None,
                "assignee": lambda: self.assignee.to_simplified_dict()
                if self.assignee
                else None,
                "reporter": lambda: self.reporter.to_simplified_dict()
                if self.reporter
                else None,
                "labels": lambda: self.labels,
                "components": lambda: self.components,
                "comment": lambda: [
                    comment.to_simplified_dict() for comment in self.comments
                ],
                "comments": lambda: [
                    comment.to_simplified_dict() for comment in self.comments
                ],
                "attachments": lambda: [
                    attachment.to_simplified_dict() for attachment in self.attachments
                ],
                "url": lambda: self.url,
                "epic_key": lambda: self.epic_key,
                "epic_name": lambda: self.epic_name,
                "fix_versions": lambda: self.fix_versions,
            }

            # Process each requested field
            for field in self.requested_fields:
                # Handle standard fields
                if field in field_mapping:
                    value = field_mapping[field]()
                    if value is not None:  # Only include non-None values
                        result[field] = value
                # All other fields are custom fields
                elif field in self.custom_fields:
                    result[field] = self.custom_fields[field]

        # Case 3: No specific fields requested - use essential fields
        else:
            field_mapping = {
                "summary": lambda: self.summary,
                "description": lambda: self.description,
                "status": lambda: self.status.to_simplified_dict()
                if self.status
                else None,
                "assignee": lambda: self.assignee.to_simplified_dict()
                if self.assignee
                else None,
                "reporter": lambda: self.reporter.to_simplified_dict()
                if self.reporter
                else None,
                "priority": lambda: self.priority.to_simplified_dict()
                if self.priority
                else None,
                "created": lambda: self.format_timestamp(self.created),
                "updated": lambda: self.format_timestamp(self.updated),
                "issuetype": lambda: self.issue_type.to_simplified_dict()
                if self.issue_type
                else None,
            }

            # Add each essential field if it has a value
            for field in essential_fields:
                if field in field_mapping:
                    value = field_mapping[field]()
                    if value is not None:
                        result[field] = value

        return result


class JiraProject(ApiModel):
    """
    Model representing a Jira project.

    This model contains the basic information about a Jira project,
    including its key, name, and category.
    """

    id: str = JIRA_DEFAULT_PROJECT
    key: str = EMPTY_STRING
    name: str = UNKNOWN
    description: str | None = None
    lead: JiraUser | None = None
    url: str | None = None
    category_name: str | None = None
    avatar_url: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraProject":
        """
        Create a JiraProject instance from an API response dictionary.

        Args:
            data: The API response data
            **kwargs: Additional options

        Returns:
            A new JiraProject instance
        """
        if not data:
            return cls()

        project_data: dict[str, Any] = {}

        project_data["id"] = data.get("id", JIRA_DEFAULT_PROJECT)
        project_data["key"] = data.get("key", EMPTY_STRING)
        project_data["name"] = data.get("name", UNKNOWN)
        project_data["description"] = data.get("description")

        # Extract lead user information if available
        lead_data = data.get("lead")
        if lead_data:
            project_data["lead"] = JiraUser.from_api_response(lead_data)

        # Extract project URL
        if "self" in data:
            project_data["url"] = data.get("self")

        # Extract project category if available
        if "projectCategory" in data and data["projectCategory"]:
            project_data["category_name"] = data["projectCategory"].get("name")

        # Extract avatar URL if available
        if "avatarUrls" in data and data["avatarUrls"]:
            # Typically we want the medium size avatar
            project_data["avatar_url"] = data["avatarUrls"].get("48x48")

        return cls(**project_data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary representation."""
        result = {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "category": self.category_name,
        }

        # Handle lead user information with correct naming
        if self.lead:
            lead_dict = self.lead.to_simplified_dict()
            # Change display_name to name for backward compatibility
            if "display_name" in lead_dict:
                lead_dict["name"] = lead_dict["display_name"]
            result["lead"] = lead_dict
        else:
            result["lead"] = None

        return result


class JiraTransition(ApiModel):
    """
    Model representing a Jira issue transition.

    This model contains information about possible status transitions
    for Jira issues, including the target status and related metadata.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = EMPTY_STRING
    to_status: JiraStatus | None = None
    has_screen: bool = False
    is_global: bool = False
    is_initial: bool = False
    is_conditional: bool = False

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraTransition":
        """
        Create a JiraTransition instance from an API response dictionary.

        Args:
            data: The API response data
            **kwargs: Additional options

        Returns:
            A new JiraTransition instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        transition_data: dict[str, Any] = {}

        # Ensure ID is a string (API sometimes returns integers)
        transition_id = data.get("id", JIRA_DEFAULT_ID)
        if transition_id is not None:
            transition_id = str(transition_id)
        transition_data["id"] = transition_id

        transition_data["name"] = str(data.get("name", EMPTY_STRING))

        # Extract the "to" status information
        to_status_data = data.get("to")
        if to_status_data:
            # If "to" is a string (simple name), convert it to a minimal status dict
            if isinstance(to_status_data, str):
                to_status_data = {
                    "id": transition_id,  # Use transition ID as status ID
                    "name": to_status_data,
                }
            transition_data["to_status"] = JiraStatus.from_api_response(to_status_data)

        # Extract flags
        transition_data["has_screen"] = bool(data.get("hasScreen", False))
        transition_data["is_global"] = bool(data.get("isGlobal", False))
        transition_data["is_initial"] = bool(data.get("isInitial", False))
        transition_data["is_conditional"] = bool(data.get("isConditional", False))

        return cls(**transition_data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "to_status": self.to_status.to_simplified_dict()
            if self.to_status
            else None,
            "has_screen": self.has_screen,
        }


class JiraWorklog(ApiModel, TimestampMixin):
    """
    Model representing a Jira worklog entry.

    This model contains information about time spent on an issue,
    including the author, time spent, and related metadata.
    """

    id: str = JIRA_DEFAULT_ID
    author: JiraUser | None = None
    comment: str | None = None
    created: str = EMPTY_STRING
    updated: str = EMPTY_STRING
    started: str = EMPTY_STRING
    time_spent: str = EMPTY_STRING
    time_spent_seconds: int = 0

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraWorklog":
        """
        Create a JiraWorklog instance from an API response dictionary.

        Args:
            data: The API response data
            **kwargs: Additional options

        Returns:
            A new JiraWorklog instance
        """
        if not data:
            return cls()

        worklog_data: dict[str, Any] = {}

        worklog_data["id"] = data.get("id", JIRA_DEFAULT_ID)
        worklog_data["comment"] = data.get("comment")

        # Extract timestamp fields
        worklog_data["created"] = data.get("created", EMPTY_STRING)
        worklog_data["updated"] = data.get("updated", EMPTY_STRING)
        worklog_data["started"] = data.get("started", EMPTY_STRING)

        # Extract time spent information
        worklog_data["time_spent"] = data.get("timeSpent", EMPTY_STRING)
        worklog_data["time_spent_seconds"] = data.get("timeSpentSeconds", 0)

        # Extract author information
        author_data = data.get("author") or data.get("updateAuthor")
        if author_data:
            worklog_data["author"] = JiraUser.from_api_response(author_data)

        return cls(**worklog_data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary representation."""
        result = {
            "id": self.id,
            "comment": self.comment,
            "created": self.format_timestamp(self.created),
            "updated": self.format_timestamp(self.updated),
            "started": self.format_timestamp(self.started),
            "time_spent": self.time_spent,
            "time_spent_seconds": self.time_spent_seconds,
        }

        # Handle author information with correct naming
        if self.author:
            author_dict = self.author.to_simplified_dict()
            # Add name field for backward compatibility
            if "display_name" in author_dict:
                author_dict["name"] = author_dict["display_name"]
            result["author"] = author_dict
        else:
            result["author"] = None

        return result


class JiraSearchResult(ApiModel):
    """
    Model representing a Jira search (JQL) result.
    """

    total: int = 0
    start_at: int = 0
    max_results: int = 0
    issues: list[JiraIssue] = Field(default_factory=list)

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "JiraSearchResult":
        """
        Create a JiraSearchResult from a Jira API response.

        Args:
            data: The search result data from the Jira API
            **kwargs: Additional context parameters, including:
                - base_url: Base URL for constructing issue URLs
                - requested_fields: List of fields that were requested (if "*all" or specific fields)

        Returns:
            A JiraSearchResult instance
        """
        if not data:
            return cls()

        # Check if specific fields were requested
        requested_fields = kwargs.get("requested_fields")

        # If requested_fields is a comma-separated string, split it
        if isinstance(requested_fields, str):
            requested_fields = [field.strip() for field in requested_fields.split(",")]
            kwargs["requested_fields"] = requested_fields

        # Convert raw issues to JiraIssue models
        issues = [
            JiraIssue.from_api_response(issue, **kwargs)
            for issue in data.get("issues", [])
        ]

        return cls(
            total=data.get("total", 0),
            start_at=data.get("startAt", 0),
            max_results=data.get("maxResults", 0),
            issues=issues,
        )

    @model_validator(mode="after")
    def validate_search_result(self) -> "JiraSearchResult":
        """Validate the search result and log warnings if needed."""
        if self.total > 0 and not self.issues:
            logger.warning(
                "Search found %d issues but no issue data was returned", self.total
            )
        return self


class JiraBoard(ApiModel):
    """
    Model representing a Jira board.
    """

    id: str = JIRA_DEFAULT_ID
    name: str = UNKNOWN
    type: str = UNKNOWN

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraBoard":
        """
        Create a JiraBoard instance from an API response dictionary.

        Args:
            data: The API response data
            **kwargs: Additional options

        Returns:
            A new JiraBoard instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        transition_data: dict[str, Any] = {}

        # Ensure ID is a string (API sometimes returns integers)
        transition_id = data.get("id", JIRA_DEFAULT_ID)
        if transition_id is not None:
            transition_id = str(transition_id)
        transition_data["id"] = transition_id

        transition_data["name"] = str(data.get("name", UNKNOWN))
        transition_data["type"] = str(data.get("type", UNKNOWN))

        return cls(
            id=transition_id,
            name=str(data.get("name", UNKNOWN)),
            type=str(data.get("type", UNKNOWN)),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """
        Convert to a simplified dictionary representation.
        """
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
        }


class JiraSprint(ApiModel):
    """
    Model representing a Jira sprint.
    """

    id: str = JIRA_DEFAULT_ID
    state: str = UNKNOWN
    name: str = UNKNOWN
    start_date: str = EMPTY_STRING
    end_date: str = EMPTY_STRING
    activated_date: str = EMPTY_STRING
    origin_board_id: str = JIRA_DEFAULT_ID
    goal: str = EMPTY_STRING
    synced: bool = False
    auto_start_stop: bool = False

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraSprint":
        """
        Create a JiraSprint instance from an API response dictionary.

        Args:
            data: The API response data
            **kwargs: Additional options

        Returns:
            A new JiraSprint instance
        """
        if not data:
            return cls()

        # Handle non-dictionary data by returning a default instance
        if not isinstance(data, dict):
            logger.debug("Received non-dictionary data, returning default instance")
            return cls()

        transition_data: dict[str, Any] = {}

        # Ensure ID is a string (API sometimes returns integers)
        transition_id = data.get("id", JIRA_DEFAULT_ID)
        if transition_id is not None:
            transition_id = str(transition_id)
        transition_data["id"] = transition_id

        transition_data["state"] = data.get("state", UNKNOWN)
        transition_data["name"] = data.get("name", UNKNOWN)

        transition_data["start_date"] = data.get("startDate", EMPTY_STRING)
        transition_data["end_date"] = data.get("endDate", EMPTY_STRING)
        transition_data["activatedDate"] = data.get("activatedDate", EMPTY_STRING)

        transition_data["originBoardId"] = str(
            data.get("originBoardId", JIRA_DEFAULT_ID)
        )

        transition_data["goal"] = data.get("goal", EMPTY_STRING)
        transition_data["synced"] = data.get("synced", False)
        transition_data["autoStartStop"] = data.get("autoStartStop", False)

        return cls(**transition_data)

    def to_simplified_dict(self) -> dict[str, Any]:
        """
        Convert to a simplified dictionary representation.
        """
        return {
            "id": self.id,
            "state": self.state,
            "name": self.name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "activatedDate": self.activated_date,
            "originBoardId": self.origin_board_id,
            "goal": self.goal,
            "synced": self.synced,
            "autoStartStop": self.auto_start_stop,
        }
