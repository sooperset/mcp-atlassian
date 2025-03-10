"""
Pydantic models for Jira and Confluence API responses.

This package provides type-safe models for working with Atlassian API data,
including conversion methods from API responses to structured models and
simplified dictionaries for API responses.
"""

# Re-export models for easier imports
from .base import ApiModel, TimestampMixin

# Confluence models
from .confluence import (
    ConfluenceComment,
    ConfluencePage,
    ConfluenceSearchResult,
    ConfluenceSpace,
    ConfluenceUser,
    ConfluenceVersion,
)
from .constants import (
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

# Jira models
from .jira import (
    JiraComment,
    JiraIssue,
    JiraIssueType,
    JiraPriority,
    JiraProject,
    JiraSearchResult,
    JiraStatus,
    JiraStatusCategory,
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
    "JiraTransition",
    "JiraWorklog",
    "JiraSearchResult",
    # Confluence models
    "ConfluenceUser",
    "ConfluenceSpace",
    "ConfluencePage",
    "ConfluenceComment",
    "ConfluenceVersion",
    "ConfluenceSearchResult",
]
