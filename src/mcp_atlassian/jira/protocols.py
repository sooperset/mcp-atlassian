"""Module for Jira protocol definitions."""

from abc import abstractmethod
from typing import Any, Protocol, runtime_checkable

from ..models.jira import JiraIssue
from ..models.jira.search import JiraSearchResult


class AttachmentsOperationsProto(Protocol):
    """Protocol defining attachments operations interface."""

    @abstractmethod
    def upload_attachments(
        self, issue_key: str, file_paths: list[str]
    ) -> dict[str, Any]:
        """
        Upload multiple attachments to a Jira issue.

        Args:
            issue_key: The Jira issue key (e.g., 'PROJ-123')
            file_paths: List of paths to files to upload

        Returns:
            A dictionary with upload results
        """


class IssueOperationsProto(Protocol):
    """Protocol defining issue operations interface."""

    @abstractmethod
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


class SearchOperationsProto(Protocol):
    """Protocol defining search operations interface."""

    @abstractmethod
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


class EpicOperationsProto(Protocol):
    """Protocol defining epic operations interface."""

    @abstractmethod
    def update_epic_fields(self, issue_key: str, kwargs: dict[str, Any]) -> JiraIssue:
        """
        Update Epic-specific fields after Epic creation.

        This method implements the second step of the two-step Epic creation process,
        applying Epic-specific fields that may be rejected during initial creation
        due to screen configuration restrictions.

        Args:
            issue_key: The key of the created Epic
            kwargs: Dictionary containing special keys with Epic field information

        Returns:
            JiraIssue: The updated Epic

        Raises:
            Exception: If there is an error updating the Epic fields
        """

    @abstractmethod
    def prepare_epic_fields(
        self, fields: dict[str, Any], summary: str, kwargs: dict[str, Any]
    ) -> None:
        """
        Prepare epic-specific fields for issue creation.

        Args:
            fields: The fields dictionary to update
            summary: The issue summary that can be used as a default epic name
            kwargs: Additional fields from the user
        """

    @abstractmethod
    def _try_discover_fields_from_existing_epic(
        self, field_ids: dict[str, str]
    ) -> None:
        """
        Try to discover Epic fields from existing epics in the Jira instance.

        This is a fallback method used when standard field discovery doesn't find
        all the necessary Epic-related fields. It searches for an existing Epic and
        analyzes its field structure to identify Epic fields dynamically.

        Args:
            field_ids: Dictionary of field IDs to update with discovered fields
        """


class FieldsOperationsProto(Protocol):
    """Protocol defining fields operations interface."""

    @abstractmethod
    def _generate_field_map(self, force_regenerate: bool = False) -> dict[str, str]:
        """
        Generates and caches a map of lowercase field names to field IDs.

        Args:
            force_regenerate: If True, forces regeneration even if cache exists.

        Returns:
            A dictionary mapping lowercase field names and field IDs to actual field IDs.
        """

    @abstractmethod
    def get_field_by_id(
        self, field_id: str, refresh: bool = False
    ) -> dict[str, Any] | None:
        """
        Get field definition by ID.
        """

    @abstractmethod
    def get_field_ids_to_epic(self) -> dict[str, str]:
        """
        Dynamically discover Jira field IDs relevant to Epic linking.
        This method queries the Jira API to find the correct custom field IDs
        for Epic-related fields, which can vary between different Jira instances.

        Returns:
            Dictionary mapping field names to their IDs
            (e.g., {'epic_link': 'customfield_10014', 'epic_name': 'customfield_10011'})
        """


@runtime_checkable
class UsersOperationsProto(Protocol):
    """Protocol defining user operations interface."""

    @abstractmethod
    def _get_account_id(self, assignee: str) -> str:
        """Get the account ID for a username.

        Args:
            assignee: Username or account ID

        Returns:
            Account ID

        Raises:
            ValueError: If the account ID could not be found
        """
