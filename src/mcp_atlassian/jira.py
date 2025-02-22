import logging
import os
from datetime import datetime
from typing import Any

from atlassian import Jira

from .config import JiraConfig
from .document_types import Document
from .preprocessing import TextPreprocessor

# Configure logging
logger = logging.getLogger("mcp-jira")


class JiraFetcher:
    """Handles fetching and parsing content from Jira."""

    def __init__(self):
        url = os.getenv("JIRA_URL")
        username = os.getenv("JIRA_USERNAME")
        token = os.getenv("JIRA_API_TOKEN")

        if not all([url, username, token]):
            raise ValueError("Missing required Jira environment variables")

        self.config = JiraConfig(url=url, username=username, api_token=token)
        self.jira = Jira(
            url=self.config.url,
            username=self.config.username,
            password=self.config.api_token,  # API token is used as password
            cloud=True,
        )
        self.preprocessor = TextPreprocessor(self.config.url)

    def _clean_text(self, text: str) -> str:
        """
        Clean text content by:
        1. Processing user mentions and links
        2. Converting HTML/wiki markup to markdown
        """
        if not text:
            return ""

        return self.preprocessor.clean_jira_text(text)

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str,
        description: str = "",
        **kwargs: Any,
    ) -> Document:
        """
        Create a new issue in Jira and return it as a Document.

        Args:
            project_key: The key of the project (e.g. 'PROJ')
            summary: Summary of the issue
            issue_type: Issue type (e.g. 'Task', 'Bug', 'Story')
            description: Issue description
            kwargs: Any other custom Jira fields

        Returns:
            Document representing the newly created issue
        """
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
            "description": description,
        }
        for key, value in kwargs.items():
            fields[key] = value

        try:
            created = self.jira.issue_create(fields=fields)
            issue_key = created.get("key")
            if not issue_key:
                raise ValueError(f"Failed to create issue in project {project_key}")

            return self.get_issue(issue_key)
        except Exception as e:
            logger.error(f"Error creating issue in project {project_key}: {str(e)}")
            raise

    def update_issue(self, issue_key: str, fields: dict[str, Any] = None, **kwargs: Any) -> Document:
        """
        Update an existing issue.

        Args:
            issue_key: The key of the issue (e.g. 'PROJ-123')
            fields: Dictionary of fields to update
            kwargs: Additional fields to update

        Returns:
            Document representing the updated issue
        """
        fields = fields or {}
        for k, v in kwargs.items():
            fields[k] = v

        try:
            self.jira.issue_update(issue_key, fields=fields)
            return self.get_issue(issue_key)
        except Exception as e:
            logger.error(f"Error updating issue {issue_key}: {str(e)}")
            raise

    def delete_issue(self, issue_key: str) -> bool:
        """
        Delete an existing issue.

        Args:
            issue_key: The key of the issue (e.g. 'PROJ-123')

        Returns:
            True if delete succeeded, otherwise raise an exception
        """
        try:
            self.jira.delete_issue(issue_key)
            return True
        except Exception as e:
            logger.error(f"Error deleting issue {issue_key}: {str(e)}")
            raise

    def _parse_date(self, date_str: str) -> str:
        """Parse date string to handle various ISO formats."""
        if not date_str:
            return ""

        # Handle various timezone formats
        if "+0000" in date_str:
            date_str = date_str.replace("+0000", "+00:00")
        elif "-0000" in date_str:
            date_str = date_str.replace("-0000", "+00:00")
        # Handle other timezone formats like +0900, -0500, etc.
        elif len(date_str) >= 5 and date_str[-5] in "+-" and date_str[-4:].isdigit():
            # Insert colon between hours and minutes of timezone
            date_str = date_str[:-2] + ":" + date_str[-2:]

        try:
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return date.strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning(f"Error parsing date {date_str}: {e}")
            return date_str

    def get_issue(self, issue_key: str, expand: str | None = None) -> Document:
        """
        Get a single issue with all its details.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            expand: Optional fields to expand

        Returns:
            Document containing issue content and metadata
        """
        try:
            issue = self.jira.issue(issue_key, expand=expand)

            # Process description and comments
            description = self._clean_text(issue["fields"].get("description", ""))

            # Get comments
            comments = []
            if "comment" in issue["fields"]:
                for comment in issue["fields"]["comment"]["comments"]:
                    processed_comment = self._clean_text(comment["body"])
                    created = self._parse_date(comment["created"])
                    author = comment["author"].get("displayName", "Unknown")
                    comments.append(
                        {
                            "body": processed_comment,
                            "created": created,
                            "author": author,
                        }
                    )

            # Format created date using new parser
            created_date = self._parse_date(issue["fields"]["created"])

            # Combine content in a more structured way
            content = f"""Issue: {issue_key}
Title: {issue['fields'].get('summary', '')}
Type: {issue['fields']['issuetype']['name']}
Status: {issue['fields']['status']['name']}
Created: {created_date}

Description:
{description}

Comments:
""" + "\n".join([f"{c['created']} - {c['author']}: {c['body']}" for c in comments])

            # Streamlined metadata with only essential information
            metadata = {
                "key": issue_key,
                "title": issue["fields"].get("summary", ""),
                "type": issue["fields"]["issuetype"]["name"],
                "status": issue["fields"]["status"]["name"],
                "created_date": created_date,
                "priority": issue["fields"].get("priority", {}).get("name", "None"),
                "link": f"{self.config.url.rstrip('/')}/browse/{issue_key}",
            }

            return Document(page_content=content, metadata=metadata)

        except Exception as e:
            logger.error(f"Error fetching issue {issue_key}: {str(e)}")
            raise

    def search_issues(
        self,
        jql: str,
        fields: str = "*all",
        start: int = 0,
        limit: int = 50,
        expand: str | None = None,
    ) -> list[Document]:
        """
        Search for issues using JQL.

        Args:
            jql: JQL query string
            fields: Comma-separated string of fields to return
            start: Starting index
            limit: Maximum results to return
            expand: Fields to expand

        Returns:
            List of Documents containing matching issues
        """
        try:
            results = self.jira.jql(jql, fields=fields, start=start, limit=limit, expand=expand)

            documents = []
            for issue in results["issues"]:
                # Get full issue details
                doc = self.get_issue(issue["key"], expand=expand)
                documents.append(doc)

            return documents

        except Exception as e:
            logger.error(f"Error searching issues with JQL {jql}: {str(e)}")
            raise

    def get_project_issues(self, project_key: str, start: int = 0, limit: int = 50) -> list[Document]:
        """
        Get all issues for a project.

        Args:
            project_key: The project key
            start: Starting index
            limit: Maximum results to return

        Returns:
            List of Documents containing project issues
        """
        jql = f"project = {project_key} ORDER BY created DESC"
        return self.search_issues(jql, start=start, limit=limit)
