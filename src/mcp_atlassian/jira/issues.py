"""Module for Jira issue operations."""

import logging
from datetime import datetime
from typing import Any

from ..document_types import Document
from .users import UsersMixin

logger = logging.getLogger("mcp-jira")


class IssuesMixin(UsersMixin):
    """Mixin for Jira issue operations."""

    def get_issue(
        self,
        issue_key: str,
        expand: str | None = None,
        comment_limit: int | str | None = 10,
    ) -> Document:
        """
        Get a Jira issue by key.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)
            expand: Fields to expand in the response
            comment_limit: Maximum number of comments to include, or "all"

        Returns:
            Document with issue content and metadata

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

            # Extract basic information
            summary = fields.get("summary", "")
            description = fields.get("description")
            desc = self._clean_text(description) if description is not None else ""

            # Handle status safely
            status = "Unknown"
            status_data = fields.get("status")
            if status_data is not None and isinstance(status_data, dict):
                status = status_data.get("name", "Unknown")

            # Handle issue type safely
            issue_type = "Unknown"
            issuetype_data = fields.get("issuetype")
            if issuetype_data is not None and isinstance(issuetype_data, dict):
                issue_type = issuetype_data.get("name", "Unknown")

            # Handle priority safely
            priority = "None"
            priority_data = fields.get("priority")
            if priority_data is not None and isinstance(priority_data, dict):
                priority = priority_data.get("name", "None")

            # Handle created date
            created_date = ""
            created = fields.get("created")
            if created is not None:
                created_date = self._parse_date(created)

            # Build metadata
            metadata = {
                "key": issue_key,
                "title": summary,
                "type": issue_type,
                "status": status,
                "created_date": created_date,
                "priority": priority,
                "link": f"{self.config.url.rstrip('/')}/browse/{issue_key}",
            }

            # Get comments if available
            if "comment" in expand_param if expand_param else False:
                comments_data = fields.get("comment", {})
                if comments_data and isinstance(comments_data, dict):
                    comments = comments_data.get("comments", [])
                    metadata["comments"] = [
                        {
                            "id": comment.get("id"),
                            "author": comment.get("author", {}).get(
                                "displayName", "Unknown"
                            ),
                            "body": self._clean_text(comment.get("body", "")),
                            "created": comment.get("created", ""),
                        }
                        for comment in comments
                    ]

            return Document(page_content=desc, metadata=metadata)

        except Exception as e:
            logger.error(f"Error retrieving issue {issue_key}: {str(e)}")
            raise Exception(f"Error retrieving issue {issue_key}: {str(e)}") from e

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

        fields = issue.get("fields", {})
        issue_type = fields.get("issuetype", {}).get("name", "").lower()

        # Check if this is an epic
        if issue_type == "epic":
            epic_info["is_epic"] = True
            epic_info["epic_name"] = fields.get(
                "customfield_10011", ""
            )  # Epic Name field

        # If not an epic, check for epic link
        elif (
            "customfield_10014" in fields and fields["customfield_10014"]
        ):  # Epic Link field
            epic_key = fields["customfield_10014"]
            epic_info["epic_key"] = epic_key

            # Try to get epic details
            try:
                epic = self.jira.get_issue(epic_key)
                epic_fields = epic.get("fields", {})
                epic_info["epic_name"] = epic_fields.get("customfield_10011", "")
                epic_info["epic_summary"] = epic_fields.get("summary", "")
            except Exception as e:
                logger.warning(f"Error getting epic details for {epic_key}: {str(e)}")

        return epic_info

    def _parse_date(self, date_str: str) -> str:
        """
        Parse a date string to a formatted date.

        Args:
            date_str: The date string to parse

        Returns:
            Formatted date string
        """
        try:
            # Parse ISO 8601 format
            date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            # Format: January 1, 2023
            return date_obj.strftime("%B %d, %Y")
        except (ValueError, TypeError):
            return date_str

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
    ) -> Document:
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
            Document with the created issue

        Raises:
            Exception: If there is an error creating the issue
        """
        try:
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

            # Return the newly created issue
            return self.get_issue(issue_key)

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
    ) -> Document:
        """
        Update a Jira issue.

        Args:
            issue_key: The key of the issue to update
            fields: Dictionary of fields to update
            **kwargs: Additional fields to update

        Returns:
            Document with the updated issue

        Raises:
            Exception: If there is an error updating the issue
        """
        try:
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
            self.jira.update_issue(issue_key, fields=update_fields)

            # Return the updated issue
            return self.get_issue(issue_key)

        except Exception as e:
            logger.error(f"Error updating issue {issue_key}: {str(e)}")
            raise Exception(f"Error updating issue {issue_key}: {str(e)}") from e

    def _update_issue_with_status(
        self, issue_key: str, fields: dict[str, Any]
    ) -> Document:
        """
        Update an issue with a status change.

        Args:
            issue_key: The key of the issue to update
            fields: Dictionary of fields to update

        Returns:
            Document with the updated issue

        Raises:
            Exception: If there is an error updating the issue
        """
        # First update any fields if needed
        if fields:
            self.jira.update_issue(issue_key, fields=fields)

        # Get the status from fields
        status = fields.get("status")
        if not status:
            return self.get_issue(issue_key)

        # Get available transitions
        transitions = self.get_available_transitions(issue_key)

        # Find the right transition
        transition_id = None
        for transition in transitions:
            if transition.get("name", "").lower() == status.lower():
                transition_id = transition.get("id")
                break

        if not transition_id:
            error_msg = (
                f"Could not find transition to status '{status}' for issue {issue_key}"
            )
            raise ValueError(error_msg)

        # Perform the transition
        return self.transition_issue(issue_key, transition_id)

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

            # Try to discover fields from existing epics
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
            field: The field definition
            field_ids: Dictionary of field IDs to update
        """
        name = field.get("name", "").lower()
        field_id = field.get("id")

        # Check for epic-related fields
        if "epic" in name and field_id:
            if "link" in name:
                field_ids["Epic Link"] = field_id
            elif "name" in name:
                field_ids["Epic Name"] = field_id

    def _try_discover_fields_from_existing_epic(
        self, field_ids: dict[str, str]
    ) -> None:
        """
        Try to discover field IDs from an existing epic.

        Args:
            field_ids: Dictionary of field IDs to update
        """
        # If we already have both epic fields, no need to search
        if "Epic Link" in field_ids and "Epic Name" in field_ids:
            return

        try:
            # Search for an epic
            results = self.jira.jql("issuetype = Epic", fields="*all", limit=1)
            issues = results.get("issues", [])

            if not issues:
                return

            # Get the first epic
            epic = issues[0]
            fields = epic.get("fields", {})

            # Check each field for epic-related data
            for field_id, value in fields.items():
                if field_id.startswith("customfield_"):
                    field_name = field_id.lower()

                    # Check for Epic Name field
                    if "Epic Name" not in field_ids and isinstance(value, str):
                        field_ids["Epic Name"] = field_id

            # Also try to find Epic Link by searching for issues linked to an epic
            if "Epic Link" not in field_ids:
                # Search for issues that might be linked to epics
                results = self.jira.jql("project is not empty", fields="*all", limit=10)
                issues = results.get("issues", [])

                for issue in issues:
                    fields = issue.get("fields", {})

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

    def link_issue_to_epic(self, issue_key: str, epic_key: str) -> Document:
        """
        Link an issue to an epic.

        Args:
            issue_key: The key of the issue to link
            epic_key: The key of the epic to link to

        Returns:
            Document with the updated issue

        Raises:
            Exception: If there is an error linking the issue
        """
        try:
            # Verify both keys exist
            self.jira.get_issue(issue_key)
            epic = self.jira.get_issue(epic_key)

            # Verify epic_key is actually an epic
            fields = epic.get("fields", {})
            issue_type = fields.get("issuetype", {}).get("name", "").lower()

            if issue_type != "epic":
                error_msg = f"{epic_key} is not an Epic"
                raise ValueError(error_msg)

            # Get the epic link field ID
            field_ids = self.get_jira_field_ids()
            epic_link_field = field_ids.get("Epic Link")

            if not epic_link_field:
                error_msg = "Could not determine Epic Link field"
                raise ValueError(error_msg)

            # Update the issue to link it to the epic
            update_fields = {epic_link_field: epic_key}
            self.jira.update_issue(issue_key, fields=update_fields)

            # Return the updated issue
            return self.get_issue(issue_key)

        except Exception as e:
            logger.error(f"Error linking {issue_key} to epic {epic_key}: {str(e)}")
            raise Exception(f"Error linking issue to epic: {str(e)}") from e

    def get_available_transitions(self, issue_key: str) -> list[dict]:
        """
        Get available transitions for an issue.

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

    def transition_issue(self, issue_key: str, transition_id: str) -> Document:
        """
        Transition an issue to a new status.

        Args:
            issue_key: The key of the issue
            transition_id: The ID of the transition to perform

        Returns:
            Document with the updated issue

        Raises:
            Exception: If there is an error transitioning the issue
        """
        try:
            self.jira.issue_transition(issue_key, transition_id)
            return self.get_issue(issue_key)
        except Exception as e:
            logger.error(f"Error transitioning issue {issue_key}: {str(e)}")
            raise Exception(f"Error transitioning issue {issue_key}: {str(e)}") from e
