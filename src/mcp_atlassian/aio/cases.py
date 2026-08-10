"""Module for AIO Tests test case operations."""

import html
import logging
from typing import Any

from ..models.aio import AIOTestCase, AIOTestCaseSearchResult
from .constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MIN_PAGE_SIZE,
    READ_ONLY_CASE_FIELDS,
    RICH_TEXT_CASE_FIELDS,
    RICH_TEXT_CUSTOM_FIELD_TYPE,
    RICH_TEXT_STEP_KEYS,
    STEP_TYPES,
)
from .folders import FoldersMixin
from .projects import ProjectsMixin
from .tags import TagsMixin

logger = logging.getLogger("mcp-aio")

# Mapping of the snake_case step keys accepted by this server to the API keys.
_STEP_KEY_MAP = {
    "step": "step",
    "data": "data",
    "expected_result": "expectedResult",
    "expectedresult": "expectedResult",
    "bdd_step": "bddStep",
    "bddstep": "bddStep",
    "step_type": "stepType",
    "steptype": "stepType",
    "id": "ID",
}


def _build_step_payload(step: dict[str, Any], index: int) -> dict[str, Any]:
    """Convert a step given to a tool into the API step payload.

    Args:
        step: Step definition using snake_case or API keys.
        index: Zero-based position of the step, used in error messages.

    Returns:
        The API step payload.

    Raises:
        ValueError: If the step is malformed or uses an unknown step type.
    """
    if not isinstance(step, dict):
        raise ValueError(
            f"Step {index + 1} must be an object, got {type(step).__name__}"
        )

    payload: dict[str, Any] = {}
    for key, value in step.items():
        normalized = _STEP_KEY_MAP.get(str(key).lower())
        if normalized is None:
            if str(key) == "referenced_case_key":
                payload["referencedCase"] = {"key": value}
                continue
            raise ValueError(
                f"Unknown key '{key}' in step {index + 1}. Supported keys: "
                "step, data, expected_result, bdd_step, step_type, "
                "referenced_case_key"
            )
        if value is not None:
            payload[normalized] = value

    step_type = payload.get("stepType")
    if not step_type:
        step_type = "BDD_GIVEN" if payload.get("bddStep") else "TEXT"
        payload["stepType"] = step_type
    if step_type not in STEP_TYPES:
        raise ValueError(
            f"Invalid step_type '{step_type}' in step {index + 1}. "
            f"Expected one of: {', '.join(STEP_TYPES)}"
        )
    if step_type.startswith("BDD_") and not payload.get("bddStep"):
        raise ValueError(f"Step {index + 1} uses {step_type} but has no bdd_step text")
    if step_type == "TEXT" and not payload.get("step"):
        raise ValueError(f"Step {index + 1} is a TEXT step but has no step text")
    if step_type == "REFERENCE" and "referencedCase" not in payload:
        raise ValueError(
            f"Step {index + 1} is a REFERENCE step but has no referenced_case_key"
        )
    return payload


def _plain_text_to_html(value: Any) -> Any:
    """Escape plain text so it survives being stored as rich text.

    Args:
        value: The value to escape; non-string values are returned unchanged.

    Returns:
        The HTML-escaped value with line breaks preserved.
    """
    if not isinstance(value, str):
        return value
    return html.escape(value).replace("\n", "<br/>")


def _date_criteria(after: str | None, before: str | None) -> dict[str, Any] | None:
    """Build a date search criteria from an optional range.

    Args:
        after: Lower bound of the range, if any.
        before: Upper bound of the range, if any.

    Returns:
        The criteria payload, or None when no bound was given.
    """
    if after and before:
        return {"comparisonType": "BETWEEN", "value1": after, "value2": before}
    if after:
        return {"comparisonType": "AFTER", "value1": after}
    if before:
        return {"comparisonType": "BEFORE", "value1": before}
    return None


class TestCasesMixin(ProjectsMixin, FoldersMixin, TagsMixin):
    """Mixin for AIO Tests test case operations."""

    def get_test_case(
        self,
        project_key: str,
        test_case_id: str,
        *,
        version: int | None = None,
        include_rtf: bool = False,
        include_attachments: bool = False,
    ) -> AIOTestCase:
        """Retrieve the complete details of a test case.

        Args:
            project_key: Jira project key or ID.
            test_case_id: Case key (e.g. ``AT-TC-17``) or numeric case ID.
            version: Case version to read. Ignored when a numeric case ID is
                given; defaults to the latest version.
            include_rtf: Keep the HTML markup of rich-text fields.
            include_attachments: Include attachment metadata.

        Returns:
            The test case details.
        """
        response = self.get(
            self.project_path(project_key, "testcase", test_case_id, "detail"),
            params={
                "needDataInRTF": include_rtf or None,
                "needAttachments": include_attachments or None,
                "version": version,
            },
        )
        return AIOTestCase.from_api_response(
            response if isinstance(response, dict) else {}
        )

    def get_test_case_versions(
        self, project_key: str, test_case_id: str
    ) -> AIOTestCase:
        """Retrieve the version history of a test case.

        Args:
            project_key: Jira project key or ID.
            test_case_id: Case key (e.g. ``AT-TC-17``) or numeric case ID.

        Returns:
            The test case, whose ``versions`` list holds every saved version
            with the case ID that stores it.
        """
        return self.get_test_case(project_key, test_case_id)

    def search_test_cases(
        self,
        project_key: str,
        *,
        title: str | None = None,
        title_match: str = "CONTAINS",
        keys: list[str] | None = None,
        folders: list[Any] | None = None,
        statuses: list[Any] | None = None,
        priorities: list[Any] | None = None,
        types: list[Any] | None = None,
        automation_statuses: list[Any] | None = None,
        tags: list[str] | None = None,
        owner_ids: list[str] | None = None,
        requirement_ids: list[str] | None = None,
        automation_key: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        updated_after: str | None = None,
        updated_before: str | None = None,
        include_archived: bool | None = None,
        start_at: int = 0,
        max_results: int = DEFAULT_PAGE_SIZE,
        include_rtf: bool = False,
    ) -> AIOTestCaseSearchResult:
        """Search test cases in a project.

        Lookup filters accept either names or numeric IDs; names are resolved
        against the project configuration. When no filter is given, the plain
        case listing is returned.

        Args:
            project_key: Jira project key or ID.
            title: Text to match against the case title.
            title_match: ``CONTAINS`` or ``EXACT_MATCH``.
            keys: Case keys to match.
            folders: Folder IDs, names or paths.
            statuses: Case status names or IDs.
            priorities: Case priority names or IDs.
            types: Case type names or IDs.
            automation_statuses: Automation status names or IDs.
            tags: Tag names.
            owner_ids: Jira account IDs of case owners.
            requirement_ids: Jira issue keys or IDs covered by the case.
            automation_key: Automation key to match (contains).
            created_after: Lower bound of the creation date range.
            created_before: Upper bound of the creation date range.
            updated_after: Lower bound of the update date range.
            updated_before: Upper bound of the update date range.
            include_archived: Filter on the archived flag.
            start_at: Index of the first result.
            max_results: Maximum number of results to return.
            include_rtf: Keep the HTML markup of rich-text fields.

        Returns:
            A page of matching test cases.

        Raises:
            ValueError: If a lookup name or folder cannot be resolved.
        """
        criteria: dict[str, Any] = {}
        if title:
            match = str(title_match).upper()
            if match not in ("CONTAINS", "EXACT_MATCH"):
                raise ValueError(
                    f"Invalid title_match '{title_match}'. "
                    "Expected CONTAINS or EXACT_MATCH."
                )
            criteria["title"] = {"comparisonType": match, "value": title}
        if automation_key:
            criteria["automationKey"] = {
                "comparisonType": "CONTAINS",
                "value": automation_key,
            }
        if keys:
            criteria["key"] = {"comparisonType": "IN", "list": [str(k) for k in keys]}
        if owner_ids:
            criteria["ownedByID"] = {
                "comparisonType": "IN",
                "list": [str(value) for value in owner_ids],
            }
        if requirement_ids:
            criteria["requirementID"] = {
                "comparisonType": "IN",
                "list": [str(value) for value in requirement_ids],
            }
        if tags:
            criteria["tag"] = {
                "comparisonType": "IN",
                "list": [str(value) for value in tags],
            }
        if folders:
            criteria["folderID"] = {
                "comparisonType": "IN",
                "list": [
                    self.resolve_folder_id(project_key, folder) for folder in folders
                ],
            }
        for field, values, config_key in (
            ("statusID", statuses, "caseStatuses"),
            ("priorityID", priorities, "casePriorities"),
            ("typeID", types, "caseTypes"),
            ("automationStatusID", automation_statuses, "caseAutomationStatuses"),
        ):
            if values:
                criteria[field] = {
                    "comparisonType": "IN",
                    "list": [
                        self.resolve_lookup_id(project_key, config_key, value)
                        for value in values
                    ],
                }
        created = _date_criteria(created_after, created_before)
        if created:
            criteria["createdDate"] = created
        updated = _date_criteria(updated_after, updated_before)
        if updated:
            criteria["updatedDate"] = updated
        if include_archived is not None:
            criteria["isArchived"] = {"value": include_archived}

        requested = max(1, int(max_results))
        page_size = min(MAX_PAGE_SIZE, max(MIN_PAGE_SIZE, requested))
        params: dict[str, Any] = {
            "startAt": start_at,
            "maxResults": page_size,
            "needDataInRTF": include_rtf or None,
        }

        if criteria:
            response = self.post(
                self.project_path(project_key, "testcase", "search"),
                json=criteria,
                params=params,
            )
        else:
            response = self.get(
                self.project_path(project_key, "testcase"), params=params
            )

        result = AIOTestCaseSearchResult.from_api_response(
            response if isinstance(response, dict) else {}
        )
        if len(result.cases) > requested:
            result.cases = result.cases[:requested]
            result.is_last = False
        result.max_results = requested
        return result

    def create_test_case(
        self,
        project_key: str,
        title: str,
        *,
        include_rtf: bool = False,
        create_folder_if_missing: bool = True,
        **fields: Any,
    ) -> AIOTestCase:
        """Create a test case.

        Args:
            project_key: Jira project key or ID.
            title: Case title. The only mandatory field.
            include_rtf: Treat rich-text field values as HTML instead of plain
                text.
            create_folder_if_missing: Create the target folder hierarchy when it
                does not exist yet.
            **fields: Optional case fields, see :meth:`_build_case_payload`.

        Returns:
            The created test case.

        Raises:
            ValueError: If the title is empty or a field value cannot be
                resolved.
        """
        if not title or not title.strip():
            raise ValueError("Test case title is required")

        payload = self._build_case_payload(
            project_key,
            fields,
            create_folder_if_missing=create_folder_if_missing,
        )
        payload["title"] = title

        response = self.post(
            self.project_path(project_key, "testcase"),
            json=payload,
            params={"needDataInRTF": include_rtf or None},
        )
        return AIOTestCase.from_api_response(
            response if isinstance(response, dict) else {}
        )

    def update_test_case(
        self,
        project_key: str,
        test_case_id: str,
        *,
        version: int | None = None,
        create_new_version: bool = False,
        include_rtf: bool = False,
        create_folder_if_missing: bool = True,
        **fields: Any,
    ) -> AIOTestCase:
        """Update an existing test case.

        Only the supplied fields change; everything else is carried over from
        the current case, as the API replaces the whole case document.

        Args:
            project_key: Jira project key or ID.
            test_case_id: Case key (e.g. ``AT-TC-17``) or numeric case ID.
            version: Case version to update. Ignored when a numeric case ID is
                given; defaults to the latest version.
            create_new_version: Save the change as a new case version instead of
                modifying the current one.
            include_rtf: Treat the supplied rich-text values as HTML. When False
                they are treated as plain text and escaped; either way the
                formatting of the fields left untouched is preserved.
            create_folder_if_missing: Create the target folder hierarchy when it
                does not exist yet.
            **fields: Case fields to change, see :meth:`_build_case_payload`.

        Returns:
            The updated test case.

        Raises:
            ValueError: If no field was supplied or a value cannot be resolved.
        """
        # The API replaces the whole case document, so the current case is read
        # back with its HTML intact and written back the same way. Otherwise the
        # formatting of every field the caller did not touch would be flattened
        # to plain text. Plain-text input is escaped to match.
        changes = self._build_case_payload(
            project_key,
            fields,
            create_folder_if_missing=create_folder_if_missing,
            escape_rich_text=not include_rtf,
        )
        title = fields.get("title")
        if title is not None:
            if not str(title).strip():
                raise ValueError("Test case title cannot be empty")
            changes["title"] = title
        if not changes:
            raise ValueError("No fields to update were provided")

        current = self.get(
            self.project_path(project_key, "testcase", test_case_id, "detail"),
            params={"needDataInRTF": True, "version": version},
        )
        if not isinstance(current, dict):
            raise ValueError(f"Test case '{test_case_id}' was not found")

        payload = {
            key: value
            for key, value in current.items()
            if key not in READ_ONLY_CASE_FIELDS
        }
        payload.update(changes)

        response = self.put(
            self.project_path(project_key, "testcase", test_case_id, "detail"),
            json=payload,
            params={
                "needDataInRTF": True,
                "version": version,
                "createNewVersion": create_new_version or None,
            },
        )
        return AIOTestCase.from_api_response(
            response if isinstance(response, dict) else {}
        )

    def _build_case_payload(
        self,
        project_key: str,
        fields: dict[str, Any],
        *,
        create_folder_if_missing: bool,
        escape_rich_text: bool = False,
    ) -> dict[str, Any]:
        """Translate tool-level case fields into an API payload.

        Args:
            project_key: Jira project key or ID.
            fields: Supported keys: ``description``, ``precondition``, ``folder``,
                ``status``, ``priority``, ``type``, ``script_type``,
                ``automation_status``, ``automation_key``, ``automation_owner_id``,
                ``owner_id``, ``estimated_effort``, ``steps``, ``tags``,
                ``requirement_ids``, ``component_ids``, ``release_ids`` and
                ``custom_fields``. ``title`` is handled by the callers.
            create_folder_if_missing: Create the target folder hierarchy when it
                does not exist yet.
            escape_rich_text: Escape rich-text values as HTML, for requests that
                are sent with ``needDataInRTF`` enabled.

        Returns:
            The API payload holding only the supplied fields.

        Raises:
            ValueError: If a key is unknown or a value cannot be resolved.
        """
        known = {
            "title",
            "description",
            "precondition",
            "folder",
            "status",
            "priority",
            "type",
            "script_type",
            "automation_status",
            "automation_key",
            "automation_owner_id",
            "owner_id",
            "estimated_effort",
            "steps",
            "tags",
            "requirement_ids",
            "component_ids",
            "release_ids",
            "custom_fields",
        }
        unknown = set(fields) - known
        if unknown:
            raise ValueError(
                f"Unknown test case field(s): {', '.join(sorted(unknown))}. "
                f"Supported fields: {', '.join(sorted(known))}"
            )

        payload: dict[str, Any] = {}
        for key, api_key in (
            ("description", "description"),
            ("precondition", "precondition"),
            ("owner_id", "ownedByID"),
            ("automation_key", "automationKey"),
            ("automation_owner_id", "automationOwnerID"),
            ("estimated_effort", "estimatedEffort"),
        ):
            value = fields.get(key)
            if value is not None:
                payload[api_key] = (
                    _plain_text_to_html(value)
                    if escape_rich_text and api_key in RICH_TEXT_CASE_FIELDS
                    else value
                )

        for key, api_key, config_key in (
            ("status", "status", "caseStatuses"),
            ("priority", "priority", "casePriorities"),
            ("type", "type", "caseTypes"),
            ("script_type", "scriptType", "caseScriptTypes"),
            ("automation_status", "automationStatus", "caseAutomationStatuses"),
        ):
            value = fields.get(key)
            if value is not None:
                resolved = self.resolve_lookup_id(project_key, config_key, value)
                if resolved is not None:
                    payload[api_key] = {"ID": resolved}

        folder = fields.get("folder")
        if folder is not None:
            folder_id = self.resolve_folder_id(
                project_key,
                folder,
                "testcase",
                create_missing=create_folder_if_missing,
            )
            if folder_id is not None:
                payload["folder"] = {"ID": folder_id}

        steps = fields.get("steps")
        if steps is not None:
            if not isinstance(steps, list):
                raise ValueError("steps must be a list of step objects")
            step_payloads = [
                _build_step_payload(step, index) for index, step in enumerate(steps)
            ]
            if escape_rich_text:
                for step_payload in step_payloads:
                    for step_key in RICH_TEXT_STEP_KEYS:
                        if step_key in step_payload:
                            step_payload[step_key] = _plain_text_to_html(
                                step_payload[step_key]
                            )
            payload["steps"] = step_payloads

        tags = fields.get("tags")
        if tags is not None:
            payload["tags"] = self.resolve_tags(project_key, list(tags))

        requirement_ids = fields.get("requirement_ids")
        if requirement_ids is not None:
            payload["jiraRequirementIDs"] = [str(value) for value in requirement_ids]
        component_ids = fields.get("component_ids")
        if component_ids is not None:
            payload["jiraComponentIDs"] = [int(value) for value in component_ids]
        release_ids = fields.get("release_ids")
        if release_ids is not None:
            payload["jiraReleaseIDs"] = [int(value) for value in release_ids]

        custom_fields = fields.get("custom_fields")
        if custom_fields is not None:
            payload["customFields"] = self._build_custom_fields(
                project_key, custom_fields, escape_rich_text=escape_rich_text
            )
        return payload

    def _build_custom_fields(
        self,
        project_key: str,
        custom_fields: Any,
        *,
        escape_rich_text: bool = False,
    ) -> list[dict[str, Any]]:
        """Translate custom field values into the API payload shape.

        Args:
            project_key: Jira project key or ID.
            custom_fields: Either a mapping of field name to value, or a list of
                ``{"name"|"id": ..., "value": ...}`` entries.
            escape_rich_text: Escape multi-line text values as HTML, for requests
                that are sent with ``needDataInRTF`` enabled.

        Returns:
            A list of ``{"ID": ..., "name": ..., "value": ...}`` entries.

        Raises:
            ValueError: If a custom field name is not defined for the project.
        """
        if isinstance(custom_fields, dict):
            entries = [
                {"name": name, "value": value} for name, value in custom_fields.items()
            ]
        elif isinstance(custom_fields, list):
            entries = list(custom_fields)
        else:
            raise ValueError(
                "custom_fields must be an object of name/value pairs or a list "
                "of {name|id, value} entries"
            )

        config = self.get_project_configuration(project_key)
        defined = [
            field
            for field in (config.get("customFields") or [])
            if isinstance(field, dict)
        ]
        by_name = {
            str(field.get("name", "")).lower(): field
            for field in defined
            if field.get("name")
        }
        rich_text_ids = {
            field.get("ID")
            for field in defined
            if field.get("type") == RICH_TEXT_CUSTOM_FIELD_TYPE
        }

        payload: dict[int | str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(
                    "Each custom field entry must be an object with name or id "
                    "and value"
                )
            field_id = entry.get("id", entry.get("ID"))
            name = entry.get("name")
            if field_id is None:
                if not name:
                    raise ValueError("Custom field entries need a name or an id")
                match = by_name.get(str(name).lower())
                if match is None:
                    available = ", ".join(sorted(str(f.get("name")) for f in defined))
                    raise ValueError(
                        f"Custom field '{name}' is not defined for project "
                        f"'{project_key}'. Available: {available or 'none'}"
                    )
                field_id = match.get("ID")
                name = match.get("name")
            value = entry.get("value")
            if escape_rich_text and field_id in rich_text_ids:
                value = _plain_text_to_html(value)
            payload[field_id if field_id is not None else str(name)] = {
                "ID": field_id,
                "name": name,
                "value": value,
            }
        return list(payload.values())
