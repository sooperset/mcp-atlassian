"""Module for Jira transition operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from ..exceptions import MCPAtlassianAuthenticationError
from ..models import JiraIssue, JiraTransition
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
            MCPAtlassianAuthenticationError: If authentication fails with the Jira API (401/403)
            Exception: If there is an error getting transitions
        """
        try:
            transitions_data = self.jira.get_issue_transitions(issue_key)
            result: list[dict[str, Any]] = []

            # Handle different response formats
            transitions = []

            # The API might return transitions inside a 'transitions' key
            if isinstance(transitions_data, dict) and "transitions" in transitions_data:
                transitions = transitions_data["transitions"]
            # Or it might return transitions directly as a list
            elif isinstance(transitions_data, list):
                transitions = transitions_data

            for transition in transitions:
                # Skip non-dict transitions
                if not isinstance(transition, dict):
                    continue

                # Extract the essential information
                transition_info = {
                    "id": transition.get("id", ""),
                    "name": transition.get("name", ""),
                }

                # Handle "to" field in different formats
                to_status = None
                # Option 1: 'to' field with sub-fields
                if "to" in transition and isinstance(transition["to"], dict):
                    to_status = transition["to"].get("name")
                # Option 2: 'to_status' field directly
                elif "to_status" in transition:
                    to_status = transition.get("to_status")
                # Option 3: 'status' field directly (sometimes used in tests)
                elif "status" in transition:
                    to_status = transition.get("status")

                # Add to_status if found in any format
                if to_status:
                    transition_info["to_status"] = to_status

                result.append(transition_info)

            return result
        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code in [
                401,
                403,
            ]:
                error_msg = (
                    f"Authentication failed for Jira API ({http_err.response.status_code}). "
                    "Token may be expired or invalid. Please verify credentials."
                )
                logger.error(error_msg)
                raise MCPAtlassianAuthenticationError(error_msg) from http_err
            else:
                logger.error(f"HTTP error during API call: {http_err}", exc_info=False)
                raise http_err
        except Exception as e:
            error_msg = f"Error getting transitions for {issue_key}: {str(e)}"
            logger.error(error_msg)
            raise Exception(f"Error getting transitions: {str(e)}") from e

    def get_transitions(self, issue_key: str) -> dict[str, Any]:
        """
        Get the raw transitions data for an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            Raw transitions data from the API
        """
        return self.jira.get_issue_transitions(issue_key)

    def get_transitions_models(self, issue_key: str) -> list[JiraTransition]:
        """
        Get the available status transitions for an issue as JiraTransition models.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of JiraTransition models
        """
        transitions_data = self.get_transitions(issue_key)
        result: list[JiraTransition] = []

        # The API returns transitions inside a 'transitions' key
        if "transitions" in transitions_data:
            for transition_data in transitions_data["transitions"]:
                transition = JiraTransition.from_api_response(transition_data)
                result.append(transition)

        return result

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str | int,
        fields: dict[str, Any] | None = None,
        comment: str | None = None,
    ) -> JiraIssue:
        """
        Transition a Jira issue to a new status.

        Args:
            issue_key: The key of the issue to transition
            transition_id: The ID of the transition to perform (integer preferred, string accepted)
            fields: Optional fields to set during the transition
            comment: Optional comment to add during the transition

        Returns:
            JiraIssue model representing the transitioned issue

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails with the Jira API (401/403)
            ValueError: If there is an error transitioning the issue
        """
        try:
            # Normalize transition_id to an integer when possible, or string otherwise
            normalized_transition_id = self._normalize_transition_id(transition_id)

            # Validate that this is a valid transition ID
            valid_transitions = self.get_transitions_models(issue_key)
            valid_ids = [t.id for t in valid_transitions]

            # Convert string IDs to integers for proper comparison if normalized_transition_id is an integer
            if isinstance(normalized_transition_id, int):
                valid_ids = [
                    int(id_val)
                    if isinstance(id_val, str) and id_val.isdigit()
                    else id_val
                    for id_val in valid_ids
                ]

            # Check if the normalized_transition_id is in the list of valid IDs
            id_to_check = normalized_transition_id
            if id_to_check not in valid_ids:
                available_transitions = ", ".join(
                    f"{t.id} ({t.name})" for t in valid_transitions
                )
                logger.warning(
                    f"Transition ID {id_to_check} not in available transitions: {available_transitions}"
                )
                # Continue anyway as Jira will validate

            # Find the target status name corresponding to the transition ID
            target_status_name = None
            for transition in valid_transitions:
                if str(transition.id) == str(normalized_transition_id):
                    if transition.to_status and transition.to_status.name:
                        target_status_name = transition.to_status.name
                        break

            # Sanitize fields if provided
            fields_for_api = None
            if fields:
                sanitized_fields = self._sanitize_transition_fields(fields)
                if sanitized_fields:
                    fields_for_api = sanitized_fields

            # Prepare update data for comments if provided
            update_for_api = None
            if comment:
                # Create a temporary dict to hold the transition data
                temp_transition_data = {}
                self._add_comment_to_transition_data(temp_transition_data, comment)
                update_for_api = temp_transition_data.get("update")

            # Log the transition request for debugging
            logger.info(
                f"Transitioning issue {issue_key} with transition ID {normalized_transition_id}"
            )
            logger.debug(f"Fields: {fields_for_api}, Update: {update_for_api}")

            # Attempt to transition the issue using the appropriate method
            if target_status_name:
                # If we have a status name, use set_issue_status
                logger.info(f"Using status name '{target_status_name}' for transition")
                self.jira.set_issue_status(
                    issue_key=issue_key,
                    status_name=target_status_name,
                    fields=fields_for_api,
                    update=update_for_api,
                )
            else:
                # If no status name is found, try direct transition ID method
                logger.info(f"Using direct transition ID {normalized_transition_id}")
                # Convert to integer if it's a string that looks like an integer
                if (
                    isinstance(normalized_transition_id, str)
                    and normalized_transition_id.isdigit()
                ):
                    normalized_transition_id = int(normalized_transition_id)

                # Use set_issue_status_by_transition_id for direct ID transition
                self.jira.set_issue_status_by_transition_id(
                    issue_key=issue_key, transition_id=normalized_transition_id
                )

                # Apply fields and comments separately if needed
                if fields_for_api or update_for_api:
                    payload = {}
                    if fields_for_api:
                        payload["fields"] = fields_for_api
                    if update_for_api:
                        payload["update"] = update_for_api

                    if payload:
                        base_url = self.jira.resource_url("issue")
                        url = f"{base_url}/{issue_key}"
                        self.jira.put(url, data=payload)

            # Return the updated issue
            # Using get_issue from the base class or IssuesMixin if available
            if hasattr(self, "get_issue") and callable(self.get_issue):
                return self.get_issue(issue_key)
            else:
                # Fallback to using jira.get_issue directly
                issue = self.jira.get_issue(issue_key)
                if not issue:
                    raise ValueError(f"Issue {issue_key} not found after transition")

                # Create and return the JiraIssue model
                return JiraIssue.from_api_response(
                    issue, base_url=self.config.url if hasattr(self, "config") else None
                )
        except HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code in [
                401,
                403,
            ]:
                error_msg = (
                    f"Authentication failed for Jira API ({http_err.response.status_code}). "
                    "Token may be expired or invalid. Please verify credentials."
                )
                logger.error(error_msg)
                raise MCPAtlassianAuthenticationError(error_msg) from http_err
            else:
                logger.error(f"HTTP error during API call: {http_err}", exc_info=False)
                raise http_err
        except ValueError as e:
            logger.error(f"Value error transitioning issue {issue_key}: {str(e)}")
            raise
        except Exception as e:
            error_msg = (
                f"Error transitioning issue {issue_key} with transition ID "
                f"{transition_id}: {str(e)}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg) from e

    def _normalize_transition_id(self, transition_id: str | int | dict) -> str | int:
        """
        Normalize the transition ID to a common format.

        Args:
            transition_id: The transition ID, which can be a string, int, or dict

        Returns:
            The normalized transition ID as an integer when possible, or string otherwise
        """
        logger.debug(
            f"Normalizing transition_id: {transition_id}, type: {type(transition_id)}"
        )

        # Handle empty or None values
        if transition_id is None:
            logger.warning("Received None for transition_id, using default 0")
            return 0

        # Handle integer directly (preferred by the API)
        if isinstance(transition_id, int):
            return transition_id

        # Handle string by converting to integer if it's numeric
        if isinstance(transition_id, str):
            if transition_id.isdigit():
                return int(transition_id)
            else:
                # For non-numeric strings, keep as string for backward compatibility
                return transition_id

        # Handle dictionary case
        if isinstance(transition_id, dict):
            logger.warning(
                f"Received dict for transition_id when string expected: {transition_id}"
            )

            # Try to extract ID from standard formats
            for key in ["id", "ID", "transitionId", "transition_id"]:
                if key in transition_id and transition_id[key] is not None:
                    value = transition_id[key]
                    if isinstance(value, str | int):
                        logger.warning(f"Using {key}={value} as transition ID")
                        # Try to convert to int if possible
                        if isinstance(value, int):
                            return value
                        elif isinstance(value, str) and value.isdigit():
                            return int(value)
                        else:
                            return str(value)

            # If no standard key found, try to use any string or int value
            for key, value in transition_id.items():
                if value is not None and isinstance(value, str | int):
                    logger.warning(f"Using {key}={value} as transition ID from dict")
                    # Try to convert to int if possible
                    if isinstance(value, int):
                        return value
                    elif isinstance(value, str) and value.isdigit():
                        return int(value)
                    else:
                        return str(value)

            # Last resort: try to use the first value
            try:
                first_value = next(iter(transition_id.values()))
                if first_value is not None:
                    # Try to convert to int if possible
                    if isinstance(first_value, int):
                        return first_value
                    elif isinstance(first_value, str) and str(first_value).isdigit():
                        return int(first_value)
                    else:
                        return str(first_value)
            except (StopIteration, AttributeError):
                pass

            # Nothing worked, return a default
            logger.error(f"Could not extract valid transition ID from: {transition_id}")
            return 0

        # For any other type, convert to string with warning
        logger.warning(
            f"Unexpected type for transition_id: {type(transition_id)}, trying conversion"
        )
        try:
            str_value = str(transition_id)
            if str_value.isdigit():
                return int(str_value)
            else:
                return str_value
        except Exception as e:
            logger.error(f"Failed to convert transition_id: {str(e)}")
            return 0

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
