"""Build status operations for Bitbucket Server."""

import logging
from typing import Any

from .client import BitbucketServerClient

logger = logging.getLogger("mcp-atlassian.bitbucket_server")


class BitbucketServerBuilds:
    """Bitbucket Server build status operations."""

    def __init__(self, client: BitbucketServerClient) -> None:
        """Initialize Bitbucket Server build status operations.

        Args:
            client: Bitbucket Server client
        """
        self.client = client

    def get_build_status(self, commit_id: str) -> dict[str, Any]:
        """Get build status for a commit.

        Args:
            commit_id: Commit ID (SHA)

        Returns:
            Build status data

        Raises:
            BitbucketServerApiError: If the API request fails
        """
        logger.debug(f"Getting build status for commit {commit_id}")

        # This uses a special endpoint outside the normal API base path
        url = f"{self.client.root_url}/rest/build-status/1.0/commits/{commit_id}"

        try:
            # Using session.get directly since this is a non-standard endpoint
            response = self.client.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting build status for commit {commit_id}: {str(e)}")
            raise
