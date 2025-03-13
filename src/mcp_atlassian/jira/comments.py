"""Module for Jira comment operations."""

import logging
from typing import Any

from .client import JiraClient
from .utils import parse_date_ymd

logger = logging.getLogger("mcp-jira")


class CommentsMixin(JiraClient):
    """Mixin for Jira comment operations."""

    def get_issue_comments(
        self, issue_key: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        Get comments for a specific issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            limit: Maximum number of comments to return

        Returns:
            List of comments with author, creation date, and content

        Raises:
            Exception: If there is an error getting comments
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
            raise Exception(f"Error getting comments: {str(e)}") from e

    def add_comment(self, issue_key: str, comment: str) -> dict[str, Any]:
        """
        Add a comment to an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            comment: Comment text to add (in Markdown format)

        Returns:
            The created comment details

        Raises:
            Exception: If there is an error adding the comment
        """
        try:
            # Convert Markdown to Jira's markup format
            jira_formatted_comment = self._markdown_to_jira(comment)

            result = self.jira.issue_add_comment(issue_key, jira_formatted_comment)
            return {
                "id": result.get("id"),
                "body": self._clean_text(result.get("body", "")),
                "created": self._parse_date(result.get("created")),
                "author": result.get("author", {}).get("displayName", "Unknown"),
            }
        except Exception as e:
            logger.error(f"Error adding comment to issue {issue_key}: {str(e)}")
            raise Exception(f"Error adding comment: {str(e)}") from e

    def _markdown_to_jira(self, markdown_text: str) -> str:
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

        # Use the existing preprocessor
        try:
            return self.preprocessor.markdown_to_jira(markdown_text)
        except Exception as e:
            logger.warning(f"Error converting markdown to Jira format: {str(e)}")
            # Return the original text if conversion fails
            return markdown_text

    def _parse_date(self, date_str: str | None) -> str:
        """
        Parse a date string from ISO format to a more readable format.

        Args:
            date_str: Date string in ISO format or None

        Returns:
            Formatted date string or empty string if date_str is None
        """
        logger.debug(f"CommentsMixin._parse_date called with: '{date_str}'")

        # Call the utility function and capture the result
        result = parse_date_ymd(date_str)

        logger.debug(f"CommentsMixin._parse_date returning: '{result}'")
        return result
