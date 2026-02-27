"""Module for Jira comment operations."""

import logging
from typing import Any

from ..models.jira.adf import adf_to_text
from ..utils import parse_date
from .client import JiraClient

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

            if not isinstance(comments, dict):
                msg = f"Unexpected return value type from `jira.issue_get_comments`: {type(comments)}"
                logger.error(msg)
                raise TypeError(msg)

            processed_comments = []
            for comment in comments.get("comments", [])[:limit]:
                processed_comment = {
                    "id": comment.get("id"),
                    "body": self._clean_text(comment.get("body", "")),
                    "created": str(parse_date(comment.get("created"))),
                    "updated": str(parse_date(comment.get("updated"))),
                    "author": comment.get("author", {}).get("displayName", "Unknown"),
                }
                processed_comments.append(processed_comment)

            return processed_comments
        except Exception as e:
            logger.error(f"Error getting comments for issue {issue_key}: {str(e)}")
            raise Exception(f"Error getting comments: {str(e)}") from e

    def add_comment(
        self,
        issue_key: str,
        comment: str,
        visibility: dict[str, str] | None = None,
        public: bool | None = None,
    ) -> dict[str, Any]:
        """Add a comment to an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            comment: Comment text to add (in Markdown format)
            visibility: (optional) Restrict comment visibility
                (e.g. {"type":"group","value":"jira-users"})
            public: (optional) For JSM issues only. True for
                customer-visible, False for internal/agent-only.
                Uses ServiceDesk API (plain text, not Markdown).
                Cannot be combined with visibility.

        Returns:
            The created comment details

        Raises:
            ValueError: If both public and visibility are set
            Exception: If there is an error adding the comment
        """
        # ServiceDesk API path for internal/public comments
        if public is not None:
            if visibility is not None:
                raise ValueError(
                    "Cannot use both 'public' and 'visibility'. "
                    "'public' uses the ServiceDesk API which "
                    "does not support Jira visibility "
                    "restrictions."
                )
            return self._add_servicedesk_comment(issue_key, comment, public)

        try:
            # Convert Markdown to Jira's markup format
            jira_formatted_comment = self._markdown_to_jira(comment)

            # Use v3 API on Cloud for ADF comments
            if isinstance(jira_formatted_comment, dict) and self.config.is_cloud:
                data: dict[str, Any] = {"body": jira_formatted_comment}
                if visibility:
                    data["visibility"] = visibility
                result = self._post_api3(f"issue/{issue_key}/comment", data)
            else:
                result = self.jira.issue_add_comment(
                    issue_key, jira_formatted_comment, visibility
                )
            if not isinstance(result, dict):
                msg = f"Unexpected return value type from `jira.issue_add_comment`: {type(result)}"
                logger.error(msg)
                raise TypeError(msg)

            body_raw = result.get("body", "")
            body_text = (
                adf_to_text(body_raw) if isinstance(body_raw, dict) else body_raw
            )
            return {
                "id": result.get("id"),
                "body": self._clean_text(body_text or ""),
                "created": str(parse_date(result.get("created"))),
                "author": result.get("author", {}).get("displayName", "Unknown"),
            }
        except Exception as e:
            logger.error(f"Error adding comment to issue {issue_key}: {str(e)}")
            raise Exception(f"Error adding comment: {str(e)}") from e

    def _add_servicedesk_comment(
        self,
        issue_key: str,
        comment: str,
        public: bool,
    ) -> dict[str, Any]:
        """Add a comment via the ServiceDesk API.

        Supports internal (agent-only) and public (customer-visible)
        comments on JSM issues. Uses plain text, not ADF or wiki
        markup.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            comment: Comment text (plain text, not Markdown)
            public: True for customer-visible, False for internal

        Returns:
            The created comment details

        Raises:
            Exception: If the issue is not a JSM issue or API fails
        """
        try:
            url = f"rest/servicedeskapi/request/{issue_key}/comment"
            data = {"body": comment, "public": public}
            headers = {
                **self.jira.default_headers,
                "X-ExperimentalApi": "opt-in",
            }
            response = self.jira.post(
                url,
                data=data,
                headers=headers,
            )
            if not isinstance(response, dict):
                msg = (
                    "Unexpected return value type from "
                    f"ServiceDesk API: {type(response)}"
                )
                logger.error(msg)
                raise TypeError(msg)

            body_text = response.get("body", "")
            # ServiceDesk API returns DateDTO format
            created_dto = response.get("created", {})
            created_str = (
                created_dto.get("iso8601", "")
                if isinstance(created_dto, dict)
                else str(created_dto)
            )
            author_data = response.get("author", {})
            author_name = author_data.get("displayName", "Unknown")

            return {
                "id": str(response.get("id", "")),
                "body": self._clean_text(body_text),
                "created": (str(parse_date(created_str)) if created_str else ""),
                "author": author_name,
                "public": response.get("public", public),
            }
        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                raise Exception(
                    f"Issue {issue_key} is not a JSM service "
                    f"desk issue or does not exist: {error_msg}"
                ) from e
            raise Exception(
                f"Error adding ServiceDesk comment to {issue_key}: {error_msg}"
            ) from e

    def edit_comment(
        self,
        issue_key: str,
        comment_id: str,
        comment: str,
        visibility: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Edit an existing comment on an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            comment_id: The ID of the comment to edit
            comment: Updated comment text (in Markdown format)
            visibility: (optional) Restrict comment visibility (e.g. {"type":"group","value":"jira-users"})

        Returns:
            The updated comment details

        Raises:
            Exception: If there is an error editing the comment
        """
        try:
            # Convert Markdown to Jira's markup format
            jira_formatted_comment = self._markdown_to_jira(comment)

            # Use v3 API on Cloud for ADF comments
            if isinstance(jira_formatted_comment, dict) and self.config.is_cloud:
                data: dict[str, Any] = {"body": jira_formatted_comment}
                if visibility:
                    data["visibility"] = visibility
                result = self._put_api3(f"issue/{issue_key}/comment/{comment_id}", data)
            else:
                result = self.jira.issue_edit_comment(
                    issue_key, comment_id, jira_formatted_comment, visibility
                )
            if not isinstance(result, dict):
                msg = f"Unexpected return value type from `jira.issue_edit_comment`: {type(result)}"
                logger.error(msg)
                raise TypeError(msg)

            body_raw = result.get("body", "")
            body_text = (
                adf_to_text(body_raw) if isinstance(body_raw, dict) else body_raw
            )
            return {
                "id": result.get("id"),
                "body": self._clean_text(body_text or ""),
                "updated": str(parse_date(result.get("updated"))),
                "author": result.get("author", {}).get("displayName", "Unknown"),
            }
        except Exception as e:
            logger.error(
                f"Error editing comment {comment_id} on issue {issue_key}: {str(e)}"
            )
            raise Exception(f"Error editing comment: {str(e)}") from e
