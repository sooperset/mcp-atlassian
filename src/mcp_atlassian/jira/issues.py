"""Module for Jira issue operations."""

import logging
from collections import defaultdict
from typing import Any

from requests.exceptions import HTTPError

from ..exceptions import MCPAtlassianAuthenticationError
from ..models.jira import JiraIssue
from ..models.jira.common import JiraChangelog
from ..utils import parse_date
from .client import JiraClient
from .constants import DEFAULT_READ_JIRA_FIELDS
from .protocols import (
    AttachmentsOperationsProto,
    EpicOperationsProto,
    FieldsOperationsProto,
    IssueOperationsProto,
    UsersOperationsProto,
)

logger = logging.getLogger("mcp-jira")


class IssuesMixin(
    JiraClient,
    AttachmentsOperationsProto,
    EpicOperationsProto,
    FieldsOperationsProto,
    IssueOperationsProto,
    UsersOperationsProto,
):
    """Mixin for Jira issue operations."""

    def get_issue(
        self,
        issue_key: str,
        expand: str | None = None,
        comment_limit: int | str | None = 10,
        fields: str | list[str] | tuple[str, ...] | set[str] | None = None,
        properties: str | list[str] | None = None,
        update_history: bool = True,
    ) -> JiraIssue:
        """
        Get a Jira issue by key.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)
            expand: Fields to expand in the response
            comment_limit: Maximum number of comments to include, or "all"
            fields: Fields to return (comma-separated string, list, tuple, set, or "*all")
            properties: Issue properties to return (comma-separated string or list)
            update_history: Whether to update the issue view history

        Returns:
            JiraIssue model with issue data and metadata

        Raises:
            MCPAtlassianAuthenticationError: If authentication fails with the Jira API (401/403)
            Exception: If there is an error retrieving the issue
        """
        try:
            # Determine fields_param: use provided fields or default from constant
            fields_param = fields
            if fields_param is None:
                fields_param = ",".join(DEFAULT_READ_JIRA_FIELDS)
            elif isinstance(fields_param, list | tuple | set):
                fields_param = ",".join(fields_param)

            # Ensure necessary fields are included based on special parameters
            if (
                fields_param == ",".join(DEFAULT_READ_JIRA_FIELDS)
                or fields_param == "*all"
            ):
                # Default fields are being used - preserve the order
                default_fields_list = (
                    fields_param.split(",")
                    if fields_param != "*all"
                    else list(DEFAULT_READ_JIRA_FIELDS)
                )
                additional_fields = []

                # Add appropriate fields based on expand parameter
                if expand:
                    expand_params = expand.split(",")
                    if (
                        "changelog" in expand_params
                        and "changelog" not in default_fields_list
                        and "changelog" not in additional_fields
                    ):
                        additional_fields.append("changelog")
                    if (
                        "renderedFields" in expand_params
                        and "rendered" not in default_fields_list
                        and "rendered" not in additional_fields
                    ):
                        additional_fields.append("rendered")

                # Add appropriate fields based on properties parameter
                if (
                    properties
                    and "properties" not in default_fields_list
                    and "properties" not in additional_fields
                ):
                    additional_fields.append("properties")

                # Combine default fields with additional fields, preserving order
                if additional_fields:
                    fields_param = ",".join(default_fields_list + additional_fields)
            # Handle non-default fields string

            # Build expand parameter if provided
            expand_param = expand

            # Convert properties to proper format if it's a list
            properties_param = properties
            if properties and isinstance(properties, list | tuple | set):
                properties_param = ",".join(properties)

            # Get the issue data with all parameters
            issue = self.jira.get_issue(
                issue_key,
                expand=expand_param,
                fields=fields_param,
                properties=properties_param,
                update_history=update_history,
            )
            if not issue:
                msg = f"Issue {issue_key} not found"
                raise ValueError(msg)
            if not isinstance(issue, dict):
                msg = (
                    f"Unexpected return value type from `jira.get_issue`: {type(issue)}"
                )
                logger.error(msg)
                raise TypeError(msg)

            # Extract fields data, safely handling None
            fields_data = issue.get("fields", {}) or {}

            # Get comments if needed
            if "comment" in fields_data:
                comment_limit_int = self._normalize_comment_limit(comment_limit)
                comments = self._get_issue_comments_if_needed(
                    issue_key, comment_limit_int
                )
                # Add comments to the issue data for processing by the model
                fields_data["comment"]["comments"] = comments

            # Extract epic information
            try:
                epic_info = self._extract_epic_information(issue)
            except Exception as e:
                logger.warning(f"Error extracting epic information: {str(e)}")
                epic_info = {"epic_key": None, "epic_name": None}

            # If this is linked to an epic, add the epic information to the fields
            if epic_info.get("epic_key"):
                try:
                    # Get field IDs for epic fields
                    field_ids = self.get_field_ids_to_epic()

                    # Add epic link field if it doesn't exist
                    if (
                        "epic_link" in field_ids
                        and field_ids["epic_link"] not in fields_data
                    ):
                        fields_data[field_ids["epic_link"]] = epic_info["epic_key"]

                    # Add epic name field if it doesn't exist
                    if (
                        epic_info.get("epic_name")
                        and "epic_name" in field_ids
                        and field_ids["epic_name"] not in fields_data
                    ):
                        fields_data[field_ids["epic_name"]] = epic_info["epic_name"]
                except Exception as e:
                    logger.warning(f"Error setting epic fields: {str(e)}")

            # Update the issue data with the fields
            issue["fields"] = fields_data

            # Create and return the JiraIssue model, passing requested_fields
            return JiraIssue.from_api_response(
                issue,
                base_url=self.config.url if hasattr(self, "config") else None,
                requested_fields=fields,
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
                raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error retrieving issue {issue_key}: {error_msg}")
            raise Exception(f"Error retrieving issue {issue_key}: {error_msg}") from e

    def _normalize_comment_limit(self, comment_limit: int | str | None) -> int | None:
        """
        Normalize the comment limit to an integer or None.

        Args:
            comment_limit: The comment limit as int, string, or None

        Returns:
            Normalized comment limit as int or None
        """
        if comment_limit is None:
            return None

        if isinstance(comment_limit, int):
            return comment_limit

        if comment_limit == "all":
            return None  # No limit

        # Try to convert to int
        try:
            return int(comment_limit)
        except ValueError:
            # If conversion fails, default to 10
            return 10

    def _get_issue_comments_if_needed(
        self, issue_key: str, comment_limit: int | None
    ) -> list[dict]:
        """
        Get comments for an issue if needed.

        Args:
            issue_key: The issue key
            comment_limit: Maximum number of comments to include

        Returns:
            List of comments
        """
        if comment_limit is None or comment_limit > 0:
            try:
                response = self.jira.issue_get_comments(issue_key)
                if not isinstance(response, dict):
                    msg = f"Unexpected return value type from `jira.issue_get_comments`: {type(response)}"
                    logger.error(msg)
                    raise TypeError(msg)

                comments = response["comments"]

                # Limit comments if needed
                if comment_limit is not None:
                    comments = comments[:comment_limit]

                return comments
            except Exception as e:
                logger.warning(f"Error getting comments for {issue_key}: {str(e)}")
                return []
        return []

    def _extract_epic_information(self, issue: dict) -> dict[str, str | None]:
        """
        Extract epic information from an issue.

        Args:
            issue: The issue data

        Returns:
            Dictionary with epic information
        """
        # Initialize with default values
        epic_info = {
            "epic_key": None,
            "epic_name": None,
            "epic_summary": None,
            "is_epic": False,
        }

        try:
            fields = issue.get("fields", {}) or {}
            issue_type = fields.get("issuetype", {}).get("name", "").lower()

            # Get field IDs for epic fields
            try:
                field_ids = self.get_field_ids_to_epic()
            except Exception as e:
                logger.warning(f"Error getting Jira fields: {str(e)}")
                field_ids = {}

            # Check if this is an epic
            if issue_type == "epic":
                epic_info["is_epic"] = True

                # Use the discovered field ID for epic name
                if "epic_name" in field_ids and field_ids["epic_name"] in fields:
                    epic_info["epic_name"] = fields.get(field_ids["epic_name"], "")

            # If not an epic, check for epic link
            elif "epic_link" in field_ids:
                epic_link_field = field_ids["epic_link"]

                if epic_link_field in fields and fields[epic_link_field]:
                    epic_key = fields[epic_link_field]
                    epic_info["epic_key"] = epic_key

                    # Try to get epic details
                    try:
                        epic = self.jira.get_issue(
                            epic_key,
                            expand=None,
                            fields=None,
                            properties=None,
                            update_history=True,
                        )
                        if not isinstance(epic, dict):
                            msg = f"Unexpected return value type from `jira.get_issue`: {type(epic)}"
                            logger.error(msg)
                            raise TypeError(msg)

                        epic_fields = epic.get("fields", {}) or {}

                        # Get epic name using the discovered field ID
                        if "epic_name" in field_ids:
                            epic_info["epic_name"] = epic_fields.get(
                                field_ids["epic_name"], ""
                            )

                        epic_info["epic_summary"] = epic_fields.get("summary", "")
                    except Exception as e:
                        logger.warning(
                            f"Error getting epic details for {epic_key}: {str(e)}"
                        )
        except Exception as e:
            logger.warning(f"Error extracting epic information: {str(e)}")

        return epic_info

    def _format_issue_content(
        self,
        issue_key: str,
        issue: dict,
        description: str,
        comments: list[dict],
        created_date: str,
        epic_info: dict[str, str | None],
    ) -> str:
        """
        Format issue content for display.

        Args:
            issue_key: The issue key
            issue: The issue data
            description: The issue description
            comments: The issue comments
            created_date: The formatted creation date
            epic_info: Epic information

        Returns:
            Formatted issue content
        """
        fields = issue.get("fields", {})

        # Basic issue information
        summary = fields.get("summary", "")
        status = fields.get("status", {}).get("name", "")
        issue_type = fields.get("issuetype", {}).get("name", "")

        # Format content
        content = [f"# {issue_key}: {summary}"]
        content.append(f"**Type**: {issue_type}")
        content.append(f"**Status**: {status}")
        content.append(f"**Created**: {created_date}")

        # Add reporter
        reporter = fields.get("reporter", {})
        reporter_name = reporter.get("displayName", "") or reporter.get("name", "")
        if reporter_name:
            content.append(f"**Reporter**: {reporter_name}")

        # Add assignee
        assignee = fields.get("assignee", {})
        assignee_name = assignee.get("displayName", "") or assignee.get("name", "")
        if assignee_name:
            content.append(f"**Assignee**: {assignee_name}")

        # Add epic information
        if epic_info["is_epic"]:
            content.append(f"**Epic Name**: {epic_info['epic_name']}")
        elif epic_info["epic_key"]:
            content.append(
                f"**Epic**: [{epic_info['epic_key']}] {epic_info['epic_summary']}"
            )

        # Add description
        if description:
            content.append("\n## Description\n")
            content.append(description)

        # Add comments
        if comments:
            content.append("\n## Comments\n")
            for comment in comments:
                author = comment.get("author", {})
                author_name = author.get("displayName", "") or author.get("name", "")
                comment_body = self._clean_text(comment.get("body", ""))

                if author_name and comment_body:
                    comment_date = comment.get("created", "")
                    if comment_date:
                        comment_date = parse_date(comment_date)
                        content.append(f"**{author_name}** ({comment_date}):")
                    else:
                        content.append(f"**{author_name}**:")

                    content.append(f"{comment_body}\n")

        return "\n".join(content)

    def _create_issue_metadata(
        self,
        issue_key: str,
        issue: dict,
        comments: list[dict],
        created_date: str,
        epic_info: dict[str, str | None],
    ) -> dict[str, Any]:
        """
        Create metadata for a Jira issue.

        Args:
            issue_key: The issue key
            issue: The issue data
            comments: The issue comments
            created_date: The formatted creation date
            epic_info: Epic information

        Returns:
            Metadata dictionary
        """
        fields = issue.get("fields", {})

        # Initialize metadata
        metadata = {
            "key": issue_key,
            "title": fields.get("summary", ""),
            "status": fields.get("status", {}).get("name", ""),
            "type": fields.get("issuetype", {}).get("name", ""),
            "created": created_date,
            "url": f"{self.config.url}/browse/{issue_key}",
        }

        # Add assignee if available
        assignee = fields.get("assignee", {})
        if assignee:
            metadata["assignee"] = assignee.get("displayName", "") or assignee.get(
                "name", ""
            )

        # Add epic information
        if epic_info["is_epic"]:
            metadata["is_epic"] = True
            metadata["epic_name"] = epic_info["epic_name"]
        elif epic_info["epic_key"]:
            metadata["epic_key"] = epic_info["epic_key"]
            metadata["epic_name"] = epic_info["epic_name"]
            metadata["epic_summary"] = epic_info["epic_summary"]

        # Add comment count
        metadata["comment_count"] = len(comments)

        return metadata

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str,
        description: str = "",
        assignee: str | None = None,
        components: list[str] | None = None,
        **kwargs: Any,  # noqa: ANN401 - Dynamic field types are necessary for Jira API
    ) -> JiraIssue:
        """
        Create a new Jira issue.

        Args:
            project_key: The key of the project
            summary: The issue summary
            issue_type: The type of issue to create
            description: The issue description
            assignee: The username or account ID of the assignee
            components: List of component names to assign (e.g., ["Frontend", "API"])
            **kwargs: Additional fields to set on the issue

        Returns:
            JiraIssue model representing the created issue

        Raises:
            Exception: If there is an error creating the issue
        """
        try:
            # Validate required fields
            if not project_key:
                raise ValueError("Project key is required")
            if not summary:
                raise ValueError("Summary is required")
            if not issue_type:
                raise ValueError("Issue type is required")

            # Prepare fields
            fields: dict[str, Any] = {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issue_type},
            }

            # Add description if provided
            if description:
                fields["description"] = description

            # Add assignee if provided
            if assignee:
                try:
                    # _get_account_id now returns the correct identifier (accountId for cloud, name for server)
                    assignee_identifier = self._get_account_id(assignee)
                    self._add_assignee_to_fields(fields, assignee_identifier)
                except ValueError as e:
                    logger.warning(f"Could not assign issue: {str(e)}")

            # Add components if provided
            if components:
                if isinstance(components, list):
                    # Filter out any None or empty/whitespace-only strings
                    valid_components = [
                        comp_name.strip()
                        for comp_name in components
                        if isinstance(comp_name, str) and comp_name.strip()
                    ]
                    if valid_components:
                        # Format as list of {"name": ...} dicts for the API
                        fields["components"] = [
                            {"name": comp_name} for comp_name in valid_components
                        ]

            # Make a copy of kwargs to preserve original values for two-step Epic creation
            kwargs_copy = kwargs.copy()

            # Prepare epic fields if this is an epic
            # This step now stores epic-specific fields in kwargs for post-creation update
            if issue_type.lower() == "epic":
                self._prepare_epic_fields(fields, summary, kwargs)

            # Prepare parent field if this is a subtask
            if issue_type.lower() == "subtask" or issue_type.lower() == "sub-task":
                self._prepare_parent_fields(fields, kwargs)
            # Allow parent field for all issue types when explicitly provided
            elif "parent" in kwargs:
                self._prepare_parent_fields(fields, kwargs)

            # Process **kwargs using the dynamic field map
            self._process_additional_fields(fields, kwargs_copy)

            # Create the issue
            response = self.jira.create_issue(fields=fields)
            if not isinstance(response, dict):
                msg = f"Unexpected return value type from `jira.create_issue`: {type(response)}"
                logger.error(msg)
                raise TypeError(msg)

            # Get the created issue key
            issue_key = response.get("key")
            if not issue_key:
                error_msg = "No issue key in response"
                raise ValueError(error_msg)

            # For Epics, perform the second step: update Epic-specific fields
            if issue_type.lower() == "epic":
                # Check if we have any stored Epic fields to update
                has_epic_fields = any(k.startswith("__epic_") for k in kwargs)
                if has_epic_fields:
                    logger.info(
                        f"Performing post-creation update for Epic {issue_key} with Epic-specific fields"
                    )
                    try:
                        return self.update_epic_fields(issue_key, kwargs)
                    except Exception as update_error:
                        logger.error(
                            f"Error during post-creation update of Epic {issue_key}: {str(update_error)}"
                        )
                        logger.info(
                            "Continuing with the original Epic that was successfully created"
                        )

            # Get the full issue data and convert to JiraIssue model
            issue_data = self.jira.get_issue(issue_key)
            if not isinstance(issue_data, dict):
                msg = f"Unexpected return value type from `jira.get_issue`: {type(issue_data)}"
                logger.error(msg)
                raise TypeError(msg)
            return JiraIssue.from_api_response(issue_data)

        except Exception as e:
            self._handle_create_issue_error(e, issue_type)
            raise  # Re-raise after logging

    def _prepare_epic_fields(
        self, fields: dict[str, Any], summary: str, kwargs: dict[str, Any]
    ) -> None:
        """
        Prepare fields for epic creation.

        This method delegates to the prepare_epic_fields method in EpicsMixin.

        Args:
            fields: The fields dictionary to update
            summary: The epic summary
            kwargs: Additional fields from the user
        """
        # Delegate to EpicsMixin.prepare_epic_fields
        # Since JiraFetcher inherits from both IssuesMixin and EpicsMixin,
        # this will correctly use the prepare_epic_fields method from EpicsMixin
        # which implements the two-step Epic creation approach
        self.prepare_epic_fields(fields, summary, kwargs)

    def _prepare_parent_fields(
        self, fields: dict[str, Any], kwargs: dict[str, Any]
    ) -> None:
        """
        Prepare fields for parent relationship.

        Args:
            fields: The fields dictionary to update
            kwargs: Additional fields from the user

        Raises:
            ValueError: If parent issue key is not specified for a subtask
        """
        if "parent" in kwargs:
            parent_key = kwargs.get("parent")
            if parent_key:
                fields["parent"] = {"key": parent_key}
            # Remove parent from kwargs to avoid double processing
            kwargs.pop("parent", None)
        elif "issuetype" in fields and fields["issuetype"]["name"].lower() in (
            "subtask",
            "sub-task",
        ):
            # Only raise error if issue type is subtask and parent is missing
            raise ValueError(
                "Issue type is a sub-task but parent issue key or id not specified. Please provide a 'parent' parameter with the parent issue key."
            )

    def _add_assignee_to_fields(self, fields: dict[str, Any], assignee: str) -> None:
        """
        Add assignee to issue fields.

        Args:
            fields: The fields dictionary to update
            assignee: The assignee account ID
        """
        # Cloud instance uses accountId
        if self.config.is_cloud:
            fields["assignee"] = {"accountId": assignee}
        else:
            # Server/DC might use name instead of accountId
            fields["assignee"] = {"name": assignee}

    def _process_additional_fields(
        self, fields: dict[str, Any], kwargs: dict[str, Any]
    ) -> None:
        """
        Processes keyword arguments to add standard or custom fields to the issue fields dictionary.
        Uses the dynamic field map from FieldsMixin to identify field IDs.

        Args:
            fields: The fields dictionary to update
            kwargs: Additional fields provided via **kwargs
        """
        # Ensure field map is loaded/cached
        field_map = (
            self._generate_field_map()
        )  # Ensure map is ready (method from FieldsMixin)
        if not field_map:
            logger.error(
                "Could not generate field map. Cannot process additional fields."
            )
            return

        # Process each kwarg
        # Iterate over a copy to allow modification of the original kwargs if needed elsewhere
        for key, value in kwargs.copy().items():
            # Skip keys used internally for epic/parent handling or explicitly handled args like assignee/components
            if key.startswith("__epic_") or key in ("parent", "assignee", "components"):
                continue

            normalized_key = key.lower()
            api_field_id = None

            # 1. Check if key is a known field name in the map
            if normalized_key in field_map:
                api_field_id = field_map[normalized_key]
                logger.debug(
                    f"Identified field '{key}' as '{api_field_id}' via name map."
                )

            # 2. Check if key is a direct custom field ID
            elif key.startswith("customfield_"):
                api_field_id = key
                logger.debug(f"Identified field '{key}' as direct custom field ID.")

            # 3. Check if key is a standard system field ID (like 'summary', 'priority')
            elif key in field_map:  # Check original case for system fields
                api_field_id = field_map[key]
                logger.debug(f"Identified field '{key}' as standard system field ID.")

            if api_field_id:
                # Get the full field definition for formatting context if needed
                field_definition = self.get_field_by_id(
                    api_field_id
                )  # From FieldsMixin
                formatted_value = self._format_field_value_for_write(
                    api_field_id, value, field_definition
                )
                if formatted_value is not None:  # Only add if formatting didn't fail
                    fields[api_field_id] = formatted_value
                    logger.debug(
                        f"Added field '{api_field_id}' from kwarg '{key}': {formatted_value}"
                    )
                else:
                    logger.warning(
                        f"Skipping field '{key}' due to formatting error or invalid value."
                    )
            else:
                # 4. Unrecognized key - log a warning and skip
                logger.warning(
                    f"Ignoring unrecognized field '{key}' passed via kwargs."
                )

    def _format_field_value_for_write(
        self, field_id: str, value: Any, field_definition: dict | None
    ) -> Any:
        """Formats field values for the Jira API."""
        # Get schema type if definition is available
        schema_type = (
            field_definition.get("schema", {}).get("type") if field_definition else None
        )
        # Prefer name from definition if available, else use ID for logging/lookup
        field_name_for_format = (
            field_definition.get("name", field_id) if field_definition else field_id
        )

        # Example formatting rules based on standard field names (use lowercase for comparison)
        normalized_name = field_name_for_format.lower()

        if normalized_name == "priority":
            if isinstance(value, str):
                return {"name": value}
            elif isinstance(value, dict) and ("name" in value or "id" in value):
                return value  # Assume pre-formatted
            else:
                logger.warning(
                    f"Invalid format for priority field: {value}. Expected string name or dict."
                )
                return None  # Or raise error
        elif normalized_name == "labels":
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                return value
            # Allow comma-separated string if passed via additional_fields JSON string
            elif isinstance(value, str):
                return [label.strip() for label in value.split(",") if label.strip()]
            else:
                logger.warning(
                    f"Invalid format for labels field: {value}. Expected list of strings or comma-separated string."
                )
                return None
        elif normalized_name in ["fixversions", "versions", "components"]:
            # These expect lists of objects, typically {"name": "..."} or {"id": "..."}
            if isinstance(value, list):
                formatted_list = []
                for item in value:
                    if isinstance(item, str):
                        formatted_list.append({"name": item})  # Convert simple strings
                    elif isinstance(item, dict) and ("name" in item or "id" in item):
                        formatted_list.append(item)  # Keep pre-formatted dicts
                    else:
                        logger.warning(
                            f"Invalid item format in {normalized_name} list: {item}"
                        )
                return formatted_list
            else:
                logger.warning(
                    f"Invalid format for {normalized_name} field: {value}. Expected list."
                )
                return None
        elif normalized_name == "reporter":
            if isinstance(value, str):
                try:
                    reporter_identifier = self._get_account_id(value)
                    if self.config.is_cloud:
                        return {"accountId": reporter_identifier}
                    else:
                        return {"name": reporter_identifier}
                except ValueError as e:
                    logger.warning(f"Could not format reporter field: {str(e)}")
                    return None
            elif isinstance(value, dict) and ("name" in value or "accountId" in value):
                return value  # Assume pre-formatted
            else:
                logger.warning(f"Invalid format for reporter field: {value}")
                return None
        # Add more formatting rules for other standard fields based on schema_type or field_id
        elif normalized_name == "duedate":
            if isinstance(value, str):  # Basic check, could add date validation
                return value
            else:
                logger.warning(
                    f"Invalid format for duedate field: {value}. Expected YYYY-MM-DD string."
                )
                return None
        elif schema_type == "datetime" and isinstance(value, str):
            # Example: Ensure datetime fields are in ISO format if needed by API
            try:
                dt = parse_date(value)  # Assuming parse_date handles various inputs
                return (
                    dt.isoformat() if dt else value
                )  # Return ISO or original if parse fails
            except Exception:
                logger.warning(
                    f"Could not parse datetime for field {field_id}: {value}"
                )
                return value  # Return original on error

        # Default: return value as is if no specific formatting needed/identified
        return value

    def _handle_create_issue_error(self, exception: Exception, issue_type: str) -> None:
        """
        Handle errors when creating an issue.

        Args:
            exception: The exception that occurred
            issue_type: The type of issue being created
        """
        error_msg = str(exception)

        # Check for specific error types
        if "epic name" in error_msg.lower() or "epicname" in error_msg.lower():
            logger.error(
                f"Error creating {issue_type}: {error_msg}. "
                "Try specifying an epic_name in the additional fields"
            )
        elif "customfield" in error_msg.lower():
            logger.error(
                f"Error creating {issue_type}: {error_msg}. "
                "This may be due to a required custom field"
            )
        else:
            logger.error(f"Error creating {issue_type}: {error_msg}")

    def update_issue(
        self,
        issue_key: str,
        fields: dict[str, Any] | None = None,
        **kwargs: Any,  # noqa: ANN401 - Dynamic field types are necessary for Jira API
    ) -> JiraIssue:
        """
        Update a Jira issue.

        Args:
            issue_key: The key of the issue to update
            fields: Dictionary of fields to update
            **kwargs: Additional fields to update. Special fields include:
                - attachments: List of file paths to upload as attachments
                - status: New status for the issue (handled via transitions)
                - assignee: New assignee for the issue

        Returns:
            JiraIssue model representing the updated issue

        Raises:
            Exception: If there is an error updating the issue
        """
        try:
            # Validate required fields
            if not issue_key:
                raise ValueError("Issue key is required")

            update_fields = fields or {}
            attachments_result = None

            # Process kwargs
            for key, value in kwargs.items():
                if key == "status":
                    # Status changes are handled separately via transitions
                    # Add status to fields so _update_issue_with_status can find it
                    update_fields["status"] = value
                    return self._update_issue_with_status(issue_key, update_fields)

                elif key == "attachments":
                    # Handle attachments separately - they're not part of fields update
                    if value and isinstance(value, list | tuple):
                        # We'll process attachments after updating fields
                        pass
                    else:
                        logger.warning(f"Invalid attachments value: {value}")

                elif key == "assignee":
                    # Handle assignee updates
                    try:
                        account_id = self._get_account_id(value)
                        self._add_assignee_to_fields(update_fields, account_id)
                    except ValueError as e:
                        logger.warning(f"Could not update assignee: {str(e)}")
                else:
                    # Process regular fields using _process_additional_fields
                    # Create a temporary dict with just this field
                    field_kwargs = {key: value}
                    self._process_additional_fields(update_fields, field_kwargs)

            # Update the issue fields
            if update_fields:
                self.jira.update_issue(
                    issue_key=issue_key, update={"fields": update_fields}
                )

            # Handle attachments if provided
            if "attachments" in kwargs and kwargs["attachments"]:
                try:
                    attachments_result = self.upload_attachments(
                        issue_key, kwargs["attachments"]
                    )
                    logger.info(
                        f"Uploaded attachments to {issue_key}: {attachments_result}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error uploading attachments to {issue_key}: {str(e)}"
                    )
                    # Continue with the update even if attachments fail

            # Get the updated issue data and convert to JiraIssue model
            issue_data = self.jira.get_issue(issue_key)
            if not isinstance(issue_data, dict):
                msg = f"Unexpected return value type from `jira.get_issue`: {type(issue_data)}"
                logger.error(msg)
                raise TypeError(msg)
            issue = JiraIssue.from_api_response(issue_data)

            # Add attachment results to the response if available
            if attachments_result:
                issue.custom_fields["attachment_results"] = attachments_result

            return issue

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error updating issue {issue_key}: {error_msg}")
            raise ValueError(f"Failed to update issue {issue_key}: {error_msg}") from e

    def _update_issue_with_status(
        self, issue_key: str, fields: dict[str, Any]
    ) -> JiraIssue:
        """
        Update an issue with a status change.

        Args:
            issue_key: The key of the issue to update
            fields: Dictionary of fields to update

        Returns:
            JiraIssue model representing the updated issue

        Raises:
            Exception: If there is an error updating the issue
        """
        # Extract status from fields and remove it for the standard update
        status = fields.pop("status", None)

        # First update any fields if needed
        if fields:
            self.jira.update_issue(issue_key=issue_key, fields=fields)  # type: ignore[call-arg]

        # If no status change is requested, return the issue
        if not status:
            issue_data = self.jira.get_issue(issue_key)
            if not isinstance(issue_data, dict):
                msg = f"Unexpected return value type from `jira.get_issue`: {type(issue_data)}"
                logger.error(msg)
                raise TypeError(msg)
            return JiraIssue.from_api_response(issue_data)

        # Get available transitions
        transitions = self.get_available_transitions(issue_key)

        # Extract status name or ID depending on what we received
        status_name = None
        status_id = None

        # Handle different input formats for status
        if isinstance(status, dict):
            # Dictionary format: {"name": "In Progress"} or {"id": "123"}
            status_name = status.get("name")
            status_id = status.get("id")
        elif isinstance(status, str):
            # String format: could be a name or an ID
            if status.isdigit():
                status_id = status
            else:
                status_name = status
        elif isinstance(status, int):
            # Integer format: must be an ID
            status_id = str(status)
        else:
            # Unknown format
            logger.warning(
                f"Unrecognized status format: {status} (type: {type(status)})"
            )
            status_name = str(status)

        # Log what we're searching for
        if status_name:
            logger.info(f"Looking for transition to status name: '{status_name}'")
        if status_id:
            logger.info(f"Looking for transition with ID: '{status_id}'")

        # Find the appropriate transition
        transition_id = None
        for transition in transitions:
            to_status = transition.get("to", {})
            transition_status_name = to_status.get("name", "")
            transition_status_id = to_status.get("id")

            # Match by name (case-insensitive)
            if (
                status_name
                and transition_status_name
                and transition_status_name.lower() == status_name.lower()
            ):
                transition_id = transition.get("id")
                logger.info(
                    f"Found transition ID {transition_id} matching status name '{status_name}'"
                )
                break

            # Match by ID
            if (
                status_id
                and transition_status_id
                and str(transition_status_id) == str(status_id)
            ):
                transition_id = transition.get("id")
                logger.info(
                    f"Found transition ID {transition_id} matching status ID '{status_id}'"
                )
                break

            # Direct transition ID match (if status is actually a transition ID)
            if status_id and str(transition.get("id", "")) == str(status_id):
                transition_id = transition.get("id")
                logger.info(f"Using direct transition ID {transition_id}")
                break

        if not transition_id:
            available_statuses = ", ".join(
                [t.get("to", {}).get("name", "") for t in transitions]
            )
            error_msg = (
                f"Could not find transition to status '{status}'. "
                f"Available statuses: {available_statuses}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Perform the transition
        logger.info(f"Performing transition with ID {transition_id}")
        self.jira.set_issue_status_by_transition_id(
            issue_key=issue_key,
            transition_id=(
                int(transition_id)
                if isinstance(transition_id, str) and transition_id.isdigit()
                else transition_id
            ),
        )

        # Get the updated issue data
        issue_data = self.jira.get_issue(issue_key)
        if not isinstance(issue_data, dict):
            msg = f"Unexpected return value type from `jira.get_issue`: {type(issue_data)}"
            logger.error(msg)
            raise TypeError(msg)
        return JiraIssue.from_api_response(issue_data)

    def delete_issue(self, issue_key: str) -> bool:
        """
        Delete a Jira issue.

        Args:
            issue_key: The key of the issue to delete

        Returns:
            True if the issue was deleted successfully

        Raises:
            Exception: If there is an error deleting the issue
        """
        try:
            self.jira.delete_issue(issue_key)
            return True
        except Exception as e:
            msg = f"Error deleting issue {issue_key}: {str(e)}"
            logger.error(msg)
            raise Exception(msg) from e

    def _log_available_fields(self, fields: list[dict]) -> None:
        """
        Log available fields for debugging.

        Args:
            fields: List of field definitions
        """
        logger.debug("Available Jira fields:")
        for field in fields:
            logger.debug(
                f"{field.get('id')}: {field.get('name')} ({field.get('schema', {}).get('type')})"
            )

    def _process_field_for_epic_data(
        self, field: dict, field_ids: dict[str, str]
    ) -> None:
        """
        Process a field for epic-related data.

        Args:
            field: The field data to process
            field_ids: Dictionary of field IDs to update
        """
        try:
            field_id = field.get("id")
            if not field_id:
                return

            # Skip non-custom fields
            if not field_id.startswith("customfield_"):
                return

            name = field.get("name", "").lower()

            # Look for field names related to epics
            if "epic" in name:
                if "link" in name:
                    field_ids["epic_link"] = field_id
                    field_ids["Epic Link"] = field_id
                elif "name" in name:
                    field_ids["epic_name"] = field_id
                    field_ids["Epic Name"] = field_id
        except Exception as e:
            logger.warning(f"Error processing field for epic data: {str(e)}")

    def get_available_transitions(self, issue_key: str) -> list[dict]:
        """
        Get all available transitions for an issue.

        Args:
            issue_key: The key of the issue

        Returns:
            List of available transitions

        Raises:
            Exception: If there is an error getting transitions
        """
        try:
            transitions = self.jira.get_issue_transitions(issue_key)
            return transitions
        except Exception as e:
            logger.error(f"Error getting transitions for issue {issue_key}: {str(e)}")
            raise Exception(
                f"Error getting transitions for issue {issue_key}: {str(e)}"
            ) from e

    def transition_issue(self, issue_key: str, transition_id: str) -> JiraIssue:
        """
        Transition an issue to a new status.

        Args:
            issue_key: The key of the issue
            transition_id: The ID of the transition to perform

        Returns:
            JiraIssue model with the updated issue data

        Raises:
            Exception: If there is an error transitioning the issue
        """
        try:
            self.jira.set_issue_status(
                issue_key=issue_key, status_name=transition_id, fields=None, update=None
            )
            return self.get_issue(issue_key)
        except Exception as e:
            logger.error(f"Error transitioning issue {issue_key}: {str(e)}")
            raise

    def batch_create_issues(
        self,
        issues: list[dict[str, Any]],
        validate_only: bool = False,
    ) -> list[JiraIssue]:
        """Create multiple Jira issues in a batch.

        Args:
            issues: List of issue dictionaries, each containing:
                - project_key (str): Key of the project
                - summary (str): Issue summary
                - issue_type (str): Type of issue
                - description (str, optional): Issue description
                - assignee (str, optional): Username of assignee
                - components (list[str], optional): List of component names
                - **kwargs: Additional fields specific to your Jira instance
            validate_only: If True, only validates the issues without creating them

        Returns:
            List of created JiraIssue objects

        Raises:
            ValueError: If any required fields are missing or invalid
            MCPAtlassianAuthenticationError: If authentication fails
        """
        if not issues:
            return []

        # Prepare issues for bulk creation
        issue_updates = []
        for issue_data in issues:
            try:
                # Extract and validate required fields
                project_key = issue_data.pop("project_key", None)
                summary = issue_data.pop("summary", None)
                issue_type = issue_data.pop("issue_type", None)
                description = issue_data.pop("description", "")
                assignee = issue_data.pop("assignee", None)
                components = issue_data.pop("components", None)

                # Validate required fields
                if not all([project_key, summary, issue_type]):
                    raise ValueError(
                        f"Missing required fields for issue: {project_key=}, {summary=}, {issue_type=}"
                    )

                # Prepare fields dictionary
                fields = {
                    "project": {"key": project_key},
                    "summary": summary,
                    "issuetype": {"name": issue_type},
                }

                # Add optional fields
                if description:
                    fields["description"] = description

                # Add assignee if provided
                if assignee:
                    try:
                        # _get_account_id now returns the correct identifier (accountId for cloud, name for server)
                        assignee_identifier = self._get_account_id(assignee)
                        self._add_assignee_to_fields(fields, assignee_identifier)
                    except ValueError as e:
                        logger.warning(f"Could not assign issue: {str(e)}")

                # Add components if provided
                if components:
                    if isinstance(components, list):
                        valid_components = [
                            comp_name.strip()
                            for comp_name in components
                            if isinstance(comp_name, str) and comp_name.strip()
                        ]
                        if valid_components:
                            fields["components"] = [
                                {"name": comp_name} for comp_name in valid_components
                            ]

                # Add any remaining custom fields
                self._process_additional_fields(fields, issue_data)

                if validate_only:
                    # For validation, just log the issue that would be created
                    logger.info(
                        f"Validated issue creation: {project_key} - {summary} ({issue_type})"
                    )
                    continue

                # Add to bulk creation list
                issue_updates.append({"fields": fields})

            except Exception as e:
                logger.error(f"Failed to prepare issue for creation: {str(e)}")
                if not issue_updates:
                    raise

        if validate_only:
            return []

        try:
            # Call Jira's bulk create endpoint
            response = self.jira.create_issues(issue_updates)
            if not isinstance(response, dict):
                msg = f"Unexpected return value type from `jira.create_issues`: {type(response)}"
                logger.error(msg)
                raise TypeError(msg)

            # Process results
            created_issues = []
            for issue_info in response.get("issues", []):
                issue_key = issue_info.get("key")
                if issue_key:
                    try:
                        # Fetch the full issue data
                        issue_data = self.jira.get_issue(issue_key)
                        if not isinstance(issue_data, dict):
                            msg = f"Unexpected return value type from `jira.get_issue`: {type(issue_data)}"
                            logger.error(msg)
                            raise TypeError(msg)

                        created_issues.append(
                            JiraIssue.from_api_response(
                                issue_data,
                                base_url=self.config.url
                                if hasattr(self, "config")
                                else None,
                            )
                        )
                    except Exception as e:
                        logger.error(
                            f"Error fetching created issue {issue_key}: {str(e)}"
                        )

            # Log any errors from the bulk creation
            errors = response.get("errors", [])
            if errors:
                for error in errors:
                    logger.error(f"Bulk creation error: {error}")

            return created_issues

        except Exception as e:
            logger.error(f"Error in bulk issue creation: {str(e)}")
            raise

    def batch_get_changelogs(
        self, issue_ids_or_keys: list[str], fields: list[str] | None = None
    ) -> list[JiraIssue]:
        """
        Get changelogs for multiple issues in a batch. Repeatly fetch data if necessary.

        Warning:
            This function is only avaiable on Jira Cloud.

        Args:
            issue_ids_or_keys: List of issue IDs or keys
            fields: Filter the changelogs by fields, e.g. ['status', 'assignee']. Default to None for all fields.

        Returns:
            List of JiraIssue objects that only contain changelogs and id
        """

        if not self.config.is_cloud:
            error_msg = "Batch get issue changelogs is only available on Jira Cloud."
            logger.error(error_msg)
            raise NotImplementedError(error_msg)

        # Get paged api results
        paged_api_results = self.get_paged(
            method="post",
            url=self.jira.resource_url("changelog/bulkfetch"),
            params_or_json={
                "fieldIds": fields,
                "issueIdsOrKeys": issue_ids_or_keys,
            },
        )

        # Save (issue_id, changelogs)
        issue_changelog_results: defaultdict[str, list[JiraChangelog]] = defaultdict(
            list
        )

        for api_result in paged_api_results:
            for data in api_result.get("issueChangeLogs", []):
                issue_id = data.get("issueId", "")
                changelogs = [
                    JiraChangelog.from_api_response(changelog_data)
                    for changelog_data in data.get("changeHistories", [])
                ]

                issue_changelog_results[issue_id].extend(changelogs)

        issues = [
            JiraIssue(id=issue_id, changelogs=changelogs)
            for issue_id, changelogs in issue_changelog_results.items()
        ]

        return issues
