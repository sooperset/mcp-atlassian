"""Module for Jira search operations.

This module provides search functionality for both Jira Cloud and Server/Data Center deployments.

Key differences between deployment types:

**Cloud (API v3 - /rest/api/3/search/jql):**
- Uses POST with JSON body containing JQL and parameters
- Pagination via nextPageToken (token-based, sequential only)
- Returns total=-1 (v3 API doesn't provide total count)
- Requires non-empty JQL (returns 400 error if empty)
- Fields must be explicitly requested (returns only IDs by default)
- Up to 100 issues per request
- Comments limited to 20 items per issue (use separate API for more)
- Changelog limited to 20 items per issue (use separate API for more)
- start parameter ignored (uses token-based pagination)

**Server/DC (API v2 - /rest/api/2/search):**
- Uses GET with query parameters
- Pagination via startAt (offset-based, random access)
- Returns actual total count
- Allows empty JQL queries
- Returns all fields by default
- Limited to 50 issues per request
- No comment/changelog limits
- start parameter respected for pagination

Example:
    >>> from mcp_atlassian.jira import JiraClient
    >>> client = JiraClient(config)
    >>>
    >>> # Cloud example with pagination
    >>> result = client.search_issues(
    ...     jql="project = DEMO AND status = Open",
    ...     fields=["summary", "status", "assignee"],
    ...     limit=100
    ... )
    >>> print(f"Found {len(result.issues)} issues")
    >>> if result.next_page_token:
    ...     print("More results available")
    >>>
    >>> # Server/DC example with offset pagination
    >>> result = client.search_issues(
    ...     jql="project = DEMO",
    ...     start=50,  # Get next page
    ...     limit=50
    ... )
    >>> print(f"Total: {result.total}, showing {result.start_at}-{result.start_at + len(result.issues)}")
"""

import logging

import requests
from requests.exceptions import HTTPError

from ..exceptions import MCPAtlassianAuthenticationError
from ..models.jira import JiraSearchResult
from .client import JiraClient
from .constants import DEFAULT_READ_JIRA_FIELDS
from .protocols import IssueOperationsProto

logger = logging.getLogger("mcp-jira")


class SearchMixin(JiraClient, IssueOperationsProto):
    """Mixin providing search operations for Jira issues.

    This mixin extends JiraClient with search capabilities including:
    - JQL-based issue search with automatic project filtering
    - Board-specific issue retrieval
    - Sprint-specific issue retrieval

    Inherits from:
        JiraClient: Base client with configuration and API access
        IssueOperationsProto: Protocol defining issue operation interface
    """

    def search_issues(
        self,
        jql: str,
        fields: list[str] | tuple[str, ...] | set[str] | str | None = None,
        start: int = 0,
        limit: int = 50,
        expand: str | None = None,
        projects_filter: str | None = None,
    ) -> JiraSearchResult:
        """
        Search for issues using JQL (Jira Query Language).

        This method automatically handles differences between Cloud and Server/DC deployments:

        **Cloud Behavior (API v3):**
        - Uses POST /rest/api/3/search/jql with JSON body
        - Implements nextPageToken pagination (not startAt)
        - Ignores 'start' parameter (uses token-based pagination)
        - Can retrieve up to 100 issues per request
        - Returns total=-1 (v3 API doesn't provide total count)
        - Requires non-empty JQL (raises ValueError if empty)
        - Fields must be explicitly requested (returns only IDs by default)
        - Comments/changelog limited to 20 items (use separate requests for more)

        **Server/DC Behavior (API v2):**
        - Uses GET /rest/api/2/search with query parameters
        - Respects 'start' parameter for offset-based pagination
        - Limited to 50 issues per request (enforced)
        - Returns actual total count
        - Allows empty JQL queries

        **Project Filtering:**
        If projects_filter is provided (or configured), automatically modifies JQL:
        - Single project: Adds 'project = "KEY"'
        - Multiple projects: Adds 'project IN ("KEY1", "KEY2")'
        - Preserves existing JQL logic and ORDER BY clauses
        - Skips if JQL already contains project filter

        Args:
            jql: JQL query string (e.g., "status = Open ORDER BY created DESC")
                 Cloud: Cannot be empty (raises ValueError)
                 Server/DC: Can be empty
            fields: Fields to return. Accepts:
                - None: Uses DEFAULT_READ_JIRA_FIELDS
                - list/tuple/set: Converted to comma-separated string
                - str: Used as-is (e.g., "summary,status,assignee" or "*all")
            start: Starting index for pagination
                   Cloud: Ignored (uses nextPageToken internally)
                   Server/DC: Used for offset-based pagination
            limit: Maximum issues to return
                   Cloud: Up to 100 per request, handles pagination automatically
                   Server/DC: Max 50 per request (enforced)
            expand: Optional comma-separated items to expand (e.g., "changelog,renderedFields")
            projects_filter: Comma-separated project keys (e.g., "PROJ,DEV").
                Overrides config.projects_filter if provided.

        Returns:
            JiraSearchResult: Object containing:
                - issues: List of JiraIssue models
                - total: Total matching issues (Cloud: -1, Server/DC: actual count)
                - start_at: Starting index (Cloud: 0, Server/DC: actual offset)
                - max_results: Maximum results per page
                - next_page_token: Pagination token (Cloud only, None if no more pages)

        Raises:
            ValueError: Empty JQL query on Cloud deployment
            MCPAtlassianAuthenticationError: Authentication failed (401/403 status)
            TypeError: Unexpected API response type
            HTTPError: Other HTTP errors from Jira API
            Exception: General search errors

        Example:
            >>> # Simple search
            >>> result = client.search_issues("project = DEMO")
            >>>
            >>> # With specific fields and project filter
            >>> result = client.search_issues(
            ...     jql="status = 'In Progress'",
            ...     fields=["summary", "assignee", "priority"],
            ...     projects_filter="PROJ,DEV",
            ...     limit=100
            ... )
            >>> print(f"Found {result.total} issues, showing {len(result.issues)}")
            >>>
            >>> # Cloud pagination example
            >>> if result.next_page_token:
            ...     print("More results available (Cloud uses token-based pagination)")
        """
        try:
            # Use projects_filter parameter if provided, otherwise fall back to config
            filter_to_use = projects_filter or self.config.projects_filter

            # Apply projects filter if present
            if filter_to_use:
                # Split projects filter by commas and handle possible whitespace
                projects = [p.strip() for p in filter_to_use.split(",")]

                # Build the project filter query part
                # Single project: project = "KEY"
                # Multiple projects: project IN ("KEY1", "KEY2")
                if len(projects) == 1:
                    project_query = f'project = "{projects[0]}"'
                else:
                    quoted_projects = [f'"{p}"' for p in projects]
                    projects_list = ", ".join(quoted_projects)
                    project_query = f"project IN ({projects_list})"

                # Intelligently merge project filter with existing JQL
                if not jql:
                    # Empty JQL - just use project filter
                    jql = project_query
                elif jql.strip().upper().startswith("ORDER BY"):
                    # JQL starts with ORDER BY - prepend project filter
                    jql = f"{project_query} {jql}"
                elif "project = " not in jql and "project IN" not in jql:
                    # Only add if not already filtering by project
                    jql = f"({jql}) AND {project_query}"

                logger.info(f"Applied projects filter to query: {jql}")

            # Normalize fields parameter to comma-separated string
            # Supports: None (use defaults), list/tuple/set (convert), or string (use as-is)
            fields_param: str | None
            if fields is None:
                fields_param = ",".join(DEFAULT_READ_JIRA_FIELDS)
            elif isinstance(fields, list | tuple | set):
                fields_param = ",".join(fields)
            else:
                fields_param = fields

            if self.config.is_cloud:
                # Cloud deployment: Use v3 API with proper request/response format
                # Validate JQL not empty (v3 API requirement)
                if not jql or not jql.strip():
                    raise ValueError("JQL query cannot be empty for Jira Cloud API v3")

                # Build v3 request body with explicit fields
                fields_list = fields_param.split(",") if fields_param else ["id"]
                request_body = {
                    "jql": jql,
                    "maxResults": min(limit, 100),  # v3 API max per request
                    "fields": fields_list,
                }
                if expand:
                    request_body["expand"] = expand

                # Fetch issues with nextPageToken pagination
                all_issues = []
                next_token = None

                while len(all_issues) < limit:
                    if next_token:
                        request_body["nextPageToken"] = next_token

                    try:
                        response = self.jira.post(
                            "rest/api/3/search/jql", json=request_body
                        )

                        if not isinstance(response, dict):
                            msg = f"Unexpected return value type from v3 search API: {type(response)}"
                            logger.error(msg)
                            raise TypeError(msg)

                        issues = response.get("issues", [])
                        all_issues.extend(issues)

                        next_token = response.get("nextPageToken")
                        if not next_token:
                            break

                    except Exception as e:
                        logger.error(f"Error fetching issues from v3 API: {str(e)}")
                        raise

                # Build result with v3 format
                response_dict = {
                    "issues": all_issues[:limit],
                    "total": -1,  # v3 doesn't provide total
                    "startAt": 0,
                    "maxResults": limit,
                    "nextPageToken": next_token if len(all_issues) >= limit else None,
                }

                return JiraSearchResult.from_api_response(
                    response_dict,
                    base_url=self.config.url,
                    requested_fields=fields_param,
                    is_cloud=True,
                )
            else:
                # Server/DC deployment: Use standard JQL API with 50-issue limit
                limit = min(limit, 50)  # Enforce Server/DC maximum
                response = self.jira.jql(
                    jql, fields=fields_param, start=start, limit=limit, expand=expand
                )
                if not isinstance(response, dict):
                    msg = f"Unexpected return value type from `jira.jql`: {type(response)}"
                    logger.error(msg)
                    raise TypeError(msg)

                # Convert the response to a search result model
                search_result = JiraSearchResult.from_api_response(
                    response,
                    base_url=self.config.url,
                    requested_fields=fields_param,
                    is_cloud=False,
                )

                # Return the full search result object
                return search_result

        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code in [
                401,
                403,
            ]:
                error_msg = (
                    f"Authentication failed for Jira API ({http_err.response.status_code}). "
                    "Token may be expired or invalid. Please verify credentials."
                )
                logger.error(error_msg)
                raise MCPAtlassianAuthenticationError(error_msg) from http_err
            else:
                logger.error(f"HTTP error during API call: {http_err}", exc_info=False)
                raise http_err
        except Exception as e:
            logger.error(f"Error searching issues with JQL '{jql}': {str(e)}")
            raise Exception(f"Error searching issues: {str(e)}") from e

    def get_board_issues(
        self,
        board_id: str,
        jql: str,
        fields: str | None = None,
        start: int = 0,
        limit: int = 50,
        expand: str | None = None,
    ) -> JiraSearchResult:
        """
        Get all issues linked to a specific Agile board.

        Retrieves issues associated with a board (Scrum or Kanban) using the
        Jira Agile API. The JQL parameter allows additional filtering beyond
        the board's default filter.

        Args:
            board_id: The numeric ID of the board (e.g., "123")
            jql: Additional JQL query to filter board issues (e.g., "status = 'In Progress'")
            fields: Comma-separated field names or "*all" (default: DEFAULT_READ_JIRA_FIELDS)
            start: Starting index for pagination
            limit: Maximum issues to return (default: 50)
            expand: Optional comma-separated items to expand (e.g., "changelog")

        Returns:
            JiraSearchResult: Object containing board issues and metadata

        Raises:
            TypeError: If API returns unexpected response type
            HTTPError: If board doesn't exist or access is denied
            Exception: General errors during board issue retrieval

        Example:
            >>> # Get all in-progress issues from board 42
            >>> result = client.get_board_issues(
            ...     board_id="42",
            ...     jql="status = 'In Progress'",
            ...     fields="summary,assignee,status"
            ... )
        """
        try:
            # Use default fields if none specified
            fields_param = fields if fields else ",".join(DEFAULT_READ_JIRA_FIELDS)

            response = self.jira.get_issues_for_board(
                board_id=board_id,
                jql=jql,
                fields=fields_param,
                start=start,
                limit=limit,
                expand=expand,
            )
            if not isinstance(response, dict):
                msg = f"Unexpected return value type from `jira.get_issues_for_board`: {type(response)}"
                logger.error(msg)
                raise TypeError(msg)

            # Convert the response to a search result model
            search_result = JiraSearchResult.from_api_response(
                response, base_url=self.config.url, requested_fields=fields_param
            )
            return search_result
        except requests.HTTPError as e:
            logger.error(
                f"Error searching issues for board with JQL '{board_id}': {str(e.response.content)}"
            )
            raise Exception(
                f"Error searching issues for board with JQL: {str(e.response.content)}"
            ) from e
        except Exception as e:
            logger.error(f"Error searching issues for board with JQL '{jql}': {str(e)}")
            raise Exception(
                f"Error searching issues for board with JQL {str(e)}"
            ) from e

    def get_sprint_issues(
        self,
        sprint_id: str,
        fields: str | None = None,
        start: int = 0,
        limit: int = 50,
    ) -> JiraSearchResult:
        """
        Get all issues linked to a specific sprint.

        Retrieves all issues that are part of a sprint, including issues that
        were added, removed, or completed during the sprint.

        Args:
            sprint_id: The numeric ID of the sprint (e.g., "456")
            fields: Comma-separated field names or "*all" (default: DEFAULT_READ_JIRA_FIELDS)
            start: Starting index for pagination
            limit: Maximum issues to return (default: 50)

        Returns:
            JiraSearchResult: Object containing sprint issues and metadata

        Raises:
            TypeError: If API returns unexpected response type
            HTTPError: If sprint doesn't exist or access is denied
            Exception: General errors during sprint issue retrieval

        Example:
            >>> # Get all issues from sprint 456
            >>> result = client.get_sprint_issues(
            ...     sprint_id="456",
            ...     fields="summary,status,storyPoints"
            ... )
        """
        try:
            # Use default fields if none specified
            fields_param = fields if fields else ",".join(DEFAULT_READ_JIRA_FIELDS)

            response = self.jira.get_sprint_issues(
                sprint_id=sprint_id,
                start=start,
                limit=limit,
            )
            if not isinstance(response, dict):
                msg = f"Unexpected return value type from `jira.get_sprint_issues`: {type(response)}"
                logger.error(msg)
                raise TypeError(msg)

            # Convert the response to a search result model
            search_result = JiraSearchResult.from_api_response(
                response, base_url=self.config.url, requested_fields=fields_param
            )
            return search_result
        except requests.HTTPError as e:
            logger.error(
                f"Error searching issues for sprint '{sprint_id}': {str(e.response.content)}"
            )
            raise Exception(
                f"Error searching issues for sprint: {str(e.response.content)}"
            ) from e
        except Exception as e:
            logger.error(f"Error searching issues for sprint: {sprint_id}': {str(e)}")
            raise Exception(f"Error searching issues for sprint: {str(e)}") from e
