"""
Pydantic models for Jira and Confluence API responses.

This package provides type-safe models for working with Atlassian API data,
including conversion methods from API responses to structured models and
simplified dictionaries for API responses.
"""

# Re-export models for easier imports
from .base import ApiModel, TimestampMixin

# Confluence models (Import from the new structure)
from .confluence import (
    ConfluenceAttachment,
    ConfluenceComment,
    ConfluenceLabel,
    ConfluencePage,
    ConfluenceSearchResult,
    ConfluenceSpace,
    ConfluenceUser,
    ConfluenceVersion,
)
from .constants import (  # noqa: F401 - Keep constants available
    CONFLUENCE_DEFAULT_ID,
    CONFLUENCE_DEFAULT_SPACE,
    CONFLUENCE_DEFAULT_VERSION,
    DEFAULT_TIMESTAMP,
    EMPTY_STRING,
    JIRA_DEFAULT_ID,
    JIRA_DEFAULT_ISSUE_TYPE,
    JIRA_DEFAULT_KEY,
    JIRA_DEFAULT_PRIORITY,
    JIRA_DEFAULT_PROJECT,
    JIRA_DEFAULT_STATUS,
    NONE_VALUE,
    UNASSIGNED,
    UNKNOWN,
)

# Jira models (Keep existing imports)
from .jira import (
    JiraAttachment,
    JiraBoard,
    JiraComment,
    JiraIssue,
    JiraIssueType,
    JiraPriority,
    JiraProject,
    JiraResolution,
    JiraSearchResult,
    JiraSprint,
    JiraStatus,
    JiraStatusCategory,
    JiraTimetracking,
    JiraTransition,
    JiraUser,
    JiraWorklog,
)

# Additional models will be added as they are implemented

__all__ = [
    # Base models
    "ApiModel",
    "TimestampMixin",
    # Constants
    "CONFLUENCE_DEFAULT_ID",
    "CONFLUENCE_DEFAULT_SPACE",
    "CONFLUENCE_DEFAULT_VERSION",
    "DEFAULT_TIMESTAMP",
    "EMPTY_STRING",
    "JIRA_DEFAULT_ID",
    "JIRA_DEFAULT_ISSUE_TYPE",
    "JIRA_DEFAULT_KEY",
    "JIRA_DEFAULT_PRIORITY",
    "JIRA_DEFAULT_PROJECT",
    "JIRA_DEFAULT_STATUS",
    "NONE_VALUE",
    "UNASSIGNED",
    "UNKNOWN",
    # Jira models
    "JiraUser",
    "JiraStatus",
    "JiraStatusCategory",
    "JiraIssueType",
    "JiraPriority",
    "JiraComment",
    "JiraIssue",
    "JiraProject",
    "JiraResolution",
    "JiraTransition",
    "JiraWorklog",
    "JiraSearchResult",
    "JiraAttachment",
    "JiraTimetracking",
    "JiraBoard",
    "JiraSprint",
    # Confluence models
    "ConfluenceUser",
    "ConfluenceSpace",
    "ConfluencePage",
    "ConfluenceComment",
    "ConfluenceLabel",
    "ConfluenceVersion",
    "ConfluenceSearchResult",
    "ConfluenceAttachment",
]
