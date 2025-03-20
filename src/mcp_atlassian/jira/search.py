"""Module for Jira search operations."""

import logging
from typing import Any, Callable, Iterator, List, Optional, Tuple

from ..models.jira import JiraIssue, JiraSearchResult
from ..utils import cached, paginated_iterator
from .client import JiraClient
from .utils import parse_date_ymd

logger = logging.getLogger("mcp-jira")


class SearchMixin(JiraClient):
    """Mixin for Jira search operations."""

    # Conjuntos de campos padrão para diferentes tipos de consultas
    _DEFAULT_FIELDS = [
        "summary", "issuetype", "created", "updated", "project", "status",
        "priority", "assignee", "reporter", "creator"
    ]
    
    _MINIMAL_FIELDS = [
        "summary", "issuetype", "status", "project"
    ]
    
    _DETAILED_FIELDS = [
        "summary", "issuetype", "created", "updated", "project", "status",
        "priority", "assignee", "reporter", "creator", "description",
        "comment", "fixVersions", "components", "labels", "duedate"
    ]

    def search_issues(
        self,
        jql: str,
        fields: str = "*all",
        start: int = 0,
        limit: int = 50,
        expand: str | None = None,
    ) -> list[JiraIssue]:
        """
        Search for issues using JQL (Jira Query Language).

        Args:
            jql: JQL query string
            fields: Fields to return (comma-separated string or "*all")
            start: Starting index
            limit: Maximum issues to return
            expand: Optional items to expand (comma-separated)

        Returns:
            List of JiraIssue models representing the search results

        Raises:
            Exception: If there is an error searching for issues
        """
        try:
            response = self.jira.jql(
                jql, fields=fields, start=start, limit=limit, expand=expand
            )

            # Convert the response to a search result model
            search_result = JiraSearchResult.from_api_response(
                response, base_url=self.config.url
            )

            # Return the list of issues
            return search_result.issues
        except Exception as e:
            logger.error(f"Error searching issues with JQL '{jql}': {str(e)}")
            raise Exception(f"Error searching issues: {str(e)}") from e

    def get_project_issues(
        self, project_key: str, start: int = 0, limit: int = 50
    ) -> list[JiraIssue]:
        """
        Get all issues for a project.

        Args:
            project_key: The project key
            start: Starting index
            limit: Maximum results to return

        Returns:
            List of JiraIssue models containing project issues

        Raises:
            Exception: If there is an error getting project issues
        """
        jql = f"project = {project_key} ORDER BY created DESC"
        return self.search_issues(jql, start=start, limit=limit)

    def get_epic_issues(self, epic_key: str, limit: int = 50) -> list[JiraIssue]:
        """
        Get all issues linked to a specific epic.

        Args:
            epic_key: The key of the epic (e.g. 'PROJ-123')
            limit: Maximum number of issues to return

        Returns:
            List of JiraIssue models representing the issues linked to the epic

        Raises:
            ValueError: If the issue is not an Epic
            Exception: If there is an error getting epic issues
        """
        try:
            # First, check if the issue is an Epic
            epic = self.jira.issue(epic_key)
            fields_data = epic.get("fields", {})

            # Safely check if the issue is an Epic
            issue_type = None
            issuetype_data = fields_data.get("issuetype")
            if issuetype_data is not None:
                issue_type = issuetype_data.get("name", "")

            if issue_type != "Epic":
                error_msg = (
                    f"Issue {epic_key} is not an Epic, it is a "
                    f"{issue_type or 'unknown type'}"
                )
                raise ValueError(error_msg)

            # Try with 'issueFunction in issuesScopedToEpic'
            try:
                jql = f'issueFunction in issuesScopedToEpic("{epic_key}")'
                return self.search_issues(jql, limit=limit)
            except Exception as e:
                # Log exception but continue with fallback
                logger.warning(
                    f"Error searching epic issues with issueFunction: {str(e)}"
                )

            # Fallback to 'Epic Link' field
            jql = f"'Epic Link' = {epic_key}"
            return self.search_issues(jql, limit=limit)

        except ValueError:
            # Re-raise ValueError for non-epic issues
            raise
        except Exception as e:
            logger.error(f"Error getting issues for epic {epic_key}: {str(e)}")
            raise Exception(f"Error getting epic issues: {str(e)}") from e

    def _parse_date(self, date_str: str) -> str:
        """
        Parse a date string from ISO format to a more readable format.

        Args:
            date_str: Date string in ISO format

        Returns:
            Formatted date string
        """
        # Use the common utility function for consistent formatting
        return parse_date_ymd(date_str)

    @cached("jira_jql_search", 300)  # Cache for 5 minutes
    def jql_search(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 50,
        validate: bool = True,
        fields: list[str] | None = None,
        expand: list[str] | None = None,
        field_set: str = "default",
    ) -> dict[str, Any]:
        """
        Execute a JQL search and get raw results.

        Args:
            jql: JQL query string
            start_at: The index of the first result
            max_results: Maximum results to return
            validate: Whether to validate the JQL before running
            fields: List of fields to return (overrides field_set if provided)
            expand: List of items to expand
            field_set: Predefined set of fields to return: "minimal", "default", "detailed", or "all"

        Returns:
            Dictionary with search results
        """
        try:
            # Determine which fields to request
            request_fields = fields
            
            if not request_fields:
                if field_set == "minimal":
                    request_fields = self._MINIMAL_FIELDS
                elif field_set == "default":
                    request_fields = self._DEFAULT_FIELDS
                elif field_set == "detailed":
                    request_fields = self._DETAILED_FIELDS
                # "all" or invalid values will pass None for fields, retrieving all fields
            
            results = self.jira.jql(
                jql=jql,
                start=start_at,
                limit=max_results,
                validate=validate,
                fields=request_fields,
                expand=expand,
            )
            return results if isinstance(results, dict) else {}
        except Exception as e:
            logger.warning(f"Error executing JQL search: {e}")
            logger.debug(f"Failed JQL query: {jql}")
            return {}

    def jql_search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 50,
        validate: bool = True,
        fields: list[str] | None = None,
        expand: list[str] | None = None,
        field_set: str = "default",
    ) -> list[JiraIssue]:
        """
        Execute a JQL search and return parsed issue models.

        Args:
            jql: JQL query string
            start_at: The index of the first result
            max_results: Maximum results to return
            validate: Whether to validate the JQL before running
            fields: List of fields to return (overrides field_set if provided)
            expand: List of items to expand
            field_set: Predefined set of fields to return: "minimal", "default", "detailed", or "all"

        Returns:
            List of JiraIssue objects
        """
        raw_results = self.jql_search(
            jql=jql,
            start_at=start_at,
            max_results=max_results,
            validate=validate,
            fields=fields,
            expand=expand,
            field_set=field_set,
        )

        issues = []
        for issue_data in raw_results.get("issues", []):
            try:
                issue = JiraIssue.from_api_response(issue_data)
                issues.append(issue)
            except Exception as e:
                logger.warning(f"Error parsing issue data: {e}")
                continue

        return issues

    def jql_search_result(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 50,
        validate: bool = True,
        fields: list[str] | None = None,
        expand: list[str] | None = None,
        field_set: str = "default",
    ) -> JiraSearchResult:
        """
        Execute a JQL search and return a paginated search result.

        Args:
            jql: JQL query string
            start_at: The index of the first result
            max_results: Maximum results to return
            validate: Whether to validate the JQL before running
            fields: List of fields to return (overrides field_set if provided)
            expand: List of items to expand
            field_set: Predefined set of fields to return: "minimal", "default", "detailed", or "all"

        Returns:
            JiraSearchResult with pagination metadata and issues
        """
        raw_results = self.jql_search(
            jql=jql,
            start_at=start_at,
            max_results=max_results,
            validate=validate,
            fields=fields,
            expand=expand,
            field_set=field_set,
        )

        # Parse pagination metadata
        total = raw_results.get("total", 0)
        start_at_resp = raw_results.get("startAt", start_at)
        max_results_resp = raw_results.get("maxResults", max_results)

        # Parse issues
        issues = []
        for issue_data in raw_results.get("issues", []):
            try:
                issue = JiraIssue.from_api_response(issue_data)
                issues.append(issue)
            except Exception as e:
                logger.warning(f"Error parsing issue data: {e}")
                continue

        return JiraSearchResult(
            issues=issues,
            total=total,
            start_at=start_at_resp,
            max_results=max_results_resp,
        )

    def jql_search_iter(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 1000,
        page_size: int = 50,
        validate: bool = True,
        fields: list[str] | None = None,
        expand: list[str] | None = None,
        field_set: str = "default",
    ) -> Iterator[JiraIssue]:
        """
        Execute a JQL search and iterate through all matching issues.
        This uses efficient pagination to avoid loading all results at once.

        Args:
            jql: JQL query string
            start_at: The index of the first result
            max_results: Maximum total number of results to return (None for all)
            page_size: Number of results to fetch per page
            validate: Whether to validate the JQL before running
            fields: List of fields to return (overrides field_set if provided)
            expand: List of items to expand
            field_set: Predefined set of fields to return: "minimal", "default", "detailed", or "all"

        Yields:
            JiraIssue objects one at a time
        """
        def fetch_page(start: int, limit: int) -> Tuple[List[JiraIssue], int]:
            """Internal function to fetch a page of results."""
            results = self.jql_search(
                jql=jql,
                start_at=start,
                max_results=limit,
                validate=validate,
                fields=fields,
                expand=expand,
                field_set=field_set,
            )
            
            issues = []
            for issue_data in results.get("issues", []):
                try:
                    issue = JiraIssue.from_api_response(issue_data)
                    issues.append(issue)
                except Exception as e:
                    logger.warning(f"Error parsing issue data: {e}")
                    continue
                    
            return issues, results.get("total", 0)
            
        # Use the paginated iterator
        return paginated_iterator(
            fetch_function=fetch_page,
            start_at=start_at,
            max_per_page=page_size,
            max_total=max_results,
        )
