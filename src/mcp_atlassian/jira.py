import logging
import os
import re
from datetime import datetime
from typing import Any

import requests
from atlassian import Jira

from .config import JiraConfig
from .document_types import Document
from .preprocessing import TextPreprocessor

# Configure logging
logger = logging.getLogger("mcp-jira")


class JiraFetcher:
    """Handles fetching and parsing content from Jira."""

    def __init__(self) -> None:
        """Initialize the Jira client."""
        url = os.getenv("JIRA_URL")

        if not url:
            error_msg = "Missing required JIRA_URL environment variable"
            raise ValueError(error_msg)

        # Initialize variables with default values
        username = ""
        token = ""
        personal_token = ""

        # Determine if this is a cloud or server installation based on URL
        is_cloud = url.endswith(".atlassian.net")

        if is_cloud:
            username = os.getenv("JIRA_USERNAME", "")
            token = os.getenv("JIRA_API_TOKEN", "")
            if not username or not token:
                error_msg = (
                    "Cloud authentication requires JIRA_USERNAME and JIRA_API_TOKEN"
                )
                raise ValueError(error_msg)
        else:
            # Server/Data Center authentication uses a Personal Access Token
            personal_token = os.getenv("JIRA_PERSONAL_TOKEN", "")
            if not personal_token:
                error_msg = (
                    "Server/Data Center authentication requires JIRA_PERSONAL_TOKEN"
                )
                raise ValueError(error_msg)

        # For self-signed certificates in on-premise installations
        verify_ssl = os.getenv("JIRA_SSL_VERIFY", "true").lower() != "false"

        self.config = JiraConfig(
            url=url,
            username=username,
            api_token=token,
            personal_token=personal_token,
            verify_ssl=verify_ssl,
        )

        # Initialize Jira client based on instance type
        if self.config.is_cloud:
            self.jira = Jira(
                url=self.config.url,
                username=self.config.username,
                password=self.config.api_token,  # API token is used as password
                cloud=True,
                verify_ssl=self.config.verify_ssl,
            )
        else:
            # For Server/Data Center, use token-based authentication
            # Note: The token param is used for Bearer token authentication
            # as per atlassian-python-api implementation
            self.jira = Jira(
                url=self.config.url,
                token=self.config.personal_token,
                cloud=False,
                verify_ssl=self.config.verify_ssl,
            )

        self.preprocessor = TextPreprocessor(self.config.url)

        # Field IDs cache
        self._field_ids_cache: dict[str, str] = {}

    def _clean_text(self, text: str) -> str:
        """
        Clean text content by:
        1. Processing user mentions and links
        2. Converting HTML/wiki markup to markdown
        """
        if not text:
            return ""

        return self.preprocessor.clean_jira_text(text)

    def _get_account_id(self, assignee: str) -> str:
        """
        Convert a username or display name to an account ID.

        Args:
            assignee: Username, email, or display name

        Returns:
            The account ID string
        """
        # Handle direct account ID assignment
        if assignee and assignee.startswith("accountid:"):
            return assignee.replace("accountid:", "")

        try:
            # First try direct user lookup
            account_id = self._lookup_user_directly(assignee)
            if account_id:
                return account_id

            # Fall back to project permission based search
            account_id = self._lookup_user_by_permissions(assignee)
            if account_id:
                return account_id

            # If we get here, we couldn't find a user
            logger.warning(f"No user found matching '{assignee}'")
            error_msg = f"No user found matching '{assignee}'"
            raise ValueError(error_msg)

        except Exception as e:
            logger.error(f"Error finding user '{assignee}': {str(e)}")
            error_msg = f"Could not resolve account ID for '{assignee}'"
            raise ValueError(error_msg) from e

    def _lookup_user_directly(self, username: str) -> str | None:
        """
        Look up a user directly by username or email.

        Args:
            username: The username or email to look up

        Returns:
            The account ID as a string if found, None otherwise
        """
        try:
            users = self.jira.user(username)
            if isinstance(users, dict):
                users = [users]

            account_id = users[0].get("accountId") if users else None
            if account_id:
                return str(account_id)  # Ensure we return a string
            else:
                logger.warning(
                    f"Direct user lookup failed for '{username}': "
                    "user found but no account ID present"
                )
                return None

        except IndexError:
            logger.warning(
                f"Direct user lookup failed for '{username}': "
                "user result has unexpected format"
            )
        except KeyError:
            logger.warning(
                f"Direct user lookup failed for '{username}': "
                "missing accountId in response"
            )
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Direct user lookup failed for '{username}': "
                f"invalid data format: {str(e)}"
            )
        except requests.RequestException as e:
            logger.warning(
                f"Direct user lookup failed for '{username}': API error: {str(e)}"
            )
        except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
            logger.warning(
                f"Direct user lookup failed for '{username}': "
                f"unexpected error: {str(e)}"
            )
            logger.debug(
                f"Full exception details for user lookup '{username}':", exc_info=True
            )

        return None

    def _lookup_user_by_permissions(self, username: str) -> str | None:
        """
        Look up a user by checking project permissions.

        Args:
            username: The username or email to look up

        Returns:
            The account ID as a string if found, None otherwise
        """
        users = self.jira.get_users_with_browse_permission_to_a_project(
            username=username
        )

        if not users:
            return None

        # Return the first matching user's account ID
        account_id = users[0].get("accountId")
        if not account_id or not isinstance(account_id, str):
            logger.warning(
                f"Permission-based user lookup failed for '{username}': "
                "invalid string format in response"
            )
            return None

        logger.info(f"Found account ID via browse permission lookup: {account_id}")
        return str(account_id)  # Explicit str conversion

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
        Create a new issue in Jira and return it as a Document.

        Args:
            project_key: The key of the project (e.g. 'PROJ')
            summary: Summary of the issue
            issue_type: Issue type (e.g. 'Task', 'Bug', 'Story')
            description: Issue description
            assignee: Email, full name, or account ID of the user to assign the issue to
            kwargs: Any other custom Jira fields

        Returns:
            Document representing the newly created issue

        Raises:
            ValueError: If required fields for the issue type cannot be determined
        """
        # Prepare base fields
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
            "description": self._markdown_to_jira(description),
        }

        # Handle epic-specific fields if needed
        if issue_type.lower() == "epic":
            self._prepare_epic_fields(fields, summary, kwargs)

        # Add assignee if provided
        if assignee:
            self._add_assignee_to_fields(fields, assignee)

        # Add any remaining custom fields
        self._add_custom_fields(fields, kwargs)

        # Create the issue
        try:
            response = self.jira.create_issue(fields=fields)
            issue_key = response["key"]
            logger.info(f"Created issue {issue_key}")
            return self.get_issue(issue_key)
        except Exception as e:
            self._handle_create_issue_error(e, issue_type)
            raise

    def _prepare_epic_fields(
        self, fields: dict[str, Any], summary: str, kwargs: dict[str, Any]
    ) -> None:
        """
        Prepare epic-specific fields for issue creation.

        Args:
            fields: The fields dictionary being prepared for issue creation
            summary: The issue summary that can be used as a default epic name
            kwargs: Additional fields provided by the caller
        """
        try:
            # Get the dynamic field IDs
            field_ids = self.get_jira_field_ids()
            logger.info(f"Discovered Jira field IDs for Epic creation: {field_ids}")

            # Handle Epic Name - might be required in some instances, not in others
            if "epic_name" in field_ids:
                epic_name = kwargs.pop(
                    "epic_name", summary
                )  # Use summary as default if not provided
                fields[field_ids["epic_name"]] = epic_name
                logger.info(
                    f"Setting Epic Name field {field_ids['epic_name']} to: {epic_name}"
                )

            # Handle Epic Color if the field was discovered
            if "epic_color" in field_ids:
                epic_color = (
                    kwargs.pop("epic_color", None)
                    or kwargs.pop("epic_colour", None)
                    or "green"
                )
                fields[field_ids["epic_color"]] = epic_color
                logger.info(
                    f"Setting Epic Color field {field_ids['epic_color']} "
                    f"to: {epic_color}"
                )

            # Pass through any explicitly provided custom fields
            # that might be instance-specific
            for field_key, field_value in list(kwargs.items()):
                if field_key.startswith("customfield_"):
                    fields[field_key] = field_value
                    kwargs.pop(field_key)
                    logger.info(
                        f"Using explicitly provided custom field {field_key}: "
                        f"{field_value}"
                    )

            # Warn if epic_name field is required but wasn't discovered
            if "epic_name" not in field_ids:
                logger.warning(
                    "Epic Name field not found in Jira schema. "
                    "If your Jira instance requires it, please provide "
                    "the customfield_* ID directly."
                )
        except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
            logger.error(f"Error preparing Epic-specific fields: {str(e)}")
            # Continue with creation anyway, as some instances might not
            # require special fields

    def _add_assignee_to_fields(self, fields: dict[str, Any], assignee: str) -> None:
        """
        Add assignee information to the fields dictionary.

        Args:
            fields: The fields dictionary being prepared for issue creation
            assignee: The assignee value to process
        """
        account_id = self._get_account_id(assignee)
        fields["assignee"] = {"accountId": account_id}

    def _add_custom_fields(
        self, fields: dict[str, Any], kwargs: dict[str, Any]
    ) -> None:
        """
        Add any remaining custom fields to the fields dictionary.

        Args:
            fields: The fields dictionary being prepared for issue creation
            kwargs: Additional fields provided by the caller
        """
        # Remove assignee from additional_fields if present to avoid conflicts
        if "assignee" in kwargs:
            logger.warning(
                "Assignee found in additional_fields - this will be ignored. "
                "Please use the assignee parameter instead."
            )
            kwargs.pop("assignee")

        # Add remaining kwargs to fields
        for key, value in kwargs.items():
            fields[key] = value

        # Ensure description is in Jira format
        if "description" in fields and fields["description"]:
            fields["description"] = self._markdown_to_jira(fields["description"])

    def _handle_create_issue_error(self, exception: Exception, issue_type: str) -> None:
        """
        Handle errors that occur during issue creation with better error messages.

        Args:
            exception: The exception that was raised
            issue_type: The type of issue being created
        """
        error_msg = str(exception)

        # Provide more helpful error messages for common issues
        if issue_type.lower() == "epic" and "customfield_" in error_msg:
            # Handle the case where a specific Epic field is required but missing
            missing_field_match = re.search(
                r"(?:Field '(customfield_\d+)'|'(customfield_\d+)' cannot be set)",
                error_msg,
            )
            if missing_field_match:
                field_id = missing_field_match.group(1) or missing_field_match.group(2)
                logger.error(
                    f"Failed to create Epic: Your Jira instance requires field "
                    f"'{field_id}'. "
                    "This is typically the Epic Name field. Try setting this field "
                    "explicitly using "
                    f"'{field_id}': 'Epic Name Value' in the "
                    "additional_fields parameter."
                )
            else:
                logger.error(
                    "Failed to create Epic: Your Jira instance has custom field "
                    "requirements. You may need to provide specific custom fields "
                    f"for Epics in your instance. Original error: {error_msg}"
                )
        else:
            logger.error(f"Error creating issue: {error_msg}")

    def update_issue(
        self,
        issue_key: str,
        fields: dict[str, Any] | None = None,
        **kwargs: Any,  # noqa: ANN401 - Dynamic field types are necessary for Jira API
    ) -> Document:
        """
        Update an existing Jira issue.

        Args:
            issue_key: The key of the issue to update
            fields: Fields to update in the Jira API format
            **kwargs: Additional fields to update

        Returns:
            Document with updated issue info
        """
        # Ensure we have a fields dictionary
        if fields is None:
            fields = {}

        # Process any custom fields passed via kwargs
        if kwargs:
            # Combine any fields that might be in kwargs into our fields dict
            self._add_custom_fields(fields, kwargs)

        # Check if status is being updated
        if "status" in fields:
            return self._update_issue_with_status(issue_key, fields)

        # Regular update (no status change)
        try:
            logger.info(f"Updating issue {issue_key} with fields {fields}")
            self.jira.issue_update(issue_key, fields=fields)
            # Return the updated issue
            return self.get_issue(issue_key)
        except Exception as e:
            error_msg = f"Error updating issue {issue_key}: {str(e)}"
            logger.error(error_msg)
            raise

    def _update_issue_with_status(
        self, issue_key: str, fields: dict[str, Any]
    ) -> Document:
        """
        Update an issue that includes a status change, using transitions.

        Args:
            issue_key: The key of the issue to update
            fields: Fields to update, including status

        Returns:
            Document with updated issue info
        """
        target_status = fields.pop("status")
        logger.info(
            f"Updating issue {issue_key} with status change to '{target_status}'"
        )

        # Get available transitions
        transitions = self.jira.get_issue_transitions(issue_key)

        # Find the transition that matches the target status
        transition_id = None
        for transition in transitions.get("transitions", []):
            if (
                transition.get("to", {}).get("name", "").lower()
                == target_status.lower()
            ):
                transition_id = transition["id"]
                break

        if not transition_id:
            error_msg = (
                f"No transition found for status '{target_status}' on issue {issue_key}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Create transition data
        transition_data = {"transition": {"id": transition_id}}

        # Add remaining fields if any
        if fields:
            transition_data["fields"] = fields

        # Execute the transition
        self.jira.issue_transition(issue_key, transition_data)

        # Return the updated issue
        return self.get_issue(issue_key)

    def get_jira_field_ids(self) -> dict[str, str]:
        """
        Dynamically discover Jira field IDs relevant to Epic linking.

        This method queries the Jira API to find the correct custom field IDs
        for Epic-related fields, which can vary between different Jira instances.

        Returns:
            Dictionary mapping field names to their IDs
            (e.g., {'epic_link': 'customfield_10014', 'epic_name': 'customfield_10011'})
        """
        try:
            # Check if we've already cached the field IDs
            cached_fields = self._get_cached_field_ids()
            if cached_fields:
                return cached_fields

            # Fetch all fields from Jira API
            fields = self.jira.fields()
            field_ids: dict[str, str] = {}

            # Log all fields for debugging
            self._log_available_fields(fields)

            # Process each field to identify Epic-related fields
            for field in fields:
                self._process_field_for_epic_data(field, field_ids)

            # Cache the results for future use
            self._field_ids_cache = field_ids

            # If we couldn't find certain key fields, try alternative approaches
            if "epic_name" not in field_ids or "epic_link" not in field_ids:
                logger.warning(
                    "Could not find all essential Epic fields through schema. "
                    "This may cause issues with Epic operations."
                )

                # Try to find fields by looking at an existing Epic if possible
                self._try_discover_fields_from_existing_epic(field_ids)

            return field_ids

        except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
            logger.error(f"Error discovering Jira field IDs: {str(e)}")
            # Return an empty dict as fallback
            return {}

    def _get_cached_field_ids(self) -> dict[str, str]:
        """
        Retrieve cached field IDs if available.

        Returns:
            Dictionary of cached field IDs or empty dict if no cache exists
        """
        if hasattr(self, "_field_ids_cache"):
            return self._field_ids_cache
        return {}

    def _log_available_fields(self, fields: list[dict]) -> None:
        """
        Log all available Jira fields for debugging purposes.

        Args:
            fields: List of field definitions from Jira API
        """
        all_field_names = [
            f"{field.get('name', '')} ({field.get('id', '')})" for field in fields
        ]
        logger.debug(f"All available Jira fields: {all_field_names}")

    def _process_field_for_epic_data(
        self, field: dict, field_ids: dict[str, str]
    ) -> None:
        """
        Process a single field to identify if it's an Epic-related field
        and add to field_ids.

        Args:
            field: Field definition from Jira API
            field_ids: Dictionary to update with identified fields
        """
        field_name = field.get("name", "").lower()
        original_name = field.get("name", "")
        field_id = field.get("id", "")
        field_schema = field.get("schema", {})
        field_type = field_schema.get("type", "")
        field_custom = field_schema.get("custom", "")

        # Epic Link field - used to link issues to epics
        if (
            "epic link" in field_name
            or field_custom == "com.pyxis.greenhopper.jira:gh-epic-link"
            or field_type == "any"
        ) and field_id:
            self.epic_link_field_id = field_id
            field_ids["epic_link"] = field_id
            logger.info(f"Found Epic Link field: {original_name} ({field_id})")

        # Epic Name field - used for the title of epics
        if (
            "epic name" in field_name
            or "epic-name" in field_name
            or original_name == "Epic Name"
            or field_custom == "com.pyxis.greenhopper.jira:gh-epic-label"
        ):
            field_ids["epic_name"] = field_id
            logger.info(f"Found Epic Name field: {original_name} ({field_id})")

        # Parent field - sometimes used instead of Epic Link
        elif (
            field_name == "parent"
            or field_name == "parent link"
            or original_name == "Parent Link"
        ):
            field_ids["parent"] = field_id
            logger.info(f"Found Parent field: {original_name} ({field_id})")

        # Epic Status field
        elif "epic status" in field_name or original_name == "Epic Status":
            field_ids["epic_status"] = field_id
            logger.info(f"Found Epic Status field: {original_name} ({field_id})")

        # Epic Color field
        elif (
            "epic colour" in field_name
            or "epic color" in field_name
            or original_name == "Epic Colour"
            or original_name == "Epic Color"
            or field_custom == "com.pyxis.greenhopper.jira:gh-epic-color"
        ):
            field_ids["epic_color"] = field_id
            logger.info(f"Found Epic Color field: {original_name} ({field_id})")

        # Try to detect any other fields that might be related to Epics
        elif ("epic" in field_name or "epic" in field_custom) and not any(
            k in field_ids.values() for k in [field_id]
        ):
            key = f"epic_{field_name.replace(' ', '_')}"
            field_ids[key] = field_id
            logger.info(
                f"Found additional Epic-related field: {original_name} ({field_id})"
            )

    def _try_discover_fields_from_existing_epic(self, field_ids: dict) -> None:
        """
        Attempt to discover Epic fields by examining an existing Epic issue.
        This is a fallback method when we can't find fields through the schema.

        Args:
            field_ids: Existing field_ids dictionary to update
        """
        try:
            # Find an Epic in the system
            epics_jql = "issuetype = Epic ORDER BY created DESC"
            results = self.jira.jql(epics_jql, limit=1)

            if not results.get("issues"):
                logger.warning("No existing Epics found to analyze field structure")
                return

            epic = results["issues"][0]
            epic_key = epic.get("key")

            logger.info(
                f"Analyzing existing Epic {epic_key} to discover field structure"
            )

            # Examine the fields of this Epic
            fields = epic.get("fields", {})
            for field_id, field_value in fields.items():
                if field_id.startswith("customfield_") and field_value is not None:
                    # Look for fields with non-null values that might be Epic-related
                    if (
                        "epic_name" not in field_ids
                        and isinstance(field_value, str)
                        and field_id not in field_ids.values()
                    ):
                        logger.info(
                            f"Potential Epic Name field discovered: {field_id} "
                            f"with value {field_value}"
                        )
                        if len(field_value) < 100:  # Epic names are typically short
                            field_ids["epic_name"] = field_id

                    # Color values are often simple strings like "green", "blue", etc.
                    if (
                        "epic_color" not in field_ids
                        and isinstance(field_value, str)
                        and field_id not in field_ids.values()
                    ):
                        colors = [
                            "green",
                            "blue",
                            "red",
                            "yellow",
                            "orange",
                            "purple",
                            "gray",
                            "grey",
                            "teal",
                        ]
                        if field_value.lower() in colors:
                            logger.info(
                                f"Potential Epic Color field discovered: {field_id} "
                                f"with value {field_value}"
                            )
                            field_ids["epic_color"] = field_id

        except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
            logger.warning(
                f"Could not discover Epic fields from existing Epics: {str(e)}"
            )

    def link_issue_to_epic(self, issue_key: str, epic_key: str) -> Document:
        """
        Link an issue to an epic.

        Args:
            issue_key: The key of the issue to link
            epic_key: The key of the epic to link to

        Returns:
            Document with updated issue info
        """
        # Try to get the field IDs - if we haven't initialized them yet
        field_ids = self.get_jira_field_ids()

        # Check if we've identified the epic link field
        if not field_ids.get("Epic Link"):
            logger.error("Cannot link issue to epic: Epic Link field not found")
            # Try to discover the fields by examining an existing epic
            self._try_discover_fields_from_existing_epic(field_ids)

        # Multiple attempts to link the issue using different field names
        attempts = [
            # Standard Jira Software method
            lambda: self.update_issue(
                issue_key,
                fields={
                    k: epic_key for k in [field_ids.get("Epic Link")] if k is not None
                },
            ),
            # Advanced Roadmaps method using Epic Name
            lambda: self.update_issue(
                issue_key,
                fields={
                    k: epic_key for k in [field_ids.get("Epic Name")] if k is not None
                },
            ),
            # Using the custom field directly
            lambda: self.update_issue(
                issue_key, fields={"customfield_10014": epic_key}
            ),
        ]

        # Try each method
        for attempt_fn in attempts:
            try:
                return attempt_fn()
            except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
                logger.error(
                    f"Failed to link issue {issue_key} to epic {epic_key}: {str(e)}"
                )

        # If we get here, none of our attempts worked
        error_msg = (
            f"Couldn't link issue {issue_key} to epic {epic_key}. "
            "Your Jira instance might use a different field for epic links."
        )
        raise ValueError(error_msg)

    def delete_issue(self, issue_key: str) -> bool:
        """
        Delete an existing issue.

        Args:
            issue_key: The key of the issue (e.g. 'PROJ-123')

        Returns:
            True if delete succeeded, otherwise raise an exception
        """
        try:
            self.jira.delete_issue(issue_key)
            return True
        except Exception as e:
            logger.error(f"Error deleting issue {issue_key}: {str(e)}")
            raise

    def _parse_date(self, date_str: str) -> str:
        """
        Parse a date string into a consistent format (YYYY-MM-DD).

        Args:
            date_str: The date string to parse

        Returns:
            Formatted date string
        """
        # Handle various formats of date strings from Jira
        try:
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return date.strftime("%Y-%m-%d")
        except ValueError as e:
            # This handles parsing errors in the date format
            logger.warning(f"Invalid date format for {date_str}: {e}")
            return date_str
        except AttributeError as e:
            # This handles cases where date_str isn't a string
            logger.warning(f"Invalid date type {type(date_str)}: {e}")
            return str(date_str)
        except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
            logger.warning(f"Error parsing date {date_str}: {e}")
            logger.debug("Full exception details for date parsing:", exc_info=True)
            return date_str

    def get_issue(
        self,
        issue_key: str,
        expand: str | None = None,
        comment_limit: int | str | None = 10,
    ) -> Document:
        """
        Get a single issue with all its details.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            expand: Optional fields to expand
            comment_limit: Maximum number of comments to include
                          (None for no comments, defaults to 10)
                          Can be an integer or a string that can be converted
                          to an integer.

        Returns:
            Document containing issue content and metadata
        """
        try:
            # Fetch the issue from Jira
            issue = self.jira.issue(issue_key, expand=expand)

            # Process and normalize the comment limit
            comment_limit = self._normalize_comment_limit(comment_limit)

            # Get the issue description and comments
            description = self._clean_text(issue["fields"].get("description", ""))
            comments = self._get_issue_comments_if_needed(issue_key, comment_limit)

            # Get Epic information if applicable
            epic_info = self._extract_epic_information(issue)

            # Format the created date properly
            created_date = self._parse_date(issue["fields"]["created"])

            # Generate the content for the document
            content = self._format_issue_content(
                issue_key, issue, description, comments, created_date, epic_info
            )

            # Create the metadata for the document
            metadata = self._create_issue_metadata(
                issue_key, issue, comments, created_date, epic_info
            )

            return Document(page_content=content, metadata=metadata)

        except Exception as e:
            logger.error(f"Error fetching issue {issue_key}: {str(e)}")
            raise

    def _normalize_comment_limit(self, comment_limit: int | str | None) -> int | None:
        """
        Convert comment_limit to int if it's a string.

        Args:
            comment_limit: The comment limit value to normalize

        Returns:
            Normalized comment limit as int or None
        """
        if comment_limit is not None and isinstance(comment_limit, str):
            try:
                return int(comment_limit)
            except ValueError:
                logger.warning(
                    f"Invalid comment_limit value: {comment_limit}. "
                    "Using default of 10."
                )
                return 10
        return comment_limit

    def _get_issue_comments_if_needed(
        self, issue_key: str, comment_limit: int | None
    ) -> list[dict]:
        """
        Get comments for an issue if a valid limit is specified.

        Args:
            issue_key: The issue key to get comments for
            comment_limit: Maximum number of comments to get

        Returns:
            List of comment dictionaries or empty list if no comments needed
        """
        if comment_limit is not None and comment_limit > 0:
            return self.get_issue_comments(issue_key, limit=comment_limit)
        return []

    def _extract_epic_information(self, issue: dict) -> dict[str, str | None]:
        """
        Extract epic information from issue data.

        Args:
            issue: Issue data from Jira API

        Returns:
            Dictionary with epic_key and epic_name
        """
        epic_info: dict[str, str | None] = {"epic_key": None, "epic_name": None}

        # Try both "Epic Link" and "Parent"
        if "customfield_10014" in issue["fields"]:
            epic_info["epic_key"] = issue["fields"]["customfield_10014"]
        elif (
            "parent" in issue["fields"]
            and issue["fields"]["parent"]["fields"]["issuetype"]["name"] == "Epic"
        ):
            epic_info["epic_key"] = issue["fields"]["parent"]["key"]
            epic_info["epic_name"] = issue["fields"]["parent"]["fields"]["summary"]

        # Look for Epic Name if we have an Epic Key but no name yet
        if epic_info["epic_key"] and not epic_info["epic_name"]:
            try:
                epic = self.jira.issue(epic_info["epic_key"])
                epic_info["epic_name"] = epic["fields"]["summary"]
            except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
                logger.warning(f"Error fetching epic details: {str(e)}")

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
        if epic_info["epic_key"]:
            content += f"Epic: {epic_info['epic_key']}"
            if epic_info["epic_name"]:
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

    def _create_issue_metadata(
        self,
        issue_key: str,
        issue: dict,
        comments: list[dict],
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
        # Basic metadata
        metadata = {
            "key": issue_key,
            "title": issue["fields"].get("summary", ""),
            "type": issue["fields"]["issuetype"]["name"],
            "status": issue["fields"]["status"]["name"],
            "created_date": created_date,
            "priority": issue["fields"].get("priority", {}).get("name", "None"),
            "link": f"{self.config.url.rstrip('/')}/browse/{issue_key}",
        }

        # Add Epic information to metadata if available
        if epic_info["epic_key"]:
            metadata["epic_key"] = epic_info["epic_key"]
            if epic_info["epic_name"]:
                metadata["epic_name"] = epic_info["epic_name"]

        # Add comments to metadata if present
        if comments:
            metadata["comments"] = comments

        return metadata

    def search_issues(
        self,
        jql: str,
        fields: str = "*all",
        start: int = 0,
        limit: int = 50,
        expand: str | None = None,
    ) -> list[Document]:
        """
        Search for issues using JQL (Jira Query Language).

        Args:
            jql: JQL query string
            fields: Fields to return (comma-separated string or "*all")
            start: Starting index
            limit: Maximum issues to return
            expand: Optional items to expand (comma-separated)

        Returns:
            List of Documents representing the search results
        """
        try:
            issues = self.jira.jql(
                jql, fields=fields, start=start, limit=limit, expand=expand
            )
            documents = []

            for issue in issues.get("issues", []):
                issue_key = issue["key"]
                fields_data = issue.get("fields", {})

                # Safely handle fields that might not be included in the response
                summary = fields_data.get("summary", "")

                # Handle issuetype field with fallback to "Unknown" if missing
                issue_type = "Unknown"
                issuetype_data = fields_data.get("issuetype")
                if issuetype_data is not None:
                    issue_type = issuetype_data.get("name", "Unknown")

                # Handle status field with fallback to "Unknown" if missing
                status = "Unknown"
                status_data = fields_data.get("status")
                if status_data is not None:
                    status = status_data.get("name", "Unknown")

                # Process description field
                description = fields_data.get("description")
                desc = self._clean_text(description) if description is not None else ""

                # Process created date field
                created_date = ""
                created = fields_data.get("created")
                if created is not None:
                    created_date = self._parse_date(created)

                # Process priority field
                priority = "None"
                priority_data = fields_data.get("priority")
                if priority_data is not None:
                    priority = priority_data.get("name", "None")

                # Add basic metadata
                metadata = {
                    "key": issue_key,
                    "title": summary,
                    "type": issue_type,
                    "status": status,
                    "created_date": created_date,
                    "priority": priority,
                    "link": f"{self.config.url.rstrip('/')}/browse/{issue_key}",
                }

                # Prepare content
                content = desc if desc else f"{summary} [{status}]"

                documents.append(Document(page_content=content, metadata=metadata))

            return documents
        except Exception as e:
            logger.error(f"Error searching issues with JQL '{jql}': {str(e)}")
            raise

    def get_epic_issues(self, epic_key: str, limit: int = 50) -> list[Document]:
        """
        Get all issues linked to a specific epic.

        Args:
            epic_key: The key of the epic (e.g. 'PROJ-123')
            limit: Maximum number of issues to return

        Returns:
            List of Documents representing the issues linked to the epic
        """
        try:
            # First, check if the issue is an Epic
            epic = self.jira.issue(epic_key)
            fields_data = epic.get("fields", {})

            # Safely check if the issue is an Epic
            issue_type = None
            issuetype_data = fields_data.get("issuetype")
            if issuetype_data is not None:
                issue_type = issuetype_data.get("name", "")

            if issue_type != "Epic":
                error_msg = (
                    f"Issue {epic_key} is not an Epic, it is a "
                    f"{issue_type or 'unknown type'}"
                )
                raise ValueError(error_msg)

            # Get the dynamic field IDs for this Jira instance
            field_ids = self.get_jira_field_ids()

            # Build JQL queries based on discovered field IDs
            jql_queries = []

            # Add queries based on discovered fields
            if "parent" in field_ids:
                jql_queries.append(f"parent = {epic_key}")

            if "epic_link" in field_ids:
                field_name = field_ids["epic_link"]
                jql_queries.append(f'"{field_name}" = {epic_key}')
                jql_queries.append(f'"{field_name}" ~ {epic_key}')

            # Add standard fallback queries
            jql_queries.extend(
                [
                    f"parent = {epic_key}",  # Common in most instances
                    f"'Epic Link' = {epic_key}",  # Some instances
                    f"'Epic' = {epic_key}",  # Some instances
                    f"issue in childIssuesOf('{epic_key}')",  # Some instances
                ]
            )

            # Try each query until we get results or run out of options
            documents = []
            for jql in jql_queries:
                try:
                    logger.info(f"Trying to get epic issues with JQL: {jql}")
                    documents = self.search_issues(jql, limit=limit)
                    if documents:
                        return documents
                except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
                    logger.info(f"Failed to get epic issues with JQL '{jql}': {str(e)}")
                    continue

            # If we've tried all queries and got no results, return an empty list
            # but also log a warning that we might be missing the right field
            if not documents:
                logger.warning(
                    f"Couldn't find issues linked to epic {epic_key}. "
                    "Your Jira instance might use a different field for epic links."
                )

            return documents

        except Exception as e:
            logger.error(f"Error getting issues for epic {epic_key}: {str(e)}")
            raise

    def get_project_issues(
        self, project_key: str, start: int = 0, limit: int = 50
    ) -> list[Document]:
        """
        Get all issues for a project.

        Args:
            project_key: The project key
            start: Starting index
            limit: Maximum results to return

        Returns:
            List of Documents containing project issues
        """
        jql = f"project = {project_key} ORDER BY created DESC"
        return self.search_issues(jql, start=start, limit=limit)

    def get_current_user_account_id(self) -> str:
        """
        Get the account ID of the current user.

        Returns:
            String with the account ID
        """
        try:
            user = self.jira.myself()
            account_id = user.get("accountId")
            if not account_id:
                error_msg = "No account ID found in user profile"
                raise ValueError(error_msg)
            return str(account_id)  # Ensure we return a string
        except Exception as e:
            logger.error(f"Error getting current user account ID: {str(e)}")
            error_msg = f"Failed to get current user account ID: {str(e)}"
            raise ValueError(error_msg) from e

    def get_issue_comments(self, issue_key: str, limit: int = 50) -> list[dict]:
        """
        Get comments for a specific issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            limit: Maximum number of comments to return

        Returns:
            List of comments with author, creation date, and content
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
            raise

    def add_comment(self, issue_key: str, comment: str) -> dict:
        """
        Add a comment to an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            comment: Comment text to add (in Markdown format)

        Returns:
            The created comment details
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
            raise

    def _parse_time_spent(self, time_spent: str) -> int:
        """
        Parse time spent string into seconds.

        Args:
            time_spent: Time spent string (e.g. 1h 30m, 1d, etc.)

        Returns:
            Time spent in seconds
        """
        # Base case for direct specification in seconds
        if time_spent.endswith("s"):
            try:
                return int(time_spent[:-1])
            except ValueError:
                pass

        total_seconds = 0
        time_units = {
            "w": 7 * 24 * 60 * 60,  # weeks to seconds
            "d": 24 * 60 * 60,  # days to seconds
            "h": 60 * 60,  # hours to seconds
            "m": 60,  # minutes to seconds
        }

        # Regular expression to find time components like 1w, 2d, 3h, 4m
        pattern = r"(\d+)([wdhm])"
        matches = re.findall(pattern, time_spent)

        for value, unit in matches:
            # Convert value to int and multiply by the unit in seconds
            seconds = int(value) * time_units[unit]
            total_seconds += seconds

        if total_seconds == 0:
            # If we couldn't parse anything, try using the raw value
            try:
                return int(float(time_spent))  # Convert to float first, then to int
            except ValueError:
                # If all else fails, default to 60 seconds (1 minute)
                logger.warning(
                    f"Could not parse time: {time_spent}, defaulting to 60 seconds"
                )
                return 60

        return total_seconds

    def add_worklog(
        self,
        issue_key: str,
        time_spent: str,
        comment: str | None = None,
        started: str | None = None,
        original_estimate: str | None = None,
        remaining_estimate: str | None = None,
    ) -> dict:
        """
        Add a worklog to an issue with optional estimate updates.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            time_spent: Time spent in Jira format (e.g., '1h 30m', '1d', '30m')
            comment: Optional comment for the worklog (in Markdown format)
            started: Optional start time in ISO format
                    (e.g. '2023-08-01T12:00:00.000+0000').
                    If not provided, current time will be used.
            original_estimate: Optional original estimate in Jira format
                              (e.g., '1h 30m', '1d')
                              This will update the original estimate for the issue.
            remaining_estimate: Optional remaining estimate in Jira format
                               (e.g., '1h', '30m')
                               This will update the remaining estimate for the issue.

        Returns:
            The created worklog details
        """
        try:
            # Convert time_spent string to seconds
            time_spent_seconds = self._parse_time_spent(time_spent)

            # Convert Markdown comment to Jira format if provided
            if comment:
                comment = self._markdown_to_jira(comment)

            # Step 1: Update original estimate if provided (separate API call)
            original_estimate_updated = False
            if original_estimate:
                try:
                    fields = {"timetracking": {"originalEstimate": original_estimate}}
                    self.jira.edit_issue(issue_id_or_key=issue_key, fields=fields)
                    original_estimate_updated = True
                    logger.info(f"Updated original estimate for issue {issue_key}")
                except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
                    logger.error(
                        f"Failed to update original estimate for issue {issue_key}: "
                        f"{str(e)}"
                    )
                    # Continue with worklog creation even if estimate update fails

            # Step 2: Prepare worklog data
            worklog_data = {"timeSpentSeconds": time_spent_seconds}
            if comment:
                worklog_data["comment"] = comment
            if started:
                worklog_data["started"] = started

            # Step 3: Prepare query parameters for remaining estimate
            params = {}
            remaining_estimate_updated = False
            if remaining_estimate:
                params["adjustEstimate"] = "new"
                params["newEstimate"] = remaining_estimate
                remaining_estimate_updated = True

            # Step 4: Add the worklog with remaining estimate adjustment
            base_url = self.jira.resource_url("issue")
            url = f"{base_url}/{issue_key}/worklog"
            result = self.jira.post(url, data=worklog_data, params=params)

            # Format and return the result
            return {
                "id": result.get("id"),
                "comment": self._clean_text(result.get("comment", "")),
                "created": self._parse_date(result.get("created", "")),
                "updated": self._parse_date(result.get("updated", "")),
                "started": self._parse_date(result.get("started", "")),
                "timeSpent": result.get("timeSpent", ""),
                "timeSpentSeconds": result.get("timeSpentSeconds", 0),
                "author": result.get("author", {}).get("displayName", "Unknown"),
                "original_estimate_updated": original_estimate_updated,
                "remaining_estimate_updated": remaining_estimate_updated,
            }
        except Exception as e:
            logger.error(f"Error adding worklog to issue {issue_key}: {str(e)}")
            raise

    def get_worklogs(self, issue_key: str) -> list[dict]:
        """
        Get worklogs for an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of worklog entries
        """
        try:
            result = self.jira.issue_get_worklog(issue_key)

            # Process the worklogs
            worklogs = []
            for worklog in result.get("worklogs", []):
                worklogs.append(
                    {
                        "id": worklog.get("id"),
                        "comment": self._clean_text(worklog.get("comment", "")),
                        "created": self._parse_date(worklog.get("created", "")),
                        "updated": self._parse_date(worklog.get("updated", "")),
                        "started": self._parse_date(worklog.get("started", "")),
                        "timeSpent": worklog.get("timeSpent", ""),
                        "timeSpentSeconds": worklog.get("timeSpentSeconds", 0),
                        "author": worklog.get("author", {}).get(
                            "displayName", "Unknown"
                        ),
                    }
                )

            return worklogs
        except Exception as e:
            logger.error(f"Error getting worklogs for issue {issue_key}: {str(e)}")
            raise

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
        return self.preprocessor.markdown_to_jira(markdown_text)

    def get_available_transitions(self, issue_key: str) -> list[dict]:
        """
        Get the available status transitions for an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of available transitions with id, name, and to status details
        """
        try:
            transitions_data = self.jira.get_issue_transitions(issue_key)
            result = []

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
            raise

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        fields: dict | None = None,
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
        """
        try:
            # Ensure transition_id is a string
            transition_id = self._normalize_transition_id(transition_id)

            # Prepare transition data
            transition_data = {"transition": {"id": transition_id}}

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
                f"Transitioning issue {issue_key} with transition ID {transition_id}"
            )
            logger.debug(f"Transition data: {transition_data}")

            # Perform the transition
            self.jira.issue_transition(issue_key, transition_data)

            # Return the updated issue
            return self.get_issue(issue_key)
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

    def _sanitize_transition_fields(self, fields: dict) -> dict:
        """
        Sanitize fields to ensure they're valid for the Jira API.

        Args:
            fields: Dictionary of fields to sanitize

        Returns:
            Dictionary of sanitized fields
        """
        sanitized_fields = {}
        for key, value in fields.items():
            # Skip None values
            if value is None:
                continue

            # Handle special case for assignee
            if key == "assignee" and isinstance(value, str):
                try:
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
            comment = str(comment)

        # Convert markdown to Jira format and add to transition data
        jira_formatted_comment = self._markdown_to_jira(comment)
        transition_data["update"] = {
            "comment": [{"add": {"body": jira_formatted_comment}}]
        }
