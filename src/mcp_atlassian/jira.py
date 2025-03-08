import logging
import os
import re
from datetime import datetime
from typing import Any

from atlassian import Jira

from .config import JiraConfig
from .document_types import Document
from .preprocessing import TextPreprocessor

# Configure logging
logger = logging.getLogger("mcp-jira")


class JiraFetcher:
    """Handles fetching and parsing content from Jira."""

    def __init__(self):
        """Initialize the Jira client."""
        url = os.getenv("JIRA_URL")
        username = os.getenv("JIRA_USERNAME", "")
        token = os.getenv("JIRA_API_TOKEN", "")
        personal_token = os.getenv("JIRA_PERSONAL_TOKEN", "")
        # For self-signed certificates in on-premise installations
        verify_ssl = os.getenv("JIRA_SSL_VERIFY", "true").lower() != "false"

        if not url:
            raise ValueError("Missing required JIRA_URL environment variable")

        # Check authentication method
        is_cloud = "atlassian.net" in url

        if is_cloud:
            logger.info(f"Initializing Jira Cloud client for {url}")
            if not username or not token:
                raise ValueError("Cloud authentication requires JIRA_USERNAME and JIRA_API_TOKEN")
        else:
            logger.info(f"Initializing Jira Server/Data Center client for {url}")
            if not personal_token:
                raise ValueError("Server/Data Center authentication requires JIRA_PERSONAL_TOKEN")

        self.config = JiraConfig(
            url=url, username=username, api_token=token, personal_token=personal_token, verify_ssl=verify_ssl
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
        Get account ID from email or full name.

        Args:
            assignee: Email, full name, or account ID of the user

        Returns:
            Account ID of the user

        Raises:
            ValueError: If user cannot be found
        """
        # If it looks like an account ID (alphanumeric with hyphens), return as is
        if assignee and assignee.replace("-", "").isalnum():
            logger.info(f"Using '{assignee}' as account ID")
            return assignee

        try:
            # First try direct user lookup
            try:
                users = self.jira.user_find_by_user_string(query=assignee)
                if users:
                    if len(users) > 1:
                        # Log all found users for debugging
                        user_details = [f"{u.get('displayName')} ({u.get('emailAddress')})" for u in users]
                        logger.warning(
                            f"Multiple users found for '{assignee}', using first match. "
                            f"Found users: {', '.join(user_details)}"
                        )

                    user = users[0]
                    account_id = user.get("accountId")
                    if account_id and isinstance(account_id, str):
                        logger.info(
                            f"Found account ID via direct lookup: {account_id} "
                            f"({user.get('displayName')} - {user.get('emailAddress')})"
                        )
                        return str(account_id)  # Explicit str conversion
                    logger.warning(f"Direct user lookup failed for '{assignee}': user found but no account ID present")
                else:
                    logger.warning(f"Direct user lookup failed for '{assignee}': no users found")
            except Exception as e:
                logger.warning(f"Direct user lookup failed for '{assignee}': {str(e)}")

            # Fall back to project permission based search
            users = self.jira.get_users_with_browse_permission_to_a_project(username=assignee)
            if not users:
                logger.warning(f"No user found matching '{assignee}'")
                raise ValueError(f"No user found matching '{assignee}'")

            # Return the first matching user's account ID
            account_id = users[0].get("accountId")
            if not account_id or not isinstance(account_id, str):
                logger.warning(f"Found user '{assignee}' but no account ID was returned")
                raise ValueError(f"Found user '{assignee}' but no account ID was returned")

            logger.info(f"Found account ID via browse permission lookup: {account_id}")
            return str(account_id)  # Explicit str conversion
        except Exception as e:
            logger.error(f"Error finding user '{assignee}': {str(e)}")
            raise ValueError(f"Could not resolve account ID for '{assignee}'") from e

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str,
        description: str = "",
        assignee: str | None = None,
        **kwargs: Any,
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
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
            "description": self._markdown_to_jira(description),
        }

        # If we're creating an Epic, handle Epic-specific fields dynamically
        if issue_type.lower() == "epic":
            try:
                # Get the dynamic field IDs
                field_ids = self.get_jira_field_ids()
                logger.info(f"Discovered Jira field IDs for Epic creation: {field_ids}")

                # Handle Epic Name - might be required in some instances, not in others
                # If Epic Name field was found during discovery, use it
                if "epic_name" in field_ids:
                    epic_name = kwargs.pop("epic_name", summary)  # Use summary as default if not provided
                    fields[field_ids["epic_name"]] = epic_name
                    logger.info(f"Setting Epic Name field {field_ids['epic_name']} to: {epic_name}")

                # Handle Epic Color if the field was discovered
                if "epic_color" in field_ids:
                    epic_color = kwargs.pop("epic_color", None) or kwargs.pop("epic_colour", None) or "green"
                    fields[field_ids["epic_color"]] = epic_color
                    logger.info(f"Setting Epic Color field {field_ids['epic_color']} to: {epic_color}")

                # Pass through any explicitly provided custom fields that might be instance-specific
                # This allows callers who know their instance to directly specify field IDs
                for field_key, field_value in kwargs.items():
                    if field_key.startswith("customfield_"):
                        fields[field_key] = field_value
                        logger.info(f"Using explicitly provided custom field {field_key}: {field_value}")

                # If epic_name field is required but wasn't discovered, warn the user
                # Some Jira instances require it, others don't
                if "epic_name" not in field_ids:
                    logger.warning(
                        "Epic Name field not found in Jira schema. "
                        "If your Jira instance requires it, please provide the customfield_* ID directly."
                    )
            except Exception as e:
                logger.error(f"Error preparing Epic-specific fields: {str(e)}")
                # Continue with creation anyway, as some instances might not require special fields

        # Add assignee if provided
        if assignee:
            account_id = self._get_account_id(assignee)
            fields["assignee"] = {"accountId": account_id}

        # Remove assignee from additional_fields if present to avoid conflicts
        if "assignee" in kwargs:
            logger.warning(
                "Assignee found in additional_fields - this will be ignored. Please use the assignee parameter instead."
            )
            kwargs.pop("assignee")

        for key, value in kwargs.items():
            fields[key] = value

        # Convert description to Jira format if present
        if "description" in fields and fields["description"]:
            fields["description"] = self._markdown_to_jira(fields["description"])

        try:
            response = self.jira.create_issue(fields=fields)
            issue_key = response["key"]
            logger.info(f"Created issue {issue_key}")
            return self.get_issue(issue_key)
        except Exception as e:
            error_msg = str(e)

            # Provide more helpful error messages for common issues
            if issue_type.lower() == "epic" and "customfield_" in error_msg:
                # Handle the case where a specific Epic field is required but missing
                missing_field_match = re.search(
                    r"(?:Field '(customfield_\d+)'|'(customfield_\d+)' cannot be set)", error_msg
                )
                if missing_field_match:
                    field_id = missing_field_match.group(1) or missing_field_match.group(2)
                    logger.error(
                        f"Failed to create Epic: Your Jira instance requires field '{field_id}'. "
                        f"This is typically the Epic Name field. Try setting this field explicitly "
                        f"using '{field_id}': 'Epic Name Value' in the additional_fields parameter."
                    )
                else:
                    logger.error(
                        f"Failed to create Epic: Your Jira instance has custom field requirements. "
                        f"You may need to provide specific custom fields for Epics in your instance. "
                        f"Original error: {error_msg}"
                    )
            else:
                logger.error(f"Error creating issue: {error_msg}")

            raise

    def update_issue(self, issue_key: str, fields: dict[str, Any] = None, **kwargs: Any) -> Document:
        """
        Update an existing issue in Jira and return it as a Document.

        Args:
            issue_key: The key of the issue to update (e.g. 'PROJ-123')
            fields: Fields to update
            kwargs: Any other custom Jira fields

        Returns:
            Document representing the updated issue
        """
        if fields is None:
            fields = {}

        # Handle all kwargs
        for key, value in kwargs.items():
            fields[key] = value

        # Convert description to Jira format if present
        if "description" in fields and fields["description"]:
            fields["description"] = self._markdown_to_jira(fields["description"])

        # Check if status update is requested
        if "status" in fields:
            requested_status = fields.pop("status")
            if not isinstance(requested_status, str):
                logger.warning(f"Status must be a string, got {type(requested_status)}: {requested_status}")
                # Try to convert to string if possible
                requested_status = str(requested_status)

            logger.info(f"Status update requested to: {requested_status}")

            # Get available transitions
            transitions = self.get_available_transitions(issue_key)

            # Find matching transition
            transition_id = None
            for transition in transitions:
                to_status = transition.get("to_status", "")
                if isinstance(to_status, str) and to_status.lower() == requested_status.lower():
                    transition_id = transition["id"]
                    break

            if transition_id:
                # Use transition_issue method if we found a matching transition
                logger.info(f"Found transition ID {transition_id} for status {requested_status}")
                return self.transition_issue(issue_key, transition_id, fields)
            else:
                available_statuses = [t.get("to_status", "") for t in transitions]
                logger.warning(
                    f"No transition found for status '{requested_status}'. Available transitions: {transitions}"
                )
                raise ValueError(
                    f"Cannot transition issue to status '{requested_status}'. Available status transitions: {available_statuses}"
                )

        try:
            self.jira.issue_update(issue_key, fields=fields)
            return self.get_issue(issue_key)
        except Exception as e:
            logger.error(f"Error updating issue {issue_key}: {str(e)}")
            raise

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
            if hasattr(self, "_field_ids_cache"):
                return self._field_ids_cache

            # Fetch all fields from Jira API
            fields = self.jira.fields()
            field_ids = {}

            # Log the complete list of fields for debugging
            all_field_names = [f"{field.get('name', '')} ({field.get('id', '')})" for field in fields]
            logger.debug(f"All available Jira fields: {all_field_names}")

            # Look for Epic-related fields - use multiple strategies to identify them
            for field in fields:
                field_name = field.get("name", "").lower()
                original_name = field.get("name", "")
                field_id = field.get("id", "")
                field_schema = field.get("schema", {})
                field_type = field_schema.get("type", "")
                field_custom = field_schema.get("custom", "")

                # Epic Link field - used to link issues to epics
                if (
                    "epic link" in field_name
                    or "epic-link" in field_name
                    or original_name == "Epic Link"
                    or field_custom == "com.pyxis.greenhopper.jira:gh-epic-link"
                ):
                    field_ids["epic_link"] = field_id
                    logger.info(f"Found Epic Link field: {original_name} ({field_id})")

                # Epic Name field - used when creating epics
                elif (
                    "epic name" in field_name
                    or "epic-name" in field_name
                    or original_name == "Epic Name"
                    or field_custom == "com.pyxis.greenhopper.jira:gh-epic-label"
                ):
                    field_ids["epic_name"] = field_id
                    logger.info(f"Found Epic Name field: {original_name} ({field_id})")

                # Parent field - sometimes used instead of Epic Link
                elif field_name == "parent" or field_name == "parent link" or original_name == "Parent Link":
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
                    logger.info(f"Found additional Epic-related field: {original_name} ({field_id})")

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

        except Exception as e:
            logger.error(f"Error discovering Jira field IDs: {str(e)}")
            # Return an empty dict as fallback
            return {}

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

            logger.info(f"Analyzing existing Epic {epic_key} to discover field structure")

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
                        logger.info(f"Potential Epic Name field discovered: {field_id} with value {field_value}")
                        if len(field_value) < 100:  # Epic names are typically short
                            field_ids["epic_name"] = field_id

                    # Color values are often simple strings like "green", "blue", etc.
                    if (
                        "epic_color" not in field_ids
                        and isinstance(field_value, str)
                        and field_id not in field_ids.values()
                    ):
                        colors = ["green", "blue", "red", "yellow", "orange", "purple", "gray", "grey", "teal"]
                        if field_value.lower() in colors:
                            logger.info(f"Potential Epic Color field discovered: {field_id} with value {field_value}")
                            field_ids["epic_color"] = field_id

        except Exception as e:
            logger.warning(f"Could not discover Epic fields from existing Epics: {str(e)}")

    def link_issue_to_epic(self, issue_key: str, epic_key: str) -> Document:
        """
        Link an existing issue to an epic.

        Args:
            issue_key: The key of the issue to link (e.g. 'PROJ-123')
            epic_key: The key of the epic to link to (e.g. 'PROJ-456')

        Returns:
            Document representing the updated issue
        """
        try:
            # First, check if the epic exists and is an Epic type
            epic = self.jira.issue(epic_key)
            if epic["fields"]["issuetype"]["name"] != "Epic":
                raise ValueError(f"Issue {epic_key} is not an Epic, it is a {epic['fields']['issuetype']['name']}")

            # Get the dynamic field IDs for this Jira instance
            field_ids = self.get_jira_field_ids()

            # Try the parent field first (if discovered or natively supported)
            if "parent" in field_ids or "parent" not in field_ids:
                try:
                    fields = {"parent": {"key": epic_key}}
                    self.jira.issue_update(issue_key, fields=fields)
                    return self.get_issue(issue_key)
                except Exception as e:
                    logger.info(f"Couldn't link using parent field: {str(e)}. Trying discovered fields...")

            # Try using the discovered Epic Link field
            if "epic_link" in field_ids:
                try:
                    epic_link_fields: dict[str, str] = {field_ids["epic_link"]: epic_key}
                    self.jira.issue_update(issue_key, fields=epic_link_fields)
                    return self.get_issue(issue_key)
                except Exception as e:
                    logger.info(f"Couldn't link using discovered epic_link field: {str(e)}. Trying fallback methods...")

            # Fallback to common custom fields if dynamic discovery didn't work
            custom_field_attempts: list[dict[str, str]] = [
                {"customfield_10014": epic_key},  # Common in Jira Cloud
                {"customfield_10000": epic_key},  # Common in Jira Server
                {"epic_link": epic_key},  # Sometimes used
            ]

            for fields in custom_field_attempts:
                try:
                    self.jira.issue_update(issue_key, fields=fields)
                    return self.get_issue(issue_key)
                except Exception as e:
                    logger.info(f"Couldn't link using fields {fields}: {str(e)}")
                    continue

            # If we get here, none of our attempts worked
            raise ValueError(
                f"Could not link issue {issue_key} to epic {epic_key}. Your Jira instance might use a different field for epic links."
            )

        except Exception as e:
            logger.error(f"Error linking issue {issue_key} to epic {epic_key}: {str(e)}")
            raise

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
        """Parse date string to handle various ISO formats."""
        if not date_str:
            return ""

        # Handle various timezone formats
        if "+0000" in date_str:
            date_str = date_str.replace("+0000", "+00:00")
        elif "-0000" in date_str:
            date_str = date_str.replace("-0000", "+00:00")
        # Handle other timezone formats like +0900, -0500, etc.
        elif len(date_str) >= 5 and date_str[-5] in "+-" and date_str[-4:].isdigit():
            # Insert colon between hours and minutes of timezone
            date_str = date_str[:-2] + ":" + date_str[-2:]

        try:
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return date.strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning(f"Error parsing date {date_str}: {e}")
            return date_str

    def get_issue(self, issue_key: str, expand: str | None = None, comment_limit: int | str | None = 10) -> Document:
        """
        Get a single issue with all its details.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            expand: Optional fields to expand
            comment_limit: Maximum number of comments to include (None for no comments, defaults to 10)
                          Can be an integer or a string that can be converted to an integer.

        Returns:
            Document containing issue content and metadata
        """
        try:
            issue = self.jira.issue(issue_key, expand=expand)

            # Process description and comments
            description = self._clean_text(issue["fields"].get("description", ""))

            # Convert comment_limit to int if it's a string
            if comment_limit is not None and isinstance(comment_limit, str):
                try:
                    comment_limit = int(comment_limit)
                except ValueError:
                    logger.warning(f"Invalid comment_limit value: {comment_limit}. Using default of 10.")
                    comment_limit = 10

            # Get comments if limit is specified
            comments = []
            if comment_limit is not None and comment_limit > 0:
                comments = self.get_issue_comments(issue_key, limit=comment_limit)

            # Format created date using new parser
            created_date = self._parse_date(issue["fields"]["created"])

            # Check for Epic information
            epic_key = None
            epic_name = None

            # Most Jira instances use the "parent" field for Epic relationships
            if "parent" in issue["fields"] and issue["fields"]["parent"]:
                epic_key = issue["fields"]["parent"]["key"]
                epic_name = issue["fields"]["parent"]["fields"]["summary"]

            # Some Jira instances use custom fields for Epic links
            # Common custom field names for Epic links
            epic_field_names = ["customfield_10014", "customfield_10000", "epic_link"]
            for field_name in epic_field_names:
                if field_name in issue["fields"] and issue["fields"][field_name]:
                    # If it's a string, assume it's the epic key
                    if isinstance(issue["fields"][field_name], str):
                        epic_key = issue["fields"][field_name]
                    # If it's an object, extract the key
                    elif isinstance(issue["fields"][field_name], dict) and "key" in issue["fields"][field_name]:
                        epic_key = issue["fields"][field_name]["key"]

            # Combine content in a more structured way
            content = f"""Issue: {issue_key}
Title: {issue['fields'].get('summary', '')}
Type: {issue['fields']['issuetype']['name']}
Status: {issue['fields']['status']['name']}
Created: {created_date}
"""

            # Add Epic information if available
            if epic_key:
                content += f"Epic: {epic_key}"
                if epic_name:
                    content += f" - {epic_name}"
                content += "\n"

            content += f"""
Description:
{description}
"""
            if comments:
                content += "\nComments:\n" + "\n".join(
                    [f"{c['created']} - {c['author']}: {c['body']}" for c in comments]
                )

            # Streamlined metadata with only essential information
            metadata = {
                "key": issue_key,
                "title": issue["fields"].get("summary", ""),
                "type": issue["fields"]["issuetype"]["name"],
                "status": issue["fields"]["status"]["name"],
                "created_date": created_date,
                "priority": issue["fields"].get("priority", {}).get("name", "None"),
                "link": f"{self.config.url.rstrip('/')}/browse/{issue_key}",
            }

            # Add Epic information to metadata
            if epic_key:
                metadata["epic_key"] = epic_key
                if epic_name:
                    metadata["epic_name"] = epic_name

            if comments:
                metadata["comments"] = comments

            return Document(page_content=content, metadata=metadata)

        except Exception as e:
            logger.error(f"Error fetching issue {issue_key}: {str(e)}")
            raise

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
            issues = self.jira.jql(jql, fields=fields, start=start, limit=limit, expand=expand)
            documents = []

            for issue in issues.get("issues", []):
                issue_key = issue["key"]
                summary = issue["fields"].get("summary", "")
                issue_type = issue["fields"]["issuetype"]["name"]
                status = issue["fields"]["status"]["name"]
                desc = self._clean_text(issue["fields"].get("description", ""))
                created_date = self._parse_date(issue["fields"]["created"])
                priority = issue["fields"].get("priority", {}).get("name", "None")

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
            if epic["fields"]["issuetype"]["name"] != "Epic":
                raise ValueError(f"Issue {epic_key} is not an Epic, it is a {epic['fields']['issuetype']['name']}")

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
                except Exception as e:
                    logger.info(f"Failed to get epic issues with JQL '{jql}': {str(e)}")
                    continue

            # If we've tried all queries and got no results, return an empty list
            # but also log a warning that we might be missing the right field
            if not documents:
                logger.warning(
                    f"Couldn't find issues linked to epic {epic_key}. Your Jira instance might use a different field for epic links."
                )

            return documents

        except Exception as e:
            logger.error(f"Error getting issues for epic {epic_key}: {str(e)}")
            raise

    def get_project_issues(self, project_key: str, start: int = 0, limit: int = 50) -> list[Document]:
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
            The account ID string of the current user

        Raises:
            ValueError: If unable to get the current user's account ID
        """
        try:
            myself = self.jira.myself()
            account_id: str | None = myself.get("accountId")
            if not account_id:
                raise ValueError("Unable to get account ID from user profile")
            return account_id
        except Exception as e:
            logger.error(f"Error getting current user account ID: {str(e)}")
            raise ValueError(f"Failed to get current user account ID: {str(e)}")

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
        Parse Jira time format string (e.g., '1h 30m', '1d', '30m') to seconds.

        Args:
            time_spent: Time string in Jira format

        Returns:
            Time in seconds
        """
        if not time_spent:
            raise ValueError("Time spent string cannot be empty")

        # Define time unit conversions to seconds
        units = {
            "w": 7 * 24 * 60 * 60,  # weeks
            "d": 24 * 60 * 60,  # days
            "h": 60 * 60,  # hours
            "m": 60,  # minutes
        }

        # Extract all time components (e.g., '1h', '30m')
        pattern = r"(\d+)([wdhm])"
        matches = re.findall(pattern, time_spent.lower())

        if not matches:
            raise ValueError(f"Invalid time format: {time_spent}. Expected format like '1h 30m', '1d', etc.")

        # Calculate total seconds
        total_seconds = 0
        for value, unit in matches:
            if unit in units:
                total_seconds += int(value) * units[unit]

        return total_seconds

    def add_worklog(
        self,
        issue_key: str,
        time_spent: str,
        comment: str = None,
        started: str = None,
        original_estimate: str = None,
        remaining_estimate: str = None,
    ) -> dict:
        """
        Add a worklog to an issue with optional estimate updates.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            time_spent: Time spent in Jira format (e.g., '1h 30m', '1d', '30m')
            comment: Optional comment for the worklog (in Markdown format)
            started: Optional start time in ISO format (e.g. '2023-08-01T12:00:00.000+0000').
                     If not provided, current time will be used.
            original_estimate: Optional original estimate in Jira format (e.g., '1h 30m', '1d')
                              This will update the original estimate for the issue.
            remaining_estimate: Optional remaining estimate in Jira format (e.g., '1h', '30m')
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
                except Exception as e:
                    logger.error(f"Failed to update original estimate for issue {issue_key}: {str(e)}")
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
                        "author": worklog.get("author", {}).get("displayName", "Unknown"),
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
                logger.warning(f"Unexpected format for transitions data: {type(transitions_data)}")
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

                result.append({"id": transition_id, "name": transition_name, "to_status": to_status})

            return result
        except Exception as e:
            logger.error(f"Error getting transitions for issue {issue_key}: {str(e)}")
            raise

    def transition_issue(
        self, issue_key: str, transition_id: str, fields: dict | None = None, comment: str | None = None
    ) -> Document:
        """
        Transition an issue to a new status using the appropriate workflow transition.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            transition_id: The ID of the transition to perform (get this from get_available_transitions)
            fields: Additional fields to update during the transition
            comment: Optional comment to add during the transition

        Returns:
            Document representing the updated issue
        """
        try:
            # Ensure transition_id is a string
            if not isinstance(transition_id, str):
                logger.warning(
                    f"transition_id must be a string, converting from {type(transition_id)}: {transition_id}"
                )
                transition_id = str(transition_id)

            transition_data: dict[str, Any] = {"transition": {"id": transition_id}}

            # Add fields if provided
            if fields:
                # Sanitize fields to ensure they're valid for the API
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
                        except Exception as e:
                            error_msg = f"Could not resolve assignee '{value}': {str(e)}"
                            logger.warning(error_msg)
                            # Skip this field
                            continue
                    else:
                        sanitized_fields[key] = value

                if sanitized_fields:
                    transition_data["fields"] = sanitized_fields

            # Add comment if provided
            if comment:
                if not isinstance(comment, str):
                    logger.warning(f"Comment must be a string, converting from {type(comment)}: {comment}")
                    comment = str(comment)

                jira_formatted_comment = self._markdown_to_jira(comment)
                transition_data["update"] = {"comment": [{"add": {"body": jira_formatted_comment}}]}

            # Log the transition request for debugging
            logger.info(f"Transitioning issue {issue_key} with transition ID {transition_id}")
            logger.debug(f"Transition data: {transition_data}")

            # Perform the transition
            self.jira.issue_transition(issue_key, transition_data)

            # Return the updated issue
            return self.get_issue(issue_key)
        except Exception as e:
            error_msg = f"Error transitioning issue {issue_key} with transition ID {transition_id}: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
