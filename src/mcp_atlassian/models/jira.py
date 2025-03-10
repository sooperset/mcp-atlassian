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
    url: str | None = None
    epic_key: str | None = None
    epic_name: str | None = None

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

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "JiraIssue":
        """
        Create a JiraIssue from a Jira API response.

        Args:
            data: The issue data from the Jira API
            **kwargs: Additional context parameters, including:
                - base_url: Base URL for constructing the issue URL

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

        # Extract epic information
        epic_key = fields.get("customfield_10014")
        epic_name = fields.get("customfield_10011")

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
            url=url,
            epic_key=epic_key,
            epic_name=epic_name,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary representation."""
        return {
            "id": self.id,
            "summary": self.summary,
            "key": self.key,
            "description": self.description,
            "created": self.format_timestamp(self.created),
            "updated": self.format_timestamp(self.updated),
            "status": self.status.to_simplified_dict() if self.status else None,
            "issue_type": self.issue_type.to_simplified_dict()
            if self.issue_type
            else None,
            "priority": self.priority.to_simplified_dict() if self.priority else None,
            "assignee": self.assignee.to_simplified_dict() if self.assignee else None,
            "reporter": self.reporter.to_simplified_dict() if self.reporter else None,
            "labels": self.labels,
            "components": self.components,
            "comments": [comment.to_simplified_dict() for comment in self.comments],
            "url": self.url,
        }


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

        Returns:
            A JiraSearchResult instance
        """
        if not data:
            return cls()

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
