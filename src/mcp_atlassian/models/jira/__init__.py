"""
Jira data models for the MCP Atlassian integration.

This package provides Pydantic models for Jira API data structures,
organized by entity type for better maintainability and clarity.
"""

from .agile import JiraBoard, JiraSprint
from .comment import JiraComment
from .common import (
    JiraAttachment,
    JiraIssueType,
    JiraPriority,
    JiraResolution,
    JiraStatus,
    JiraStatusCategory,
    JiraTimetracking,
    JiraUser,
)
from .issue import JiraIssue
from .link import (
    JiraIssueLink,
    JiraIssueLinkType,
    JiraLinkedIssue,
    JiraLinkedIssueFields,
)
from .metrics import (
    IssueDatesBatchResponse,
    IssueDatesResponse,
    StatusChangeEntry,
    StatusTimeSummary,
)
from .project import JiraProject
from .search import JiraSearchResult
from .sla import (
    CycleTimeMetric,
    DueDateComplianceMetric,
    FirstResponseTimeMetric,
    IssueSLABatchResponse,
    IssueSLAMetrics,
    IssueSLAResponse,
    LeadTimeMetric,
    ResolutionTimeMetric,
    TimeInStatusEntry,
    TimeInStatusMetric,
    WorkingHoursConfig,
)
from .workflow import JiraTransition
from .worklog import JiraWorklog

__all__ = [
    # Common models
    "JiraUser",
    "JiraStatusCategory",
    "JiraStatus",
    "JiraIssueType",
    "JiraPriority",
    "JiraAttachment",
    "JiraResolution",
    "JiraTimetracking",
    # Entity-specific models
    "JiraComment",
    "JiraWorklog",
    "JiraProject",
    "JiraTransition",
    "JiraBoard",
    "JiraSprint",
    "JiraIssue",
    "JiraSearchResult",
    "JiraIssueLinkType",
    "JiraIssueLink",
    "JiraLinkedIssue",
    "JiraLinkedIssueFields",
    # Metrics models
    "IssueDatesResponse",
    "IssueDatesBatchResponse",
    "StatusChangeEntry",
    "StatusTimeSummary",
    # SLA models
    "IssueSLAResponse",
    "IssueSLABatchResponse",
    "IssueSLAMetrics",
    "CycleTimeMetric",
    "LeadTimeMetric",
    "TimeInStatusEntry",
    "TimeInStatusMetric",
    "DueDateComplianceMetric",
    "ResolutionTimeMetric",
    "FirstResponseTimeMetric",
    "WorkingHoursConfig",
]
