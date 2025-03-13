"""Module for Jira content formatting utilities."""

import html
import logging
import re
from datetime import datetime
from typing import Any

from ..preprocessing.jira import JiraPreprocessor
from .client import JiraClient
from .utils import parse_date_human_readable

logger = logging.getLogger("mcp-jira")


class FormattingMixin(JiraClient):
    """Mixin for Jira content formatting operations.

    This mixin provides utilities for converting between different formats,
    formatting issue content for display, parsing dates, and sanitizing content.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the FormattingMixin.

        Args:
            *args: Positional arguments for the JiraClient
            **kwargs: Keyword arguments for the JiraClient
        """
        super().__init__(*args, **kwargs)

        # Use the JiraPreprocessor with the base URL from the client
        base_url = ""
        if hasattr(self, "config") and hasattr(self.config, "url"):
            base_url = self.config.url
        self.preprocessor = JiraPreprocessor(base_url=base_url)

    def markdown_to_jira(self, markdown_text: str) -> str:
        """
        Convert Markdown syntax to Jira markup syntax.

        This method uses the TextPreprocessor implementation for consistent
        conversion between Markdown and Jira markup.

        Args:
            markdown_text: Text in Markdown format

        Returns:
            Text in Jira markup format
        """
        if not markdown_text:
            return ""

        try:
            # Use the existing preprocessor
            return self.preprocessor.markdown_to_jira(markdown_text)

        except Exception as e:
            logger.warning(f"Error converting markdown to Jira format: {str(e)}")
            # Return the original text if conversion fails
            return markdown_text

    def format_issue_content(
        self,
        issue_key: str,
        issue: dict[str, Any],
        description: str,
        comments: list[dict[str, Any]],
        created_date: str,
        epic_info: dict[str, str | None],
    ) -> str:
        """
        Format the issue content for display.

        Args:
            issue_key: The issue key
            issue: The issue data from Jira
            description: Processed description text
            comments: List of comment dictionaries
            created_date: Formatted created date
            epic_info: Dictionary with epic_key and epic_name

        Returns:
            Formatted content string
        """
        # Basic issue information
        content = f"""Issue: {issue_key}
Title: {issue["fields"].get("summary", "")}
Type: {issue["fields"]["issuetype"]["name"]}
Status: {issue["fields"]["status"]["name"]}
Created: {created_date}
"""

        # Add Epic information if available
        if epic_info.get("epic_key"):
            content += f"Epic: {epic_info['epic_key']}"
            if epic_info.get("epic_name"):
                content += f" - {epic_info['epic_name']}"
            content += "\n"

        content += f"""
Description:
{description}
"""
        # Add comments if present
        if comments:
            content += "\nComments:\n" + "\n".join(
                [f"{c['created']} - {c['author']}: {c['body']}" for c in comments]
            )

        return content

    def create_issue_metadata(
        self,
        issue_key: str,
        issue: dict[str, Any],
        comments: list[dict[str, Any]],
        created_date: str,
        epic_info: dict[str, str | None],
    ) -> dict[str, Any]:
        """
        Create metadata for the issue document.

        Args:
            issue_key: The issue key
            issue: The issue data from Jira
            comments: List of comment dictionaries
            created_date: Formatted created date
            epic_info: Dictionary with epic_key and epic_name

        Returns:
            Metadata dictionary
        """
        # Extract fields
        fields = issue.get("fields", {})

        # Basic metadata
        metadata = {
            "key": issue_key,
            "summary": fields.get("summary", ""),
            "type": fields.get("issuetype", {}).get("name", ""),
            "status": fields.get("status", {}).get("name", ""),
            "created": created_date,
            "source": "jira",
        }

        # Add assignee if present
        if fields.get("assignee"):
            metadata["assignee"] = fields["assignee"].get(
                "displayName", fields["assignee"].get("name", "")
            )

        # Add reporter if present
        if fields.get("reporter"):
            metadata["reporter"] = fields["reporter"].get(
                "displayName", fields["reporter"].get("name", "")
            )

        # Add priority if present
        if fields.get("priority"):
            metadata["priority"] = fields["priority"].get("name", "")

        # Add Epic information to metadata if available
        if epic_info.get("epic_key"):
            metadata["epic_key"] = epic_info["epic_key"]
            if epic_info.get("epic_name"):
                metadata["epic_name"] = epic_info["epic_name"]

        # Add project information
        if fields.get("project"):
            metadata["project"] = fields["project"].get("key", "")
            metadata["project_name"] = fields["project"].get("name", "")

        # Add comment count
        metadata["comment_count"] = len(comments)

        return metadata

    def format_date(self, date_str: str) -> str:
        """
        Parse a date string from ISO format to a more readable format.

        Args:
            date_str: Date string in ISO format

        Returns:
            Formatted date string
        """
        try:
            # Handle ISO format with timezone
            date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return date_obj.strftime("%Y-%m-%d %H:%M:%S")

        except Exception as e:
            logger.warning(f"Invalid date format for {date_str}: {e}")
            return date_str

    def format_jira_date(self, date_str: str | None) -> str:
        """
        Parse a date string from ISO format to a more readable format.

        Args:
            date_str: Date string in ISO format or None

        Returns:
            Formatted date string or empty string if date_str is None
        """
        if not date_str:
            return ""

        try:
            # Handle ISO format with timezone
            date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return date_obj.strftime("%Y-%m-%d %H:%M:%S")

        except Exception as e:
            logger.warning(f"Invalid date format for {date_str}: {e}")
            return date_str or ""

    def parse_date_for_api(self, date_str: str) -> str:
        """
        Parse a date string into a consistent format (YYYY-MM-DD).

        Args:
            date_str: Date string in various formats

        Returns:
            Formatted date string
        """
        try:
            # Handle various formats of date strings from Jira
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return date.strftime("%Y-%m-%d")

        except ValueError as e:
            # This handles parsing errors in the date format
            logger.warning(f"Invalid date format for {date_str}: {e}")
            return date_str

    def extract_epic_information(self, issue: dict[str, Any]) -> dict[str, str | None]:
        """
        Extract epic information from issue data.

        Args:
            issue: Issue data dictionary

        Returns:
            Dictionary containing epic_key and epic_name (or None if not found)
        """
        epic_info = {"epic_key": None, "epic_name": None}

        # Check if the issue has fields
        if "fields" not in issue:
            return epic_info

        fields = issue["fields"]

        # Try to get the epic link from issue
        # (requires the correct field ID which varies across instances)
        if hasattr(self, "get_jira_field_ids"):
            # Use the field discovery mechanism if available
            try:
                field_ids = self.get_jira_field_ids()

                # Get the epic link field ID
                epic_link_field = field_ids.get("Epic Link")
                if (
                    epic_link_field
                    and epic_link_field in fields
                    and fields[epic_link_field]
                ):
                    epic_info["epic_key"] = fields[epic_link_field]

                    # If the issue is linked to an epic, try to get the epic name
                    if epic_info["epic_key"] and hasattr(self, "get_issue"):
                        try:
                            epic_issue = self.get_issue(epic_info["epic_key"])
                            epic_fields = epic_issue.get("fields", {})

                            # Get the epic name field ID
                            epic_name_field = field_ids.get("Epic Name")
                            if epic_name_field and epic_name_field in epic_fields:
                                epic_info["epic_name"] = epic_fields[epic_name_field]

                        except Exception as e:
                            logger.warning(f"Error getting epic details: {str(e)}")

            except Exception as e:
                logger.warning(f"Error extracting epic information: {str(e)}")

        return epic_info

    def sanitize_html(self, html_content: str) -> str:
        """
        Sanitize HTML content by removing HTML tags.

        Args:
            html_content: HTML content to sanitize

        Returns:
            Plaintext content with HTML tags removed
        """
        if not html_content:
            return ""

        try:
            # Remove HTML tags
            plain_text = re.sub(r"<[^>]+>", "", html_content)
            # Decode HTML entities
            plain_text = html.unescape(plain_text)
            # Normalize whitespace
            plain_text = re.sub(r"\s+", " ", plain_text).strip()

            return plain_text

        except Exception as e:
            logger.warning(f"Error sanitizing HTML: {str(e)}")
            return html_content

    def sanitize_transition_fields(self, fields: dict[str, Any]) -> dict[str, Any]:
        """
        Sanitize fields to ensure they're valid for the Jira API.

        This is used for transition data to properly format field values.

        Args:
            fields: Dictionary of fields to sanitize

        Returns:
            Dictionary of sanitized fields
        """
        sanitized_fields = {}

        for key, value in fields.items():
            # Skip empty values
            if value is None:
                continue

            # Handle assignee field specially
            if key in ["assignee", "reporter"]:
                # If the value is already a dictionary, use it as is
                if isinstance(value, dict) and "accountId" in value:
                    sanitized_fields[key] = value
                else:
                    # Otherwise, look up the account ID
                    if hasattr(self, "_get_account_id"):
                        try:
                            account_id = self._get_account_id(value)
                            if account_id:
                                sanitized_fields[key] = {"accountId": account_id}
                        except Exception as e:
                            logger.warning(
                                f"Error getting account ID for {value}: {str(e)}"
                            )
            # All other fields pass through as is
            else:
                sanitized_fields[key] = value

        return sanitized_fields

    def add_comment_to_transition_data(
        self, transition_data: dict[str, Any], comment: str | None
    ) -> dict[str, Any]:
        """
        Add a comment to transition data.

        Args:
            transition_data: Transition data dictionary
            comment: Comment text (in Markdown format) or None

        Returns:
            Updated transition data
        """
        if not comment:
            return transition_data

        # Convert markdown to Jira format
        jira_formatted_comment = self.markdown_to_jira(comment)

        # Add the comment to the transition data
        transition_data["update"] = {
            "comment": [{"add": {"body": jira_formatted_comment}}]
        }

        return transition_data

    def _parse_date(self, date_str: str) -> str:
        """
        Parse a date string to a formatted date.

        Args:
            date_str: The date string to parse

        Returns:
            Formatted date string
        """
        if not date_str:
            return ""

        # Use the common utility function for consistent formatting with human-readable format
        return parse_date_human_readable(date_str)
