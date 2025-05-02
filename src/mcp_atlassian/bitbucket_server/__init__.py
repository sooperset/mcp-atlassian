"""Bitbucket Server integration for MCP Atlassian."""

import logging
from typing import Any

from ..models.bitbucket_server import (
    BitbucketServerComment,
    BitbucketServerPullRequest,
)
from .activities import BitbucketServerActivities
from .client import BitbucketServerClient
from .comments import BitbucketServerComments
from .config import BitbucketServerConfig
from .diffs import BitbucketServerDiffs
from .pull_requests import BitbucketServerPullRequests

logger = logging.getLogger("mcp-atlassian.bitbucket_server")


class BitbucketServerFetcher:
    """Main interface for Bitbucket Server operations."""

    def __init__(self, config: BitbucketServerConfig) -> None:
        """Initialize Bitbucket Server fetcher.

        Args:
            config: Bitbucket Server configuration
        """
        self.config = config
        self.client = BitbucketServerClient(config)
        self.pull_requests = BitbucketServerPullRequests(self.client)
        self.comments = BitbucketServerComments(self.client)
        self.diffs = BitbucketServerDiffs(self.client)
        self.activities = BitbucketServerActivities(self.client)

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
        """
        return self.pull_requests.get_pull_request(
            repository=repository, pr_id=pr_id, project=project
        )

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
        """
        return self.comments.add_comment(
            repository=repository,
            pr_id=pr_id,
            text=text,
            project=project,
            parent_id=parent_id,
        )

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
        """
        return self.diffs.get_diff(
            repository=repository,
            pr_id=pr_id,
            project=project,
            context_lines=context_lines,
            since_revision=since_revision,
            whitespace=whitespace,
        )

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
        """
        return self.activities.get_reviews(
            repository=repository,
            pr_id=pr_id,
            project=project,
            start=start,
            limit=limit,
        )

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
        """
        return self.activities.get_activities(
            repository=repository,
            pr_id=pr_id,
            project=project,
            start=start,
            limit=limit,
        )

    def close(self) -> None:
        """Close the client connection."""
        self.client.close()


__all__ = ["BitbucketServerFetcher", "BitbucketServerConfig"]
