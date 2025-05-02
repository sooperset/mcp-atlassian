"""Pull request operations for Bitbucket Server."""

import logging

from ..models.bitbucket_server import BitbucketServerPullRequest
from .client import BitbucketServerClient

logger = logging.getLogger("mcp-atlassian.bitbucket_server")


class BitbucketServerPullRequests:
    """Bitbucket Server pull request operations."""

    def __init__(self, client: BitbucketServerClient) -> None:
        """Initialize Bitbucket Server pull requests operations.

        Args:
            client: Bitbucket Server client
        """
        self.client = client

    def get_pull_request(
        self, repository: str, pr_id: int, project: str | None = None
    ) -> BitbucketServerPullRequest:
        """Get details of a pull request.

        Args:
            repository: Repository slug
            pr_id: Pull request ID
            project: Project key (can be omitted if provided in config)

        Returns:
            Pull request details

        Raises:
            BitbucketServerApiError: If the API request fails
            ValueError: If required parameters are missing
        """
        # Use project from the configuration if not specified
        if not project:
            # For simplicity in this implementation, we'll require the project parameter
            # A more complete implementation might extract the first project from the filter
            raise ValueError(
                "Project parameter is required. If using a default project, "
                "implement a method to extract it from the config.projects_filter"
            )

        logger.debug(f"Getting pull request {pr_id} from {project}/{repository}")

        path = f"/projects/{project}/repos/{repository}/pull-requests/{pr_id}"
        response = self.client.get(path)

        return BitbucketServerPullRequest.from_raw(response)
