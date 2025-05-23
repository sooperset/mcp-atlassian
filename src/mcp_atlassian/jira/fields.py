"""Module for Jira field operations."""

import logging
from typing import Any

from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class FieldsMixin(JiraClient):
    """Mixin for Jira field operations.

    This mixin provides methods for discovering, caching, and working with Jira fields.
    Field IDs in Jira are crucial for many operations since they can differ across
    different Jira instances, especially for custom fields.
    """

    def get_fields(self, refresh: bool = False) -> list[dict[str, Any]]:
        """
        Get all available fields from Jira.

        Args:
            refresh: When True, forces a refresh from the server instead of using cache

        Returns:
            List of field definitions
        """
        try:
            # Use cached field data if available and refresh is not requested
            if hasattr(self, "_fields_cache") and self._fields_cache and not refresh:
                return self._fields_cache

            # Fetch fields from Jira API
            fields = self.jira.get_all_fields()

            # Cache the fields
            self._fields_cache = fields

            # Log available fields for debugging
            self._log_available_fields(fields)

            return fields

        except Exception as e:
            logger.error(f"Error getting Jira fields: {str(e)}")
            return []

    def get_field_id(self, field_name: str, refresh: bool = False) -> str | None:
        """
        Get the ID for a specific field by name.

        Args:
            field_name: The name of the field to look for (case-insensitive)
            refresh: When True, forces a refresh from the server

        Returns:
            Field ID if found, None otherwise
        """
        try:
            # Normalize the field name to lowercase for case-insensitive matching
            normalized_name = field_name.lower()

            # Get all fields and search for the requested field
            fields = self.get_fields(refresh=refresh)

            for field in fields:
                name = field.get("name", "")
                if name and name.lower() == normalized_name:
                    return field.get("id")

            # If not found by exact match, try partial match
            for field in fields:
                name = field.get("name", "")
                if name and normalized_name in name.lower():
                    logger.info(
                        f"Found field '{name}' as partial match for '{field_name}'"
                    )
                    return field.get("id")

            logger.warning(f"Field '{field_name}' not found")
            return None

        except Exception as e:
            logger.error(f"Error getting field ID for '{field_name}': {str(e)}")
            return None

    def get_field_by_id(
        self, field_id: str, refresh: bool = False
    ) -> dict[str, Any] | None:
        """
        Get field definition by ID.

        Args:
            field_id: The ID of the field to look for
            refresh: When True, forces a refresh from the server

        Returns:
            Field definition if found, None otherwise
        """
        try:
            fields = self.get_fields(refresh=refresh)

            for field in fields:
                if field.get("id") == field_id:
                    return field

            logger.warning(f"Field with ID '{field_id}' not found")
            return None

        except Exception as e:
            logger.error(f"Error getting field by ID '{field_id}': {str(e)}")
            return None

    def get_custom_fields(self, refresh: bool = False) -> list[dict[str, Any]]:
        """
        Get all custom fields.

        Args:
            refresh: When True, forces a refresh from the server

        Returns:
            List of custom field definitions
        """
        try:
            fields = self.get_fields(refresh=refresh)
            custom_fields = [
                field
                for field in fields
                if field.get("id", "").startswith("customfield_")
            ]

            return custom_fields

        except Exception as e:
            logger.error(f"Error getting custom fields: {str(e)}")
            return []
            
    def get_issue_type_id(self, project_key: str, issue_type_name: str) -> str:
        """
        Get the ID of an issue type by its name for a specific project.
        
        Args:
            project_key: The project key (e.g., 'PROJ')
            issue_type_name: The name of the issue type (e.g., 'Story', 'Bug')
            
        Returns:
            The ID of the issue type if found, empty string otherwise
        """
        try:
            # Get issue types for the project
            issue_types = self.jira.issue_createmeta_issuetypes(
                project=project_key
            )
            
            logger.debug(f"Issue types for project '{project_key}': {issue_types}")
            # Find the issue type ID that matches the given name
            for issue_type in issue_types.get("issueTypes", []):
                if issue_type.get("name") == issue_type_name:
                    return issue_type.get("id", "")
                    
            logger.warning(f"Issue type '{issue_type_name}' not found in project '{project_key}'")
            return ""
            
        except Exception as e:
            logger.error(f"Error getting issue type ID for '{issue_type_name}' in project '{project_key}': {str(e)}")
            return ""
    
    def get_project_fields(self, project_key: str, issue_type_name: str, include_standard_fields: bool = True,
                           include_custom_fields: bool = True, refresh: bool = False) -> list[dict[str, Any]]:
        """
        Get all fields (standard and/or custom) configured for a specific JIRA project and issue type.
        
        This method retrieves the fields that are available for use in the specified project and issue type,
        which can include both standard Jira fields and custom fields. It uses the issue_createmeta_fieldtypes
        endpoint to get detailed information about each field, including whether it's required, its allowed
        values, and other metadata.
        
        The method first gets all fields from Jira, then filters them based on the fields available
        for the specified project and issue type. It also enhances the field definitions with
        project-specific metadata such as whether the field is required and its allowed values.
        
        Args:
            project_key: The project key (e.g., 'PROJ')
            issue_type_name: The name of the issue type (e.g., 'Story', 'Bug')
            include_standard_fields: Whether to include standard Jira fields
            include_custom_fields: Whether to include custom fields
            refresh: When True, forces a refresh from the server
            
        Returns:
            List of field definitions available for the project and issue type
        """
        try:
            # Get all fields first
            all_fields = self.get_fields(refresh=refresh)

            # Get the issue type ID
            issue_type_id = self.get_issue_type_id(project_key, issue_type_name)
            
            if not issue_type_id:
                logger.error(f"Could not find issue type '{issue_type_name}' in project '{project_key}'")
                return []
                
            # Get project metadata to determine which fields are used in this project
            # We use the createmeta endpoint which provides field information for issue creation
            try:
                meta = self.jira.issue_createmeta_fieldtypes(
                    project=project_key,
                    issue_type_id=issue_type_id
                )
            except Exception as e:
                logger.error(f"Error fetching field metadata for project '{project_key}' and issue type '{issue_type_name}': {str(e)}")
                return []

            # Log the structure of the metadata for debugging
            logger.debug(f"Project metadata structure for '{project_key}' and issue type '{issue_type_name}':")
            if "fields" in meta:
                fields_type = type(meta["fields"]).__name__
                fields_count = len(meta["fields"]) if meta["fields"] else 0
                logger.debug(f"Found {fields_count} fields in the metadata (type: {fields_type})")
                
                # Log the first field to help with debugging
                if fields_count > 0:
                    if isinstance(meta["fields"], list) and meta["fields"]:
                        first_field = meta["fields"][0]
                        logger.debug(f"First field sample: {first_field}")
                    elif isinstance(meta["fields"], dict) and meta["fields"]:
                        first_key = next(iter(meta["fields"]))
                        logger.debug(f"First field sample: {first_key} -> {meta['fields'][first_key]}")
            else:
                logger.warning(f"No 'fields' found in metadata for '{project_key}' and issue type '{issue_type_name}'")
            # Extract fields from the metadata
            project_fields = {}
            
            # The issue_createmeta_fieldtypes endpoint returns field information directly
            # in the "fields" object at the top level of the response
            if "fields" in meta:
                # Check if fields is a list or a dictionary
                if isinstance(meta["fields"], list):
                    # Handle list of field objects
                    for field_meta in meta["fields"]:
                        if "key" in field_meta:
                            # Use the key as the field_id
                            field_id = field_meta["key"]
                            project_fields[field_id] = field_meta
                        elif "fieldId" in field_meta:
                            # Alternative: use fieldId if key is not present
                            field_id = field_meta["fieldId"]
                            project_fields[field_id] = field_meta
                else:
                    # Handle dictionary of field objects (original behavior)
                    for field_id, field_meta in meta["fields"].items():
                        project_fields[field_id] = field_meta
            
            # Filter the all_fields list to only include fields that are in project_fields
            result = []
            for field in all_fields:
                field_id = field.get("id")
                
                # Skip if field_id is not in the project fields
                if field_id not in project_fields:
                    continue
                    
                # Check if it's a custom field
                is_custom = field_id.startswith("customfield_")
                
                # Apply filters based on field type
                if (is_custom and include_custom_fields) or (not is_custom and include_standard_fields):
                    # Enhance the field definition with additional metadata from project_fields
                    enhanced_field = field.copy()
                    
                    # Add project-specific field metadata
                    project_meta = project_fields.get(field_id, {})
                    enhanced_field["required"] = project_meta.get("required", False)
                    enhanced_field["project_meta"] = {
                        "required": project_meta.get("required", False),
                        "has_default": "defaultValue" in project_meta,
                        "allowed_values": project_meta.get("allowedValues", [])
                    }
                    
                    result.append(enhanced_field)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting fields for project {project_key}: {str(e)}")
            return []

    def get_required_fields(self, issue_type: str, project_key: str) -> dict[str, Any]:
        """
        Get required fields for creating an issue of a specific type in a project.

        Args:
            issue_type: The issue type (e.g., 'Bug', 'Story', 'Epic')
            project_key: The project key (e.g., 'PROJ')

        Returns:
            Dictionary mapping required field names to their definitions
        """
        try:
            # Create meta provides field requirements for different issue types
            create_meta = self.jira.createmeta(
                projectKeys=project_key,
                issuetypeNames=issue_type,
                expand="projects.issuetypes.fields",
            )

            required_fields = {}

            # Navigate the nested structure to find required fields
            if "projects" in create_meta:
                for project in create_meta["projects"]:
                    if project.get("key") == project_key:
                        if "issuetypes" in project:
                            for issuetype in project["issuetypes"]:
                                if issuetype.get("name") == issue_type:
                                    fields = issuetype.get("fields", {})
                                    # Extract required fields
                                    for field_id, field_meta in fields.items():
                                        if field_meta.get("required", False):
                                            required_fields[field_id] = field_meta

            if not required_fields:
                logger.warning(
                    f"No required fields found for issue type '{issue_type}' "
                    f"in project '{project_key}'"
                )

            return required_fields

        except Exception as e:
            logger.error(
                f"Error getting required fields for issue type '{issue_type}' "
                f"in project '{project_key}': {str(e)}"
            )
            return {}

    def get_jira_field_ids(self) -> dict[str, str]:
        """
        Get a mapping of field names to their IDs.

        This method is maintained for backward compatibility and is used
        by multiple other mixins like EpicsMixin.

        Returns:
            Dictionary mapping field names to their IDs
        """
        # Check if we've already cached the field_ids
        if hasattr(self, "_field_ids_cache") and self._field_ids_cache:
            return self._field_ids_cache

        # Initialize cache if needed
        if not hasattr(self, "_field_ids_cache"):
            self._field_ids_cache = {}

        try:
            # Get all fields
            fields = self.get_fields()
            field_ids = {}

            # Extract field IDs
            for field in fields:
                name = field.get("name")
                field_id = field.get("id")
                if name and field_id:
                    field_ids[name] = field_id

            # Cache the results
            self._field_ids_cache = field_ids
            return field_ids

        except Exception as e:
            logger.error(f"Error getting field IDs: {str(e)}")
            return {}

    def _log_available_fields(self, fields: list[dict]) -> None:
        """
        Log available fields for debugging.

        Args:
            fields: List of field definitions
        """
        logger.debug("Available Jira fields:")
        for field in fields:
            field_id = field.get("id", "")
            name = field.get("name", "")
            field_type = field.get("schema", {}).get("type", "")
            logger.debug(f"{field_id}: {name} ({field_type})")

    def is_custom_field(self, field_id: str) -> bool:
        """
        Check if a field is a custom field.

        Args:
            field_id: The field ID to check

        Returns:
            True if it's a custom field, False otherwise
        """
        return field_id.startswith("customfield_")

    def format_field_value(self, field_id: str, value: Any) -> dict[str, Any]:
        """
        Format a field value based on its type for update operations.

        Different field types in Jira require different JSON formats when updating.
        This method helps format the value correctly for the specific field type.

        Args:
            field_id: The ID of the field
            value: The value to format

        Returns:
            Properly formatted value for the field
        """
        try:
            # Get field definition
            field = self.get_field_by_id(field_id)

            if not field:
                # For unknown fields, return value as-is
                return value

            field_type = field.get("schema", {}).get("type")

            # Format based on field type
            if field_type == "user":
                # Handle user fields - need accountId for cloud or name for server
                if isinstance(value, str):
                    if hasattr(self, "_get_account_id") and callable(
                        self._get_account_id
                    ):
                        try:
                            account_id = self._get_account_id(value)
                            return {"accountId": account_id}
                        except Exception as e:
                            logger.warning(
                                f"Could not resolve user '{value}': {str(e)}"
                            )
                            return value
                    else:
                        # For server/DC, just use the name
                        return {"name": value}
                else:
                    return value

            elif field_type == "array":
                # Handle array fields - convert single value to list if needed
                if not isinstance(value, list):
                    return [value]
                return value

            elif field_type == "option":
                # Handle option fields - convert to {"value": value} format
                if isinstance(value, str):
                    return {"value": value}
                return value

            # For other types, return as-is
            return value

        except Exception as e:
            logger.warning(f"Error formatting field value for '{field_id}': {str(e)}")
            return value
