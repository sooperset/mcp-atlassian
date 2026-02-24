"""Module for Jira field operations."""

import logging
from typing import Any

from thefuzz import fuzz

from ..utils import parse_date
from .client import JiraClient
from .protocols import EpicOperationsProto, UsersOperationsProto

logger = logging.getLogger("mcp-jira")


class FieldsMixin(JiraClient, EpicOperationsProto, UsersOperationsProto):
    """Mixin for Jira field operations.

    This mixin provides methods for discovering, caching, and working with Jira fields.
    Field IDs in Jira are crucial for many operations since they can differ across
    different Jira instances, especially for custom fields.
    """

    _field_name_to_id_map: dict[str, str] | None = None  # Cache for name -> id mapping

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
            if self._field_ids_cache is not None and not refresh:
                return self._field_ids_cache

            if refresh:
                self._field_name_to_id_map = (
                    None  # Clear name map cache if refreshing fields
                )

            # Fetch fields from Jira API
            fields = self.jira.get_all_fields()
            if not isinstance(fields, list):
                msg = f"Unexpected return value type from `jira.get_all_fields`: {type(fields)}"
                logger.error(msg)
                raise TypeError(msg)

            # Cache the fields
            self._field_ids_cache = fields

            # Regenerate the name map upon fetching new fields
            self._generate_field_map(force_regenerate=True)

            # Log available fields for debugging
            self._log_available_fields(fields)

            return fields

        except Exception as e:
            logger.error(f"Error getting Jira fields: {str(e)}")
            return []

    def _generate_field_map(self, force_regenerate: bool = False) -> dict[str, str]:
        """Generates and caches a map of lowercase field names to field IDs."""
        if self._field_name_to_id_map is not None and not force_regenerate:
            return self._field_name_to_id_map

        # Ensure fields are loaded into cache first
        fields = (
            self.get_fields()
        )  # Uses cache if available unless force_regenerate was True
        if not fields:
            self._field_name_to_id_map = {}
            return {}

        name_map: dict[str, str] = {}
        id_map: dict[str, str] = {}  # Also map ID to ID for consistency
        for field in fields:
            field_id = field.get("id")
            field_name = field.get("name")
            if field_id:
                id_map[field_id] = field_id  # Map ID to itself
                if field_name:
                    # Store lowercase name -> ID. Handle potential name collisions if necessary.
                    name_map.setdefault(field_name.lower(), field_id)

        # Combine maps, ensuring IDs can also be looked up directly
        self._field_name_to_id_map = name_map | id_map
        logger.debug(
            f"Generated/Updated field name map: {len(self._field_name_to_id_map)} entries"
        )
        return self._field_name_to_id_map

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
            # Ensure the map is generated/cached
            field_map = self._generate_field_map(force_regenerate=refresh)
            if not field_map:
                logger.error("Field map could not be generated.")
                return None

            normalized_name = field_name.lower()
            if normalized_name in field_map:
                return field_map[normalized_name]
            # Fallback: Check if the input IS an ID (using original casing)
            elif field_name in field_map:  # Checks the id_map part
                return field_map[field_name]
            else:
                logger.warning(f"Field '{field_name}' not found in generated map.")
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

    def get_required_fields(self, issue_type: str, project_key: str) -> dict[str, Any]:
        """
        Get required fields for creating an issue of a specific type in a project.

        Args:
            issue_type: The issue type (e.g., 'Bug', 'Story', 'Epic')
            project_key: The project key (e.g., 'PROJ')

        Returns:
            Dictionary mapping required field names to their definitions
        """
        # Initialize cache if it doesn't exist
        if not hasattr(self, "_required_fields_cache"):
            self._required_fields_cache = {}

        # Check cache first
        cache_key = (project_key, issue_type)
        if cache_key in self._required_fields_cache:
            logger.debug(
                f"Returning cached required fields for {issue_type} in {project_key}"
            )
            return self._required_fields_cache[cache_key]

        try:
            # Step 1: Get the ID for the given issue type name within the project
            if not hasattr(self, "get_project_issue_types"):
                logger.error(
                    "get_project_issue_types method not available. Cannot resolve issue type ID."
                )
                return {}

            all_issue_types = self.get_project_issue_types(project_key)
            issue_type_id = None
            for it in all_issue_types:
                if it.get("name", "").lower() == issue_type.lower():
                    issue_type_id = it.get("id")
                    break

            if not issue_type_id:
                logger.warning(
                    f"Issue type '{issue_type}' not found in project '{project_key}'"
                )
                return {}

            # Step 2: Call the correct API method to get field metadata
            meta = self.jira.issue_createmeta_fieldtypes(
                project=project_key, issue_type_id=issue_type_id
            )

            required_fields = {}
            # Step 3: Parse the response and extract required fields
            # The new createmeta endpoint returns paginated "values" array
            if isinstance(meta, dict):
                field_list = meta.get("values", meta.get("fields", []))
                if isinstance(field_list, list):
                    for field_meta in field_list:
                        if isinstance(field_meta, dict) and field_meta.get(
                            "required", False
                        ):
                            field_id = field_meta.get("fieldId")
                            if field_id:
                                required_fields[field_id] = field_meta
                else:
                    logger.warning("Unexpected format in createmeta response.")

            if not required_fields:
                logger.warning(
                    f"No required fields found for issue type '{issue_type}' "
                    f"in project '{project_key}'"
                )

            # Cache the result before returning
            self._required_fields_cache[cache_key] = required_fields
            logger.debug(
                f"Cached required fields for {issue_type} in {project_key}: "
                f"{len(required_fields)} fields"
            )

            return required_fields

        except Exception as e:
            logger.error(
                f"Error getting required fields for issue type '{issue_type}' "
                f"in project '{project_key}': {str(e)}"
            )
            return {}

    def get_field_ids_to_epic(self) -> dict[str, str]:
        """
        Dynamically discover Jira field IDs relevant to Epic linking.
        This method queries the Jira API to find the correct custom field IDs
        for Epic-related fields, which can vary between different Jira instances.

        Returns:
            Dictionary mapping field names to their IDs
            (e.g., {'epic_link': 'customfield_10014', 'epic_name': 'customfield_10011'})
        """
        try:
            # Ensure field list and map are cached/generated
            self._generate_field_map()  # Generates map and ensures fields are cached

            # Get all fields (uses cache if available)
            fields = self.get_fields()
            if not fields:  # Check if get_fields failed or returned empty
                logger.error(
                    "Could not load field definitions for epic field discovery."
                )
                return {}

            field_ids = {}

            # Log the complete list of fields for debugging
            all_field_names = [field.get("name", "").lower() for field in fields]
            logger.debug(f"All field names: {all_field_names}")

            # Enhanced logging for debugging
            custom_fields = {
                field.get("id", ""): field.get("name", "")
                for field in fields
                if field.get("id", "").startswith("customfield_")
            }
            logger.debug(f"Custom fields: {custom_fields}")

            # Look for Epic-related fields - use multiple strategies to identify them
            for field in fields:
                field_name = field.get("name", "").lower()
                original_name = field.get("name", "")
                field_id = field.get("id", "")
                field_schema = field.get("schema", {})
                field_custom = field_schema.get("custom", "")

                if original_name and field_id:
                    field_ids[original_name] = field_id

                # Epic Link field - used to link issues to epics
                if (
                    field_name == "epic link"
                    or field_name == "epic"
                    or "epic link" in field_name
                    or field_custom == "com.pyxis.greenhopper.jira:gh-epic-link"
                    or field_id == "customfield_10014"
                ):  # Common in Jira Cloud
                    field_ids["epic_link"] = field_id
                    # For backward compatibility
                    field_ids["Epic Link"] = field_id
                    logger.debug(f"Found Epic Link field: {field_id} ({original_name})")

                # Epic Name field - used when creating epics
                elif (
                    field_name == "epic name"
                    or field_name == "epic title"
                    or "epic name" in field_name
                    or field_custom == "com.pyxis.greenhopper.jira:gh-epic-label"
                    or field_id == "customfield_10011"
                ):  # Common in Jira Cloud
                    field_ids["epic_name"] = field_id
                    # For backward compatibility
                    field_ids["Epic Name"] = field_id
                    logger.debug(f"Found Epic Name field: {field_id} ({original_name})")

                # Epic Status field
                elif (
                    field_name == "epic status"
                    or "epic status" in field_name
                    or field_custom == "com.pyxis.greenhopper.jira:gh-epic-status"
                ):
                    field_ids["epic_status"] = field_id
                    logger.debug(
                        f"Found Epic Status field: {field_id} ({original_name})"
                    )

                # Epic Color field
                elif (
                    field_name == "epic color"
                    or field_name == "epic colour"
                    or "epic color" in field_name
                    or "epic colour" in field_name
                    or field_custom == "com.pyxis.greenhopper.jira:gh-epic-color"
                ):
                    field_ids["epic_color"] = field_id
                    logger.debug(
                        f"Found Epic Color field: {field_id} ({original_name})"
                    )

                # Parent field - sometimes used instead of Epic Link
                elif (
                    field_name == "parent"
                    or field_name == "parent issue"
                    or "parent issue" in field_name
                ):
                    field_ids["parent"] = field_id
                    logger.debug(f"Found Parent field: {field_id} ({original_name})")

                # Try to detect any other fields that might be related to Epics
                elif "epic" in field_name and field_id.startswith("customfield_"):
                    key = f"epic_{field_name.replace(' ', '_').replace('-', '_')}"
                    field_ids[key] = field_id
                    logger.debug(
                        f"Found potential Epic-related field: {field_id} ({original_name})"
                    )

            # If we couldn't find certain key fields, try alternative approaches
            if "epic_name" not in field_ids or "epic_link" not in field_ids:
                logger.debug(
                    "Standard field search didn't find all Epic fields, trying alternative approaches"
                )
                self._try_discover_fields_from_existing_epic(field_ids)

            logger.debug(f"Discovered field IDs: {field_ids}")

            return field_ids

        except Exception as e:
            logger.error(f"Error discovering Jira field IDs: {str(e)}")
            # Return an empty dict as fallback
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

    def format_field_value(self, field_id: str, value: Any) -> Any:
        """
        Format a field value based on its type for update operations.

        Delegates to _format_field_value_for_write with field definition lookup.

        Args:
            field_id: The ID of the field
            value: The value to format

        Returns:
            Properly formatted value for the field
        """
        field_def = self.get_field_by_id(field_id)
        return self._format_field_value_for_write(field_id, value, field_def)

    def _format_field_value_for_write(
        self, field_id: str, value: Any, field_definition: dict | None
    ) -> Any:
        """Format field values for the Jira API.

        Dispatch order:
        1. System field IDs (field_id.lower()) — always reliable
        2. Schema type from field_definition — covers custom fields

        Args:
            field_id: The Jira field ID (e.g. "priority", "customfield_10020")
            value: The raw value to format
            field_definition: Field definition dict from get_field_by_id(), or None

        Returns:
            Formatted value suitable for the Jira API, or None on invalid input
        """
        schema_type = (
            field_definition.get("schema", {}).get("type") if field_definition else None
        )
        schema_custom = (
            field_definition.get("schema", {}).get("custom")
            if field_definition
            else None
        )

        # --- 0. Check custom field plugins (before system/schema dispatch) ---
        if schema_custom and "checklist" in schema_custom.lower():
            if schema_type == "array":
                return value  # Array-type checklist (Server/DC): pass through
            return self._format_checklist_value(value)

        # --- 1. Dispatch on system field ID (reliable, not display name) ---
        normalized_id = field_id.lower()

        if normalized_id == "priority":
            if isinstance(value, str):
                return {"name": value}
            elif isinstance(value, dict) and ("name" in value or "id" in value):
                return value
            else:
                logger.warning(
                    f"Invalid format for priority field: {value}. "
                    "Expected string name or dict."
                )
                return None

        elif normalized_id == "labels":
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                return value
            elif isinstance(value, str):
                return [label.strip() for label in value.split(",") if label.strip()]
            else:
                logger.warning(
                    f"Invalid format for labels field: {value}. "
                    "Expected list of strings or comma-separated string."
                )
                return None

        elif normalized_id in ("fixversions", "versions", "components"):
            if isinstance(value, list):
                formatted_list = []
                for item in value:
                    if isinstance(item, str):
                        formatted_list.append({"name": item})
                    elif isinstance(item, dict) and ("name" in item or "id" in item):
                        formatted_list.append(item)
                    else:
                        logger.warning(
                            f"Invalid item format in {normalized_id} list: {item}"
                        )
                return formatted_list
            else:
                logger.warning(
                    f"Invalid format for {normalized_id} field: {value}. Expected list."
                )
                return None

        elif normalized_id == "reporter":
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
                return value
            else:
                logger.warning(f"Invalid format for reporter field: {value}")
                return None

        elif normalized_id == "duedate":
            if isinstance(value, str):
                return value
            else:
                logger.warning(
                    f"Invalid format for duedate field: {value}. "
                    "Expected YYYY-MM-DD string."
                )
                return None

        # --- 2. Dispatch on schema type (covers custom fields) ---
        elif schema_type == "option-with-child":
            if isinstance(value, tuple) and len(value) == 2:
                return {"value": value[0], "child": {"value": value[1]}}
            elif isinstance(value, str):
                return {"value": value}
            elif isinstance(value, dict):
                return value
            return value

        elif schema_type == "option":
            if isinstance(value, str):
                return {"value": value}
            return value

        elif schema_type == "array":
            items_type = (
                field_definition.get("schema", {}).get("items")
                if field_definition
                else None
            )
            if items_type == "option":
                if isinstance(value, str):
                    return [{"value": v.strip()} for v in value.split(",") if v.strip()]
                elif isinstance(value, list):
                    return [
                        {"value": item} if isinstance(item, str) else item
                        for item in value
                    ]
            elif items_type in ("version", "component"):
                if isinstance(value, list):
                    return [
                        {"name": item} if isinstance(item, str) else item
                        for item in value
                    ]
            return value

        elif schema_type == "user":
            if isinstance(value, str):
                try:
                    identifier = self._get_account_id(value)
                    if self.config.is_cloud:
                        return {"accountId": identifier}
                    else:
                        return {"name": identifier}
                except (ValueError, Exception) as e:
                    logger.warning(f"Could not resolve user for field {field_id}: {e}")
                    return None
            return value

        elif schema_type == "date":
            if isinstance(value, str):
                return value
            logger.warning(f"Invalid format for date field {field_id}: {value}")
            return None

        elif schema_type == "datetime" and isinstance(value, str):
            try:
                dt = parse_date(value)
                if dt is None:
                    return value
                # Jira requires ISO 8601 basic tz format (±HHMM), not extended (±HH:MM)
                iso_str = dt.isoformat(timespec="milliseconds")
                # Strip colon from tz offset: +HH:MM → +HHMM, -HH:MM → -HHMM
                if dt.tzinfo is not None and len(iso_str) >= 6 and iso_str[-3] == ":":
                    iso_str = iso_str[:-3] + iso_str[-2:]
                return iso_str
            except Exception:
                logger.warning(
                    f"Could not parse datetime for field {field_id}: {value}"
                )
                return value

        # Default: return value as-is
        return value

    @staticmethod
    def _format_checklist_value(value: Any) -> Any:
        """Format a checklist field value to markdown string.

        Checklist plugins (e.g., Okapya "Checklist for Jira") store data
        as markdown-formatted text. This converts various input formats
        to the expected string format.

        Args:
            value: The raw checklist value (list, string, etc.)

        Returns:
            Markdown-formatted checklist string
        """
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            lines = []
            for item in value:
                if isinstance(item, str):
                    lines.append(f"* {item}")
                elif isinstance(item, tuple) and len(item) == 2:
                    name, checked = item
                    prefix = "* [x] " if checked else "* "
                    lines.append(f"{prefix}{name}")
                elif isinstance(item, dict):
                    name = item.get("name", "")
                    checked = item.get("checked", False)
                    prefix = "* [x] " if checked else "* "
                    lines.append(f"{prefix}{name}")
            return "\n".join(lines)
        return value

    def search_fields(
        self, keyword: str, limit: int = 10, *, refresh: bool = False
    ) -> list[dict[str, Any]]:
        """
        Search fields using fuzzy matching.

        Args:
            keyword: The search keyword
            limit: Maximum number of results to return (default: 10)
            refresh: When True, forces a refresh from the server

        Returns:
            List of matching field definitions, sorted by relevance
        """
        try:
            # Get all fields
            fields = self.get_fields(refresh=refresh)

            # if keyword is empty, return `limit` fields
            if not keyword:
                return fields[:limit]

            def similarity(keyword: str, field: dict) -> int:
                """Calculate similarity score between keyword and field."""
                name_candidates = [
                    field.get("id", ""),
                    field.get("key", ""),
                    field.get("name", ""),
                    *field.get("clauseNames", []),
                ]

                # Calculate the fuzzy match score
                return max(
                    fuzz.partial_ratio(keyword.lower(), name.lower())
                    for name in name_candidates
                )

            # Sort by similarity
            sorted_fields = sorted(
                fields, key=lambda x: similarity(keyword, x), reverse=True
            )

            # Return the top limit results
            return sorted_fields[:limit]

        except Exception as e:
            logger.error(f"Error searching fields: {str(e)}")
            return []
