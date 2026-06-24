"""Module for Jira transition operations."""

import logging
from typing import Any

from requests.exceptions import HTTPError

from ..models import JiraIssue, JiraTransition
from ..utils.decorators import handle_auth_errors
from .client import JiraClient
from .protocols import IssueOperationsProto, UsersOperationsProto
from .transition_schema import parse_transition_field

logger = logging.getLogger("mcp-jira")
ALLOWED_VALUES_SAMPLE_SIZE = 10
ALLOWED_VALUES_COMPACT_THRESHOLD = 20


class TransitionsMixin(JiraClient, IssueOperationsProto, UsersOperationsProto):
    """Mixin for Jira transition operations."""

    @handle_auth_errors("Jira API")
    def get_available_transitions(
        self, issue_key: str, response_mode: str = "compact"
    ) -> list[dict[str, Any]]:
        """
        Get the available status transitions for an issue.

        Includes has_screen flag, complete transition screen fields,
        and required fields metadata so callers can render the same
        field set Jira exposes for the selected transition before
        attempting it.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of available transitions with id, name, to_status,
            has_screen, fields, and required_fields details

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails
                with the Jira API (401/403)
            Exception: If there is an error getting transitions
        """
        try:
            transitions_data = self.get_transitions(
                issue_key, expand="transitions.fields"
            )
            result: list[dict[str, Any]] = []
            compact = response_mode != "full"

            for transition in transitions_data:
                # Preserve the full Jira transition payload while adding
                # normalized convenience keys used by existing callers.
                transition_info: dict[str, Any] = dict(transition)
                transition_info["id"] = transition.get("id", "")
                transition_info["name"] = transition.get("name", "")

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

                if to_status:
                    transition_info["to_status"] = to_status

                # Include has_screen flag, full screen fields, and required fields
                has_screen = bool(transition.get("hasScreen"))
                transition_info["has_screen"] = has_screen

                fields = transition.get("fields")
                if isinstance(fields, dict):
                    transition_info["field_count"] = len(fields)
                    if compact:
                        transition_info["fields"] = self._compact_transition_fields(
                            fields
                        )
                    else:
                        transition_info["fields"] = fields
                    required_fields = self._extract_required_fields(
                        fields, compact=compact
                    )
                    if required_fields:
                        transition_info["required_fields"] = required_fields

                result.append(transition_info)

            return result
        except HTTPError:
            raise  # let decorator handle auth errors
        except Exception as e:
            error_msg = f"Error getting transitions for {issue_key}: {str(e)}"
            logger.error(error_msg)
            raise_msg = f"Error getting transitions: {str(e)}"
            raise Exception(raise_msg) from e

    @staticmethod
    def _extract_required_fields(
        fields: dict[str, Any], *, compact: bool = True
    ) -> list[dict[str, Any]]:
        """
        Extract required field metadata from transition fields dict.

        Args:
            fields: The "fields" dict from a transition API response.

        Returns:
            List of required field info dicts with key, name, schema,
            and allowed_values (for select-type fields).
        """
        required_fields: list[dict[str, Any]] = []
        for field_key, field_data in fields.items():
            if not isinstance(field_data, dict):
                continue
            if not field_data.get("required"):
                continue

            if compact:
                field_info = TransitionsMixin._compact_transition_field(
                    field_key, field_data
                )
                field_info.setdefault("key", field_key)
                field_info.setdefault("name", field_data.get("name", field_key))
            else:
                field_info = {
                    "key": field_key,
                    "name": field_data.get("name", field_key),
                }

                schema = field_data.get("schema")
                if isinstance(schema, dict):
                    field_info["schema"] = schema

                allowed_values = field_data.get("allowedValues")
                if isinstance(allowed_values, list):
                    field_info["allowed_values"] = [
                        TransitionsMixin._simplify_allowed_value(v)
                        for v in allowed_values
                        if isinstance(v, dict)
                    ]

            required_fields.append(field_info)

        return required_fields

    @staticmethod
    def _compact_transition_fields(
        fields: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Return transition fields without unbounded Jira allowedValues payloads."""
        compact_fields: dict[str, dict[str, Any]] = {}
        for field_key, field_data in fields.items():
            if isinstance(field_data, dict):
                compact_fields[field_key] = TransitionsMixin._compact_transition_field(
                    field_key, field_data
                )
        return compact_fields

    @staticmethod
    def _compact_transition_field(
        field_key: str,
        field_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Return one compact transition field summary."""
        allowed_values = field_data.get("allowedValues")
        if (
            isinstance(allowed_values, list)
            and len(allowed_values) <= ALLOWED_VALUES_COMPACT_THRESHOLD
        ):
            return dict(field_data)

        field_plan = parse_transition_field(field_key, field_data)
        compact_field: dict[str, Any] = {
            "key": field_key,
            "name": field_data.get("name", field_key),
            "required": bool(field_data.get("required")),
            "interaction_type": field_plan.interaction_type,
            "value_format": field_plan.value_format,
        }

        schema = field_data.get("schema")
        if isinstance(schema, dict):
            compact_field["schema"] = schema

        operations = field_data.get("operations")
        if isinstance(operations, list):
            compact_field["operations"] = [str(op) for op in operations]

        if field_plan.lookup_tool:
            compact_field["lookup_tool"] = field_plan.lookup_tool

        if isinstance(allowed_values, list):
            sample = [
                TransitionsMixin._simplify_allowed_value(value)
                for value in allowed_values[-ALLOWED_VALUES_SAMPLE_SIZE:]
                if isinstance(value, dict)
            ]
            compact_field["allowed_values_count"] = len(allowed_values)
            compact_field["allowed_values_sample"] = sample
            compact_field["allowed_values_sample_size"] = len(sample)
            compact_field["allowed_values_sample_strategy"] = "api_order_last"
            compact_field["allowed_values_truncated"] = (
                len(allowed_values) > ALLOWED_VALUES_SAMPLE_SIZE
            )

        return compact_field

    @staticmethod
    def _simplify_allowed_value(value: dict[str, Any]) -> dict[str, Any]:
        """Return a small identifier/display object for an allowed value."""
        simplified: dict[str, Any] = {}
        if "id" in value:
            simplified["id"] = str(value.get("id", ""))
        display_name = value.get("name", value.get("value", ""))
        if display_name:
            simplified["name"] = str(display_name)
        return simplified

    def get_transitions(
        self, issue_key: str, expand: str | None = "transitions.fields"
    ) -> list[dict[str, Any]]:
        """
        Get the raw transitions data for an issue.

        Uses get_issue_transitions_full() to get the complete API response
        including the full 'to' status object, not the simplified version
        from get_issue_transitions() which only returns the status name as a string.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            expand: Optional expand parameter. Defaults to 'transitions.fields'
                to include transition screen field metadata with required flags
                and allowed values.

        Returns:
            Raw transitions data from the API with full 'to' status objects
        """
        response = self.jira.get_issue_transitions_full(issue_key, expand=expand)
        if isinstance(response, dict):
            transitions = response.get("transitions", [])
            if isinstance(transitions, list):
                return [t for t in transitions if isinstance(t, dict)]
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
        update_data: dict[str, Any] | None = None,
    ) -> JiraIssue:
        """
        Transition a Jira issue to a new status.

        Args:
            issue_key: The key of the issue to transition
            transition_id: The ID of the transition to perform
                (integer preferred, string accepted)
            fields: Optional fields to set during the transition
            comment: Optional comment to add during the transition
            update_data: Optional update data (e.g., worklog) to send
                alongside the transition. Example:
                {"worklog": [{"add": {"timeSpent": "1h", "comment": "Resolved"}}]}

        Returns:
            JiraIssue model representing the transitioned issue

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails
                with the Jira API (401/403)
            ValueError: If there is an error transitioning the issue
        """
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

            # Find the target status name for the transition ID
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

            # Prepare update data (comment + extra update_data like worklog)
            update_for_api = None
            temp_transition_data: dict[str, Any] = {}
            if comment:
                self._add_comment_to_transition_data(temp_transition_data, comment)
            if update_data:
                temp_transition_data.setdefault("update", {})
                if isinstance(update_data, dict):
                    for key, value in update_data.items():
                        temp_transition_data["update"][key] = value
            update_for_api = temp_transition_data.get("update")

            # Log the transition request for debugging
            logger.info(
                f"Transitioning issue {issue_key} with"
                f" transition ID {normalized_transition_id}"
            )
            logger.debug(f"Fields: {fields_for_api}, Update: {update_for_api}")

            # Transition using the appropriate method
            if target_status_name:
                logger.info(f"Using status name '{target_status_name}' for transition")
                self.jira.set_issue_status(
                    issue_key=issue_key,
                    status_name=target_status_name,
                    fields=fields_for_api,
                    update=update_for_api,
                )
            else:
                logger.info(f"Using direct transition ID {normalized_transition_id}")
                if (
                    isinstance(normalized_transition_id, str)
                    and normalized_transition_id.isdigit()
                ):
                    normalized_transition_id = int(normalized_transition_id)

                if fields_for_api or update_for_api:
                    payload: dict[str, Any] = {
                        "transition": {"id": str(normalized_transition_id)},
                    }
                    if fields_for_api:
                        payload["fields"] = fields_for_api
                    if update_for_api:
                        payload["update"] = update_for_api

                    base_url = self.jira.resource_url("issue")
                    url = f"{base_url}/{issue_key}/transitions"
                    self.jira.post(url, json=payload)
                else:
                    self.jira.set_issue_status_by_transition_id(
                        issue_key=issue_key,
                        transition_id=normalized_transition_id,
                    )

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

    def _normalize_transition_id(self, transition_id: Any) -> str | int:
        """
        Normalize the transition ID to a common format.

        Args:
            transition_id: The transition ID, which can be a string, int, or dict

        Returns:
            The normalized transition ID as an integer when possible, or string
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
            "Unexpected type for transition_id: "
            f"{type(transition_id)}, trying conversion"
        )
        str_value = str(transition_id)
        if str_value.isdigit():
            return int(str_value)
        else:
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
