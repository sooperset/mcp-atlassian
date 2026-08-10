"""AIO Tests FastMCP server instance and tool definitions."""

import json
import logging
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from mcp_atlassian.aio.constants import DEFAULT_PAGE_SIZE, FOLDER_ENTITY_TYPES
from mcp_atlassian.servers.dependencies import get_aio_fetcher
from mcp_atlassian.utils.decorators import check_write_access

logger = logging.getLogger(__name__)

aio_mcp = FastMCP(
    name="AIO Tests MCP Service",
    instructions=(
        "Provides tools for managing test cases, folders and tags in AIO Tests, "
        "the test management app for Jira. Every tool is scoped to a Jira "
        "project; call aio_get_project first to confirm AIO Tests is enabled, "
        "and aio_get_test_case_schema before creating or updating cases so the "
        "correct field names and allowed values are used."
    ),
)

ProjectKey = Annotated[
    str,
    Field(description="Jira project key or numeric project ID (e.g. 'PROJ')"),
]
TestCaseId = Annotated[
    str,
    Field(description="Test case key (e.g. 'AT-TC-17') or numeric case ID"),
]
FolderType = Annotated[
    str,
    Field(
        description=(
            "Folder tree to operate on: 'testcase', 'testcycle' or 'testset'. "
            "Defaults to 'testcase'."
        ),
        default="testcase",
    ),
]

_CASE_FIELD_DOC = (
    "Optional case fields. Lookup fields accept a name or a numeric ID: "
    "description, precondition, folder (name, path or ID), status, priority, "
    "type, script_type ('Classic' or 'BDD'), automation_status, automation_key, "
    "automation_owner_id, owner_id (Jira account ID), estimated_effort "
    "(seconds), tags (list of names), requirement_ids (Jira issue keys or IDs), "
    "component_ids, release_ids, custom_fields (object of name/value pairs)."
)
_STEPS_DOC = (
    "Ordered test steps, replacing any existing steps. Classic steps use "
    '{"step": "...", "data": "...", "expected_result": "..."}; BDD steps use '
    '{"step_type": "BDD_GIVEN|BDD_WHEN|BDD_THEN|BDD_AND|BDD_BUT|BDD_STAR", '
    '"bdd_step": "..."}. A step may instead reference another case with '
    '{"step_type": "REFERENCE", "referenced_case_key": "AT-TC-9"}.'
)


def _dumps(payload: Any) -> str:
    """Serialize a tool result to JSON.

    Args:
        payload: The result payload.

    Returns:
        The indented JSON representation.
    """
    return json.dumps(payload, indent=2, ensure_ascii=False)


@aio_mcp.tool(
    tags={"aio", "read"},
    annotations={"title": "Get Project", "readOnlyHint": True},
)
async def get_project(ctx: Context, project_key: ProjectKey) -> str:
    """Verify that AIO Tests is enabled for a Jira project and get its details.

    Args:
        ctx: The FastMCP context.
        project_key: Jira project key or numeric project ID.

    Returns:
        JSON string with the project key, project ID and whether AIO Tests is
        enabled for the project.
    """
    aio = await get_aio_fetcher(ctx)
    project = aio.get_project(project_key)
    return _dumps(project.to_simplified_dict())


@aio_mcp.tool(
    tags={"aio", "read"},
    annotations={"title": "Get Test Case Schema", "readOnlyHint": True},
)
async def get_test_case_schema(ctx: Context, project_key: ProjectKey) -> str:
    """Get the test case schema of a project: fields, custom fields and allowed values.

    Call this before creating or updating test cases to learn which fields exist,
    which are required, and which values the project accepts for statuses,
    priorities, types, script types and automation statuses.

    Args:
        ctx: The FastMCP context.
        project_key: Jira project key or numeric project ID.

    Returns:
        JSON string describing built-in fields, custom fields, required fields
        and allowed values.
    """
    aio = await get_aio_fetcher(ctx)
    schema = aio.get_test_case_schema(project_key)
    return _dumps(schema.to_simplified_dict())


@aio_mcp.tool(
    tags={"aio", "read"},
    annotations={"title": "Search Test Cases", "readOnlyHint": True},
)
async def search_test_cases(
    ctx: Context,
    project_key: ProjectKey,
    title: Annotated[
        str | None,
        Field(description="(Optional) Text to match against the case title"),
    ] = None,
    title_match: Annotated[
        str,
        Field(
            description="How to match the title: 'CONTAINS' or 'EXACT_MATCH'",
            default="CONTAINS",
        ),
    ] = "CONTAINS",
    keys: Annotated[
        list[str] | None,
        Field(description="(Optional) Case keys to match (e.g. ['AT-TC-17'])"),
    ] = None,
    folders: Annotated[
        list[str] | None,
        Field(
            description=(
                "(Optional) Folder names, paths (e.g. '/Regression/Checkout') "
                "or numeric folder IDs"
            )
        ),
    ] = None,
    statuses: Annotated[
        list[str] | None,
        Field(description="(Optional) Case status names or IDs (e.g. ['Published'])"),
    ] = None,
    priorities: Annotated[
        list[str] | None,
        Field(description="(Optional) Case priority names or IDs (e.g. ['Critical'])"),
    ] = None,
    types: Annotated[
        list[str] | None,
        Field(description="(Optional) Case type names or IDs (e.g. ['Functional'])"),
    ] = None,
    automation_statuses: Annotated[
        list[str] | None,
        Field(description="(Optional) Automation status names or IDs"),
    ] = None,
    tags: Annotated[
        list[str] | None, Field(description="(Optional) Tag names to match")
    ] = None,
    owner_ids: Annotated[
        list[str] | None,
        Field(description="(Optional) Jira account IDs of the case owners"),
    ] = None,
    requirement_ids: Annotated[
        list[str] | None,
        Field(
            description=(
                "(Optional) Jira issue keys or IDs the cases must cover "
                "(e.g. ['PROJ-42'])"
            )
        ),
    ] = None,
    automation_key: Annotated[
        str | None,
        Field(description="(Optional) Automation key to match (contains)"),
    ] = None,
    created_after: Annotated[
        str | None,
        Field(description="(Optional) ISO 8601 lower bound of the creation date"),
    ] = None,
    created_before: Annotated[
        str | None,
        Field(description="(Optional) ISO 8601 upper bound of the creation date"),
    ] = None,
    updated_after: Annotated[
        str | None,
        Field(description="(Optional) ISO 8601 lower bound of the last update date"),
    ] = None,
    updated_before: Annotated[
        str | None,
        Field(description="(Optional) ISO 8601 upper bound of the last update date"),
    ] = None,
    include_archived: Annotated[
        bool | None,
        Field(
            description=(
                "(Optional) Set to true to return archived cases, false to "
                "exclude them. Omit to leave the filter unset."
            ),
            default=None,
        ),
    ] = None,
    start_at: Annotated[
        int,
        Field(description="Index of the first result to return", default=0, ge=0),
    ] = 0,
    max_results: Annotated[
        int,
        Field(
            description="Maximum number of results to return (1-100)",
            default=DEFAULT_PAGE_SIZE,
            ge=1,
            le=100,
        ),
    ] = DEFAULT_PAGE_SIZE,
    include_rtf: Annotated[
        bool,
        Field(
            description="Keep the HTML markup of rich-text fields",
            default=False,
        ),
    ] = False,
) -> str:
    """Search and filter test cases in a project.

    Filters combine with AND. Lookup filters accept names or numeric IDs. With no
    filter at all, the project's test cases are listed in their natural order.

    Args:
        ctx: The FastMCP context.
        project_key: Jira project key or numeric project ID.
        title: Text to match against the case title.
        title_match: 'CONTAINS' or 'EXACT_MATCH'.
        keys: Case keys to match.
        folders: Folder names, paths or IDs.
        statuses: Case status names or IDs.
        priorities: Case priority names or IDs.
        types: Case type names or IDs.
        automation_statuses: Automation status names or IDs.
        tags: Tag names to match.
        owner_ids: Jira account IDs of the case owners.
        requirement_ids: Jira issue keys or IDs the cases must cover.
        automation_key: Automation key to match.
        created_after: Lower bound of the creation date.
        created_before: Upper bound of the creation date.
        updated_after: Lower bound of the last update date.
        updated_before: Upper bound of the last update date.
        include_archived: Filter on the archived flag.
        start_at: Index of the first result.
        max_results: Maximum number of results.
        include_rtf: Keep the HTML markup of rich-text fields.

    Returns:
        JSON string with the matching test cases and pagination metadata.
    """
    aio = await get_aio_fetcher(ctx)
    result = aio.search_test_cases(
        project_key,
        title=title,
        title_match=title_match,
        keys=keys,
        folders=folders,
        statuses=statuses,
        priorities=priorities,
        types=types,
        automation_statuses=automation_statuses,
        tags=tags,
        owner_ids=owner_ids,
        requirement_ids=requirement_ids,
        automation_key=automation_key,
        created_after=created_after,
        created_before=created_before,
        updated_after=updated_after,
        updated_before=updated_before,
        include_archived=include_archived,
        start_at=start_at,
        max_results=max_results,
        include_rtf=include_rtf,
    )
    return _dumps(result.to_simplified_dict())


@aio_mcp.tool(
    tags={"aio", "read"},
    annotations={"title": "Get Test Case", "readOnlyHint": True},
)
async def get_test_case(
    ctx: Context,
    project_key: ProjectKey,
    test_case_id: TestCaseId,
    version: Annotated[
        int | None,
        Field(
            description=(
                "(Optional) Case version to read. Only applies when a case key "
                "is given; defaults to the latest version."
            ),
            default=None,
        ),
    ] = None,
    include_rtf: Annotated[
        bool,
        Field(description="Keep the HTML markup of rich-text fields", default=False),
    ] = False,
    include_attachments: Annotated[
        bool,
        Field(description="Include attachment metadata", default=False),
    ] = False,
) -> str:
    """Get the complete details of a test case, including its steps.

    Args:
        ctx: The FastMCP context.
        project_key: Jira project key or numeric project ID.
        test_case_id: Case key or numeric case ID.
        version: Case version to read.
        include_rtf: Keep the HTML markup of rich-text fields.
        include_attachments: Include attachment metadata.

    Returns:
        JSON string with the case metadata, steps, tags, folder, requirements
        and custom fields.
    """
    aio = await get_aio_fetcher(ctx)
    case = aio.get_test_case(
        project_key,
        test_case_id,
        version=version,
        include_rtf=include_rtf,
        include_attachments=include_attachments,
    )
    return _dumps(case.to_simplified_dict())


@aio_mcp.tool(
    tags={"aio", "read"},
    annotations={"title": "Get Test Case Versions", "readOnlyHint": True},
)
async def get_test_case_versions(
    ctx: Context, project_key: ProjectKey, test_case_id: TestCaseId
) -> str:
    """Get every saved version of a test case.

    Use the returned version numbers with aio_get_test_case to read the content
    of a specific historical version.

    Args:
        ctx: The FastMCP context.
        project_key: Jira project key or numeric project ID.
        test_case_id: Case key or numeric case ID.

    Returns:
        JSON string with the case key, its current version and every saved
        version with the case ID that stores it.
    """
    aio = await get_aio_fetcher(ctx)
    case = aio.get_test_case_versions(project_key, test_case_id)
    return _dumps(
        {
            "key": case.key,
            "title": case.title,
            "current_version": case.version,
            "versions": [version.to_simplified_dict() for version in case.versions],
        }
    )


@aio_mcp.tool(
    tags={"aio", "write"},
    annotations={"title": "Create Test Case", "destructiveHint": False},
)
@check_write_access
async def create_test_case(
    ctx: Context,
    project_key: ProjectKey,
    title: Annotated[str, Field(description="Case title. The only required field.")],
    steps: Annotated[
        list[dict[str, Any]] | None,
        Field(description=f"(Optional) {_STEPS_DOC}", default=None),
    ] = None,
    fields: Annotated[
        dict[str, Any] | None,
        Field(description=f"(Optional) {_CASE_FIELD_DOC}", default=None),
    ] = None,
    include_rtf: Annotated[
        bool,
        Field(
            description=("Treat rich-text field values as HTML instead of plain text"),
            default=False,
        ),
    ] = False,
    create_folder_if_missing: Annotated[
        bool,
        Field(
            description=(
                "Create the target folder hierarchy when it does not exist yet"
            ),
            default=True,
        ),
    ] = True,
) -> str:
    """Create a test case in AIO Tests, with Classic or BDD steps.

    A case with no folder is created in the 'Not Assigned' folder. Call
    aio_get_test_case_schema first if unsure which field values the project
    accepts.

    Args:
        ctx: The FastMCP context.
        project_key: Jira project key or numeric project ID.
        title: Case title.
        steps: Ordered test steps.
        fields: Optional case fields such as folder, priority, status or tags.
        include_rtf: Treat rich-text values as HTML.
        create_folder_if_missing: Create the target folder when it is missing.

    Returns:
        JSON string with the created test case.
    """
    aio = await get_aio_fetcher(ctx)
    payload: dict[str, Any] = dict(fields or {})
    payload.pop("title", None)
    if steps is not None:
        payload["steps"] = steps
    case = aio.create_test_case(
        project_key,
        title,
        include_rtf=include_rtf,
        create_folder_if_missing=create_folder_if_missing,
        **payload,
    )
    return _dumps({"success": True, "test_case": case.to_simplified_dict()})


@aio_mcp.tool(
    tags={"aio", "write"},
    annotations={"title": "Update Test Case", "destructiveHint": True},
)
@check_write_access
async def update_test_case(
    ctx: Context,
    project_key: ProjectKey,
    test_case_id: TestCaseId,
    steps: Annotated[
        list[dict[str, Any]] | None,
        Field(description=f"(Optional) {_STEPS_DOC}", default=None),
    ] = None,
    fields: Annotated[
        dict[str, Any] | None,
        Field(
            description=(
                f"(Optional) Fields to change, omitted fields keep their current "
                f"value. Also accepts 'title'. {_CASE_FIELD_DOC}"
            ),
            default=None,
        ),
    ] = None,
    version: Annotated[
        int | None,
        Field(
            description=(
                "(Optional) Case version to update. Only applies when a case key "
                "is given; defaults to the latest version."
            ),
            default=None,
        ),
    ] = None,
    create_new_version: Annotated[
        bool,
        Field(
            description=(
                "Save the change as a new case version instead of modifying the "
                "current one"
            ),
            default=False,
        ),
    ] = False,
    include_rtf: Annotated[
        bool,
        Field(
            description=(
                "Treat the supplied rich-text values as HTML instead of plain "
                "text. Formatting of the fields left untouched is preserved "
                "either way."
            ),
            default=False,
        ),
    ] = False,
    create_folder_if_missing: Annotated[
        bool,
        Field(
            description=(
                "Create the target folder hierarchy when it does not exist yet"
            ),
            default=True,
        ),
    ] = True,
) -> str:
    """Update an existing test case: steps, metadata, priority, status or tags.

    Only the supplied fields change. Supplying `steps` or `tags` replaces the
    existing list. By default this modifies the case in place without creating a
    new version.

    Args:
        ctx: The FastMCP context.
        project_key: Jira project key or numeric project ID.
        test_case_id: Case key or numeric case ID.
        steps: Replacement test steps.
        fields: Fields to change.
        version: Case version to update.
        create_new_version: Save the change as a new version.
        include_rtf: Treat rich-text values as HTML.
        create_folder_if_missing: Create the target folder when it is missing.

    Returns:
        JSON string with the updated test case.
    """
    aio = await get_aio_fetcher(ctx)
    payload: dict[str, Any] = dict(fields or {})
    if steps is not None:
        payload["steps"] = steps
    case = aio.update_test_case(
        project_key,
        test_case_id,
        version=version,
        create_new_version=create_new_version,
        include_rtf=include_rtf,
        create_folder_if_missing=create_folder_if_missing,
        **payload,
    )
    return _dumps({"success": True, "test_case": case.to_simplified_dict()})


@aio_mcp.tool(
    tags={"aio", "read"},
    annotations={"title": "Get Folder Hierarchy", "readOnlyHint": True},
)
async def get_folder_hierarchy(
    ctx: Context,
    project_key: ProjectKey,
    folder_type: FolderType = "testcase",
    flat: Annotated[
        bool,
        Field(
            description=(
                "Return a flat list of folders with their full paths instead of "
                "a nested tree"
            ),
            default=False,
        ),
    ] = False,
) -> str:
    """Get the folder structure of a project, with parent-child relationships and paths.

    Args:
        ctx: The FastMCP context.
        project_key: Jira project key or numeric project ID.
        folder_type: 'testcase', 'testcycle' or 'testset'.
        flat: Return a flat list instead of a nested tree.

    Returns:
        JSON string with the folder hierarchy.
    """
    aio = await get_aio_fetcher(ctx)
    if flat:
        folders = [
            folder.to_simplified_dict()
            for folder in aio.flatten_folders(project_key, folder_type)
        ]
    else:
        folders = [
            folder.to_simplified_dict()
            for folder in aio.get_folder_hierarchy(project_key, folder_type)
        ]
    return _dumps({"folder_type": folder_type, "folders": folders})


@aio_mcp.tool(
    tags={"aio", "write"},
    annotations={"title": "Create Folder", "destructiveHint": False},
)
@check_write_access
async def create_folder(
    ctx: Context,
    project_key: ProjectKey,
    folder_path: Annotated[
        str,
        Field(
            description=(
                "Folder name, or a path such as '/Release 1.0/Regression/Checkout' "
                "to create nested folders in one call"
            )
        ),
    ],
    folder_type: FolderType = "testcase",
    parent_folder_id: Annotated[
        int | None,
        Field(
            description=(
                "(Optional) ID of an existing folder to create the path under. "
                "Omit to create from the top level."
            ),
            default=None,
        ),
    ] = None,
) -> str:
    """Create a folder (or a whole folder path) in AIO Tests.

    Folders that already exist along the path are reused, so this is safe to call
    repeatedly.

    Args:
        ctx: The FastMCP context.
        project_key: Jira project key or numeric project ID.
        folder_path: Folder name or path to create.
        folder_type: 'testcase', 'testcycle' or 'testset'.
        parent_folder_id: Existing folder to create the path under.

    Returns:
        JSON string with the leaf folder of the created hierarchy.
    """
    aio = await get_aio_fetcher(ctx)
    folder = aio.create_folder(
        project_key,
        folder_path,
        folder_type=folder_type,
        parent_folder_id=parent_folder_id,
    )
    return _dumps(
        {
            "success": True,
            "folder_type": folder_type,
            "folder": folder.to_simplified_dict(),
        }
    )


@aio_mcp.tool(
    tags={"aio", "read"},
    annotations={"title": "Get Tags", "readOnlyHint": True},
)
async def get_tags(ctx: Context, project_key: ProjectKey) -> str:
    """Get every tag configured for a project, for organizing and filtering test cases.

    Args:
        ctx: The FastMCP context.
        project_key: Jira project key or numeric project ID.

    Returns:
        JSON string with the project's tags.
    """
    aio = await get_aio_fetcher(ctx)
    tags = aio.get_tags(project_key)
    return _dumps({"tags": [tag.to_simplified_dict() for tag in tags]})


# Exported for tests and documentation.
SUPPORTED_FOLDER_TYPES = FOLDER_ENTITY_TYPES
