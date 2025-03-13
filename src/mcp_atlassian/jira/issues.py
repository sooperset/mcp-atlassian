"""Module for Jira issue operations."""

import logging
from typing import Any

from ..models.jira import JiraIssue
from .users import UsersMixin
from .utils import parse_date_human_readable

logger = logging.getLogger("mcp-jira")


class IssuesMixin(UsersMixin):
    """Mixin for Jira issue operations."""

    def get_issue(
        self,
        issue_key: str,
        expand: str | None = None,
        comment_limit: int | str | None = 10,
    ) -> JiraIssue:
        """
        Get a Jira issue by key.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)
            expand: Fields to expand in the response
            comment_limit: Maximum number of comments to include, or "all"

        Returns:
            JiraIssue model with issue data and metadata

        Raises:
            Exception: If there is an error retrieving the issue
        """
        try:
            # Build expand parameter if provided
            expand_param = None
            if expand:
                expand_param = expand

            # Get the issue data
            issue = self.jira.issue(issue_key, expand=expand_param)
            if not issue:
                raise ValueError(f"Issue {issue_key} not found")

            # Extract fields data, safely handling None
            fields = issue.get("fields", {}) or {}

            # Get comments if needed
            comment_limit_int = self._normalize_comment_limit(comment_limit)
            comments = []
            if comment_limit_int is not None:
                comments = self._get_issue_comments_if_needed(
                    issue_key, comment_limit_int
                )

            # Add comments to the issue data for processing by the model
            if comments:
                if "comment" not in fields:
                    fields["comment"] = {}
                fields["comment"]["comments"] = comments

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
                    field_ids = self.get_jira_field_ids()

                    # Add epic link field if it doesn't exist
                    if (
                        "epic_link" in field_ids
                        and field_ids["epic_link"] not in fields
                    ):
                        fields[field_ids["epic_link"]] = epic_info["epic_key"]

                    # Add epic name field if it doesn't exist
                    if (
                        epic_info.get("epic_name")
                        and "epic_name" in field_ids
                        and field_ids["epic_name"] not in fields
                    ):
                        fields[field_ids["epic_name"]] = epic_info["epic_name"]
                except Exception as e:
                    logger.warning(f"Error setting epic fields: {str(e)}")

            # Update the issue data with the fields
            issue["fields"] = fields

            # Create and return the JiraIssue model
            return JiraIssue.from_api_response(issue, base_url=self.config.url)
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
                comments = self.jira.issue_get_comments(issue_key)
                if isinstance(comments, dict) and "comments" in comments:
                    comments = comments["comments"]

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
                field_ids = self.get_jira_field_ids()
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
                        epic = self.jira.issue(epic_key)
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

    def _parse_date(self, date_str: str) -> str:
        """
        Parse a date string to a formatted date.

        Args:
            date_str: The date string to parse

        Returns:
            Formatted date string
        """
        # Use the common utility function for consistent formatting
        return parse_date_human_readable(date_str)

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
                        comment_date = self._parse_date(comment_date)
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
                    account_id = self._get_account_id(assignee)
                    self._add_assignee_to_fields(fields, account_id)
                except ValueError as e:
                    logger.warning(f"Could not assign issue: {str(e)}")

            # Prepare epic fields if this is an epic
            if issue_type.lower() == "epic":
                self._prepare_epic_fields(fields, summary, kwargs)

            # Add custom fields
            self._add_custom_fields(fields, kwargs)

            # Create the issue
            response = self.jira.create_issue(fields=fields)

            # Get the created issue key
            issue_key = response.get("key")
            if not issue_key:
                error_msg = "No issue key in response"
                raise ValueError(error_msg)

            # Get the full issue data and convert to JiraIssue model
            issue_data = self.jira.issue(issue_key)
            return JiraIssue.from_api_response(issue_data)

        except Exception as e:
            self._handle_create_issue_error(e, issue_type)
            raise  # Re-raise after logging

    def _prepare_epic_fields(
        self, fields: dict[str, Any], summary: str, kwargs: dict[str, Any]
    ) -> None:
        """
        Prepare fields for epic creation.

        Args:
            fields: The fields dictionary to update
            summary: The epic summary
            kwargs: Additional fields from the user
        """
        # Get all field IDs
        field_ids = self.get_jira_field_ids()

        # Epic Name field
        epic_name_field = field_ids.get("Epic Name")
        if epic_name_field and "epic_name" not in kwargs:
            fields[epic_name_field] = summary

        # Override with user-provided epic name if available
        if "epic_name" in kwargs and epic_name_field:
            fields[epic_name_field] = kwargs["epic_name"]

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

    def _add_custom_fields(
        self, fields: dict[str, Any], kwargs: dict[str, Any]
    ) -> None:
        """
        Add custom fields to issue.

        Args:
            fields: The fields dictionary to update
            kwargs: Additional fields from the user
        """
        field_ids = self.get_jira_field_ids()

        # Process each kwarg
        for key, value in kwargs.items():
            if key in ("epic_name", "epic_link"):
                continue  # Handled separately

            # Check if this is a known field
            if key in field_ids:
                fields[field_ids[key]] = value
            elif key.startswith("customfield_"):
                # Direct custom field reference
                fields[key] = value

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
            **kwargs: Additional fields to update

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

            # Process kwargs
            for key, value in kwargs.items():
                if key == "status":
                    # Status changes are handled separately via transitions
                    # Add status to fields so _update_issue_with_status can find it
                    update_fields["status"] = value
                    return self._update_issue_with_status(issue_key, update_fields)

                if key == "assignee":
                    # Handle assignee updates
                    try:
                        account_id = self._get_account_id(value)
                        self._add_assignee_to_fields(update_fields, account_id)
                    except ValueError as e:
                        logger.warning(f"Could not update assignee: {str(e)}")
                else:
                    # Process regular fields
                    field_ids = self.get_jira_field_ids()
                    if key in field_ids:
                        update_fields[field_ids[key]] = value
                    elif key.startswith("customfield_"):
                        update_fields[key] = value
                    else:
                        update_fields[key] = value

            # Update the issue
            if update_fields:
                self.jira.update_issue(
                    issue_key=issue_key, update={"fields": update_fields}
                )

            # Get the updated issue data and convert to JiraIssue model
            issue_data = self.jira.issue(issue_key)
            return JiraIssue.from_api_response(issue_data)

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
            self.jira.update_issue(issue_key=issue_key, fields=fields)

        # If no status change is requested, return the issue
        if not status:
            issue_data = self.jira.issue(issue_key)
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
        issue_data = self.jira.issue(issue_key)
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
            logger.error(f"Error deleting issue {issue_key}: {str(e)}")
            raise Exception(f"Error deleting issue {issue_key}: {str(e)}") from e

    def get_jira_field_ids(self) -> dict[str, str]:
        """
        Get mappings of field names to IDs.

        Returns:
            Dictionary mapping field names to their IDs
        """
        # Use cached field IDs if available
        if hasattr(self, "_field_ids_cache") and self._field_ids_cache:
            return self._field_ids_cache

        # Get cached field IDs or fetch from server
        return self._get_cached_field_ids()

    def _get_cached_field_ids(self) -> dict[str, str]:
        """
        Get cached field IDs or fetch from server.

        Returns:
            Dictionary mapping field names to their IDs
        """
        # Initialize cache if needed
        if not hasattr(self, "_field_ids_cache"):
            self._field_ids_cache = {}

        # Return cache if not empty
        if self._field_ids_cache:
            return self._field_ids_cache

        # Fetch field IDs from server
        try:
            # Check if get_all_fields method exists before calling it
            if not hasattr(self.jira, "get_all_fields"):
                logger.warning("Jira object does not have 'get_all_fields' method")
                return {}

            fields = self.jira.get_all_fields()
            field_ids = {}

            for field in fields:
                name = field.get("name")
                field_id = field.get("id")
                if name and field_id:
                    field_ids[name] = field_id

            # Log available fields to help with debugging
            self._log_available_fields(fields)

            # Try to discover EPIC field IDs
            for field in fields:
                self._process_field_for_epic_data(field, field_ids)

            # Call the method from EpicsMixin through inheritance
            self._try_discover_fields_from_existing_epic(field_ids)

            # Cache the results
            self._field_ids_cache = field_ids
            return field_ids

        except Exception as e:
            logger.warning(f"Error getting field IDs: {str(e)}")
            return {}

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

    def _try_discover_fields_from_existing_epic(
        self, field_ids: dict[str, str]
    ) -> None:
        """
        Try to discover epic fields by analyzing existing epics and linked issues.

        Args:
            field_ids: Dictionary of field IDs to update
        """
        try:
            # Try to find an epic using JQL search
            jql = "issuetype = Epic ORDER BY created DESC"
            try:
                results = self.jira.jql(jql, limit=1)
            except AttributeError:
                # If jql method doesn't exist, try another approach or skip
                logger.debug("JQL method not available on this Jira instance")
                return

            if not results or not results.get("issues"):
                return

            # Get the first epic
            epic = results["issues"][0]
            epic_key = epic.get("key")

            if not epic_key:
                return

            # Try to find issues linked to this epic using JQL
            linked_jql = f'issue in linkedIssues("{epic_key}") ORDER BY created DESC'
            try:
                results = self.jira.jql(linked_jql, limit=10)
            except Exception as e:
                logger.debug(f"Error querying linked issues: {str(e)}")
                return

            if not results or not results.get("issues"):
                return

            # Check issues for potential epic link fields
            issues = results.get("issues", [])

            for issue in issues:
                fields = issue.get("fields", {})
                if not fields or not isinstance(fields, dict):
                    continue

                # Check each field for a potential epic link
                for field_id, value in fields.items():
                    if (
                        field_id.startswith("customfield_")
                        and value
                        and isinstance(value, str)
                    ):
                        # If it looks like a key (e.g., PRJ-123), it might be an epic link
                        if "-" in value and any(c.isdigit() for c in value):
                            field_ids["Epic Link"] = field_id
                            break

        except Exception as e:
            logger.debug(f"Error discovering epic fields: {str(e)}")
            # Continue with existing field_ids

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
            transitions = self.jira.issue_get_transitions(issue_key)
            if isinstance(transitions, dict) and "transitions" in transitions:
                return transitions["transitions"]
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
