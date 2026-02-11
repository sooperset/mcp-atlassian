"""Module for Jira development information operations (PRs, commits, branches)."""

import logging
from typing import Any

from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class DevelopmentMixin(JiraClient):
    """Mixin for Jira development information operations."""

    def get_issue_development_info(
        self,
        issue_key: str,
        application_type: str | None = None,
        data_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Get development information (PRs, commits, branches) for a Jira issue.

        This uses the /rest/dev-status/1.0/issue/detail endpoint to retrieve
        development panel information linked to an issue.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)
            application_type: Filter by application type
                (e.g., 'stash', 'github', 'bitbucket').
                If None, tries common application types.
            data_type: Filter by data type
                (e.g., 'pullrequest', 'branch', 'repository').
                If None, returns all data types.

        Returns:
            Dictionary containing development information with structure:
            {
                "detail": [...],  # List of development details by application
                "pullRequests": [...],  # Extracted list of all PRs
                "branches": [...],  # Extracted list of all branches
                "commits": [...],  # Extracted list of all commits
            }

        Raises:
            ValueError: If the issue is not found or issue ID cannot be retrieved
            Exception: If there is an error retrieving development info
        """
        try:
            # First, get the issue to obtain its numeric ID
            issue = self.jira.get_issue(issue_key, fields="id")
            if not isinstance(issue, dict):
                msg = f"Unexpected return value type from jira.get_issue: {type(issue)}"
                logger.error(msg)
                raise TypeError(msg)

            issue_id = issue.get("id")
            if not issue_id:
                msg = f"Could not get issue ID for {issue_key}"
                raise ValueError(msg)

            # If application_type is specified, use it directly
            if application_type:
                return self._fetch_dev_info_for_app_type(
                    issue_key, issue_id, application_type, data_type
                )

            # Otherwise, try common application types and merge results
            # Common types: stash (Bitbucket Server), bitbucket, github, gitlab
            app_types = ["stash", "bitbucket", "github", "gitlab"]
            # Data types to try for each app type
            data_types = ["pullrequest", "branch", "repository"]
            merged_result: dict[str, Any] = {
                "issue_key": issue_key,
                "detail": [],
                "pullRequests": [],
                "branches": [],
                "commits": [],
                "repositories": [],
            }

            for app_type in app_types:
                for dt in data_types:
                    try:
                        result = self._fetch_dev_info_for_app_type(
                            issue_key, issue_id, app_type, dt
                        )
                        # Merge results
                        merged_result["detail"].extend(result.get("detail", []))
                        merged_result["pullRequests"].extend(
                            result.get("pullRequests", [])
                        )
                        merged_result["branches"].extend(result.get("branches", []))
                        merged_result["commits"].extend(result.get("commits", []))
                        for repo in result.get("repositories", []):
                            if repo not in merged_result["repositories"]:
                                merged_result["repositories"].append(repo)
                    except Exception as e:
                        # Log but continue trying other combinations
                        logger.debug(
                            f"No dev info for {issue_key} "
                            f"from {app_type}/{dt}: {str(e)}"
                        )

            return merged_result

        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Error retrieving development info for {issue_key}: {error_msg}"
            )
            msg = f"Error retrieving development info for {issue_key}: {error_msg}"
            raise Exception(msg) from e

    def _fetch_dev_info_for_app_type(
        self,
        issue_key: str,
        issue_id: str,
        application_type: str,
        data_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetch development info for a specific application type.

        Args:
            issue_key: The issue key
            issue_id: The numeric issue ID
            application_type: The application type (stash, github, etc.)
            data_type: Optional data type filter

        Returns:
            Parsed development information
        """
        params: dict[str, str] = {
            "issueId": str(issue_id),
            "applicationType": application_type,
        }
        if data_type:
            params["dataType"] = data_type

        # Call the dev-status API using the session directly
        # The jira.get() method doesn't work well with this endpoint
        url = f"{self.config.url}/rest/dev-status/1.0/issue/detail"
        http_response = self.jira._session.get(
            url, params=params, verify=self.config.ssl_verify
        )
        http_response.raise_for_status()
        response = http_response.json()

        if not isinstance(response, dict):
            msg = f"Unexpected response type from dev-status API: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)

        # Extract and organize the development information
        return self._parse_development_info(response, issue_key)

    def _parse_development_info(
        self, response: dict[str, Any], issue_key: str
    ) -> dict[str, Any]:
        """
        Parse the development info response into a structured format.

        Args:
            response: Raw response from dev-status API
            issue_key: The issue key for reference

        Returns:
            Structured development information
        """
        result: dict[str, Any] = {
            "issue_key": issue_key,
            "detail": [],
            "pullRequests": [],
            "branches": [],
            "commits": [],
            "repositories": [],
        }

        # Get the detail array from response
        details = response.get("detail", [])
        if not details:
            return result

        for detail in details:
            if not isinstance(detail, dict):
                continue

            # Store the raw detail
            result["detail"].append(detail)

            # Get instance info for context
            instance = detail.get("_instance", {})
            instance_name = instance.get("name", "Unknown")
            instance_url = instance.get("baseUrl", "")

            # Extract PRs directly from detail (not nested under repositories)
            for pr in detail.get("pullRequests", []):
                if isinstance(pr, dict):
                    source = pr.get("source", {})
                    destination = pr.get("destination", {})
                    source_repo = source.get("repository", {})

                    result["pullRequests"].append(
                        {
                            "id": pr.get("id", ""),
                            "name": pr.get("name", ""),
                            "status": pr.get("status", ""),
                            "url": pr.get("url", ""),
                            "source": source.get("branch", ""),
                            "destination": destination.get("branch", ""),
                            "author": pr.get("author", {}).get("name", ""),
                            "reviewers": [
                                r.get("name", "")
                                for r in pr.get("reviewers", [])
                                if isinstance(r, dict)
                            ],
                            "lastUpdate": pr.get("lastUpdate", ""),
                            "repository": source_repo.get("name", ""),
                            "repositoryUrl": source_repo.get("url", ""),
                            "instance": instance_name,
                        }
                    )

            # Extract branches directly from detail
            for branch in detail.get("branches", []):
                if isinstance(branch, dict):
                    result["branches"].append(
                        {
                            "name": branch.get("name", ""),
                            "url": branch.get("url", ""),
                            "createPullRequestUrl": branch.get(
                                "createPullRequestUrl", ""
                            ),
                            "instance": instance_name,
                        }
                    )

            # Also check repositories array if present
            repositories = detail.get("repositories", [])
            for repo in repositories:
                if not isinstance(repo, dict):
                    continue

                repo_name = repo.get("name", "Unknown")
                repo_url = repo.get("url", "")
                avatar_url = repo.get("avatar", "")

                # Extract commits from repositories
                for commit in repo.get("commits", []):
                    if isinstance(commit, dict):
                        result["commits"].append(
                            {
                                "id": commit.get("id", ""),
                                "displayId": commit.get("displayId", ""),
                                "message": commit.get("message", ""),
                                "author": commit.get("author", {}).get("name", ""),
                                "authorTimestamp": commit.get("authorTimestamp", ""),
                                "url": commit.get("url", ""),
                                "repository": repo_name,
                                "repositoryUrl": repo_url,
                            }
                        )

                # Extract PRs from repositories (fallback)
                for pr in repo.get("pullRequests", []):
                    if isinstance(pr, dict):
                        result["pullRequests"].append(
                            {
                                "id": pr.get("id", ""),
                                "name": pr.get("name", ""),
                                "status": pr.get("status", ""),
                                "url": pr.get("url", ""),
                                "source": pr.get("source", {}).get("branch", ""),
                                "destination": pr.get("destination", {}).get(
                                    "branch", ""
                                ),
                                "author": pr.get("author", {}).get("name", ""),
                                "reviewers": [
                                    r.get("name", "")
                                    for r in pr.get("reviewers", [])
                                    if isinstance(r, dict)
                                ],
                                "lastUpdate": pr.get("lastUpdate", ""),
                                "repository": repo_name,
                                "repositoryUrl": repo_url,
                            }
                        )

                # Extract branches from repositories (fallback)
                for branch in repo.get("branches", []):
                    if isinstance(branch, dict):
                        result["branches"].append(
                            {
                                "name": branch.get("name", ""),
                                "url": branch.get("url", ""),
                                "createPullRequestUrl": branch.get(
                                    "createPullRequestUrl", ""
                                ),
                                "repository": repo_name,
                                "repositoryUrl": repo_url,
                            }
                        )

                # Track unique repositories
                if repo_name and repo_name != "Unknown":
                    repo_info = {
                        "name": repo_name,
                        "url": repo_url,
                        "avatar": avatar_url,
                    }
                    if repo_info not in result["repositories"]:
                        result["repositories"].append(repo_info)

        return result

    def get_issues_development_info(
        self,
        issue_keys: list[str],
        application_type: str | None = None,
        data_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get development information for multiple Jira issues.

        Args:
            issue_keys: List of issue keys (e.g., ['PROJECT-123', 'PROJECT-456'])
            application_type: Filter by application type
            data_type: Filter by data type

        Returns:
            List of development information dictionaries, one per issue
        """
        results = []
        for issue_key in issue_keys:
            try:
                info = self.get_issue_development_info(
                    issue_key=issue_key,
                    application_type=application_type,
                    data_type=data_type,
                )
                results.append(info)
            except Exception as e:
                logger.warning(
                    f"Failed to get development info for {issue_key}: {str(e)}"
                )
                results.append(
                    {
                        "issue_key": issue_key,
                        "error": str(e),
                        "pullRequests": [],
                        "branches": [],
                        "commits": [],
                    }
                )
        return results
