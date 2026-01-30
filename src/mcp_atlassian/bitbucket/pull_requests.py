"""Module for Bitbucket pull request operations."""

import logging
from typing import Any

from ..models.bitbucket.pull_request import BitbucketPullRequest
from .client import BitbucketClient

logger = logging.getLogger("mcp-bitbucket")


class PullRequestsMixin(BitbucketClient):
    """Mixin for Bitbucket pull request operations.

    This mixin provides methods for creating and managing pull requests.
    Supports both Bitbucket Cloud and Server/Data Center.
    """

    def create_pr(
        self,
        repository: str,
        title: str,
        source_branch: str,
        destination_branch: str,
        description: str | None = None,
        workspace: str | None = None,
        project_key: str | None = None,
        reviewers: list[str] | None = None,
        close_source_branch: bool = False,
    ) -> BitbucketPullRequest:
        """
        Create a new pull request.

        For Bitbucket Cloud:
            - workspace and repository are required
            - repository format: "repo-slug"

        For Bitbucket Server:
            - project_key and repository are required
            - repository format: "repo-slug"

        Args:
            repository: Repository slug
            title: Pull request title
            source_branch: Source branch name
            destination_branch: Destination branch name
                (default branch if not specified)
            description: Pull request description
            workspace: Workspace slug (Cloud only)
            project_key: Project key (Server only)
            reviewers: List of reviewer usernames/UUIDs (optional)
            close_source_branch: Whether to close source branch after merge (Cloud only)

        Returns:
            BitbucketPullRequest object

        Raises:
            ValueError: If required parameters are missing
            requests.HTTPError: If the API request fails
        """
        try:
            if self.config.is_cloud:
                if not workspace:
                    error_msg = "workspace parameter is required for Bitbucket Cloud"
                    raise ValueError(error_msg)

                # Bitbucket Cloud API endpoint
                endpoint = f"/2.0/repositories/{workspace}/{repository}/pullrequests"

                # Build request payload
                payload: dict[str, Any] = {
                    "title": title,
                    "source": {"branch": {"name": source_branch}},
                    "destination": {"branch": {"name": destination_branch}},
                }

                if description:
                    payload["description"] = description

                if close_source_branch:
                    payload["close_source_branch"] = True

                if reviewers:
                    payload["reviewers"] = [{"uuid": r} for r in reviewers]

                logger.debug(
                    f"Creating pull request in {workspace}/{repository}: "
                    f"{source_branch} -> {destination_branch}"
                )

                response = self._post(endpoint, json_data=payload)
                return BitbucketPullRequest.from_api_response(response, is_cloud=True)

            else:
                if not project_key:
                    error_msg = "project_key parameter is required for Bitbucket Server"
                    raise ValueError(error_msg)

                # Bitbucket Server/Data Center API endpoint
                endpoint = (
                    f"/rest/api/1.0/projects/{project_key}/"
                    f"repos/{repository}/pull-requests"
                )

                # Build request payload
                payload: dict[str, Any] = {
                    "title": title,
                    "fromRef": {
                        "id": f"refs/heads/{source_branch}",
                        "repository": {
                            "slug": repository,
                            "project": {"key": project_key},
                        },
                    },
                    "toRef": {
                        "id": f"refs/heads/{destination_branch}",
                        "repository": {
                            "slug": repository,
                            "project": {"key": project_key},
                        },
                    },
                }

                if description:
                    payload["description"] = description

                if reviewers:
                    payload["reviewers"] = [{"user": {"name": r}} for r in reviewers]

                logger.debug(
                    f"Creating pull request in {project_key}/{repository}: "
                    f"{source_branch} -> {destination_branch}"
                )

                response = self._post(endpoint, json_data=payload)
                return BitbucketPullRequest.from_api_response(response, is_cloud=False)

        except Exception as e:
            logger.error(f"Error creating pull request: {str(e)}")
            raise

    def get_pull_request(
        self,
        repository: str,
        pr_id: int,
        workspace: str | None = None,
        project_key: str | None = None,
    ) -> BitbucketPullRequest | None:
        """
        Get detailed information about a specific pull request.

        Args:
            repository: Repository slug
            pr_id: Pull request ID
            workspace: Workspace slug (Cloud only)
            project_key: Project key (Server only)

        Returns:
            BitbucketPullRequest object or None if not found
        """
        try:
            if self.config.is_cloud:
                if not workspace:
                    error_msg = "workspace parameter is required for Bitbucket Cloud"
                    raise ValueError(error_msg)

                endpoint = (
                    f"/2.0/repositories/{workspace}/{repository}/pullrequests/{pr_id}"
                )
                pr_data = self._get(endpoint)
                return BitbucketPullRequest.from_api_response(pr_data, is_cloud=True)

            else:
                if not project_key:
                    error_msg = "project_key parameter is required for Bitbucket Server"
                    raise ValueError(error_msg)

                endpoint = (
                    f"/rest/api/1.0/projects/{project_key}/"
                    f"repos/{repository}/pull-requests/{pr_id}"
                )
                pr_data = self._get(endpoint)
                return BitbucketPullRequest.from_api_response(pr_data, is_cloud=False)

        except Exception as e:
            logger.error(f"Error getting pull request {pr_id}: {str(e)}")
            return None

    def list_pull_requests(
        self,
        repository: str,
        workspace: str | None = None,
        project_key: str | None = None,
        state: str | None = None,
        limit: int = 50,
    ) -> list[BitbucketPullRequest]:
        """
        List pull requests for a repository.

        Args:
            repository: Repository slug
            workspace: Workspace slug (Cloud only)
            project_key: Project key (Server only)
            state: Filter by state
                (Cloud: OPEN, MERGED, DECLINED; Server: OPEN, MERGED, DECLINED, ALL)
            limit: Maximum number of pull requests to return

        Returns:
            List of BitbucketPullRequest objects
        """
        try:
            if self.config.is_cloud:
                if not workspace:
                    error_msg = "workspace parameter is required for Bitbucket Cloud"
                    raise ValueError(error_msg)

                endpoint = f"/2.0/repositories/{workspace}/{repository}/pullrequests"
                params = {"pagelen": min(limit, 100)}
                if state:
                    params["state"] = state

                pull_requests = []
                while len(pull_requests) < limit:
                    response = self._get(endpoint, params=params)

                    if not isinstance(response, dict):
                        logger.error(f"Unexpected response type: {type(response)}")
                        break

                    values = response.get("values", [])
                    for pr_data in values:
                        if len(pull_requests) >= limit:
                            break
                        pr = BitbucketPullRequest.from_api_response(
                            pr_data, is_cloud=True
                        )
                        pull_requests.append(pr)

                    # Check if there are more pages
                    next_url = response.get("next")
                    if not next_url or len(pull_requests) >= limit:
                        break

                    endpoint = next_url.replace(self.config.url, "")

                return pull_requests

            else:
                if not project_key:
                    error_msg = "project_key parameter is required for Bitbucket Server"
                    raise ValueError(error_msg)

                endpoint = (
                    f"/rest/api/1.0/projects/{project_key}/"
                    f"repos/{repository}/pull-requests"
                )
                params = {"limit": min(limit, 1000)}
                if state:
                    params["state"] = state

                pull_requests = []
                start = 0
                while len(pull_requests) < limit:
                    params["start"] = start
                    response = self._get(endpoint, params=params)

                    if not isinstance(response, dict):
                        logger.error(f"Unexpected response type: {type(response)}")
                        break

                    values = response.get("values", [])
                    for pr_data in values:
                        if len(pull_requests) >= limit:
                            break
                        pr = BitbucketPullRequest.from_api_response(
                            pr_data, is_cloud=False
                        )
                        pull_requests.append(pr)

                    # Check if there are more pages
                    is_last_page = response.get("isLastPage", True)
                    if is_last_page or len(pull_requests) >= limit:
                        break

                    start = response.get("nextPageStart", start + len(values))

                return pull_requests

        except Exception as e:
            logger.error(f"Error listing pull requests: {str(e)}")
            raise
