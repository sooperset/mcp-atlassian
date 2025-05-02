"""Bitbucket Server integration for MCP Atlassian."""

import logging
from typing import Any

from ..models.bitbucket_server import (
    BitbucketServerComment,
    BitbucketServerPullRequest,
)
from .activities import BitbucketServerActivities
from .branches import BitbucketServerBranches
from .builds import BitbucketServerBuilds
from .client import BitbucketServerClient
from .comments import BitbucketServerComments
from .commits import BitbucketServerCommits
from .config import BitbucketServerConfig
from .diffs import BitbucketServerDiffs
from .files import BitbucketServerFiles
from .pull_requests import BitbucketServerPullRequests
from .search import BitbucketServerSearch

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
        self.search = BitbucketServerSearch(self.client, config)
        self.files = BitbucketServerFiles(self.client)
        self.branches = BitbucketServerBranches(self.client)
        self.builds = BitbucketServerBuilds(self.client)
        self.commits = BitbucketServerCommits(self.client)

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

    def search_code(
        self,
        query: str,
        project_key: str | None = None,
        repository_slug: str | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search code content in repositories.

        Args:
            query: The search query
            project_key: Project key to limit search to a specific project
            repository_slug: Repository slug to limit search to a specific repository
            page: Page number to start from (1-based indexing)
            limit: Maximum number of results to return per page

        Returns:
            Search results
        """
        return self.search.search_code(
            query=query,
            project_key=project_key,
            repository_slug=repository_slug,
            page=page,
            limit=limit,
        )

    def search_repositories(
        self,
        query: str,
        project_key: str | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search for repositories.

        Args:
            query: The search query
            project_key: Project key to limit search to a specific project
            page: Page number to start from (1-based indexing)
            limit: Maximum number of results to return per page

        Returns:
            Search results
        """
        return self.search.search_repositories(
            query=query,
            project_key=project_key,
            page=page,
            limit=limit,
        )

    def get_file_content(
        self,
        repository: str,
        file_path: str,
        project: str | None = None,
        at: str | None = None,
    ) -> str:
        """Get the content of a file from Bitbucket Server.

        Args:
            repository: Repository slug
            file_path: Path to the file within the repository
            project: Project key (optional if provided in config)
            at: Branch or commit to get the file from (optional, defaults to default branch)

        Returns:
            Raw content of the file as a string
        """
        return self.files.get_file_content(
            repository=repository,
            file_path=file_path,
            project=project,
            at=at,
        )

    def get_branches(
        self,
        repository: str,
        project: str | None = None,
        filter_text: str | None = None,
        start: int = 0,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Get branches for a repository.

        Args:
            repository: Repository slug
            project: Project key (can be omitted if provided in config)
            filter_text: Optional text to filter branches by name
            start: Starting index for pagination
            limit: Maximum number of branches to return

        Returns:
            Branch data
        """
        return self.branches.get_branches(
            repository=repository,
            project=project,
            filter_text=filter_text,
            start=start,
            limit=limit,
        )

    def get_branch_commits(
        self,
        repository: str,
        branch: str,
        project: str | None = None,
        start: int = 0,
        limit: int = 1,
    ) -> dict[str, Any]:
        """Get commits for a branch.

        Args:
            repository: Repository slug
            branch: Branch name or ref (e.g., 'master', 'develop', 'refs/heads/master')
            project: Project key (can be omitted if provided in config)
            start: Starting index for pagination
            limit: Maximum number of commits to return (default 1 for last commit)

        Returns:
            Commit data
        """
        return self.branches.get_branch_commits(
            repository=repository,
            branch=branch,
            project=project,
            start=start,
            limit=limit,
        )

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
        """
        return self.commits.get_commit(
            repository=repository, commit_id=commit_id, project=project
        )

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
        """
        return self.commits.get_commit_changes(
            repository=repository, commit_id=commit_id, project=project
        )

    def get_build_status(self, commit_id: str) -> dict[str, Any]:
        """Get build status for a commit.

        Args:
            commit_id: Commit ID (SHA)

        Returns:
            Build status data
        """
        return self.builds.get_build_status(commit_id=commit_id)

    def close(self) -> None:
        """Close the client connection."""
        self.client.close()


__all__ = ["BitbucketServerFetcher", "BitbucketServerConfig"]
