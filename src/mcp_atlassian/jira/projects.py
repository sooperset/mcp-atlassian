"""Module for Jira project operations."""

import logging
from typing import Any

from ..models import JiraIssue, JiraProject, JiraSearchResult
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class ProjectsMixin(JiraClient):
    """Mixin for Jira project operations.

    This mixin provides methods for retrieving and working with Jira projects,
    including project details, components, versions, and other project-related operations.
    """

    def get_all_projects(self, include_archived: bool = False) -> list[dict[str, Any]]:
        """
        Get all projects visible to the current user.

        Args:
            include_archived: Whether to include archived projects

        Returns:
            List of project data dictionaries
        """
        try:
            params = {}
            if include_archived:
                params["includeArchived"] = "true"

            projects = self.jira.projects(included_archived=include_archived)
            return projects if isinstance(projects, list) else []

        except Exception as e:
            logger.error(f"Error getting all projects: {str(e)}")
            return []

    def get_project(self, project_key: str) -> dict[str, Any] | None:
        """
        Get project information by key.

        Args:
            project_key: The project key (e.g. 'PROJ')

        Returns:
            Project data or None if not found
        """
        try:
            project_data = self.jira.project(project_key)
            return project_data
        except Exception as e:
            logger.warning(f"Error getting project {project_key}: {e}")
            return None

    def get_project_model(self, project_key: str) -> JiraProject | None:
        """
        Get project information as a JiraProject model.

        Args:
            project_key: The project key (e.g. 'PROJ')

        Returns:
            JiraProject model or None if not found
        """
        project_data = self.get_project(project_key)
        if not project_data:
            return None

        return JiraProject.from_api_response(project_data)

    def project_exists(self, project_key: str) -> bool:
        """
        Check if a project exists.

        Args:
            project_key: The project key to check

        Returns:
            True if the project exists, False otherwise
        """
        try:
            project = self.get_project(project_key)
            return project is not None

        except Exception:
            return False

    def get_project_components(self, project_key: str) -> list[dict[str, Any]]:
        """
        Get all components for a project.

        Args:
            project_key: The project key

        Returns:
            List of component data dictionaries
        """
        try:
            components = self.jira.get_project_components(key=project_key)
            return components if isinstance(components, list) else []

        except Exception as e:
            logger.error(
                f"Error getting components for project {project_key}: {str(e)}"
            )
            return []

    def get_project_versions(self, project_key: str) -> list[dict[str, Any]]:
        """
        Get all versions for a project.

        Args:
            project_key: The project key

        Returns:
            List of version data dictionaries
        """
        try:
            versions = self.jira.get_project_versions(key=project_key)
            return versions if isinstance(versions, list) else []

        except Exception as e:
            logger.error(f"Error getting versions for project {project_key}: {str(e)}")
            return []

    def get_project_roles(self, project_key: str) -> dict[str, Any]:
        """
        Get all roles for a project.

        Args:
            project_key: The project key

        Returns:
            Dictionary of role names mapped to role details
        """
        try:
            roles = self.jira.get_project_roles(project_key=project_key)
            return roles if isinstance(roles, dict) else {}

        except Exception as e:
            logger.error(f"Error getting roles for project {project_key}: {str(e)}")
            return {}

    def get_project_role_members(
        self, project_key: str, role_id: str
    ) -> list[dict[str, Any]]:
        """
        Get members assigned to a specific role in a project.

        Args:
            project_key: The project key
            role_id: The role ID

        Returns:
            List of role members
        """
        try:
            members = self.jira.get_project_actors_for_role_project(
                project_key=project_key, role_id=role_id
            )
            # Extract the actors from the response
            actors = []
            if isinstance(members, dict) and "actors" in members:
                actors = members.get("actors", [])
            return actors

        except Exception as e:
            logger.error(
                f"Error getting role members for project {project_key}, role {role_id}: {str(e)}"
            )
            return []

    def get_project_permission_scheme(self, project_key: str) -> dict[str, Any] | None:
        """
        Get the permission scheme for a project.

        Args:
            project_key: The project key

        Returns:
            Permission scheme data if found, None otherwise
        """
        try:
            scheme = self.jira.get_project_permission_scheme(
                project_id_or_key=project_key
            )
            return scheme

        except Exception as e:
            logger.error(
                f"Error getting permission scheme for project {project_key}: {str(e)}"
            )
            return None

    def get_project_notification_scheme(
        self, project_key: str
    ) -> dict[str, Any] | None:
        """
        Get the notification scheme for a project.

        Args:
            project_key: The project key

        Returns:
            Notification scheme data if found, None otherwise
        """
        try:
            scheme = self.jira.get_project_notification_scheme(
                project_id_or_key=project_key
            )
            return scheme

        except Exception as e:
            logger.error(
                f"Error getting notification scheme for project {project_key}: {str(e)}"
            )
            return None

    def get_project_issue_types(self, project_key: str) -> list[dict[str, Any]]:
        """
        Get all issue types available for a project.

        Args:
            project_key: The project key

        Returns:
            List of issue type data dictionaries
        """
        try:
            meta = self.jira.issue_createmeta(project=project_key)

            issue_types = []
            # Extract issue types from createmeta response
            if "projects" in meta and len(meta["projects"]) > 0:
                project_data = meta["projects"][0]
                if "issuetypes" in project_data:
                    issue_types = project_data["issuetypes"]

            return issue_types

        except Exception as e:
            logger.error(
                f"Error getting issue types for project {project_key}: {str(e)}"
            )
            return []

    def get_project_issues_count(self, project_key: str) -> int:
        """
        Get the total number of issues in a project.

        Args:
            project_key: The project key

        Returns:
            Count of issues in the project
        """
        try:
            # Use JQL to count issues in the project
            jql = f"project = {project_key}"
            result = self.jira.jql(jql=jql, fields=["key"], limit=1)

            # Extract total from the response
            total = 0
            if isinstance(result, dict) and "total" in result:
                total = result.get("total", 0)

            return total

        except Exception as e:
            logger.error(
                f"Error getting issue count for project {project_key}: {str(e)}"
            )
            return 0

    def get_project_issues(
        self, project_key: str, start: int = 0, limit: int = 50
    ) -> list[JiraIssue]:
        """
        Get issues for a specific project.

        Args:
            project_key: The project key
            start: Index of the first issue to return
            limit: Maximum number of issues to return

        Returns:
            List of JiraIssue models representing the issues
        """
        try:
            # Use JQL to get issues in the project
            jql = f"project = {project_key}"

            # Use search_issues if available (delegate to SearchMixin)
            if hasattr(self, "search_issues") and callable(self.search_issues):
                # This assumes search_issues returns JiraIssue objects already
                return self.search_issues(jql, start=start, limit=limit)

            # Fallback implementation if search_issues is not available
            result = self.jira.jql(jql=jql, fields="*all", start=start, limit=limit)

            issues = []
            if isinstance(result, dict) and "issues" in result:
                # Create a JiraSearchResult and extract the issues
                search_result = JiraSearchResult.from_api_response(result)
                issues = search_result.issues

            return issues

        except Exception as e:
            logger.error(f"Error getting issues for project {project_key}: {str(e)}")
            return []

    def get_project_keys(self) -> list[str]:
        """
        Get all project keys.

        Returns:
            List of project keys
        """
        try:
            projects = self.get_all_projects()
            return [project.get("key") for project in projects if "key" in project]

        except Exception as e:
            logger.error(f"Error getting project keys: {str(e)}")
            return []

    def get_project_leads(self) -> dict[str, str]:
        """
        Get all project leads mapped to their projects.

        Returns:
            Dictionary mapping project keys to lead usernames
        """
        try:
            projects = self.get_all_projects()
            leads = {}

            for project in projects:
                if "key" in project and "lead" in project:
                    key = project.get("key")
                    lead = project.get("lead", {})

                    # Handle different formats of lead information
                    lead_name = None
                    if isinstance(lead, dict):
                        lead_name = lead.get("name") or lead.get("displayName")
                    elif isinstance(lead, str):
                        lead_name = lead

                    if key and lead_name:
                        leads[key] = lead_name

            return leads

        except Exception as e:
            logger.error(f"Error getting project leads: {str(e)}")
            return {}

    def get_user_accessible_projects(self, username: str) -> list[dict[str, Any]]:
        """
        Get projects that a specific user can access.

        Args:
            username: The username to check access for

        Returns:
            List of accessible project data dictionaries
        """
        try:
            # This requires admin permissions
            # For non-admins, a different approach might be needed
            all_projects = self.get_all_projects()
            accessible_projects = []

            for project in all_projects:
                project_key = project.get("key")
                if not project_key:
                    continue

                try:
                    # Check if user has browse permission for this project
                    browse_users = (
                        self.jira.get_users_with_browse_permission_to_a_project(
                            username=username, project_key=project_key, limit=1
                        )
                    )

                    # If the user is in the list, they have access
                    user_has_access = False
                    if isinstance(browse_users, list):
                        for user in browse_users:
                            if isinstance(user, dict) and user.get("name") == username:
                                user_has_access = True
                                break

                    if user_has_access:
                        accessible_projects.append(project)

                except Exception:
                    # Skip projects that cause errors
                    continue

            return accessible_projects

        except Exception as e:
            logger.error(
                f"Error getting accessible projects for user {username}: {str(e)}"
            )
            return []
