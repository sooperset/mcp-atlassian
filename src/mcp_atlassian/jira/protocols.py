"""Module for Jira protocol definitions."""

from typing import Protocol, runtime_checkable

from ..models.jira import JiraIssue
from ..models.jira.search import JiraSearchResult


@runtime_checkable
class IssueOperationsProto(Protocol):
    """Protocol defining issue operations interface."""

    def get_issue(
        self,
        issue_key: str,
        expand: str | None = None,
        comment_limit: int | str | None = 10,
        fields: str
        | list[str]
        | tuple[str, ...]
        | set[str]
        | None = "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
        properties: str | list[str] | None = None,
        update_history: bool = True,
    ) -> JiraIssue:
        """Get a Jira issue by key."""


@runtime_checkable
class SearchOperationsProto(Protocol):
    """Protocol defining search operations interface."""

    def search_issues(
        self,
        jql: str,
        fields: str
        | list[str]
        | tuple[str, ...]
        | set[str]
        | None = "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
        start: int = 0,
        limit: int = 50,
        expand: str | None = None,
        projects_filter: str | None = None,
    ) -> JiraSearchResult:
        """Search for issues using JQL."""
