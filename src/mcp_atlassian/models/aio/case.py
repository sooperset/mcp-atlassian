"""Models for AIO Tests test cases."""

from typing import Any

from ..base import ApiModel
from .common import AIOEntity, AIOFolder, AIOTag


class AIOTestStep(ApiModel):
    """A single step of a test case, in either Classic or BDD form."""

    id: int | None = None
    step_type: str | None = None
    step: str | None = None
    data: str | None = None
    expected_result: str | None = None
    bdd_step: str | None = None
    referenced_case_key: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "AIOTestStep":
        """Create a step from an AIO Tests API response.

        Args:
            data: Raw step payload.
            **kwargs: Unused, accepted for interface compatibility.

        Returns:
            The parsed step.
        """
        if not isinstance(data, dict):
            return cls()
        referenced = data.get("referencedCase")
        return cls(
            id=data.get("ID"),
            step_type=data.get("stepType"),
            step=data.get("step"),
            data=data.get("data"),
            expected_result=data.get("expectedResult"),
            bdd_step=data.get("bddStep"),
            referenced_case_key=(
                referenced.get("key") if isinstance(referenced, dict) else None
            ),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary.

        Returns:
            Dictionary with the populated step fields.
        """
        result: dict[str, Any] = {}
        if self.id is not None:
            result["id"] = self.id
        if self.step_type:
            result["step_type"] = self.step_type
        if self.step:
            result["step"] = self.step
        if self.data:
            result["data"] = self.data
        if self.expected_result:
            result["expected_result"] = self.expected_result
        if self.bdd_step:
            result["bdd_step"] = self.bdd_step
        if self.referenced_case_key:
            result["referenced_case_key"] = self.referenced_case_key
        return result


class AIOTestCaseVersion(ApiModel):
    """A saved version of a test case."""

    version: int | None = None
    id: int | None = None
    is_current: bool = False

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "AIOTestCaseVersion":
        """Create a version entry from an AIO Tests API response.

        Args:
            data: Raw ``{"version": n, "ID": n}`` payload.
            **kwargs: Optional ``current_version`` to flag the active version.

        Returns:
            The parsed version entry.
        """
        if not isinstance(data, dict):
            return cls()
        version = data.get("version")
        current_version = kwargs.get("current_version")
        return cls(
            version=version,
            id=data.get("ID"),
            is_current=version is not None and version == current_version,
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary.

        Returns:
            Dictionary with the version number, case ID and current flag.
        """
        result: dict[str, Any] = {"is_current": self.is_current}
        if self.version is not None:
            result["version"] = self.version
        if self.id is not None:
            result["id"] = self.id
        return result


class AIOTestCase(ApiModel):
    """Full details of an AIO Tests test case."""

    id: int | None = None
    key: str | None = None
    title: str | None = None
    version: int | None = None
    description: str | None = None
    precondition: str | None = None
    owned_by_id: str | None = None
    folder: AIOFolder | None = None
    status: AIOEntity | None = None
    priority: AIOEntity | None = None
    type: AIOEntity | None = None
    script_type: AIOEntity | None = None
    automation_status: AIOEntity | None = None
    automation_key: str | None = None
    automation_owner_id: str | None = None
    estimated_effort: int | None = None
    jira_project_id: int | None = None
    jira_component_ids: list[int] = []
    jira_release_ids: list[int] = []
    jira_requirement_ids: list[str] = []
    tags: list[AIOTag] = []
    steps: list[AIOTestStep] = []
    custom_fields: list[dict[str, Any]] = []
    versions: list[AIOTestCaseVersion] = []
    created_date: str | None = None
    updated_date: str | None = None
    is_archived: bool | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any], **kwargs: Any) -> "AIOTestCase":
        """Create a test case from an AIO Tests API response.

        Args:
            data: Raw ``CaseFullDetails`` payload.
            **kwargs: Unused, accepted for interface compatibility.

        Returns:
            The parsed test case.
        """
        if not isinstance(data, dict):
            return cls()

        def entity(key: str) -> AIOEntity | None:
            value = data.get(key)
            return (
                AIOEntity.from_api_response(value) if isinstance(value, dict) else None
            )

        folder = data.get("folder")
        version = data.get("version")
        return cls(
            id=data.get("ID"),
            key=data.get("key"),
            title=data.get("title"),
            version=version,
            description=data.get("description"),
            precondition=data.get("precondition"),
            owned_by_id=data.get("ownedByID"),
            folder=(
                AIOFolder.from_api_response(folder)
                if isinstance(folder, dict)
                else None
            ),
            status=entity("status"),
            priority=entity("priority"),
            type=entity("type"),
            script_type=entity("scriptType"),
            automation_status=entity("automationStatus"),
            automation_key=data.get("automationKey"),
            automation_owner_id=data.get("automationOwnerID"),
            estimated_effort=data.get("estimatedEffort"),
            jira_project_id=data.get("jiraProjectID"),
            jira_component_ids=list(data.get("jiraComponentIDs") or []),
            jira_release_ids=list(data.get("jiraReleaseIDs") or []),
            jira_requirement_ids=[
                str(value) for value in (data.get("jiraRequirementIDs") or [])
            ],
            tags=[
                AIOTag.from_api_response(tag)
                for tag in (data.get("tags") or [])
                if isinstance(tag, dict)
            ],
            steps=[
                AIOTestStep.from_api_response(step)
                for step in (data.get("steps") or [])
                if isinstance(step, dict)
            ],
            custom_fields=[
                field
                for field in (data.get("customFields") or [])
                if isinstance(field, dict)
            ],
            versions=[
                AIOTestCaseVersion.from_api_response(entry, current_version=version)
                for entry in (data.get("versions") or [])
                if isinstance(entry, dict)
            ],
            created_date=data.get("createdDate"),
            updated_date=data.get("updatedDate"),
            is_archived=data.get("isArchived"),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary.

        Returns:
            Dictionary with the populated test case fields.
        """
        result: dict[str, Any] = {}
        for key, value in (
            ("id", self.id),
            ("key", self.key),
            ("title", self.title),
            ("version", self.version),
            ("description", self.description),
            ("precondition", self.precondition),
            ("owned_by_id", self.owned_by_id),
            ("automation_key", self.automation_key),
            ("automation_owner_id", self.automation_owner_id),
            ("estimated_effort", self.estimated_effort),
            ("jira_project_id", self.jira_project_id),
            ("created_date", self.created_date),
            ("updated_date", self.updated_date),
            ("is_archived", self.is_archived),
        ):
            if value is not None:
                result[key] = value

        for key, entity in (
            ("folder", self.folder),
            ("status", self.status),
            ("priority", self.priority),
            ("type", self.type),
            ("script_type", self.script_type),
            ("automation_status", self.automation_status),
        ):
            if entity is not None:
                simplified = entity.to_simplified_dict()
                if simplified:
                    result[key] = simplified

        if self.jira_component_ids:
            result["jira_component_ids"] = self.jira_component_ids
        if self.jira_release_ids:
            result["jira_release_ids"] = self.jira_release_ids
        if self.jira_requirement_ids:
            result["jira_requirement_ids"] = self.jira_requirement_ids
        if self.tags:
            result["tags"] = [tag.to_simplified_dict() for tag in self.tags]
        if self.steps:
            result["steps"] = [step.to_simplified_dict() for step in self.steps]
        if self.custom_fields:
            result["custom_fields"] = self.custom_fields
        if self.versions:
            result["versions"] = [
                version.to_simplified_dict() for version in self.versions
            ]
        return result


class AIOTestCaseSearchResult(ApiModel):
    """A page of test cases returned by the list or search API."""

    cases: list[AIOTestCase] = []
    start_at: int = 0
    max_results: int = 0
    is_last: bool = True

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "AIOTestCaseSearchResult":
        """Create a search result page from an AIO Tests API response.

        Args:
            data: Raw ``TestCasePaginatedResponse`` payload.
            **kwargs: Unused, accepted for interface compatibility.

        Returns:
            The parsed page of results.
        """
        if not isinstance(data, dict):
            return cls()
        items = data.get("items") or []
        return cls(
            cases=[
                AIOTestCase.from_api_response(item)
                for item in items
                if isinstance(item, dict)
            ],
            start_at=data.get("startAt") or 0,
            max_results=data.get("maxResults") or 0,
            is_last=bool(data.get("isLast", True)),
        )

    def to_simplified_dict(self) -> dict[str, Any]:
        """Convert to a simplified dictionary.

        Returns:
            Dictionary with the page of test cases and pagination metadata.
        """
        return {
            "start_at": self.start_at,
            "max_results": self.max_results,
            "count": len(self.cases),
            "is_last": self.is_last,
            "test_cases": [case.to_simplified_dict() for case in self.cases],
        }
