"""Module for Jira epic operations."""

import logging
from typing import Any

from ..document_types import Document
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class EpicsMixin(JiraClient):
    """Mixin for Jira epic operations."""

    def get_jira_field_ids(self) -> dict[str, str]:
        """
        Get mappings of field names to IDs.

        This method discovers and caches various Jira field IDs, with a focus
        on Epic-related fields, which can vary between different Jira instances.

        Returns:
            Dictionary mapping field names to their IDs
            (e.g., {'epic_link': 'customfield_10014', 'epic_name': 'customfield_10011'})
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

            # Log available fields to help with debugging
            self._log_available_fields(fields)

            # Process each field to identify Epic-related fields
            for field in fields:
                self._process_field_for_epic_data(field, field_ids)

            # If we couldn't find all essential fields, try other discovery methods
            if "epic_name" not in field_ids or "epic_link" not in field_ids:
                logger.warning(
                    "Could not find all essential Epic fields through schema. "
                    "This may cause issues with Epic operations."
                )
                # Try to find fields by looking at an existing Epic if possible
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
        Process a single field to identify if it's an Epic-related field.

        Args:
            field: The field definition
            field_ids: Dictionary of field IDs to update
        """
        try:
            field_id = field.get("id")
            original_name = field.get("name", "")
            field_name = original_name.lower() if original_name else ""

            # Skip if no field ID or name
            if not field_id or not field_name:
                return

            # Get the custom schema type if available
            field_custom = ""
            schema = field.get("schema", {})
            if schema:
                field_custom = schema.get("custom", "").lower()

            # Epic Link field - used to link issues to epics
            if (
                "epic link" in field_name
                or field_custom == "com.pyxis.greenhopper.jira:gh-epic-link"
            ):
                self.epic_link_field_id = field_id
                field_ids["epic_link"] = field_id
                logger.info(f"Found Epic Link field: {original_name} ({field_id})")

            # Epic Name field - used for the title of epics
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
                original_name == "Parent"
                or field_name == "parent"
                or field_name == "parent link"
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
                key in field_ids
                for key in ["epic_link", "epic_name", "epic_status", "epic_color"]
            ):
                key = f"epic_{field_name.replace(' ', '_')}"
                field_ids[key] = field_id
                logger.info(
                    f"Found additional Epic-related field: {original_name} ({field_id})"
                )
        except Exception as e:
            logger.warning(f"Error processing field for Epic data: {str(e)}")

    def _try_discover_fields_from_existing_epic(
        self, field_ids: dict[str, str]
    ) -> None:
        """
        Attempt to discover Epic fields by examining an existing Epic issue.

        This is a fallback method that attempts to find Epic fields by looking
        at actual Epic issues already in the system.

        Args:
            field_ids: Dictionary of field IDs to update
        """
        # If we already have both epic fields, no need to search
        if "epic_link" in field_ids and "epic_name" in field_ids:
            return

        try:
            # Find an Epic in the system
            epics_jql = "issuetype = Epic ORDER BY created DESC"
            results = self.jira.jql(epics_jql, limit=1)

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
                if "epic_name" not in field_ids and isinstance(value, str) and value:
                    field_ids["epic_name"] = field_id
                    logger.info(
                        f"Discovered Epic Name field from existing epic: {field_id}"
                    )

            # Now try to find issues linked to this Epic to discover the Epic Link field
            if "epic_link" not in field_ids:
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
                        link_results = self.jira.jql(query, limit=1)
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
                                    field_ids["epic_link"] = field_id
                                    logger.info(
                                        f"Discovered Epic Link field from linked issue: {field_id}"
                                    )
                                    break

                            # If we found the epic link field, we can stop
                            if "epic_link" in field_ids:
                                break
                    except Exception:  # noqa: BLE001 - Intentional fallback with logging
                        continue

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
            epic_link_field = field_ids.get("epic_link")

            if not epic_link_field:
                error_msg = "Could not determine Epic Link field"
                raise ValueError(error_msg)

            # Update the issue to link it to the epic
            update_fields = {epic_link_field: epic_key}
            self.jira.update_issue(issue_key, fields=update_fields)

            # Return the updated issue
            if hasattr(self, "get_issue") and callable(self.get_issue):
                return self.get_issue(issue_key)
            else:
                # Fallback if get_issue is not available
                logger.warning(
                    "get_issue method not available, returning empty Document"
                )
                return Document(page_content="", metadata={"key": issue_key})

        except Exception as e:
            logger.error(f"Error linking {issue_key} to epic {epic_key}: {str(e)}")
            raise Exception(f"Error linking issue to epic: {str(e)}") from e

    def get_epic_issues(self, epic_key: str, limit: int = 50) -> list[Document]:
        """
        Get all issues linked to a specific epic.

        Args:
            epic_key: The key of the epic (e.g. 'PROJ-123')
            limit: Maximum number of issues to return

        Returns:
            List of Documents representing the issues linked to the epic

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
                    if hasattr(self, "search_issues") and callable(self.search_issues):
                        documents = self.search_issues(jql, limit=limit)
                    else:
                        # Fallback if search_issues is not available
                        results = self.jira.jql(jql, limit=limit)
                        documents = []
                        for issue in results.get("issues", []):
                            key = issue.get("key", "")
                            summary = issue.get("fields", {}).get("summary", "")
                            documents.append(
                                Document(
                                    page_content=summary,
                                    metadata={"key": key, "type": "issue"},
                                )
                            )

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

        except ValueError:
            # Re-raise ValueError for non-epic issues
            raise

        except Exception as e:
            logger.error(f"Error getting issues for epic {epic_key}: {str(e)}")
            raise Exception(f"Error getting epic issues: {str(e)}") from e
