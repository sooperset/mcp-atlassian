"""Module for Bitbucket project operations."""

import logging

from ..models.bitbucket.project import BitbucketProject
from .client import BitbucketClient

logger = logging.getLogger("mcp-bitbucket")


class ProjectsMixin(BitbucketClient):
    """Mixin for Bitbucket project operations.

    This mixin provides methods for retrieving and working with Bitbucket projects.
    Supports both Bitbucket Cloud and Server/Data Center.
    """

    def list_projects(
        self,
        workspace: str | None = None,
        limit: int = 100,
    ) -> list[BitbucketProject]:
        """
        List all projects accessible to the authenticated user.

        For Bitbucket Cloud: Lists projects in a workspace
        For Bitbucket Server: Lists all projects

        Args:
            workspace: Workspace slug (Cloud only, required for Cloud)
            limit: Maximum number of projects to return

        Returns:
            List of BitbucketProject objects

        Raises:
            ValueError: If workspace is not provided for Cloud instances
            requests.HTTPError: If the API request fails
        """
        try:
            if self.config.is_cloud:
                if not workspace:
                    error_msg = "workspace parameter is required for Bitbucket Cloud"
                    raise ValueError(error_msg)

                # Bitbucket Cloud API endpoint
                endpoint = f"/2.0/workspaces/{workspace}/projects"
                params = {"pagelen": min(limit, 100)}

                projects = []
                while len(projects) < limit:
                    response = self._get(endpoint, params=params)

                    if not isinstance(response, dict):
                        logger.error(f"Unexpected response type: {type(response)}")
                        break

                    values = response.get("values", [])
                    for project_data in values:
                        if len(projects) >= limit:
                            break
                        project = BitbucketProject.from_api_response(
                            project_data, is_cloud=True
                        )
                        projects.append(project)

                    # Check if there are more pages
                    next_url = response.get("next")
                    if not next_url or len(projects) >= limit:
                        break

                    # Extract the next page URL
                    endpoint = next_url.replace(self.config.url, "")

                return projects

            else:
                # Bitbucket Server/Data Center API endpoint
                endpoint = "/rest/api/1.0/projects"
                params = {"limit": min(limit, 1000)}

                projects = []
                start = 0
                while len(projects) < limit:
                    params["start"] = start
                    response = self._get(endpoint, params=params)

                    if not isinstance(response, dict):
                        logger.error(f"Unexpected response type: {type(response)}")
                        break

                    values = response.get("values", [])
                    for project_data in values:
                        if len(projects) >= limit:
                            break
                        project = BitbucketProject.from_api_response(
                            project_data, is_cloud=False
                        )
                        projects.append(project)

                    # Check if there are more pages
                    is_last_page = response.get("isLastPage", True)
                    if is_last_page or len(projects) >= limit:
                        break

                    # Move to next page
                    start = response.get("nextPageStart", start + len(values))

                return projects

        except Exception as e:
            logger.error(f"Error listing projects: {str(e)}")
            raise

    def get_project(
        self,
        project_key: str,
        workspace: str | None = None,
    ) -> BitbucketProject | None:
        """
        Get detailed information about a specific project.

        Args:
            project_key: The project key
            workspace: Workspace slug (Cloud only, required for Cloud)

        Returns:
            BitbucketProject object or None if not found

        Raises:
            ValueError: If workspace is not provided for Cloud instances
        """
        try:
            if self.config.is_cloud:
                if not workspace:
                    error_msg = "workspace parameter is required for Bitbucket Cloud"
                    raise ValueError(error_msg)

                endpoint = f"/2.0/workspaces/{workspace}/projects/{project_key}"
                project_data = self._get(endpoint)
                return BitbucketProject.from_api_response(project_data, is_cloud=True)

            else:
                endpoint = f"/rest/api/1.0/projects/{project_key}"
                project_data = self._get(endpoint)
                return BitbucketProject.from_api_response(project_data, is_cloud=False)

        except Exception as e:
            logger.error(f"Error getting project '{project_key}': {str(e)}")
            return None
