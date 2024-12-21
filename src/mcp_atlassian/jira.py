import logging
import os
from datetime import datetime
from typing import List, Optional

from atlassian import Jira
from dotenv import load_dotenv

from .config import JiraConfig
from .preprocessing import TextPreprocessor
from .types import Document

# Load environment variables
load_dotenv()

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

    def create_issue(self, project_key: str, fields: dict) -> Document:
        """
        Create a new Jira issue.

        Args:
            fields: Dictionary of fields to create the issue. It must adhere with Jira API documentation.

        Returns:
            Document containing created issue content and metadata
        """
        try:
            fields["project"] = {"key": project_key}
            issue = self.jira.create_issue(fields)
            return self.get_issue(issue["key"])
        except Exception as e:
            logger.error(f"Error creating issue: {e}")
            raise

    def update_issue(self, issue_key: str, fields: dict) -> Document:
        """
        Update an existing Jira issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            fields: Dictionary of fields to update. Examples:
                   {
                       'summary': 'New title',
                       'description': 'New description',
                       'assignee': {'name': 'username'},
                       'priority': {'name': 'High'}
                   }

        Returns:
            Document containing updated issue content
        """
        try:
            # Update the issue
            self.jira.update_issue_field(issue_key, fields)

            # Fetch and return the updated issue
            return self.get_issue(issue_key)

        except Exception as e:
            logger.error(f"Error updating issue {issue_key}: {str(e)}")
            raise

    def get_issue(self, issue_key: str, expand: Optional[str] = None) -> Document:
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
                    created = datetime.fromisoformat(comment["created"].replace("Z", "+00:00"))
                    author = comment["author"].get("displayName", "Unknown")
                    comments.append(
                        {"body": processed_comment, "created": created.strftime("%Y-%m-%d"), "author": author}
                    )

            # Format created date
            created_date = datetime.fromisoformat(issue["fields"]["created"].replace("Z", "+00:00"))
            formatted_created = created_date.strftime("%Y-%m-%d")

            # Combine content in a more structured way
            content = f"""Issue: {issue_key}
Title: {issue['fields'].get('summary', '')}
Type: {issue['fields']['issuetype']['name']}
Status: {issue['fields']['status']['name']}
Created: {formatted_created}

Description:
{description}

Comments:
""" + "\n".join(
                [f"{c['created']} - {c['author']}: {c['body']}" for c in comments]
            )

            # Streamlined metadata with only essential information
            metadata = {
                "key": issue_key,
                "title": issue["fields"].get("summary", ""),
                "type": issue["fields"]["issuetype"]["name"],
                "status": issue["fields"]["status"]["name"],
                "created_date": formatted_created,
                "priority": issue["fields"].get("priority", {}).get("name", "None"),
                "link": f"{self.config.url.rstrip('/')}/browse/{issue_key}",
            }

            return Document(page_content=content, metadata=metadata)

        except Exception as e:
            logger.error(f"Error fetching issue {issue_key}: {str(e)}")
            raise

    def search_issues(
        self, jql: str, fields: str = "*all", start: int = 0, limit: int = 50, expand: Optional[str] = None
    ) -> List[Document]:
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

    def get_project_issues(self, project_key: str, start: int = 0, limit: int = 50) -> List[Document]:
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
