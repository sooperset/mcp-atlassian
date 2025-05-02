"""Module for Bitbucket Server file operations."""

import logging

from ..exceptions import BitbucketServerApiError
from .client import BitbucketServerClient

logger = logging.getLogger("mcp-atlassian.bitbucket_server")


class BitbucketServerFiles:
    """Class for Bitbucket Server file operations."""

    def __init__(self, client: BitbucketServerClient) -> None:
        """Initialize BitbucketServerFiles with a client.

        Args:
            client: BitbucketServerClient for API communication
        """
        self.client = client

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

        Raises:
            BitbucketServerApiError: If the API call fails
        """
        # Ensure we have a project key
        if not project:
            raise BitbucketServerApiError("Project key is required")

        # Prepare URL
        url = f"{self.client.root_url}/rest/api/1.0/projects/{project}/repos/{repository}/raw/{file_path}"

        # Add 'at' parameter for specific branch/commit if provided
        params = {"at": at} if at else None

        try:
            # Get raw file content - this endpoint returns content directly
            # rather than JSON, so we need to use a custom approach
            response = self.client.session.get(url, params=params)
            response.raise_for_status()

            # Return the raw text content
            return response.text
        except Exception as e:
            error_msg = f"Failed to get file content: {str(e)}"
            logger.error(error_msg)
            raise BitbucketServerApiError(error_msg) from e
