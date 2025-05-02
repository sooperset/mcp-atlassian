"""Pull request activities operations for Bitbucket Server."""

import logging
from typing import Any

from .client import BitbucketServerClient

logger = logging.getLogger("mcp-atlassian.bitbucket_server")


class BitbucketServerActivities:
    """Bitbucket Server pull request activities operations."""

    def __init__(self, client: BitbucketServerClient) -> None:
        """Initialize Bitbucket Server pull request activities operations.

        Args:
            client: Bitbucket Server client
        """
        self.client = client

    def get_activities(
        self,
        repository: str,
        pr_id: int,
        project: str | None = None,
        start: int = 0,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Get activities for a pull request.

        Args:
            repository: Repository slug
            pr_id: Pull request ID
            project: Project key (can be omitted if provided in config)
            start: Starting index for pagination
            limit: Maximum number of activities to return

        Returns:
            Activities for the pull request

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

        logger.debug(f"Getting activities for PR {pr_id} from {project}/{repository}")

        path = (
            f"/projects/{project}/repos/{repository}/pull-requests/{pr_id}/activities"
        )
        params: dict[str, Any] = {"start": start, "limit": limit}

        response = self.client.get(path, params=params)

        return response

    def get_reviews(
        self,
        repository: str,
        pr_id: int,
        project: str | None = None,
        start: int = 0,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Get reviews for a pull request.

        Args:
            repository: Repository slug
            pr_id: Pull request ID
            project: Project key (can be omitted if provided in config)
            start: Starting index for pagination
            limit: Maximum number of reviews to return

        Returns:
            Reviews for the pull request

        Raises:
            BitbucketServerApiError: If the API request fails
            ValueError: If required parameters are missing
        """
        activities_data = self.get_activities(
            repository=repository,
            pr_id=pr_id,
            project=project,
            start=start,
            limit=limit,
        )

        # Filter activities for reviews
        reviews = [
            activity
            for activity in activities_data.get("values", [])
            if activity.get("action") in ["APPROVED", "REVIEWED"]
        ]

        return reviews
