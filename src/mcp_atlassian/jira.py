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

    def _get_account_id(self, assignee: str) -> str:
        """
        Get account ID from email or full name.

        Args:
            assignee: Email, full name, or account ID of the user

        Returns:
            Account ID of the user

        Raises:
            ValueError: If user cannot be found
        """
        # If it looks like an account ID (alphanumeric with hyphens), return as is
        if assignee and assignee.replace("-", "").isalnum():
            logger.info(f"Using '{assignee}' as account ID")
            return assignee

        try:
            # First try direct user lookup
            try:
                users = self.jira.user_find_by_user_string(query=assignee)
                if users:
                    if len(users) > 1:
                        # Log all found users for debugging
                        user_details = [f"{u.get('displayName')} ({u.get('emailAddress')})" for u in users]
                        logger.warning(
                            f"Multiple users found for '{assignee}', using first match. "
                            f"Found users: {', '.join(user_details)}"
                        )

                    user = users[0]
                    account_id = user.get("accountId")
                    if account_id and isinstance(account_id, str):
                        logger.info(
                            f"Found account ID via direct lookup: {account_id} "
                            f"({user.get('displayName')} - {user.get('emailAddress')})"
                        )
                        return str(account_id)  # Explicit str conversion
                    logger.warning(f"Direct user lookup failed for '{assignee}': user found but no account ID present")
                else:
                    logger.warning(f"Direct user lookup failed for '{assignee}': no users found")
            except Exception as e:
                logger.warning(f"Direct user lookup failed for '{assignee}': {str(e)}")

            # Fall back to project permission based search
            users = self.jira.get_users_with_browse_permission_to_a_project(username=assignee)
            if not users:
                logger.warning(f"No user found matching '{assignee}'")
                raise ValueError(f"No user found matching '{assignee}'")

            # Return the first matching user's account ID
            account_id = users[0].get("accountId")
            if not account_id or not isinstance(account_id, str):
                logger.warning(f"Found user '{assignee}' but no account ID was returned")
                raise ValueError(f"Found user '{assignee}' but no account ID was returned")

            logger.info(f"Found account ID via browse permission lookup: {account_id}")
            return str(account_id)  # Explicit str conversion
        except Exception as e:
            logger.error(f"Error finding user '{assignee}': {str(e)}")
            raise ValueError(f"Could not resolve account ID for '{assignee}'") from e

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str,
        description: str = "",
        assignee: str | None = None,
        **kwargs: Any,
    ) -> Document:
        """
        Create a new issue in Jira and return it as a Document.

        Args:
            project_key: The key of the project (e.g. 'PROJ')
            summary: Summary of the issue
            issue_type: Issue type (e.g. 'Task', 'Bug', 'Story')
            description: Issue description
            assignee: Email, full name, or account ID of the user to assign the issue to
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

        # Add assignee if provided
        if assignee:
            account_id = self._get_account_id(assignee)
            fields["assignee"] = {"accountId": account_id}

        # Remove assignee from additional_fields if present to avoid conflicts
        if "assignee" in kwargs:
            logger.warning(
                "Assignee found in additional_fields - this will be ignored. Please use the assignee parameter instead."
            )
            kwargs.pop("assignee")

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

        # Handle assignee if provided in fields
        if "assignee" in fields:
            assignee = fields.pop("assignee")  # Remove from fields to handle separately
            if assignee:
                account_id = self._get_account_id(assignee)
                fields["assignee"] = {"accountId": account_id}
            else:
                fields["assignee"] = None  # Unassign the issue

        for k, v in kwargs.items():
            fields[k] = v

        try:
            self.jira.issue_update(issue_key, fields=fields)
            return self.get_issue(issue_key)
        except Exception as e:
            logger.error(f"Error updating issue {issue_key}: {str(e)}")
            raise

    def link_issue_to_epic(self, issue_key: str, epic_key: str) -> Document:
        """
        Link an existing issue to an epic.
        
        Args:
            issue_key: The key of the issue to link (e.g. 'PROJ-123')
            epic_key: The key of the epic to link to (e.g. 'PROJ-456')
            
        Returns:
            Document representing the updated issue
        """
        try:
            # First, check if the epic exists and is an Epic type
            epic = self.jira.issue(epic_key)
            if epic["fields"]["issuetype"]["name"] != "Epic":
                raise ValueError(f"Issue {epic_key} is not an Epic, it is a {epic['fields']['issuetype']['name']}")
                
            # Different Jira configurations use different field names for epic links
            # Try the parent field first (most common)
            try:
                fields = {"parent": {"key": epic_key}}
                self.jira.issue_update(issue_key, fields=fields)
                return self.get_issue(issue_key)
            except Exception as e:
                logger.info(f"Couldn't link using parent field: {str(e)}. Trying custom fields...")
            
            # Try common custom fields for epic links
            custom_field_attempts = [
                {"customfield_10014": epic_key},  # Common in Jira Cloud
                {"customfield_10000": epic_key},  # Common in Jira Server
                {"epic_link": epic_key}           # Sometimes used 
            ]
            
            for fields in custom_field_attempts:
                try:
                    self.jira.issue_update(issue_key, fields=fields)
                    return self.get_issue(issue_key)
                except Exception as e:
                    logger.info(f"Couldn't link using fields {fields}: {str(e)}")
                    continue
                    
            # If we get here, none of our attempts worked
            raise ValueError(f"Could not link issue {issue_key} to epic {epic_key}. Your Jira instance might use a different field for epic links.")
            
        except Exception as e:
            logger.error(f"Error linking issue {issue_key} to epic {epic_key}: {str(e)}")
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

    def get_issue(self, issue_key: str, expand: str | None = None, comment_limit: int | None = None) -> Document:
        """
        Get a single issue with all its details.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            expand: Optional fields to expand
            comment_limit: Maximum number of comments to include (None for no comments)

        Returns:
            Document containing issue content and metadata
        """
        try:
            issue = self.jira.issue(issue_key, expand=expand)

            # Process description and comments
            description = self._clean_text(issue["fields"].get("description", ""))

            # Get comments if limit is specified
            comments = []
            if comment_limit is not None and comment_limit > 0:
                comments = self.get_issue_comments(issue_key, limit=comment_limit)

            # Format created date using new parser
            created_date = self._parse_date(issue["fields"]["created"])

            # Check for Epic information
            epic_key = None
            epic_name = None
            
            # Most Jira instances use the "parent" field for Epic relationships
            if "parent" in issue["fields"] and issue["fields"]["parent"]:
                epic_key = issue["fields"]["parent"]["key"]
                epic_name = issue["fields"]["parent"]["fields"]["summary"]
            
            # Some Jira instances use custom fields for Epic links
            # Common custom field names for Epic links
            epic_field_names = ["customfield_10014", "customfield_10000", "epic_link"]
            for field_name in epic_field_names:
                if field_name in issue["fields"] and issue["fields"][field_name]:
                    # If it's a string, assume it's the epic key
                    if isinstance(issue["fields"][field_name], str):
                        epic_key = issue["fields"][field_name]
                    # If it's an object, extract the key
                    elif isinstance(issue["fields"][field_name], dict) and "key" in issue["fields"][field_name]:
                        epic_key = issue["fields"][field_name]["key"]
            
            # Combine content in a more structured way
            content = f"""Issue: {issue_key}
Title: {issue['fields'].get('summary', '')}
Type: {issue['fields']['issuetype']['name']}
Status: {issue['fields']['status']['name']}
Created: {created_date}
"""
            
            # Add Epic information if available
            if epic_key:
                content += f"Epic: {epic_key}"
                if epic_name:
                    content += f" - {epic_name}"
                content += "\n"
                
            content += f"""
Description:
{description}
"""
            if comments:
                content += "\nComments:\n" + "\n".join(
                    [f"{c['created']} - {c['author']}: {c['body']}" for c in comments]
                )

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
            
            # Add Epic information to metadata
            if epic_key:
                metadata["epic_key"] = epic_key
                if epic_name:
                    metadata["epic_name"] = epic_name
                    
            if comments:
                metadata["comments"] = comments

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
        Search for issues using JQL (Jira Query Language).

        Args:
            jql: JQL query string
            fields: Fields to return (comma-separated string or "*all")
            start: Starting index
            limit: Maximum issues to return
            expand: Optional items to expand (comma-separated)

        Returns:
            List of Documents representing the search results
        """
        try:
            issues = self.jira.jql(jql, fields=fields, start=start, limit=limit, expand=expand)
            documents = []

            for issue in issues.get("issues", []):
                issue_key = issue["key"]
                summary = issue["fields"].get("summary", "")
                issue_type = issue["fields"]["issuetype"]["name"]
                status = issue["fields"]["status"]["name"]
                desc = self._clean_text(issue["fields"].get("description", ""))
                created_date = self._parse_date(issue["fields"]["created"])
                priority = issue["fields"].get("priority", {}).get("name", "None")

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
            raise
            
    def get_epic_issues(self, epic_key: str, limit: int = 50) -> list[Document]:
        """
        Get all issues linked to a specific epic.
        
        Args:
            epic_key: The key of the epic (e.g. 'PROJ-123')
            limit: Maximum number of issues to return
            
        Returns:
            List of Documents representing the issues linked to the epic
        """
        try:
            # First, check if the issue is an Epic
            epic = self.jira.issue(epic_key)
            if epic["fields"]["issuetype"]["name"] != "Epic":
                raise ValueError(f"Issue {epic_key} is not an Epic, it is a {epic['fields']['issuetype']['name']}")
            
            # Try different JQL queries that might work depending on the Jira configuration
            jql_queries = [
                f"parent = {epic_key}",                # Most common
                f"'Epic Link' = {epic_key}",           # Some instances
                f"'Epic' = {epic_key}",                # Some instances
                f"issue in childIssuesOf('{epic_key}')" # Some instances
            ]
            
            # Try each query until we get results or run out of options
            documents = []
            for jql in jql_queries:
                try:
                    logger.info(f"Trying to get epic issues with JQL: {jql}")
                    documents = self.search_issues(jql, limit=limit)
                    if documents:
                        return documents
                except Exception as e:
                    logger.info(f"Failed to get epic issues with JQL '{jql}': {str(e)}")
                    continue
            
            # If we've tried all queries and got no results, return an empty list
            # but also log a warning that we might be missing the right field
            if not documents:
                logger.warning(f"Couldn't find issues linked to epic {epic_key}. Your Jira instance might use a different field for epic links.")
                
            return documents
                
        except Exception as e:
            logger.error(f"Error getting issues for epic {epic_key}: {str(e)}")
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

    def get_current_user_account_id(self) -> str:
        """
        Get the account ID of the current user.

        Returns:
            The account ID string of the current user

        Raises:
            ValueError: If unable to get the current user's account ID
        """
        try:
            myself = self.jira.myself()
            account_id: str | None = myself.get("accountId")
            if not account_id:
                raise ValueError("Unable to get account ID from user profile")
            return account_id
        except Exception as e:
            logger.error(f"Error getting current user account ID: {str(e)}")
            raise ValueError(f"Failed to get current user account ID: {str(e)}")

    def get_issue_comments(self, issue_key: str, limit: int = 50) -> list[dict]:
        """
        Get comments for a specific issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            limit: Maximum number of comments to return

        Returns:
            List of comments with author, creation date, and content
        """
        try:
            comments = self.jira.issue_get_comments(issue_key)
            processed_comments = []

            for comment in comments.get("comments", [])[:limit]:
                processed_comment = {
                    "id": comment.get("id"),
                    "body": self._clean_text(comment.get("body", "")),
                    "created": self._parse_date(comment.get("created")),
                    "updated": self._parse_date(comment.get("updated")),
                    "author": comment.get("author", {}).get("displayName", "Unknown"),
                }
                processed_comments.append(processed_comment)

            return processed_comments
        except Exception as e:
            logger.error(f"Error getting comments for issue {issue_key}: {str(e)}")
            raise

    def add_comment(self, issue_key: str, comment: str) -> dict:
        """
        Add a comment to an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            comment: Comment text to add

        Returns:
            The created comment details
        """
        try:
            result = self.jira.issue_add_comment(issue_key, comment)
            return {
                "id": result.get("id"),
                "body": self._clean_text(result.get("body", "")),
                "created": self._parse_date(result.get("created")),
                "author": result.get("author", {}).get("displayName", "Unknown"),
            }
        except Exception as e:
            logger.error(f"Error adding comment to issue {issue_key}: {str(e)}")
            raise
