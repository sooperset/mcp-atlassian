"""Commit operations for Bitbucket Server."""

import logging
from typing import Any

from .client import BitbucketServerClient

logger = logging.getLogger("mcp-atlassian.bitbucket_server")


class BitbucketServerCommits:
    """Bitbucket Server commit operations."""

    def __init__(self, client: BitbucketServerClient) -> None:
        """Initialize Bitbucket Server commit operations.

        Args:
            client: Bitbucket Server client
        """
        self.client = client

    def get_commit(
        self, repository: str, commit_id: str, project: str | None = None
    ) -> dict[str, Any]:
        """Get a commit by ID.

        Args:
            repository: Repository slug
            commit_id: Commit ID (SHA)
            project: Project key (can be omitted if provided in config)

        Returns:
            Commit data

        Raises:
            BitbucketServerApiError: If the API request fails
            ValueError: If required parameters are missing
        """
        if not project:
            # For simplicity in this implementation, we'll require the project parameter
            raise ValueError(
                "Project parameter is required. If using a default project, "
                "implement a method to extract it from the config.projects_filter"
            )

        logger.debug(f"Getting commit {commit_id} from {project}/{repository}")

        path = f"/projects/{project}/repos/{repository}/commits/{commit_id}"
        response = self.client.get(path)

        return response

    def get_commit_changes(
        self, repository: str, commit_id: str, project: str | None = None
    ) -> dict[str, Any]:
        """Get the changes made in a commit.

        Args:
            repository: Repository slug
            commit_id: Commit ID (SHA)
            project: Project key (can be omitted if provided in config)

        Returns:
            Changes made in the commit

        Raises:
            BitbucketServerApiError: If the API request fails
            ValueError: If required parameters are missing
        """
        if not project:
            # For simplicity in this implementation, we'll require the project parameter
            raise ValueError(
                "Project parameter is required. If using a default project, "
                "implement a method to extract it from the config.projects_filter"
            )

        logger.debug(
            f"Getting changes for commit {commit_id} from {project}/{repository}"
        )

        path = f"/projects/{project}/repos/{repository}/commits/{commit_id}/changes"
        response = self.client.get(path)

        return response
