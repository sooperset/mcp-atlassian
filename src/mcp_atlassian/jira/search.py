"""Module for Jira search operations."""

import logging
import re
from typing import Any

import requests
from requests.exceptions import HTTPError

from ..models.jira import JiraSearchResult
from ..utils.decorators import handle_auth_errors
from ..utils.pagination import clamp_limit
from .client import JiraClient
from .constants import DEFAULT_READ_JIRA_FIELDS
from .protocols import IssueOperationsProto
from .utils import quote_jql_identifier_if_needed, sanitize_jql_reserved_words

logger = logging.getLogger("mcp-jira")


class SearchMixin(JiraClient, IssueOperationsProto):
    """Mixin for Jira search operations."""

    def _apply_projects_filter(
        self, jql: str, projects_filter: str | None = None
    ) -> str:
        """Constrain a JQL query to the allowed projects (JIRA_PROJECTS_FILTER).

        Every JQL-issuing path routes through here so none can escape the project
        allowlist. ``config.projects_filter`` is a hard boundary and is always
        applied; a caller-supplied ``projects_filter`` may only *narrow* within it
        (both are ANDed), never replace it — otherwise the tool argument would
        defeat the operator's allowlist in shared-credential deployments.
        """
        for filter_str in (self.config.projects_filter, projects_filter):
            if filter_str:
                jql = self._and_projects_filter(jql, filter_str)
        return jql

    def _and_projects_filter(self, jql: str, filter_to_use: str) -> str:
        """AND a single comma-separated project allowlist into ``jql``."""
        projects = [p.strip() for p in filter_to_use.split(",")]

        if len(projects) == 1:
            quoted = quote_jql_identifier_if_needed(projects[0])
            project_query = f"project = {quoted}"
        else:
            quoted_projects = [quote_jql_identifier_if_needed(p) for p in projects]
            projects_list = ", ".join(quoted_projects)
            project_query = f"project IN ({projects_list})"
        grouped_project_query = f"({project_query})"

        if not jql:
            jql = project_query
        elif jql.strip().upper().startswith("ORDER BY"):
            jql = f"{project_query} {jql}"
        else:
            # Always AND the allowlist, even when the caller's query already names a
            # project: a caller-supplied `project = X` must not be able to escape the
            # configured allowlist (out-of-allowlist queries then return empty).
            # Extract a trailing ORDER BY so the AND does not produce invalid JQL.
            order_match = re.search(r"\s+(ORDER\s+BY\s+.*)$", jql, re.IGNORECASE)
            if order_match:
                order_clause = order_match.group(1)
                jql_without_order = jql[: order_match.start()]
                jql = (
                    f"({jql_without_order}) AND {grouped_project_query} {order_clause}"
                )
            else:
                jql = f"({jql}) AND {grouped_project_query}"

        logger.info(f"Applied projects filter to query: {jql}")
        return jql

    @handle_auth_errors("Jira API")
    def search_issues(
        self,
        jql: str,
        fields: list[str] | tuple[str, ...] | set[str] | str | None = None,
        start: int = 0,
        limit: int = 50,
        expand: str | None = None,
        projects_filter: str | None = None,
        page_token: str | None = None,
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
            projects_filter: Optional comma-separated list of project keys to narrow
                results within the configured allowlist (ANDed with config, never
                replaces it)
            page_token: Optional pagination token from a previous search result.
                  Cloud only — Server/DC uses start for pagination.

        Returns:
            JiraSearchResult object containing issues and metadata (total, start_at, max_results)

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails with the Jira API (401/403)
            Exception: If there is an error searching for issues
        """
        try:
            limit = clamp_limit(limit, context="jira.search_issues")

            # Sanitize JQL reserved words in project key values
            jql = sanitize_jql_reserved_words(jql)

            # Constrain to the allowed projects (JIRA_PROJECTS_FILTER)
            jql = self._apply_projects_filter(jql, projects_filter)

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
                    "fields": fields_list,
                }
                # Note: v3 API uses 'expand' as a comma-separated string, not an array
                if expand:
                    request_body["expand"] = expand

                # Fetch issues using v3 API with nextPageToken pagination
                all_issues: list[dict[str, Any]] = []
                field_names: dict[str, Any] = {}
                next_page_token: str | None = page_token

                while len(all_issues) < limit:
                    # Only request the remaining count to avoid over-fetching.
                    # This ensures the returned nextPageToken aligns with
                    # the last issue we actually return to the caller.
                    remaining = limit - len(all_issues)
                    request_body["maxResults"] = min(remaining, 100)

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

                    names = response.get("names")
                    if isinstance(names, dict):
                        field_names.update(names)

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
                if next_page_token:
                    response_dict["nextPageToken"] = next_page_token
                if field_names:
                    response_dict["names"] = field_names

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

        except HTTPError:
            raise  # let decorator handle auth errors
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
            limit = clamp_limit(limit, context="jira.get_board_issues")

            # Sanitize JQL reserved words in project key values
            jql = sanitize_jql_reserved_words(jql) or jql

            # Constrain board issues to the allowed projects (JIRA_PROJECTS_FILTER)
            jql = self._apply_projects_filter(jql)

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
            Exception: If there is an error getting sprint issues
        """
        # sprint_id is interpolated into JQL; require an integer to prevent
        # JQL injection via a crafted non-numeric value.
        try:
            sprint_id_int = int(str(sprint_id).strip())
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"Invalid sprint_id {sprint_id!r}: must be an integer"
            ) from e

        try:
            limit = clamp_limit(limit, context="jira.get_sprint_issues")

            # Use JQL search to get sprint issues with proper fields filtering
            jql = f"sprint = {sprint_id_int}"
            return self.search_issues(
                jql=jql,
                fields=fields,
                start=start,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error searching issues for sprint '{sprint_id}': {str(e)}")
            raise Exception(f"Error searching issues for sprint: {str(e)}") from e
