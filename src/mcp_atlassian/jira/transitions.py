"""Module for Jira transition operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from ..models import JiraIssue, JiraTransition
from ..utils.decorators import handle_auth_errors
from .client import JiraClient
from .protocols import IssueOperationsProto, UsersOperationsProto

logger = logging.getLogger("mcp-jira")


class TransitionsMixin(JiraClient, IssueOperationsProto, UsersOperationsProto):
    """Mixin for Jira transition operations."""

    @handle_auth_errors("Jira API")
    def get_available_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get the available status transitions for an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of available transitions with id, name,
            and to status details

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails
                with the Jira API (401/403)
            Exception: If there is an error getting transitions
        """
        try:
            transitions_data: object = self.jira.get_issue_transitions(issue_key)
            if not isinstance(transitions_data, list):
                return []
            result: list[dict[str, Any]] = []

            for transition in transitions_data:
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
                # Option 3: 'status' field directly
                elif "status" in transition:
                    to_status = transition.get("status")

                # Add to_status if found in any format
                if to_status:
                    transition_info["to_status"] = to_status

                result.append(transition_info)

            return result
        except HTTPError:
            raise  # let decorator handle auth errors
        except Exception as e:
            error_msg = f"Error getting transitions for {issue_key}: {str(e)}"
            logger.error(error_msg)
            public_error = f"Error getting transitions: {str(e)}"
            raise Exception(public_error) from e

    def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get the raw transitions data for an issue.

        Uses get_issue_transitions_full() to get the complete API response
        including the full 'to' status object, not the simplified version
        from get_issue_transitions() which only returns the status name as a string.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            Raw transitions data from the API with full 'to' status objects
        """
        response = self.jira.get_issue_transitions_full(issue_key)
        if isinstance(response, dict):
            transitions = response.get("transitions", [])
            if isinstance(transitions, list):
                return [item for item in transitions if isinstance(item, dict)]
        return []

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

        for transition_data in transitions_data:
            transition = JiraTransition.from_api_response(transition_data)
            result.append(transition)

        return result

    @handle_auth_errors("Jira API")
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
            transition_id: The ID of the transition to perform
                (integer preferred, string accepted)
            fields: Optional fields to set during the transition
            comment: Optional comment to add during the transition.
                Rejected for projects listed in
                JIRA_INTERNAL_ONLY_PROJECTS: a transition comment is a
                standard Jira comment whose customer-visibility on JSM
                cannot be controlled from this call, so it may not be
                posted on an internal-only project.

        Returns:
            JiraIssue model representing the transitioned issue

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails
                with the Jira API (401/403)
            ValueError: If there is an error transitioning the issue, or
                if a comment is provided for a project listed in
                JIRA_INTERNAL_ONLY_PROJECTS
        """
        if comment:
            self._enforce_internal_only_transition_comment(issue_key)

        try:
            # Normalize transition_id to int when possible
            normalized_transition_id = self._normalize_transition_id(transition_id)

            # Validate that this is a valid transition ID
            valid_transitions = self.get_transitions_models(issue_key)
            valid_ids: list[str | int] = [t.id for t in valid_transitions]

            # Convert string IDs to integers for proper comparison
            if isinstance(normalized_transition_id, int):
                valid_ids = [
                    int(id_val)
                    if isinstance(id_val, str) and id_val.isdigit()
                    else id_val
                    for id_val in valid_ids
                ]

            # Check if normalized_transition_id is valid
            id_to_check = normalized_transition_id
            if id_to_check not in valid_ids:
                available_transitions = ", ".join(
                    f"{t.id} ({t.name})" for t in valid_transitions
                )
                logger.warning(
                    f"Transition ID {id_to_check} not in"
                    " available transitions:"
                    f" {available_transitions}"
                )
                # Continue anyway as Jira will validate

            # Sanitize fields if provided
            fields_for_api = None
            if fields:
                sanitized_fields = self._sanitize_transition_fields(fields)
                if sanitized_fields:
                    fields_for_api = sanitized_fields

            # Prepare update data for comments if provided
            update_for_api = None
            if comment:
                temp_transition_data: dict[str, Any] = {}
                self._add_comment_to_transition_data(temp_transition_data, comment)
                update_for_api = temp_transition_data.get("update")

            # Log the transition request for debugging
            logger.info(
                f"Transitioning issue {issue_key} with"
                f" transition ID {normalized_transition_id}"
            )
            logger.debug(f"Fields: {fields_for_api}, Update: {update_for_api}")

            payload: dict[str, Any] = {
                "transition": {"id": str(normalized_transition_id)},
            }
            if fields_for_api:
                payload["fields"] = fields_for_api
            if update_for_api:
                payload["update"] = update_for_api

            if self.config.is_cloud:
                # Cloud comments are ADF and require the REST v3 endpoint.
                self._post_api3(f"issue/{issue_key}/transitions", payload)
            else:
                # Server/DC comments use wiki markup on REST v2.
                base_url = self.jira.resource_url("issue")
                url = f"{base_url}/{issue_key}/transitions"
                self.jira.post(url, data=payload)

            # Return the updated issue
            return self.get_issue(issue_key)
        except ValueError as e:
            logger.error(f"Value error transitioning issue {issue_key}: {str(e)}")
            raise
        except HTTPError:
            raise  # let decorator handle auth errors
        except Exception as e:
            error_msg = (
                f"Error transitioning issue {issue_key}"
                f" with transition ID"
                f" {transition_id}: {str(e)}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg) from e

    def _normalize_transition_id(self, transition_id: object) -> str | int:
        """
        Normalize the transition ID to a common format.

        Args:
            transition_id: The transition ID, which can be a string, int, or dict

        Returns:
            The normalized transition ID as an integer when possible, or a string
            otherwise
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
            f"Unexpected type for transition_id: {type(transition_id)}, "
            "trying conversion"
        )
        str_value = str(transition_id)
        if str_value.isdigit():
            return int(str_value)
        return str_value

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
                    account_id = self._get_account_id(value)
                    sanitized_fields[key] = {"accountId": account_id}
                except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
                    error_msg = f"Could not resolve assignee '{value}': {str(e)}"
                    logger.warning(error_msg)
                    # Skip this field
                    continue
            else:
                sanitized_fields[key] = value

        return sanitized_fields

    def _enforce_internal_only_transition_comment(self, issue_key: str) -> None:
        """Reject transition comments on JIRA_INTERNAL_ONLY_PROJECTS projects.

        A transition comment is posted through the core Jira API
        (``update.comment[].add``), which on JSM issues is commonly
        customer-visible by default — and this call offers no way to
        force it internal. Allowing it would re-open the exact hole the
        internal-only guard on add_comment/edit_comment closes, through a
        sibling entry point. So for listed projects the transition
        comment is refused outright; the transition itself (without a
        comment) is unaffected.

        Args:
            issue_key: The issue key (e.g. 'CC-123')

        Raises:
            ValueError: If issue_key's project is listed in
                JIRA_INTERNAL_ONLY_PROJECTS
        """
        if not self._is_internal_only_project(issue_key):
            return
        raise ValueError(
            f"Issue {issue_key} belongs to a project configured as "
            "internal-only (JIRA_INTERNAL_ONLY_PROJECTS). Transition "
            "comments are posted via the core Jira API and may be "
            "customer-visible on JSM, with no way to force them "
            "internal from this call — so they are blocked here. "
            "Perform the transition WITHOUT a comment, then post an "
            "internal note with add_comment(public=False)."
        )

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
        jira_formatted_comment: str | dict[str, Any] = comment_str
        if hasattr(self, "_markdown_to_jira"):
            jira_formatted_comment = self._markdown_to_jira(comment_str)

        # Add to transition data
        transition_data["update"] = {
            "comment": [{"add": {"body": jira_formatted_comment}}]
        }
