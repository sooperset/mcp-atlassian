"""Module for Jira transition operations."""

import logging
from typing import Any

from ..document_types import Document
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class TransitionsMixin(JiraClient):
    """Mixin for Jira transition operations."""

    def get_available_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get the available status transitions for an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of available transitions with id, name, and to status details

        Raises:
            Exception: If there is an error getting transitions
        """
        try:
            transitions_data = self.jira.get_issue_transitions(issue_key)
            result: list[dict[str, Any]] = []

            # Handle different response formats from the Jira API
            transitions = []
            if isinstance(transitions_data, dict) and "transitions" in transitions_data:
                # Handle the case where the response is a dict with a "transitions" key
                transitions = transitions_data.get("transitions", [])
            elif isinstance(transitions_data, list):
                # Handle the case where the response is a list of transitions directly
                transitions = transitions_data
            else:
                logger.warning(
                    f"Unexpected format for transitions data: {type(transitions_data)}"
                )
                return []

            for transition in transitions:
                if not isinstance(transition, dict):
                    continue

                # Extract the transition information safely
                transition_id = transition.get("id")
                transition_name = transition.get("name")

                # Handle different formats for the "to" status
                to_status = None
                if "to" in transition and isinstance(transition["to"], dict):
                    to_status = transition["to"].get("name")
                elif "to_status" in transition:
                    to_status = transition["to_status"]
                elif "status" in transition:
                    to_status = transition["status"]

                result.append(
                    {
                        "id": transition_id,
                        "name": transition_name,
                        "to_status": to_status,
                    }
                )

            return result
        except Exception as e:
            logger.error(f"Error getting transitions for issue {issue_key}: {str(e)}")
            raise Exception(f"Error getting transitions: {str(e)}") from e

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str | int,
        fields: dict[str, Any] | None = None,
        comment: str | None = None,
    ) -> Document:
        """
        Transition a Jira issue to a new status.

        Args:
            issue_key: The key of the issue to transition
            transition_id: The ID of the transition to perform
            fields: Optional fields to set during the transition
            comment: Optional comment to add during the transition

        Returns:
            Document representing the transitioned issue

        Raises:
            ValueError: If there is an error transitioning the issue
        """
        try:
            # Ensure transition_id is a string
            transition_id_str = self._normalize_transition_id(transition_id)

            # Prepare transition data
            transition_data: dict[str, Any] = {"transition": {"id": transition_id_str}}

            # Add fields if provided
            if fields:
                sanitized_fields = self._sanitize_transition_fields(fields)
                if sanitized_fields:
                    transition_data["fields"] = sanitized_fields

            # Add comment if provided
            if comment:
                self._add_comment_to_transition_data(transition_data, comment)

            # Log the transition request for debugging
            logger.info(
                f"Transitioning issue {issue_key} with transition ID {transition_id_str}"
            )
            logger.debug(f"Transition data: {transition_data}")

            # Perform the transition
            self.jira.issue_transition(issue_key, transition_data)

            # Return the updated issue
            # Using get_issue from the base class or IssuesMixin if available
            if hasattr(self, "get_issue") and callable(self.get_issue):
                return self.get_issue(issue_key)
            else:
                # Fallback if get_issue is not available
                logger.warning(
                    "get_issue method not available, returning empty Document"
                )
                return Document(page_content="", metadata={"key": issue_key})
        except Exception as e:
            error_msg = (
                f"Error transitioning issue {issue_key} with transition ID "
                f"{transition_id}: {str(e)}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg) from e

    def _normalize_transition_id(self, transition_id: str | int) -> str:
        """
        Normalize transition ID to a string.

        Args:
            transition_id: Transition ID as string or int

        Returns:
            String representation of transition ID
        """
        return str(transition_id)

    def _sanitize_transition_fields(self, fields: dict[str, Any]) -> dict[str, Any]:
        """
        Sanitize fields to ensure they're valid for the Jira API.

        Args:
            fields: Dictionary of fields to sanitize

        Returns:
            Dictionary of sanitized fields
        """
        sanitized_fields: dict[str, Any] = {}
        for key, value in fields.items():
            # Skip None values
            if value is None:
                continue

            # Handle special case for assignee
            if key == "assignee" and isinstance(value, str):
                try:
                    # Check if _get_account_id is available (from UsersMixin)
                    if hasattr(self, "_get_account_id"):
                        account_id = self._get_account_id(value)
                        sanitized_fields[key] = {"accountId": account_id}
                    else:
                        # If _get_account_id is not available, log warning and skip
                        logger.warning(
                            f"Cannot resolve assignee '{value}' without _get_account_id method"
                        )
                        continue
                except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
                    error_msg = f"Could not resolve assignee '{value}': {str(e)}"
                    logger.warning(error_msg)
                    # Skip this field
                    continue
            else:
                sanitized_fields[key] = value

        return sanitized_fields

    def _add_comment_to_transition_data(
        self, transition_data: dict[str, Any], comment: str | int
    ) -> None:
        """
        Add comment to transition data.

        Args:
            transition_data: The transition data dictionary to update
            comment: The comment to add
        """
        # Ensure comment is a string
        if not isinstance(comment, str):
            logger.warning(
                f"Comment must be a string, converting from {type(comment)}: {comment}"
            )
            comment_str = str(comment)
        else:
            comment_str = comment

        # Convert markdown to Jira format if _markdown_to_jira is available
        jira_formatted_comment = comment_str
        if hasattr(self, "_markdown_to_jira"):
            jira_formatted_comment = self._markdown_to_jira(comment_str)

        # Add to transition data
        transition_data["update"] = {
            "comment": [{"add": {"body": jira_formatted_comment}}]
        }
