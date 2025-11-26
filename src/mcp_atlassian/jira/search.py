"""Module for Jira search operations."""

import logging
from typing import Any

import requests
from requests.exceptions import HTTPError

from ..exceptions import MCPAtlassianAuthenticationError
from ..models.jira import JiraSearchResult
from .client import JiraClient
from .constants import DEFAULT_READ_JIRA_FIELDS
from .protocols import IssueOperationsProto

logger = logging.getLogger("mcp-jira")


class SearchMixin(JiraClient, IssueOperationsProto):
    """Mixin for Jira search operations."""

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

        Args:
            jql: JQL query string
            fields: Fields to return (comma-separated string, list, tuple, set, or "*all")
            start: Starting index if number of issues is greater than the limit
                  Note: This parameter is ignored in Cloud environments and results will always
                  start from the first page.
            limit: Maximum issues to return
            expand: Optional items to expand (comma-separated)
            projects_filter: Optional comma-separated list of project keys to filter by, overrides config

        Returns:
            JiraSearchResult object containing issues and metadata (total, start_at, max_results)

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails with the Jira API (401/403)
            Exception: If there is an error searching for issues
        """
        try:
            # Use projects_filter parameter if provided, otherwise fall back to config
            filter_to_use = projects_filter or self.config.projects_filter

            # Apply projects filter if present
            if filter_to_use:
                # Split projects filter by commas and handle possible whitespace
                projects = [p.strip() for p in filter_to_use.split(",")]

                # Build the project filter query part
                if len(projects) == 1:
                    project_query = f'project = "{projects[0]}"'
                else:
                    quoted_projects = [f'"{p}"' for p in projects]
                    projects_list = ", ".join(quoted_projects)
                    project_query = f"project IN ({projects_list})"

                # Add the project filter to existing query
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

            # Convert fields to proper format if it's a list/tuple/set
            fields_param: str | None
            if fields is None:  # Use default if None
                fields_param = ",".join(DEFAULT_READ_JIRA_FIELDS)
            elif isinstance(fields, list | tuple | set):
                fields_param = ",".join(fields)
            else:
                fields_param = fields

            if self.config.is_cloud:
                # Cloud: Use v3 API endpoint POST /rest/api/3/search/jql
                # The old v2 /rest/api/*/search endpoint is deprecated
                # See: https://developer.atlassian.com/changelog/#CHANGE-2046

                # Build request body for v3 API
                fields_list = fields_param.split(",") if fields_param else ["id", "key"]
                request_body: dict[str, Any] = {
                    "jql": jql,
                    "maxResults": min(limit, 100),  # v3 API max is 100 per request
                    "fields": fields_list,
                }
                # Note: v3 API uses 'expand' as a comma-separated string, not an array
                if expand:
                    request_body["expand"] = expand

                # Fetch issues using v3 API with nextPageToken pagination
                all_issues: list[dict[str, Any]] = []
                next_page_token: str | None = None

                while len(all_issues) < limit:
                    if next_page_token:
                        request_body["nextPageToken"] = next_page_token

                    response = self.jira.post(
                        "rest/api/3/search/jql", json=request_body
                    )

                    if not isinstance(response, dict):
                        msg = f"Unexpected response type from v3 search API: {type(response)}"
                        logger.error(msg)
                        raise TypeError(msg)

                    issues = response.get("issues", [])
                    all_issues.extend(issues)

                    # Check for more pages
                    next_page_token = response.get("nextPageToken")
                    if not next_page_token:
                        break

                # Build response dict for model
                # Note: v3 API doesn't provide total count, so we use -1
                response_dict: dict[str, Any] = {
                    "issues": all_issues[:limit],
                    "total": -1,
                    "startAt": 0,
                    "maxResults": limit,
                }

                search_result = JiraSearchResult.from_api_response(
                    response_dict,
                    base_url=self.config.url,
                    requested_fields=fields_param,
                )

                return search_result
            else:
                limit = min(limit, 50)
                response = self.jira.jql(
                    jql, fields=fields_param, start=start, limit=limit, expand=expand
                )
                if not isinstance(response, dict):
                    msg = f"Unexpected return value type from `jira.jql`: {type(response)}"
                    logger.error(msg)
                    raise TypeError(msg)

                # Convert the response to a search result model
                search_result = JiraSearchResult.from_api_response(
                    response, base_url=self.config.url, requested_fields=fields_param
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
        Get all issues linked to a specific board.

        Args:
            board_id: The ID of the board
            jql: JQL query string
            fields: Fields to return (comma-separated string or "*all")
            start: Starting index
            limit: Maximum issues to return
            expand: Optional items to expand (comma-separated)

        Returns:
            JiraSearchResult object containing board issues and metadata

        Raises:
            Exception: If there is an error getting board issues
        """
        try:
            # Determine fields_param
            fields_param = fields
            if fields_param is None:
                fields_param = ",".join(DEFAULT_READ_JIRA_FIELDS)

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

        Args:
            sprint_id: The ID of the sprint
            fields: Fields to return (comma-separated string or "*all")
            start: Starting index
            limit: Maximum issues to return

        Returns:
            JiraSearchResult object containing sprint issues and metadata

        Raises:
            Exception: If there is an error getting board issues
        """
        try:
            # Determine fields_param
            fields_param = fields
            if fields_param is None:
                fields_param = ",".join(DEFAULT_READ_JIRA_FIELDS)

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
