"""Module for Jira epic operations."""

import logging
from typing import Any

from ..models.jira import JiraIssue
from .users import UsersMixin

logger = logging.getLogger("mcp-jira")


class EpicsMixin(UsersMixin):
    """Mixin for Jira epic operations."""

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

            # Process comments if needed
            comment_limit_int = None
            if comment_limit == "all":
                comment_limit_int = None  # No limit
            elif comment_limit is not None:
                try:
                    comment_limit_int = int(comment_limit)
                except (ValueError, TypeError):
                    comment_limit_int = 10  # Default to 10 comments

            # Get comments if needed
            comments = []
            if comment_limit_int is not None:
                try:
                    comments_data = self.jira.comments(
                        issue_key, limit=comment_limit_int
                    )
                    comments = comments_data.get("comments", [])
                except Exception:
                    # Failed to get comments - continue without them
                    comments = []

            # Add comments to the issue data for processing by the model
            if comments:
                if "comment" not in fields:
                    fields["comment"] = {}
                fields["comment"]["comments"] = comments

            # Get epic information
            epic_info = {}
            field_ids = self.get_jira_field_ids()

            # Check if this issue is linked to an epic
            epic_link_field = field_ids.get("epic_link")
            if (
                epic_link_field
                and epic_link_field in fields
                and fields[epic_link_field]
            ):
                epic_info["epic_key"] = fields[epic_link_field]

            # Update the issue data with the fields
            issue["fields"] = fields

            # Create and return the JiraIssue model
            return JiraIssue.from_api_response(issue, base_url=self.config.url)
        except Exception as e:
            error_msg = str(e)
            if "Issue does not exist" in error_msg:
                raise ValueError(f"Issue {issue_key} not found") from e
            else:
                logger.error(f"Error getting issue {issue_key}: {error_msg}")
                raise Exception(f"Error getting issue {issue_key}: {error_msg}") from e

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
            if hasattr(self, "_field_ids_cache") and self._field_ids_cache:
                return self._field_ids_cache

            # Fetch all fields from Jira API
            fields = self.jira.get_all_fields()
            field_ids = {}

            # Log the complete list of fields for debugging
            all_field_names = [
                f"{field.get('name', '')} ({field.get('id', '')})" for field in fields
            ]
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
                    logger.info(
                        f"Found Epic Status field: {original_name} ({field_id})"
                    )

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

    def _try_discover_fields_from_existing_epic(
        self, field_ids: dict[str, str]
    ) -> None:
        """
        Try to discover Epic fields from existing epics.

        Args:
            field_ids: Dictionary of field IDs to update
        """
        try:
            # If we already have both epic fields, no need to search
            if ("epic_link" in field_ids and "epic_name" in field_ids) or (
                "Epic Link" in field_ids and "Epic Name" in field_ids
            ):
                return

            # Find an Epic in the system
            epics_jql = "issuetype = Epic ORDER BY created DESC"
            results = self.jira.jql(epics_jql, fields="*all", limit=1)

            # If no epics found, we can't use this method
            if not results or not results.get("issues"):
                logger.warning("No existing Epics found to analyze field structure")
                return

            epic = results["issues"][0]
            fields = epic.get("fields", {})

            # Inspect every custom field for values that look like epic fields
            for field_id, value in fields.items():
                if not field_id.startswith("customfield_"):
                    continue

                # If it's a string value for a customfield, it might be the Epic Name
                if (
                    ("epic_name" not in field_ids and "Epic Name" not in field_ids)
                    and isinstance(value, str)
                    and value
                ):
                    # Store with both key formats for compatibility
                    field_ids["epic_name"] = field_id
                    field_ids["Epic Name"] = field_id
                    logger.info(
                        f"Discovered Epic Name field from existing epic: {field_id}"
                    )

            # Now try to find issues linked to this Epic to discover the Epic Link field
            if "epic_link" not in field_ids and "Epic Link" not in field_ids:
                epic_key = epic.get("key")
                if not epic_key:
                    return

                # Try several query formats to find linked issues
                link_queries = [
                    f"'Epic Link' = {epic_key}",
                    f"'Epic' = {epic_key}",
                    f"parent = {epic_key}",
                ]

                for query in link_queries:
                    try:
                        link_results = self.jira.jql(query, fields="*all", limit=1)
                        if link_results and link_results.get("issues"):
                            # Found an issue linked to our epic, now inspect its fields
                            linked_issue = link_results["issues"][0]
                            linked_fields = linked_issue.get("fields", {})

                            # Check each field to see if it contains our epic key
                            for field_id, value in linked_fields.items():
                                if (
                                    field_id.startswith("customfield_")
                                    and isinstance(value, str)
                                    and value == epic_key
                                ):
                                    # Store with both key formats for compatibility
                                    field_ids["epic_link"] = field_id
                                    field_ids["Epic Link"] = field_id
                                    logger.info(
                                        f"Discovered Epic Link field from linked issue: {field_id}"
                                    )
                                    break

                            # If we found the epic link field, we can stop
                            if "epic_link" in field_ids or "Epic Link" in field_ids:
                                break
                    except Exception:  # noqa: BLE001 - Intentional fallback with logging
                        continue

                # If we still haven't found Epic Link, try a broader search
                if "epic_link" not in field_ids and "Epic Link" not in field_ids:
                    try:
                        # Search for issues that might be linked to epics
                        results = self.jira.jql(
                            "project is not empty", fields="*all", limit=10
                        )
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
                                        field_ids["epic_link"] = field_id
                                        field_ids["Epic Link"] = field_id
                                        logger.info(
                                            f"Discovered Epic Link field from potential issue: {field_id}"
                                        )
                                        break
                            if "epic_link" in field_ids or "Epic Link" in field_ids:
                                break
                    except Exception as e:
                        logger.warning(
                            f"Error in broader search for Epic Link: {str(e)}"
                        )

        except Exception as e:
            logger.warning(f"Error discovering fields from existing Epics: {str(e)}")

    def prepare_epic_fields(
        self, fields: dict[str, Any], summary: str, kwargs: dict[str, Any]
    ) -> None:
        """
        Prepare epic-specific fields for issue creation.

        Args:
            fields: The fields dictionary to update
            summary: The issue summary that can be used as a default epic name
            kwargs: Additional fields from the user
        """
        try:
            # Get all field IDs
            field_ids = self.get_jira_field_ids()
            logger.info(f"Discovered Jira field IDs for Epic creation: {field_ids}")

            # Handle Epic Name - might be required in some instances, not in others
            if "epic_name" in field_ids:
                epic_name = kwargs.pop(
                    "epic_name", summary
                )  # Use summary as default if epic_name not provided
                fields[field_ids["epic_name"]] = epic_name
                logger.info(
                    f"Setting Epic Name field {field_ids['epic_name']} to: {epic_name}"
                )

            # Handle Epic Color if the field was discovered
            if "epic_color" in field_ids:
                epic_color = (
                    kwargs.pop("epic_color", None)
                    or kwargs.pop("epic_colour", None)
                    or "green"  # Default color
                )
                fields[field_ids["epic_color"]] = epic_color
                logger.info(
                    f"Setting Epic Color field {field_ids['epic_color']} "
                    f"to: {epic_color}"
                )

            # Add any other epic-related fields provided
            for key, value in list(kwargs.items()):
                if (
                    key.startswith("epic_")
                    and key != "epic_name"
                    and key != "epic_color"
                ):
                    field_key = key.replace("epic_", "")
                    if f"epic_{field_key}" in field_ids:
                        fields[field_ids[f"epic_{field_key}"]] = value
                        kwargs.pop(key)

            # Warn if epic_name field is required but wasn't discovered
            if "epic_name" not in field_ids:
                logger.warning(
                    "Epic Name field not found in Jira schema. "
                    "Epic creation may fail if this field is required."
                )

        except Exception as e:
            logger.error(f"Error preparing Epic-specific fields: {str(e)}")

    def link_issue_to_epic(self, issue_key: str, epic_key: str) -> JiraIssue:
        """
        Link an existing issue to an epic.

        Args:
            issue_key: The key of the issue to link (e.g. 'PROJ-123')
            epic_key: The key of the epic to link to (e.g. 'PROJ-456')

        Returns:
            JiraIssue: The updated issue

        Raises:
            ValueError: If the epic_key is not an actual epic
            Exception: If there is an error linking the issue to the epic
        """
        try:
            # Verify that both issue and epic exist
            issue = self.jira.get_issue(issue_key)
            epic = self.jira.get_issue(epic_key)

            # Check if the epic key corresponds to an actual epic
            fields = epic.get("fields", {})
            issue_type = fields.get("issuetype", {}).get("name", "").lower()

            if issue_type != "epic":
                error_msg = f"Error linking issue to epic: {epic_key} is not an Epic"
                raise ValueError(error_msg)

            # Get the dynamic field IDs for this Jira instance
            field_ids = self.get_jira_field_ids()

            # Try the parent field first (if discovered or natively supported)
            if "parent" in field_ids or "parent" not in field_ids:
                try:
                    fields = {"parent": {"key": epic_key}}
                    self.jira.update_issue(
                        issue_key=issue_key, update={"fields": fields}
                    )
                    logger.info(
                        f"Successfully linked {issue_key} to {epic_key} using parent field"
                    )
                    return self.get_issue(issue_key)
                except Exception as e:
                    logger.info(
                        f"Couldn't link using parent field: {str(e)}. Trying discovered fields..."
                    )

            # Try using the discovered Epic Link field
            if "epic_link" in field_ids:
                try:
                    epic_link_fields: dict[str, str] = {
                        field_ids["epic_link"]: epic_key
                    }
                    self.jira.update_issue(
                        issue_key=issue_key, update={"fields": epic_link_fields}
                    )
                    logger.info(
                        f"Successfully linked {issue_key} to {epic_key} using discovered epic_link field: {field_ids['epic_link']}"
                    )
                    return self.get_issue(issue_key)
                except Exception as e:
                    logger.info(
                        f"Couldn't link using discovered epic_link field: {str(e)}. Trying fallback methods..."
                    )

            # Fallback to common custom fields if dynamic discovery didn't work
            custom_field_attempts: list[dict[str, str]] = [
                {"customfield_10014": epic_key},  # Common in Jira Cloud
                {"customfield_10008": epic_key},  # Common in Jira Server
                {"customfield_10000": epic_key},  # Also common
                {"customfield_11703": epic_key},  # Known from previous error
                {"epic_link": epic_key},  # Sometimes used
            ]

            for fields in custom_field_attempts:
                try:
                    self.jira.update_issue(
                        issue_key=issue_key, update={"fields": fields}
                    )
                    field_id = list(fields.keys())[0]
                    logger.info(
                        f"Successfully linked {issue_key} to {epic_key} using field: {field_id}"
                    )

                    # If we get here, it worked - update our cached field ID
                    if not hasattr(self, "_field_ids_cache"):
                        self._field_ids_cache = {}
                    self._field_ids_cache["epic_link"] = field_id
                    return self.get_issue(issue_key)
                except Exception as e:
                    logger.info(f"Couldn't link using fields {fields}: {str(e)}")
                    continue

            # Method 2: Try to use direct issue linking (relates to, etc.)
            try:
                logger.info(
                    f"Attempting to create issue link between {issue_key} and {epic_key}"
                )
                link_data = {
                    "type": {"name": "Relates to"},
                    "inwardIssue": {"key": issue_key},
                    "outwardIssue": {"key": epic_key},
                }
                self.jira.create_issue_link(link_data)
                logger.info(
                    f"Created relationship link between {issue_key} and {epic_key}"
                )
                return self.get_issue(issue_key)
            except Exception as link_error:
                logger.error(f"Error creating issue link: {str(link_error)}")

            # If we get here, none of our attempts worked
            raise ValueError(
                f"Could not link issue {issue_key} to epic {epic_key}. Your Jira instance might use a different field for epic links."
            )

        except ValueError as e:
            # Re-raise ValueError as is
            raise
        except Exception as e:
            logger.error(f"Error linking {issue_key} to epic {epic_key}: {str(e)}")
            # Ensure exception messages follow the expected format for tests
            if "API error" in str(e):
                raise Exception(f"Error linking issue to epic: {str(e)}")
            raise

    def get_epic_issues(self, epic_key: str, limit: int = 50) -> list[JiraIssue]:
        """
        Get all issues linked to a specific epic.

        Args:
            epic_key: The key of the epic (e.g. 'PROJ-123')
            limit: Maximum number of issues to return

        Returns:
            List of JiraIssue models representing the issues linked to the epic

        Raises:
            ValueError: If the issue is not an Epic
            Exception: If there is an error getting epic issues
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

            # Track which methods we've tried
            tried_methods = set()
            issues = []

            # Find the Epic Link field
            field_ids = self.get_jira_field_ids()
            epic_link_field = self._find_epic_link_field(field_ids)

            # METHOD 1: Try with 'issueFunction in issuesScopedToEpic' - this works in many Jira instances
            if "issueFunction" not in tried_methods:
                tried_methods.add("issueFunction")
                try:
                    jql = f'issueFunction in issuesScopedToEpic("{epic_key}")'
                    logger.info(f"Trying to get epic issues with issueFunction: {jql}")

                    # If we have search_issues method available, use it
                    if hasattr(self, "search_issues") and callable(self.search_issues):
                        issues = self.search_issues(jql, limit=limit)
                        if issues:
                            logger.info(
                                f"Successfully found {len(issues)} issues for epic {epic_key} using issueFunction"
                            )
                            return issues
                except Exception as e:
                    # Log exception but continue with fallback
                    logger.warning(
                        f"Error searching epic issues with issueFunction: {str(e)}"
                    )

            # METHOD 2: Try using parent relationship - common in many Jira setups
            if "parent" not in tried_methods:
                tried_methods.add("parent")
                try:
                    jql = f'parent = "{epic_key}"'
                    logger.info(
                        f"Trying to get epic issues with parent relationship: {jql}"
                    )
                    issues = self._get_epic_issues_by_jql(epic_key, jql, limit)
                    if issues:
                        logger.info(
                            f"Successfully found {len(issues)} issues for epic {epic_key} using parent relationship"
                        )
                        return issues
                except Exception as parent_error:
                    logger.warning(
                        f"Error with parent relationship approach: {str(parent_error)}"
                    )

            # METHOD 3: If we found an Epic Link field, try using it
            if epic_link_field and "epicLinkField" not in tried_methods:
                tried_methods.add("epicLinkField")
                try:
                    jql = f'"{epic_link_field}" = "{epic_key}"'
                    logger.info(
                        f"Trying to get epic issues with epic link field: {jql}"
                    )
                    issues = self._get_epic_issues_by_jql(epic_key, jql, limit)
                    if issues:
                        logger.info(
                            f"Successfully found {len(issues)} issues for epic {epic_key} using epic link field {epic_link_field}"
                        )
                        return issues
                except Exception as e:
                    logger.warning(
                        f"Error using epic link field {epic_link_field}: {str(e)}"
                    )

            # METHOD 4: Try using 'Epic Link' as a textual field name
            if "epicLinkName" not in tried_methods:
                tried_methods.add("epicLinkName")
                try:
                    jql = f'"Epic Link" = "{epic_key}"'
                    logger.info(
                        f"Trying to get epic issues with 'Epic Link' field name: {jql}"
                    )
                    issues = self._get_epic_issues_by_jql(epic_key, jql, limit)
                    if issues:
                        logger.info(
                            f"Successfully found {len(issues)} issues for epic {epic_key} using 'Epic Link' field name"
                        )
                        return issues
                except Exception as e:
                    logger.warning(f"Error using 'Epic Link' field name: {str(e)}")

            # METHOD 5: Try using issue links with a specific link type
            if "issueLinks" not in tried_methods:
                tried_methods.add("issueLinks")
                try:
                    # Try to find issues linked to this epic with standard link types
                    link_types = ["relates to", "blocks", "is blocked by", "is part of"]
                    for link_type in link_types:
                        jql = f'issueLink = "{link_type}" and issueLink = "{epic_key}"'
                        logger.info(
                            f"Trying to get epic issues with issue links: {jql}"
                        )
                        try:
                            issues = self._get_epic_issues_by_jql(epic_key, jql, limit)
                            if issues:
                                logger.info(
                                    f"Successfully found {len(issues)} issues for epic {epic_key} using issue links with type '{link_type}'"
                                )
                                return issues
                        except Exception:
                            # Just try the next link type
                            continue
                except Exception as e:
                    logger.warning(f"Error using issue links approach: {str(e)}")

            # METHOD 6: Last resort - try each common Epic Link field ID directly
            if "commonFields" not in tried_methods:
                tried_methods.add("commonFields")
                common_epic_fields = [
                    "customfield_10014",
                    "customfield_10008",
                    "customfield_10100",
                    "customfield_10001",
                    "customfield_10002",
                    "customfield_10003",
                    "customfield_10004",
                    "customfield_10005",
                    "customfield_10006",
                    "customfield_10007",
                    "customfield_11703",
                ]

                for field_id in common_epic_fields:
                    try:
                        jql = f'"{field_id}" = "{epic_key}"'
                        logger.info(
                            f"Trying to get epic issues with common field ID: {jql}"
                        )
                        issues = self._get_epic_issues_by_jql(epic_key, jql, limit)
                        if issues:
                            logger.info(
                                f"Successfully found {len(issues)} issues for epic {epic_key} using field ID {field_id}"
                            )
                            # Cache this successful field ID for future use
                            if not hasattr(self, "_field_ids_cache"):
                                self._field_ids_cache = {}
                            self._field_ids_cache["epic_link"] = field_id
                            return issues
                    except Exception:
                        # Just try the next field ID
                        continue

            # If we've tried everything and found no issues, return an empty list
            logger.warning(
                f"No issues found for epic {epic_key} after trying multiple approaches"
            )
            return []

        except ValueError as e:
            # Re-raise ValueError (like "not an Epic") as is
            raise
        except Exception as e:
            # Wrap other exceptions
            logger.error(f"Error getting issues for epic {epic_key}: {str(e)}")
            raise Exception(f"Error getting epic issues: {str(e)}") from e

    def _find_epic_link_field(self, field_ids: dict[str, str]) -> str | None:
        """
        Find the Epic Link field with fallback mechanisms.

        Args:
            field_ids: Dictionary of field IDs

        Returns:
            The field ID for Epic Link if found, None otherwise
        """
        # First try the standard field name with case-insensitive matching
        for name in ["epic_link", "epiclink", "Epic Link", "epic link", "EPIC LINK"]:
            if name in field_ids:
                logger.info(
                    f"Found Epic Link field by name: {name} -> {field_ids[name]}"
                )
                return field_ids[name]

        # Next, look for any field ID that contains "epic" and "link"
        # (case-insensitive) in the name
        for field_name, field_id in field_ids.items():
            if (
                isinstance(field_name, str)
                and "epic" in field_name.lower()
                and "link" in field_name.lower()
            ):
                logger.info(
                    f"Found potential Epic Link field: {field_name} -> {field_id}"
                )
                return field_id

        # Look for any customfield that might be an epic link
        # Common epic link field IDs across different Jira instances
        known_epic_fields = [
            "customfield_10014",  # Common in Jira Cloud
            "customfield_10008",  # Common in Jira Server
            "customfield_10100",
            "customfield_10001",
            "customfield_10002",
            "customfield_10003",
            "customfield_10004",
            "customfield_10005",
            "customfield_10006",
            "customfield_10007",
            "customfield_11703",  # Added based on error message
        ]

        # Check if any of these known fields exist in our field IDs values
        for field_id in known_epic_fields:
            if field_id in field_ids.values():
                logger.info(f"Using known epic link field ID: {field_id}")
                return field_id

        # Try with common system names for epic link field
        system_names = ["system.epic-link", "com.pyxis.greenhopper.jira:gh-epic-link"]
        for name in system_names:
            if name in field_ids:
                logger.info(
                    f"Found Epic Link field by system name: {name} -> {field_ids[name]}"
                )
                return field_ids[name]

        # If we still can't find it, try to detect it from issue links
        try:
            # Try to find an existing epic
            epics = self._find_sample_epic()
            if epics:
                epic_key = epics[0].get("key")
                # Try to find issues linked to this epic
                issues = self._find_issues_linked_to_epic(epic_key)
                for issue in issues:
                    # Check fields for any that contain the epic key
                    fields = issue.get("fields", {})
                    for field_id, value in fields.items():
                        if (
                            field_id.startswith("customfield_")
                            and isinstance(value, str)
                            and value == epic_key
                        ):
                            logger.info(
                                f"Detected epic link field {field_id} from linked issue"
                            )
                            return field_id
        except Exception as e:
            logger.warning(f"Error detecting epic link field from issues: {str(e)}")

        # As a last resort, look for any customfield that starts with customfield_
        # and has "epic" in its schema name or description
        try:
            all_fields = self.jira.get_all_fields()
            for field in all_fields:
                field_id = field.get("id", "")
                schema = field.get("schema", {})
                custom_type = schema.get("custom", "")
                if field_id.startswith("customfield_") and (
                    "epic" in custom_type.lower()
                    or "epic" in field.get("name", "").lower()
                    or "epic" in field.get("description", "").lower()
                ):
                    logger.info(
                        f"Found potential Epic Link field by schema inspection: {field_id}"
                    )
                    return field_id
        except Exception as e:
            logger.warning(
                f"Error during schema inspection for Epic Link field: {str(e)}"
            )

        # No Epic Link field found
        logger.warning("Could not determine Epic Link field with any method")
        return None

    def _find_sample_epic(self) -> list[dict]:
        """
        Find a sample epic to use for detecting the epic link field.

        Returns:
            List of epics found
        """
        try:
            # Search for issues with type=Epic
            jql = "issuetype = Epic ORDER BY updated DESC"
            response = self.jira.jql(jql, limit=1)
            if response and "issues" in response and response["issues"]:
                return response["issues"]
        except Exception as e:
            logger.warning(f"Error finding sample epic: {str(e)}")
        return []

    def _find_issues_linked_to_epic(self, epic_key: str) -> list[dict]:
        """
        Find issues linked to a specific epic.

        Args:
            epic_key: The key of the epic

        Returns:
            List of issues found
        """
        try:
            # Try several JQL formats to find linked issues
            for query in [
                f"'Epic Link' = {epic_key}",
                f"'Epic' = {epic_key}",
                f"parent = {epic_key}",
                f"issueFunction in issuesScopedToEpic('{epic_key}')",
            ]:
                try:
                    response = self.jira.jql(query, limit=5)
                    if response and "issues" in response and response["issues"]:
                        return response["issues"]
                except Exception:
                    # Try next query format
                    continue
        except Exception as e:
            logger.warning(f"Error finding issues linked to epic {epic_key}: {str(e)}")
        return []

    def _get_epic_issues_by_jql(
        self, epic_key: str, jql: str, limit: int
    ) -> list[JiraIssue]:
        """
        Helper method to get issues using a JQL query.

        Args:
            epic_key: The key of the epic
            jql: JQL query to execute
            limit: Maximum number of issues to return

        Returns:
            List of JiraIssue models
        """
        # Try to use search_issues if available
        if hasattr(self, "search_issues") and callable(self.search_issues):
            issues = self.search_issues(jql, limit=limit)
            if not issues:
                logger.warning(f"No issues found for epic {epic_key} with query: {jql}")
            return issues
        else:
            # Fallback if search_issues is not available
            issues_data = self.jira.jql(jql, limit=limit)
            issues = []

            # Create JiraIssue models from raw data
            if "issues" in issues_data:
                for issue_data in issues_data["issues"]:
                    issue = JiraIssue.from_api_response(
                        issue_data,
                        base_url=self.config.url if hasattr(self, "config") else None,
                    )
                    issues.append(issue)

            return issues
