"""Module for AIO Tests project and schema operations."""

import logging
from typing import Any

from ..models.aio import AIOProject, AIOSchemaField, AIOTestCaseSchema
from .client import AIOApiError, AIOClient

logger = logging.getLogger("mcp-aio")

# Built-in test case fields accepted by the Create/Update Case APIs. AIO Tests
# reports only custom fields in its project configuration, so the built-in ones
# are described here to give the full picture in one schema call.
CASE_FIELD_CATALOG: tuple[AIOSchemaField, ...] = (
    AIOSchemaField(
        name="title",
        type="string",
        description="Case title. The only mandatory field when creating a case.",
        required=True,
    ),
    AIOSchemaField(
        name="description",
        type="string",
        description="Case description. Accepts HTML when include_rtf is enabled.",
    ),
    AIOSchemaField(
        name="precondition",
        type="string",
        description="Conditions that must hold before the case can be executed.",
    ),
    AIOSchemaField(
        name="folder",
        type="folder",
        description=(
            "Folder the case belongs to. Cases without a folder land in 'Not Assigned'."
        ),
    ),
    AIOSchemaField(
        name="status",
        type="lookup",
        description="Case status, e.g. Draft or Published.",
        allowed_values_from="statuses",
    ),
    AIOSchemaField(
        name="priority",
        type="lookup",
        description="Case priority, e.g. Critical or Low.",
        allowed_values_from="priorities",
    ),
    AIOSchemaField(
        name="type",
        type="lookup",
        description="Case type, e.g. Functional or Performance.",
        allowed_values_from="types",
    ),
    AIOSchemaField(
        name="scriptType",
        type="lookup",
        description="Step style: Classic (step/data/expected result) or BDD.",
        allowed_values_from="script_types",
    ),
    AIOSchemaField(
        name="steps",
        type="array",
        description=(
            "Ordered test steps. Classic steps use step/data/expectedResult with "
            "stepType TEXT; BDD steps use bddStep with a BDD_* stepType."
        ),
    ),
    AIOSchemaField(
        name="tags",
        type="array",
        description="Tags associated with the case.",
    ),
    AIOSchemaField(
        name="ownedByID",
        type="string",
        description="Jira account ID of the case owner.",
    ),
    AIOSchemaField(
        name="estimatedEffort",
        type="integer",
        description="Estimated execution effort in seconds.",
    ),
    AIOSchemaField(
        name="automationStatus",
        type="lookup",
        description="Automation status, e.g. Manual or Automated.",
        allowed_values_from="automation_statuses",
    ),
    AIOSchemaField(
        name="automationKey",
        type="string",
        description="Key used to match imported automated execution results.",
    ),
    AIOSchemaField(
        name="automationOwnerID",
        type="string",
        description="Jira account ID of the automation owner.",
    ),
    AIOSchemaField(
        name="jiraRequirementIDs",
        type="array",
        description="Jira issue keys or IDs covered by the case.",
    ),
    AIOSchemaField(
        name="jiraComponentIDs",
        type="array",
        description="Jira component IDs associated with the case.",
    ),
    AIOSchemaField(
        name="jiraReleaseIDs",
        type="array",
        description="Jira release (version) IDs associated with the case.",
    ),
    AIOSchemaField(
        name="customFields",
        type="array",
        description="Custom field values, each identified by ID or name.",
    ),
    AIOSchemaField(
        name="key",
        type="string",
        description="Case key such as AT-TC-17.",
        read_only=True,
    ),
    AIOSchemaField(
        name="version",
        type="integer",
        description="Case version number.",
        read_only=True,
    ),
    AIOSchemaField(
        name="createdDate",
        type="date-time",
        description="Creation timestamp.",
        read_only=True,
    ),
    AIOSchemaField(
        name="updatedDate",
        type="date-time",
        description="Last update timestamp.",
        read_only=True,
    ),
    AIOSchemaField(
        name="isArchived",
        type="boolean",
        description="Whether the case is archived.",
        read_only=True,
    ),
)


class ProjectsMixin(AIOClient):
    """Mixin for AIO Tests project configuration operations."""

    _project_config_cache: dict[str, dict[str, Any]]

    def get_project_configuration(
        self, project_key: str, *, refresh: bool = False
    ) -> dict[str, Any]:
        """Fetch the AIO Tests configuration of a Jira project.

        The result is cached per client instance because it backs name-to-ID
        resolution for statuses, priorities, types and custom fields.

        Args:
            project_key: Jira project key or ID.
            refresh: Bypass the cache and re-fetch the configuration.

        Returns:
            The raw project configuration payload.
        """
        cache = getattr(self, "_project_config_cache", None)
        if cache is None:
            cache = {}
            self._project_config_cache = cache
        cache_key = str(project_key)
        if not refresh and cache_key in cache:
            return cache[cache_key]

        config = self.get(self.project_path(project_key, "config"))
        if not isinstance(config, dict):
            raise AIOApiError(
                f"Unexpected AIO Tests configuration response for '{project_key}'"
            )
        cache[cache_key] = config
        return config

    def get_project(self, project_key: str) -> AIOProject:
        """Check whether AIO Tests is enabled for a project and describe it.

        Args:
            project_key: Jira project key or ID.

        Returns:
            Project information including the resolved Jira project ID. When AIO
            Tests is not enabled (or the project is unknown), ``aio_enabled`` is
            False and ``error`` explains why.
        """
        try:
            config = self.get_project_configuration(project_key)
        except AIOApiError as exc:
            logger.info(f"AIO Tests is unavailable for project '{project_key}': {exc}")
            return AIOProject(key=project_key, aio_enabled=False, error=str(exc))
        return AIOProject.from_api_response(config, project_key=project_key)

    def get_test_case_schema(self, project_key: str) -> AIOTestCaseSchema:
        """Retrieve the complete test case schema configuration for a project.

        Args:
            project_key: Jira project key or ID.

        Returns:
            The schema: built-in fields, custom fields, required fields and the
            allowed values for every lookup field.
        """
        config = self.get_project_configuration(project_key)
        return AIOTestCaseSchema.from_api_response(
            config, project_key=project_key, fields=list(CASE_FIELD_CATALOG)
        )

    def resolve_lookup_id(
        self, project_key: str, config_key: str, value: Any
    ) -> int | None:
        """Resolve a lookup value given as a name or an ID to its numeric ID.

        Args:
            project_key: Jira project key or ID.
            config_key: Key in the project configuration, e.g. ``casePriorities``.
            value: A numeric ID, a numeric string, or a case-insensitive name.

        Returns:
            The numeric ID, or None when the value is empty.

        Raises:
            ValueError: If a name is given that the project does not define.
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, bool):
            raise ValueError(f"Invalid value for {config_key}: {value!r}")
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if text.isdigit():
            return int(text)

        config = self.get_project_configuration(project_key)
        options = [
            option
            for option in (config.get(config_key) or [])
            if isinstance(option, dict)
        ]
        for option in options:
            if str(option.get("name", "")).strip().lower() == text.lower():
                option_id = option.get("ID")
                if option_id is not None:
                    return int(option_id)
        available = ", ".join(
            str(option.get("name")) for option in options if option.get("name")
        )
        raise ValueError(
            f"'{text}' is not a valid {config_key} value for project "
            f"'{project_key}'. Available values: {available or 'none'}"
        )
