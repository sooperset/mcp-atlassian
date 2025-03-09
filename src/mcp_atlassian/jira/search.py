"""Module for Jira search operations."""

import logging

from ..document_types import Document
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class SearchMixin(JiraClient):
    """Mixin for Jira search operations."""

    def search_issues(
        self,
        jql: str,
        fields: str = "*all",
        start: int = 0,
        limit: int = 50,
        expand: str | None = None,
    ) -> list[Document]:
        """
        Search for issues using JQL (Jira Query Language).

        Args:
            jql: JQL query string
            fields: Fields to return (comma-separated string or "*all")
            start: Starting index
            limit: Maximum issues to return
            expand: Optional items to expand (comma-separated)

        Returns:
            List of Documents representing the search results

        Raises:
            Exception: If there is an error searching for issues
        """
        try:
            issues = self.jira.jql(
                jql, fields=fields, start=start, limit=limit, expand=expand
            )
            documents = []

            for issue in issues.get("issues", []):
                issue_key = issue["key"]
                fields_data = issue.get("fields", {})

                # Safely handle fields that might not be included in the response
                summary = fields_data.get("summary", "")

                # Handle issuetype field with fallback to "Unknown" if missing
                issue_type = "Unknown"
                issuetype_data = fields_data.get("issuetype")
                if issuetype_data is not None:
                    issue_type = issuetype_data.get("name", "Unknown")

                # Handle status field with fallback to "Unknown" if missing
                status = "Unknown"
                status_data = fields_data.get("status")
                if status_data is not None:
                    status = status_data.get("name", "Unknown")

                # Process description field
                description = fields_data.get("description")
                desc = self._clean_text(description) if description is not None else ""

                # Process created date field
                created_date = ""
                created = fields_data.get("created")
                if created is not None:
                    created_date = self._parse_date(created)

                # Process priority field
                priority = "None"
                priority_data = fields_data.get("priority")
                if priority_data is not None:
                    priority = priority_data.get("name", "None")

                # Add basic metadata
                metadata = {
                    "key": issue_key,
                    "title": summary,
                    "type": issue_type,
                    "status": status,
                    "created_date": created_date,
                    "priority": priority,
                    "link": f"{self.config.url.rstrip('/')}/browse/{issue_key}",
                }

                # Prepare content
                content = desc if desc else f"{summary} [{status}]"

                documents.append(Document(page_content=content, metadata=metadata))

            return documents
        except Exception as e:
            logger.error(f"Error searching issues with JQL '{jql}': {str(e)}")
            raise Exception(f"Error searching issues: {str(e)}") from e

    def get_project_issues(
        self, project_key: str, start: int = 0, limit: int = 50
    ) -> list[Document]:
        """
        Get all issues for a project.

        Args:
            project_key: The project key
            start: Starting index
            limit: Maximum results to return

        Returns:
            List of Documents containing project issues

        Raises:
            Exception: If there is an error getting project issues
        """
        jql = f"project = {project_key} ORDER BY created DESC"
        return self.search_issues(jql, start=start, limit=limit)

    def get_epic_issues(self, epic_key: str, limit: int = 50) -> list[Document]:
        """
        Get all issues linked to a specific epic.

        Args:
            epic_key: The key of the epic (e.g. 'PROJ-123')
            limit: Maximum number of issues to return

        Returns:
            List of Documents representing the issues linked to the epic

        Raises:
            ValueError: If the issue is not an Epic
            Exception: If there is an error getting epic issues
        """
        try:
            # First, check if the issue is an Epic
            epic = self.jira.issue(epic_key)
            fields_data = epic.get("fields", {})

            # Safely check if the issue is an Epic
            issue_type = None
            issuetype_data = fields_data.get("issuetype")
            if issuetype_data is not None:
                issue_type = issuetype_data.get("name", "")

            if issue_type != "Epic":
                error_msg = (
                    f"Issue {epic_key} is not an Epic, it is a "
                    f"{issue_type or 'unknown type'}"
                )
                raise ValueError(error_msg)

            # Get the dynamic field IDs for this Jira instance
            if hasattr(self, "get_jira_field_ids"):
                field_ids = self.get_jira_field_ids()
            else:
                # Fallback for when we're not using IssuesMixin
                field_ids = {}

            # Build JQL queries based on discovered field IDs
            jql_queries = []

            # Add queries based on discovered fields
            if "parent" in field_ids:
                jql_queries.append(f"parent = {epic_key}")

            if "epic_link" in field_ids:
                field_name = field_ids["epic_link"]
                jql_queries.append(f'"{field_name}" = {epic_key}')
                jql_queries.append(f'"{field_name}" ~ {epic_key}')

            # Add standard fallback queries
            jql_queries.extend(
                [
                    f"parent = {epic_key}",  # Common in most instances
                    f"'Epic Link' = {epic_key}",  # Some instances
                    f"'Epic' = {epic_key}",  # Some instances
                    f"issue in childIssuesOf('{epic_key}')",  # Some instances
                ]
            )

            # Try each query until we get results or run out of options
            documents = []
            for jql in jql_queries:
                try:
                    logger.info(f"Trying to get epic issues with JQL: {jql}")
                    documents = self.search_issues(jql, limit=limit)
                    if documents:
                        return documents
                except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
                    logger.info(f"Failed to get epic issues with JQL '{jql}': {str(e)}")
                    continue

            # If we've tried all queries and got no results, return an empty list
            # but also log a warning that we might be missing the right field
            if not documents:
                logger.warning(
                    f"Couldn't find issues linked to epic {epic_key}. "
                    "Your Jira instance might use a different field for epic links."
                )

            return documents

        except ValueError:
            # Re-raise ValueError for non-epic issues
            raise

        except Exception as e:
            logger.error(f"Error getting issues for epic {epic_key}: {str(e)}")
            raise Exception(f"Error getting epic issues: {str(e)}") from e

    def _parse_date(self, date_str: str) -> str:
        """
        Parse a date string from ISO format to a more readable format.

        This method is included in the SearchMixin for independence from other mixins,
        but will use the implementation from IssuesMixin if available.

        Args:
            date_str: Date string in ISO format

        Returns:
            Formatted date string
        """
        # If we're also using IssuesMixin, use its implementation
        if (
            hasattr(self, "_parse_date")
            and self.__class__._parse_date is not SearchMixin._parse_date
        ):
            # This avoids infinite recursion by checking that the method is different
            return super()._parse_date(date_str)

        # Fallback implementation
        try:
            from datetime import datetime

            date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return date_obj.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return date_str
