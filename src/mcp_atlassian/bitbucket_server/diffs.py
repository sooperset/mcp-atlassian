"""Pull request diff operations for Bitbucket Server."""

import logging
from typing import Any

from .client import BitbucketServerClient

logger = logging.getLogger("mcp-atlassian.bitbucket_server")


class BitbucketServerDiffs:
    """Bitbucket Server pull request diff operations."""

    def __init__(self, client: BitbucketServerClient) -> None:
        """Initialize Bitbucket Server pull request diff operations.

        Args:
            client: Bitbucket Server client
        """
        self.client = client

    def get_diff(
        self,
        repository: str,
        pr_id: int,
        project: str | None = None,
        context_lines: int = 10,
        since_revision: str | None = None,
        whitespace: bool = False,
    ) -> dict[str, Any]:
        """Get diff for a pull request.

        Args:
            repository: Repository slug
            pr_id: Pull request ID
            project: Project key (can be omitted if provided in config)
            context_lines: Number of context lines to include in the diff (default 10)
            since_revision: Only show changes since this revision
            whitespace: Ignore whitespace changes

        Returns:
            Raw diff data

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

        logger.debug(f"Getting diff for PR {pr_id} from {project}/{repository}")

        path = f"/projects/{project}/repos/{repository}/pull-requests/{pr_id}/diff"
        params: dict[str, Any] = {"contextLines": context_lines}

        if since_revision is not None:
            params["since"] = since_revision

        if whitespace:
            params["whitespace"] = "ignore-all"

        response = self.client.get(path, params=params)

        return response
