"""Pull request comment operations for Bitbucket Server."""

import logging
from typing import Any

from ..models.bitbucket_server import BitbucketServerComment
from .client import BitbucketServerClient

logger = logging.getLogger("mcp-atlassian.bitbucket_server")


class BitbucketServerComments:
    """Bitbucket Server pull request comment operations."""

    def __init__(self, client: BitbucketServerClient) -> None:
        """Initialize Bitbucket Server pull request comment operations.

        Args:
            client: Bitbucket Server client
        """
        self.client = client

    def add_comment(
        self,
        repository: str,
        pr_id: int,
        text: str,
        project: str | None = None,
        parent_id: int | None = None,
    ) -> BitbucketServerComment:
        """Add a comment to a pull request.

        Args:
            repository: Repository slug
            pr_id: Pull request ID
            text: Comment text
            project: Project key (can be omitted if provided in config)
            parent_id: ID of the parent comment (for replies)

        Returns:
            Created comment

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

        logger.debug(f"Adding comment to PR {pr_id} in {project}/{repository}")

        path = f"/projects/{project}/repos/{repository}/pull-requests/{pr_id}/comments"

        # Prepare request body
        body: dict[str, Any] = {"text": text}

        # Add parent comment if specified
        if parent_id is not None:
            body["parent"] = {"id": parent_id}

        response = self.client.post(path, json=body)

        return BitbucketServerComment.from_raw(response)
