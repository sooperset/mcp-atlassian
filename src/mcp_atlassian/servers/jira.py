"""Jira FastMCP server instance and tool definitions."""

import base64
import json
import logging
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from mcp.types import BlobResourceContents, EmbeddedResource, TextContent
from pydantic import Field
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.jira.constants import DEFAULT_READ_JIRA_FIELDS
from mcp_atlassian.jira.forms_common import convert_datetime_to_timestamp
from mcp_atlassian.models.jira.common import JiraUser
from mcp_atlassian.servers.dependencies import get_jira_fetcher
from mcp_atlassian.utils.decorators import check_write_access

logger = logging.getLogger(__name__)

# Regex patterns for Jira key validation.
# Per Atlassian docs, Cloud project keys are 2-10 chars. Server/Data Center
# allows longer keys (configurable). We accept any length to support both.
ISSUE_KEY_PATTERN = r"^[A-Z][A-Z0-9]+-\d+$"
PROJECT_KEY_PATTERN = r"^[A-Z][A-Z0-9]+$"

jira_mcp = FastMCP(
    name="Jira MCP Service",
    instructions="Provides tools for interacting with Atlassian Jira.",
)


def _parse_visibility(
    visibility: str | None,
    field_name: str = "visibility",
) -> dict[str, str] | None:
    """Parse a visibility JSON string into a dict.

    Args:
        visibility: JSON string like '{"type":"group","value":"jira-users"}', or None.
        field_name: Parameter name for error messages.

    Returns:
        Parsed dict or None.

    Raises:
        ValueError: If the input is not valid JSON or not a dict.
    """
    if visibility is None:
        return None
    try:
        parsed = json.loads(visibility)
        if not isinstance(parsed, dict):
            raise ValueError(
                f"{field_name} must be a valid JSON object, e.g. "
                '{"type":"group","value":"jira-users"}'
            )
        return parsed
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{field_name} must be a valid JSON object, e.g. "
            f'{{"type":"group","value":"jira-users"}}; got error: {e}'
        ) from e


def _parse_additional_fields(
    additional_fields: dict[str, Any] | str | None,
) -> dict[str, Any]:
    """Parse additional_fields from dict or JSON string.

    Args:
        additional_fields: Dict, JSON string, or None.

    Returns:
        Parsed dict of additional fields.

    Raises:
        ValueError: If the input is not valid JSON or not a dict.
    """
    if additional_fields is None:
        return {}
    if isinstance(additional_fields, dict):
        return additional_fields
    if isinstance(additional_fields, str):
        try:
            parsed = json.loads(additional_fields)
            if not isinstance(parsed, dict):
                raise ValueError(
                    "Parsed additional_fields is not a JSON object (dict)."
                )
            return parsed
        except json.JSONDecodeError as e:
            raise ValueError(f"additional_fields is not valid JSON: {e}") from e
    raise ValueError("additional_fields must be a dictionary or JSON string.")


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get User Profile", "readOnlyHint": True},
)
async def get_user_profile(
    ctx: Context,
    user_identifier: Annotated[
        str,
        Field(
            description="Identifier for the user (e.g., email address 'user@example.com', username 'johndoe', account ID 'accountid:...', or key for Server/DC)."
        ),
    ],
) -> str:
    """
    Retrieve profile information for a specific Jira user.

    Args:
        ctx: The FastMCP context.
        user_identifier: User identifier (email, username, key, or account ID).

    Returns:
        JSON string representing the Jira user profile object, or an error object if not found.

    Raises:
        ValueError: If the Jira client is not configured or available.
    """
    jira = await get_jira_fetcher(ctx)
    try:
        user: JiraUser = jira.get_user_profile_by_identifier(user_identifier)
        result = user.to_simplified_dict()
        response_data = {"success": True, "user": result}
    except Exception as e:
        error_message = ""
        log_level = logging.ERROR
        if isinstance(e, ValueError) and "not found" in str(e).lower():
            log_level = logging.WARNING
            error_message = str(e)
        elif isinstance(e, MCPAtlassianAuthenticationError):
            error_message = f"Authentication/Permission Error: {str(e)}"
        elif isinstance(e, OSError | HTTPError):
            error_message = f"Network or API Error: {str(e)}"
        else:
            error_message = (
                "An unexpected error occurred while fetching the user profile."
            )
            logger.exception(
                f"Unexpected error in get_user_profile for '{user_identifier}':"
            )
        error_result = {
            "success": False,
            "error": str(e),
            "user_identifier": user_identifier,
        }
        logger.log(
            log_level,
            f"get_user_profile failed for '{user_identifier}': {error_message}",
        )
        response_data = error_result
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Issue", "readOnlyHint": True},
)
async def get_issue(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    fields: Annotated[
        str,
        Field(
            description=(
                "(Optional) Comma-separated list of fields to return (e.g., 'summary,status,customfield_10010'). "
                "You may also provide a single field as a string (e.g., 'duedate'). "
                "Use '*all' for all fields (including custom fields), or omit for essential fields only."
            ),
            default=",".join(DEFAULT_READ_JIRA_FIELDS),
        ),
    ] = ",".join(DEFAULT_READ_JIRA_FIELDS),
    expand: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Fields to expand. Examples: 'renderedFields' (for rendered content), "
                "'transitions' (for available status transitions), 'changelog' (for history)"
            ),
            default=None,
        ),
    ] = None,
    comment_limit: Annotated[
        int,
        Field(
            description="Maximum number of comments to include (0 or null for no comments)",
            default=10,
            ge=0,
            le=100,
        ),
    ] = 10,
    properties: Annotated[
        str | None,
        Field(
            description="(Optional) A comma-separated list of issue properties to return",
            default=None,
        ),
    ] = None,
    update_history: Annotated[
        bool,
        Field(
            description="Whether to update the issue view history for the requesting user",
            default=True,
        ),
    ] = True,
) -> str:
    """Get details of a specific Jira issue including its Epic links and relationship information.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.
        fields: Comma-separated list of fields to return (e.g., 'summary,status,customfield_10010'), a single field as a string (e.g., 'duedate'), '*all' for all fields, or omitted for essentials.
        expand: Optional fields to expand.
        comment_limit: Maximum number of comments.
        properties: Issue properties to return.
        update_history: Whether to update issue view history.

    Returns:
        JSON string representing the Jira issue object.

    Raises:
        ValueError: If the Jira client is not configured or available.
    """
    jira = await get_jira_fetcher(ctx)
    fields_list: str | list[str] | None = fields
    if fields and fields != "*all":
        fields_list = [f.strip() for f in fields.split(",")]

    issue = jira.get_issue(
        issue_key=issue_key,
        fields=fields_list,
        expand=expand,
        comment_limit=comment_limit,
        properties=properties.split(",") if properties else None,
        update_history=update_history,
    )
    result = issue.to_simplified_dict()
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Search Issues", "readOnlyHint": True},
)
async def search(
    ctx: Context,
    jql: Annotated[
        str,
        Field(
            description=(
                "JQL query string (Jira Query Language). Examples:\n"
                '- Find Epics: "issuetype = Epic AND project = PROJ"\n'
                '- Find issues in Epic: "parent = PROJ-123"\n'
                "- Find by status: \"status = 'In Progress' AND project = PROJ\"\n"
                '- Find by assignee: "assignee = currentUser()"\n'
                '- Find recently updated: "updated >= -7d AND project = PROJ"\n'
                '- Find by label: "labels = frontend AND project = PROJ"\n'
                '- Find by priority: "priority = High AND project = PROJ"'
            )
        ),
    ],
    fields: Annotated[
        str,
        Field(
            description=(
                "(Optional) Comma-separated fields to return in the results. "
                "Use '*all' for all fields, or specify individual fields like 'summary,status,assignee,priority'"
            ),
            default=",".join(DEFAULT_READ_JIRA_FIELDS),
        ),
    ] = ",".join(DEFAULT_READ_JIRA_FIELDS),
    limit: Annotated[
        int,
        Field(description="Maximum number of results (1-50)", default=10, ge=1),
    ] = 10,
    start_at: Annotated[
        int,
        Field(description="Starting index for pagination (0-based)", default=0, ge=0),
    ] = 0,
    projects_filter: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Comma-separated list of project keys to filter results by. "
                "Overrides the environment variable JIRA_PROJECTS_FILTER if provided."
            ),
            default=None,
        ),
    ] = None,
    expand: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) fields to expand. Examples: 'renderedFields', 'transitions', 'changelog'"
            ),
            default=None,
        ),
    ] = None,
) -> str:
    """Search Jira issues using JQL (Jira Query Language).

    Args:
        ctx: The FastMCP context.
        jql: JQL query string.
        fields: Comma-separated fields to return.
        limit: Maximum number of results.
        start_at: Starting index for pagination.
        projects_filter: Comma-separated list of project keys to filter by.
        expand: Optional fields to expand.

    Returns:
        JSON string representing the search results including pagination info.
    """
    jira = await get_jira_fetcher(ctx)
    fields_list: str | list[str] | None = fields
    if fields and fields != "*all":
        fields_list = [f.strip() for f in fields.split(",")]

    search_result = jira.search_issues(
        jql=jql,
        fields=fields_list,
        limit=limit,
        start=start_at,
        expand=expand,
        projects_filter=projects_filter,
    )
    result = search_result.to_simplified_dict()
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Search Fields", "readOnlyHint": True},
)
async def search_fields(
    ctx: Context,
    keyword: Annotated[
        str,
        Field(
            description="Keyword for fuzzy search. If left empty, lists the first 'limit' available fields in their default order.",
            default="",
        ),
    ] = "",
    limit: Annotated[
        int, Field(description="Maximum number of results", default=10, ge=1)
    ] = 10,
    refresh: Annotated[
        bool,
        Field(description="Whether to force refresh the field list", default=False),
    ] = False,
) -> str:
    """Search Jira fields by keyword with fuzzy match.

    Args:
        ctx: The FastMCP context.
        keyword: Keyword for fuzzy search.
        limit: Maximum number of results.
        refresh: Whether to force refresh the field list.

    Returns:
        JSON string representing a list of matching field definitions.
    """
    jira = await get_jira_fetcher(ctx)
    result = jira.search_fields(keyword, limit=limit, refresh=refresh)
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Field Options", "readOnlyHint": True},
)
async def get_field_options(
    ctx: Context,
    field_id: Annotated[
        str,
        Field(
            description="Custom field ID (e.g., 'customfield_10001'). "
            "Use jira_search_fields to find field IDs."
        ),
    ],
    context_id: Annotated[
        str | None,
        Field(
            description="Field context ID (Cloud only). "
            "If omitted, auto-resolves to the global context.",
            default=None,
        ),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(
            description="Project key (required for Server/DC). Example: 'PROJ'",
            default=None,
        ),
    ] = None,
    issue_type: Annotated[
        str | None,
        Field(
            description="Issue type name (required for Server/DC). Example: 'Bug'",
            default=None,
        ),
    ] = None,
) -> str:
    """Get allowed option values for a custom field.

    Returns the list of valid options for select, multi-select, radio,
    checkbox, and cascading select custom fields.

    Cloud: Uses the Field Context Option API. If context_id is not provided,
    automatically resolves to the global context.

    Server/DC: Uses createmeta to get allowedValues. Requires project_key
    and issue_type parameters.

    Args:
        ctx: The FastMCP context.
        field_id: The custom field ID.
        context_id: Field context ID (Cloud only, auto-resolved if omitted).
        project_key: Project key (required for Server/DC).
        issue_type: Issue type name (required for Server/DC).

    Returns:
        JSON string with the list of available options.
    """
    jira = await get_jira_fetcher(ctx)
    options = jira.get_field_options(
        field_id=field_id,
        context_id=context_id,
        project_key=project_key,
        issue_type=issue_type,
    )
    result = [opt.to_simplified_dict() for opt in options]
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Project Issues", "readOnlyHint": True},
)
async def get_project_issues(
    ctx: Context,
    project_key: Annotated[
        str,
        Field(
            description="Jira project key (e.g., 'PROJ', 'ACV2')",
            pattern=PROJECT_KEY_PATTERN,
        ),
    ],
    limit: Annotated[
        int,
        Field(description="Maximum number of results (1-50)", default=10, ge=1, le=50),
    ] = 10,
    start_at: Annotated[
        int,
        Field(description="Starting index for pagination (0-based)", default=0, ge=0),
    ] = 0,
) -> str:
    """Get all issues for a specific Jira project.

    Args:
        ctx: The FastMCP context.
        project_key: The project key.
        limit: Maximum number of results.
        start_at: Starting index for pagination.

    Returns:
        JSON string representing the search results including pagination info.
    """
    jira = await get_jira_fetcher(ctx)
    search_result = jira.get_project_issues(
        project_key=project_key, start=start_at, limit=limit
    )
    result = search_result.to_simplified_dict()
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Transitions", "readOnlyHint": True},
)
async def get_transitions(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
) -> str:
    """Get available status transitions for a Jira issue.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.

    Returns:
        JSON string representing a list of available transitions.
    """
    jira = await get_jira_fetcher(ctx)
    # Underlying method returns list[dict] in the desired format
    transitions = jira.get_available_transitions(issue_key)
    return json.dumps(transitions, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Worklog", "readOnlyHint": True},
)
async def get_worklog(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
) -> str:
    """Get worklog entries for a Jira issue.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.

    Returns:
        JSON string representing the worklog entries.
    """
    jira = await get_jira_fetcher(ctx)
    worklogs = jira.get_worklogs(issue_key)
    result = {"worklogs": worklogs}
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Download Attachments", "readOnlyHint": True},
)
async def download_attachments(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
) -> list[TextContent | EmbeddedResource]:
    """Download attachments from a Jira issue.

    Returns attachment contents as base64-encoded embedded resources so that
    they are available over the MCP protocol without requiring filesystem
    access on the server.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.

    Returns:
        A list containing a text summary and one EmbeddedResource per
        successfully downloaded attachment.
    """
    jira = await get_jira_fetcher(ctx)
    result = jira.get_issue_attachment_contents(issue_key=issue_key)

    contents: list[TextContent | EmbeddedResource] = []

    if not result.get("success"):
        contents.append(
            TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False),
            )
        )
        return contents

    attachments = result.get("attachments", [])
    failed = result.get("failed", [])

    summary = {
        "success": True,
        "issue_key": result.get("issue_key", issue_key),
        "total": result.get("total", 0),
        "downloaded": len(attachments),
        "failed": failed,
    }

    if not attachments and not failed:
        summary["message"] = result.get(
            "message", f"No attachments found for issue {issue_key}"
        )

    contents.append(
        TextContent(
            type="text",
            text=json.dumps(summary, indent=2, ensure_ascii=False),
        )
    )

    for attachment in attachments:
        data_bytes: bytes = attachment["data"]
        encoded = base64.b64encode(data_bytes).decode("ascii")
        mime_type = attachment.get("content_type", "application/octet-stream")
        filename = attachment["filename"]

        contents.append(
            EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(
                    uri=f"attachment:///{issue_key}/{filename}",
                    mimeType=mime_type,
                    blob=encoded,
                ),
            )
        )

    return contents


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Agile Boards", "readOnlyHint": True},
)
async def get_agile_boards(
    ctx: Context,
    board_name: Annotated[
        str | None,
        Field(description="(Optional) The name of board, support fuzzy search"),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(
            description="(Optional) Jira project key (e.g., 'PROJ', 'ACV2')",
            pattern=PROJECT_KEY_PATTERN,
        ),
    ] = None,
    board_type: Annotated[
        str | None,
        Field(
            description="(Optional) The type of jira board (e.g., 'scrum', 'kanban')"
        ),
    ] = None,
    start_at: Annotated[
        int,
        Field(description="Starting index for pagination (0-based)", default=0, ge=0),
    ] = 0,
    limit: Annotated[
        int,
        Field(description="Maximum number of results (1-50)", default=10, ge=1, le=50),
    ] = 10,
) -> str:
    """Get jira agile boards by name, project key, or type.

    Args:
        ctx: The FastMCP context.
        board_name: Name of the board (fuzzy search).
        project_key: Project key.
        board_type: Board type ('scrum' or 'kanban').
        start_at: Starting index.
        limit: Maximum results.

    Returns:
        JSON string representing a list of board objects.
    """
    jira = await get_jira_fetcher(ctx)
    boards = jira.get_all_agile_boards_model(
        board_name=board_name,
        project_key=project_key,
        board_type=board_type,
        start=start_at,
        limit=limit,
    )
    result = [board.to_simplified_dict() for board in boards]
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Board Issues", "readOnlyHint": True},
)
async def get_board_issues(
    ctx: Context,
    board_id: Annotated[str, Field(description="The id of the board (e.g., '1001')")],
    jql: Annotated[
        str,
        Field(
            description=(
                "JQL query string (Jira Query Language). Examples:\n"
                '- Find Epics: "issuetype = Epic AND project = PROJ"\n'
                '- Find issues in Epic: "parent = PROJ-123"\n'
                "- Find by status: \"status = 'In Progress' AND project = PROJ\"\n"
                '- Find by assignee: "assignee = currentUser()"\n'
                '- Find recently updated: "updated >= -7d AND project = PROJ"\n'
                '- Find by label: "labels = frontend AND project = PROJ"\n'
                '- Find by priority: "priority = High AND project = PROJ"'
            )
        ),
    ],
    fields: Annotated[
        str,
        Field(
            description=(
                "Comma-separated fields to return in the results. "
                "Use '*all' for all fields, or specify individual "
                "fields like 'summary,status,assignee,priority'"
            ),
            default=",".join(DEFAULT_READ_JIRA_FIELDS),
        ),
    ] = ",".join(DEFAULT_READ_JIRA_FIELDS),
    start_at: Annotated[
        int,
        Field(description="Starting index for pagination (0-based)", default=0, ge=0),
    ] = 0,
    limit: Annotated[
        int,
        Field(description="Maximum number of results (1-50)", default=10, ge=1, le=50),
    ] = 10,
    expand: Annotated[
        str,
        Field(
            description="Optional fields to expand in the response (e.g., 'changelog').",
            default="version",
        ),
    ] = "version",
) -> str:
    """Get all issues linked to a specific board filtered by JQL.

    Args:
        ctx: The FastMCP context.
        board_id: The ID of the board.
        jql: JQL query string to filter issues.
        fields: Comma-separated fields to return.
        start_at: Starting index for pagination.
        limit: Maximum number of results.
        expand: Optional fields to expand.

    Returns:
        JSON string representing the search results including pagination info.
    """
    jira = await get_jira_fetcher(ctx)
    fields_list: str | list[str] | None = fields
    if fields and fields != "*all":
        fields_list = [f.strip() for f in fields.split(",")]

    search_result = jira.get_board_issues(
        board_id=board_id,
        jql=jql,
        fields=fields_list,
        start=start_at,
        limit=limit,
        expand=expand,
    )
    result = search_result.to_simplified_dict()
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Sprints from Board", "readOnlyHint": True},
)
async def get_sprints_from_board(
    ctx: Context,
    board_id: Annotated[str, Field(description="The id of board (e.g., '1000')")],
    state: Annotated[
        str | None,
        Field(description="Sprint state (e.g., 'active', 'future', 'closed')"),
    ] = None,
    start_at: Annotated[
        int,
        Field(description="Starting index for pagination (0-based)", default=0, ge=0),
    ] = 0,
    limit: Annotated[
        int,
        Field(description="Maximum number of results (1-50)", default=10, ge=1, le=50),
    ] = 10,
) -> str:
    """Get jira sprints from board by state.

    Args:
        ctx: The FastMCP context.
        board_id: The ID of the board.
        state: Sprint state ('active', 'future', 'closed'). If None, returns all sprints.
        start_at: Starting index.
        limit: Maximum results.

    Returns:
        JSON string representing a list of sprint objects.
    """
    jira = await get_jira_fetcher(ctx)
    sprints = jira.get_all_sprints_from_board_model(
        board_id=board_id, state=state, start=start_at, limit=limit
    )
    result = [sprint.to_simplified_dict() for sprint in sprints]
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Sprint Issues", "readOnlyHint": True},
)
async def get_sprint_issues(
    ctx: Context,
    sprint_id: Annotated[str, Field(description="The id of sprint (e.g., '10001')")],
    fields: Annotated[
        str,
        Field(
            description=(
                "Comma-separated fields to return in the results. "
                "Use '*all' for all fields, or specify individual "
                "fields like 'summary,status,assignee,priority'"
            ),
            default=",".join(DEFAULT_READ_JIRA_FIELDS),
        ),
    ] = ",".join(DEFAULT_READ_JIRA_FIELDS),
    start_at: Annotated[
        int,
        Field(description="Starting index for pagination (0-based)", default=0, ge=0),
    ] = 0,
    limit: Annotated[
        int,
        Field(description="Maximum number of results (1-50)", default=10, ge=1, le=50),
    ] = 10,
) -> str:
    """Get jira issues from sprint.

    Args:
        ctx: The FastMCP context.
        sprint_id: The ID of the sprint.
        fields: Comma-separated fields to return.
        start_at: Starting index.
        limit: Maximum results.

    Returns:
        JSON string representing the search results including pagination info.
    """
    jira = await get_jira_fetcher(ctx)
    fields_list: str | list[str] | None = fields
    if fields and fields != "*all":
        fields_list = [f.strip() for f in fields.split(",")]

    search_result = jira.get_sprint_issues(
        sprint_id=sprint_id, fields=fields_list, start=start_at, limit=limit
    )
    result = search_result.to_simplified_dict()
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Link Types", "readOnlyHint": True},
)
async def get_link_types(
    ctx: Context,
    name_filter: Annotated[
        str | None,
        Field(
            description="(Optional) Filter link types by name substring (case-insensitive)",
        ),
    ] = None,
) -> str:
    """Get all available issue link types.

    Args:
        ctx: The FastMCP context.
        name_filter: Optional substring to filter link types by name.

    Returns:
        JSON string representing a list of issue link type objects.
    """
    jira = await get_jira_fetcher(ctx)
    link_types = jira.get_issue_link_types()
    formatted_link_types = [link_type.to_simplified_dict() for link_type in link_types]
    if name_filter:
        name_lower = name_filter.lower()
        formatted_link_types = [
            lt
            for lt in formatted_link_types
            if name_lower in lt.get("name", "").lower()
        ]
    return json.dumps(formatted_link_types, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Create Issue", "destructiveHint": True},
)
@check_write_access
async def create_issue(
    ctx: Context,
    project_key: Annotated[
        str,
        Field(
            description=(
                "The JIRA project key (e.g. 'PROJ', 'DEV', 'ACV2'). "
                "This is the prefix of issue keys in your project. "
                "Never assume what it might be, always ask the user."
            ),
            pattern=PROJECT_KEY_PATTERN,
        ),
    ],
    summary: Annotated[str, Field(description="Summary/title of the issue")],
    issue_type: Annotated[
        str,
        Field(
            description=(
                "Issue type (e.g. 'Task', 'Bug', 'Story', 'Epic', 'Subtask'). "
                "The available types depend on your project configuration. "
                "For subtasks, use 'Subtask' (not 'Sub-task') and include parent in additional_fields."
            ),
        ),
    ],
    assignee: Annotated[
        str | None,
        Field(
            description="(Optional) Assignee's user identifier (string): Email, display name, or account ID (e.g., 'user@example.com', 'John Doe', 'accountid:...')",
            default=None,
        ),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="Issue description in Markdown format", default=None),
    ] = None,
    components: Annotated[
        str | None,
        Field(
            description="(Optional) Comma-separated list of component names to assign (e.g., 'Frontend,API')",
            default=None,
        ),
    ] = None,
    additional_fields: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) JSON string of additional fields to set. Examples:\n"
                '- Set priority: {"priority": {"name": "High"}}\n'
                '- Add labels: {"labels": ["frontend", "urgent"]}\n'
                '- Link to parent (for any issue type): {"parent": "PROJ-123"}\n'
                '- Link to epic: {"epicKey": "EPIC-123"} or {"epic_link": "EPIC-123"}\n'
                '- Set Fix Version/s: {"fixVersions": [{"id": "10020"}]}\n'
                '- Custom fields: {"customfield_10010": "value"}'
            ),
            default=None,
        ),
    ] = None,
) -> str:
    """Create a new Jira issue with optional Epic link or parent for subtasks.

    Args:
        ctx: The FastMCP context.
        project_key: The JIRA project key.
        summary: Summary/title of the issue.
        issue_type: Issue type (e.g., 'Task', 'Bug', 'Story', 'Epic', 'Subtask').
        assignee: Assignee's user identifier (string): Email, display name, or account ID (e.g., 'user@example.com', 'John Doe', 'accountid:...').
        description: Issue description in Markdown format.
        components: Comma-separated list of component names.
        additional_fields: JSON string of additional fields.

    Returns:
        JSON string representing the created issue object.

    Raises:
        ValueError: If in read-only mode or Jira client is unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    # Parse components from comma-separated string to list
    components_list = None
    if components and isinstance(components, str):
        components_list = [
            comp.strip() for comp in components.split(",") if comp.strip()
        ]

    extra_fields = _parse_additional_fields(additional_fields)

    issue = jira.create_issue(
        project_key=project_key,
        summary=summary,
        issue_type=issue_type,
        description=description,
        assignee=assignee,
        components=components_list,
        **extra_fields,
    )
    result = issue.to_simplified_dict()
    return json.dumps(
        {"message": "Issue created successfully", "issue": result},
        indent=2,
        ensure_ascii=False,
    )


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Batch Create Issues", "destructiveHint": True},
)
@check_write_access
async def batch_create_issues(
    ctx: Context,
    issues: Annotated[
        str,
        Field(
            description=(
                "JSON array of issue objects. Each object should contain:\n"
                "- project_key (required): The project key (e.g., 'PROJ')\n"
                "- summary (required): Issue summary/title\n"
                "- issue_type (required): Type of issue (e.g., 'Task', 'Bug')\n"
                "- description (optional): Issue description in Markdown format\n"
                "- assignee (optional): Assignee username or email\n"
                "- components (optional): Array of component names\n"
                "Example: [\n"
                '  {"project_key": "PROJ", "summary": "Issue 1", "issue_type": "Task"},\n'
                '  {"project_key": "PROJ", "summary": "Issue 2", "issue_type": "Bug", "components": ["Frontend"]}\n'
                "]"
            )
        ),
    ],
    validate_only: Annotated[
        bool,
        Field(
            description="If true, only validates the issues without creating them",
            default=False,
        ),
    ] = False,
) -> str:
    """Create multiple Jira issues in a batch.

    Args:
        ctx: The FastMCP context.
        issues: JSON array string of issue objects.
        validate_only: If true, only validates without creating.

    Returns:
        JSON string indicating success and listing created issues (or validation result).

    Raises:
        ValueError: If in read-only mode, Jira client unavailable, or invalid JSON.
    """
    jira = await get_jira_fetcher(ctx)
    # Parse issues from JSON string
    try:
        issues_list = json.loads(issues)
        if not isinstance(issues_list, list):
            raise ValueError("Input 'issues' must be a JSON array string.")
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON in issues")
    except Exception as e:
        raise ValueError(f"Invalid input for issues: {e}") from e

    # Create issues in batch
    created_issues = jira.batch_create_issues(issues_list, validate_only=validate_only)

    message = (
        "Issues validated successfully"
        if validate_only
        else "Issues created successfully"
    )
    result = {
        "message": message,
        "issues": [issue.to_simplified_dict() for issue in created_issues],
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Batch Get Changelogs", "readOnlyHint": True},
)
async def batch_get_changelogs(
    ctx: Context,
    issue_ids_or_keys: Annotated[
        str,
        Field(
            description="Comma-separated list of Jira issue IDs or keys (e.g. 'PROJ-123,PROJ-124')"
        ),
    ],
    fields: Annotated[
        str | None,
        Field(
            description="(Optional) Comma-separated list of fields to filter changelogs by (e.g. 'status,assignee'). Default to None for all fields.",
            default=None,
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(
            description=(
                "Maximum number of changelogs to return in result for each issue. "
                "Default to -1 for all changelogs. "
                "Notice that it only limits the results in the response, "
                "the function will still fetch all the data."
            ),
            default=-1,
        ),
    ] = -1,
) -> str:
    """Get changelogs for multiple Jira issues (Cloud only).

    Args:
        ctx: The FastMCP context.
        issue_ids_or_keys: List of issue IDs or keys.
        fields: List of fields to filter changelogs by. None for all fields.
        limit: Maximum changelogs per issue (-1 for all).

    Returns:
        JSON string representing a list of issues with their changelogs.

    Raises:
        NotImplementedError: If run on Jira Server/Data Center.
        ValueError: If Jira client is unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    # Ensure this runs only on Cloud, as per original function docstring
    if not jira.config.is_cloud:
        raise NotImplementedError(
            "Batch get issue changelogs is only available on Jira Cloud."
        )

    # Parse CSV strings into lists
    keys_list = [k.strip() for k in issue_ids_or_keys.split(",") if k.strip()]
    fields_list: list[str] | None = None
    if fields is not None:
        fields_list = [f.strip() for f in fields.split(",") if f.strip()]

    # Call the underlying method
    issues_with_changelogs = jira.batch_get_changelogs(
        issue_ids_or_keys=keys_list, fields=fields_list
    )

    # Format the response
    results = []
    limit_val = None if limit == -1 else limit
    for issue in issues_with_changelogs:
        results.append(
            {
                "issue_id": issue.id,
                "changelogs": [
                    changelog.to_simplified_dict()
                    for changelog in issue.changelogs[:limit_val]
                ],
            }
        )
    return json.dumps(results, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Update Issue", "destructiveHint": True},
)
@check_write_access
async def update_issue(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    fields: Annotated[
        str,
        Field(
            description=(
                "Dictionary of fields to update. For 'assignee', provide a string identifier (email, name, or accountId). "
                "For 'description', provide text in Markdown format. "
                "Example: `{'assignee': 'user@example.com', 'summary': 'New Summary', 'description': '## Updated\\nMarkdown text'}`"
            )
        ),
    ],
    additional_fields: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) JSON string of additional fields to update. "
                "Use this for custom fields or more complex updates. "
                'Link to epic: {"epicKey": "EPIC-123"} or {"epic_link": "EPIC-123"}.'
            ),
            default=None,
        ),
    ] = None,
    components: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Comma-separated list of component names "
                "(e.g., 'Frontend,API')"
            ),
            default=None,
        ),
    ] = None,
    attachments: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) JSON string array or comma-separated list of file paths to attach to the issue. "
                "Example: '/path/to/file1.txt,/path/to/file2.txt' or ['/path/to/file1.txt','/path/to/file2.txt']"
            ),
            default=None,
        ),
    ] = None,
) -> str:
    """Update an existing Jira issue including changing status, adding Epic links, updating fields, etc.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.
        fields: Dictionary of fields to update. Text fields like 'description' should use Markdown format.
        additional_fields: Optional JSON string of additional fields.
        components: Comma-separated list of component names.
        attachments: Optional JSON array string or comma-separated list of file paths.

    Returns:
        JSON string representing the updated issue object and attachment results.

    Raises:
        ValueError: If in read-only mode or Jira client unavailable, or invalid input.
    """
    jira = await get_jira_fetcher(ctx)
    update_fields = _parse_additional_fields(fields)

    # Parse components from comma-separated string to list
    components_list = None
    if components and isinstance(components, str):
        components_list = [
            comp.strip() for comp in components.split(",") if comp.strip()
        ]

    extra_fields = _parse_additional_fields(additional_fields)

    # Parse attachments
    attachment_paths = []
    if attachments:
        if isinstance(attachments, str):
            try:
                parsed = json.loads(attachments)
                if isinstance(parsed, list):
                    attachment_paths = [str(p) for p in parsed]
                else:
                    raise ValueError("attachments JSON string must be an array.")
            except json.JSONDecodeError:
                # Assume comma-separated if not valid JSON array
                attachment_paths = [
                    p.strip() for p in attachments.split(",") if p.strip()
                ]
        else:
            raise ValueError(
                "attachments must be a JSON array string or comma-separated string."
            )

    # Combine fields and additional_fields
    all_updates = {**update_fields, **extra_fields}
    if components_list:
        all_updates["components"] = components_list
    if attachment_paths:
        all_updates["attachments"] = attachment_paths

    try:
        issue = jira.update_issue(issue_key=issue_key, **all_updates)
        result = issue.to_simplified_dict()
        if (
            hasattr(issue, "custom_fields")
            and "attachment_results" in issue.custom_fields
        ):
            result["attachment_results"] = issue.custom_fields["attachment_results"]
        return json.dumps(
            {"message": "Issue updated successfully", "issue": result},
            indent=2,
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"Error updating issue {issue_key}: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to update issue {issue_key}: {str(e)}")


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Delete Issue", "destructiveHint": True},
)
@check_write_access
async def delete_issue(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
) -> str:
    """Delete an existing Jira issue.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.

    Returns:
        JSON string indicating success.

    Raises:
        ValueError: If in read-only mode or Jira client unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    deleted = jira.delete_issue(issue_key)
    result = {"message": f"Issue {issue_key} has been deleted successfully."}
    # The underlying method raises on failure, so if we reach here, it's success.
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Add Comment", "destructiveHint": True},
)
@check_write_access
async def add_comment(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    comment: Annotated[str, Field(description="Comment text in Markdown format")],
    visibility: Annotated[
        str | None,
        Field(
            description='(Optional) Comment visibility as JSON string (e.g. \'{"type":"group","value":"jira-users"}\')'
        ),
    ] = None,
) -> str:
    """Add a comment to a Jira issue.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.
        comment: Comment text in Markdown.
        visibility: (Optional) Comment visibility as JSON string.

    Returns:
        JSON string representing the added comment object.

    Raises:
        ValueError: If in read-only mode or Jira client unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    visibility_dict = _parse_visibility(visibility)
    result = jira.add_comment(issue_key, comment, visibility_dict)
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Edit Comment", "destructiveHint": True},
)
@check_write_access
async def edit_comment(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    comment_id: Annotated[str, Field(description="The ID of the comment to edit")],
    comment: Annotated[
        str, Field(description="Updated comment text in Markdown format")
    ],
    visibility: Annotated[
        str | None,
        Field(
            description='(Optional) Comment visibility as JSON string (e.g. \'{"type":"group","value":"jira-users"}\')'
        ),
    ] = None,
) -> str:
    """Edit an existing comment on a Jira issue.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.
        comment_id: The ID of the comment to edit.
        comment: Updated comment text in Markdown.
        visibility: (Optional) Comment visibility as JSON string.

    Returns:
        JSON string representing the updated comment object.

    Raises:
        ValueError: If in read-only mode or Jira client unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    visibility_dict = _parse_visibility(visibility)
    result = jira.edit_comment(issue_key, comment_id, comment, visibility_dict)
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Add Worklog", "destructiveHint": True},
)
@check_write_access
async def add_worklog(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    time_spent: Annotated[
        str,
        Field(
            description=(
                "Time spent in Jira format. Examples: "
                "'1h 30m' (1 hour and 30 minutes), '1d' (1 day), '30m' (30 minutes), '4h' (4 hours)"
            )
        ),
    ],
    comment: Annotated[
        str | None,
        Field(description="(Optional) Comment for the worklog in Markdown format"),
    ] = None,
    started: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Start time in ISO format. If not provided, the current time will be used. "
                "Example: '2023-08-01T12:00:00.000+0000'"
            )
        ),
    ] = None,
    # Add original_estimate and remaining_estimate as per original tool
    original_estimate: Annotated[
        str | None, Field(description="(Optional) New value for the original estimate")
    ] = None,
    remaining_estimate: Annotated[
        str | None, Field(description="(Optional) New value for the remaining estimate")
    ] = None,
) -> str:
    """Add a worklog entry to a Jira issue.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.
        time_spent: Time spent in Jira format.
        comment: Optional comment in Markdown.
        started: Optional start time in ISO format.
        original_estimate: Optional new original estimate.
        remaining_estimate: Optional new remaining estimate.


    Returns:
        JSON string representing the added worklog object.

    Raises:
        ValueError: If in read-only mode or Jira client unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    # add_worklog returns dict
    worklog_result = jira.add_worklog(
        issue_key=issue_key,
        time_spent=time_spent,
        comment=comment,
        started=started,
        original_estimate=original_estimate,
        remaining_estimate=remaining_estimate,
    )
    result = {"message": "Worklog added successfully", "worklog": worklog_result}
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Link to Epic", "destructiveHint": True},
)
@check_write_access
async def link_to_epic(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="The key of the issue to link (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    epic_key: Annotated[
        str,
        Field(
            description="The key of the epic to link to (e.g., 'PROJ-456')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
) -> str:
    """Link an existing issue to an epic.

    Args:
        ctx: The FastMCP context.
        issue_key: The key of the issue to link.
        epic_key: The key of the epic to link to.

    Returns:
        JSON string representing the updated issue object.

    Raises:
        ValueError: If in read-only mode or Jira client unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    issue = jira.link_issue_to_epic(issue_key, epic_key)
    result = {
        "message": f"Issue {issue_key} has been linked to epic {epic_key}.",
        "issue": issue.to_simplified_dict(),
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Create Issue Link", "destructiveHint": True},
)
@check_write_access
async def create_issue_link(
    ctx: Context,
    link_type: Annotated[
        str,
        Field(
            description="The type of link to create (e.g., 'Duplicate', 'Blocks', 'Relates to')"
        ),
    ],
    inward_issue_key: Annotated[
        str,
        Field(
            description="The key of the inward issue (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    outward_issue_key: Annotated[
        str,
        Field(
            description="The key of the outward issue (e.g., 'PROJ-456')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    comment: Annotated[
        str | None, Field(description="(Optional) Comment to add to the link")
    ] = None,
    comment_visibility: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Visibility settings for the comment as JSON string "
                '(e.g. \'{"type":"group","value":"jira-users"}\')'
            ),
            default=None,
        ),
    ] = None,
) -> str:
    """Create a link between two Jira issues.

    Args:
        ctx: The FastMCP context.
        link_type: The type of link (e.g., 'Blocks').
        inward_issue_key: The key of the source issue.
        outward_issue_key: The key of the target issue.
        comment: Optional comment text.
        comment_visibility: Optional JSON string for comment visibility.

    Returns:
        JSON string indicating success or failure.

    Raises:
        ValueError: If required fields are missing, invalid input, in read-only mode, or Jira client unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    if not all([link_type, inward_issue_key, outward_issue_key]):
        raise ValueError(
            "link_type, inward_issue_key, and outward_issue_key are required."
        )

    visibility_dict = _parse_visibility(comment_visibility, "comment_visibility")

    link_data = {
        "type": {"name": link_type},
        "inwardIssue": {"key": inward_issue_key},
        "outwardIssue": {"key": outward_issue_key},
    }

    if comment:
        comment_obj: dict[str, Any] = {"body": comment}
        if visibility_dict:
            if "type" in visibility_dict and "value" in visibility_dict:
                comment_obj["visibility"] = visibility_dict
            else:
                logger.warning("Invalid comment_visibility dictionary structure.")
        link_data["comment"] = comment_obj

    result = jira.create_issue_link(link_data)
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Create Remote Issue Link", "destructiveHint": True},
)
@check_write_access
async def create_remote_issue_link(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="The key of the issue to add the link to (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    url: Annotated[
        str,
        Field(
            description="The URL to link to (e.g., 'https://example.com/page' or Confluence page URL)"
        ),
    ],
    title: Annotated[
        str,
        Field(
            description="The title/name of the link (e.g., 'Documentation Page', 'Confluence Page')"
        ),
    ],
    summary: Annotated[
        str | None, Field(description="(Optional) Description of the link")
    ] = None,
    relationship: Annotated[
        str | None,
        Field(
            description="(Optional) Relationship description (e.g., 'causes', 'relates to', 'documentation')"
        ),
    ] = None,
    icon_url: Annotated[
        str | None, Field(description="(Optional) URL to a 16x16 icon for the link")
    ] = None,
) -> str:
    """Create a remote issue link (web link or Confluence link) for a Jira issue.

    This tool allows you to add web links and Confluence links to Jira issues.
    The links will appear in the issue's "Links" section and can be clicked to navigate to external resources.

    Args:
        ctx: The FastMCP context.
        issue_key: The key of the issue to add the link to.
        url: The URL to link to (can be any web page or Confluence page).
        title: The title/name that will be displayed for the link.
        summary: Optional description of what the link is for.
        relationship: Optional relationship description.
        icon_url: Optional URL to a 16x16 icon for the link.

    Returns:
        JSON string indicating success or failure.

    Raises:
        ValueError: If required fields are missing, invalid input, in read-only mode, or Jira client unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    if not issue_key:
        raise ValueError("issue_key is required.")
    if not url:
        raise ValueError("url is required.")
    if not title:
        raise ValueError("title is required.")

    # Build the remote link data structure
    link_object = {
        "url": url,
        "title": title,
    }

    if summary:
        link_object["summary"] = summary

    if icon_url:
        link_object["icon"] = {"url16x16": icon_url, "title": title}

    link_data = {"object": link_object}

    if relationship:
        link_data["relationship"] = relationship

    result = jira.create_remote_issue_link(issue_key, link_data)
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Remove Issue Link", "destructiveHint": True},
)
@check_write_access
async def remove_issue_link(
    ctx: Context,
    link_id: Annotated[str, Field(description="The ID of the link to remove")],
) -> str:
    """Remove a link between two Jira issues.

    Args:
        ctx: The FastMCP context.
        link_id: The ID of the link to remove.

    Returns:
        JSON string indicating success.

    Raises:
        ValueError: If link_id is missing, in read-only mode, or Jira client unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    if not link_id:
        raise ValueError("link_id is required")

    result = jira.remove_issue_link(link_id)  # Returns dict on success
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Transition Issue", "destructiveHint": True},
)
@check_write_access
async def transition_issue(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    transition_id: Annotated[
        str,
        Field(
            description=(
                "ID of the transition to perform. Use the jira_get_transitions tool first "
                "to get the available transition IDs for the issue. Example values: '11', '21', '31'"
            )
        ),
    ],
    fields: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) JSON string of fields to update during the transition. "
                "Some transitions require specific fields to be set (e.g., resolution). "
                'Example: \'{"resolution": {"name": "Fixed"}}\''
            ),
            default=None,
        ),
    ] = None,
    comment: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Comment to add during the transition in Markdown format. "
                "This will be visible in the issue history."
            ),
        ),
    ] = None,
) -> str:
    """Transition a Jira issue to a new status.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.
        transition_id: ID of the transition.
        fields: Optional JSON string of fields to update during transition.
        comment: Optional comment for the transition in Markdown format.

    Returns:
        JSON string representing the updated issue object.

    Raises:
        ValueError: If required fields missing, invalid input, in read-only mode, or Jira client unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    if not issue_key or not transition_id:
        raise ValueError("issue_key and transition_id are required.")

    # Parse fields from JSON string
    update_fields = _parse_additional_fields(fields)

    issue = jira.transition_issue(
        issue_key=issue_key,
        transition_id=transition_id,
        fields=update_fields,
        comment=comment,
    )

    result = {
        "message": f"Issue {issue_key} transitioned successfully",
        "issue": issue.to_simplified_dict() if issue else None,
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Create Sprint", "destructiveHint": True},
)
@check_write_access
async def create_sprint(
    ctx: Context,
    board_id: Annotated[str, Field(description="The id of board (e.g., '1000')")],
    sprint_name: Annotated[
        str, Field(description="Name of the sprint (e.g., 'Sprint 1')")
    ],
    start_date: Annotated[
        str, Field(description="Start time for sprint (ISO 8601 format)")
    ],
    end_date: Annotated[
        str, Field(description="End time for sprint (ISO 8601 format)")
    ],
    goal: Annotated[
        str | None, Field(description="(Optional) Goal of the sprint")
    ] = None,
) -> str:
    """Create Jira sprint for a board.

    Args:
        ctx: The FastMCP context.
        board_id: Board ID.
        sprint_name: Sprint name.
        start_date: Start date (ISO format).
        end_date: End date (ISO format).
        goal: Optional sprint goal.

    Returns:
        JSON string representing the created sprint object.

    Raises:
        ValueError: If in read-only mode or Jira client unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    sprint = jira.create_sprint(
        board_id=board_id,
        sprint_name=sprint_name,
        start_date=start_date,
        end_date=end_date,
        goal=goal,
    )
    return json.dumps(sprint.to_simplified_dict(), indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Update Sprint", "destructiveHint": True},
)
@check_write_access
async def update_sprint(
    ctx: Context,
    sprint_id: Annotated[str, Field(description="The id of sprint (e.g., '10001')")],
    sprint_name: Annotated[
        str | None, Field(description="(Optional) New name for the sprint")
    ] = None,
    state: Annotated[
        str | None,
        Field(description="(Optional) New state for the sprint (future|active|closed)"),
    ] = None,
    start_date: Annotated[
        str | None, Field(description="(Optional) New start date for the sprint")
    ] = None,
    end_date: Annotated[
        str | None, Field(description="(Optional) New end date for the sprint")
    ] = None,
    goal: Annotated[
        str | None, Field(description="(Optional) New goal for the sprint")
    ] = None,
) -> str:
    """Update jira sprint.

    Args:
        ctx: The FastMCP context.
        sprint_id: The ID of the sprint.
        sprint_name: Optional new name.
        state: Optional new state (future|active|closed).
        start_date: Optional new start date.
        end_date: Optional new end date.
        goal: Optional new goal.

    Returns:
        JSON string representing the updated sprint object or an error message.

    Raises:
        ValueError: If in read-only mode or Jira client unavailable.
    """
    jira = await get_jira_fetcher(ctx)
    sprint = jira.update_sprint(
        sprint_id=sprint_id,
        sprint_name=sprint_name,
        state=state,
        start_date=start_date,
        end_date=end_date,
        goal=goal,
    )

    if sprint is None:
        error_payload = {
            "error": f"Failed to update sprint {sprint_id}. Check logs for details."
        }
        return json.dumps(error_payload, indent=2, ensure_ascii=False)
    else:
        return json.dumps(sprint.to_simplified_dict(), indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Project Versions", "readOnlyHint": True},
)
async def get_project_versions(
    ctx: Context,
    project_key: Annotated[
        str,
        Field(
            description="Jira project key (e.g., 'PROJ', 'ACV2')",
            pattern=PROJECT_KEY_PATTERN,
        ),
    ],
) -> str:
    """Get all fix versions for a specific Jira project."""
    jira = await get_jira_fetcher(ctx)
    versions = jira.get_project_versions(project_key)
    return json.dumps(versions, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Project Components", "readOnlyHint": True},
)
async def get_project_components(
    ctx: Context,
    project_key: Annotated[str, Field(description="Jira project key (e.g., 'PROJ')")],
) -> str:
    """Get all components for a specific Jira project."""
    jira = await get_jira_fetcher(ctx)
    components = jira.get_project_components(project_key)
    return json.dumps(components, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get All Projects", "readOnlyHint": True},
)
async def get_all_projects(
    ctx: Context,
    include_archived: Annotated[
        bool,
        Field(
            description="Whether to include archived projects in the results",
            default=False,
        ),
    ] = False,
) -> str:
    """Get all Jira projects accessible to the current user.

    Args:
        ctx: The FastMCP context.
        include_archived: Whether to include archived projects.

    Returns:
        JSON string representing a list of project objects accessible to the user.
        Project keys are always returned in uppercase.
        If JIRA_PROJECTS_FILTER is configured, only returns projects matching those keys.

    Raises:
        ValueError: If the Jira client is not configured or available.
    """
    try:
        jira = await get_jira_fetcher(ctx)
        projects = jira.get_all_projects(include_archived=include_archived)
    except (MCPAtlassianAuthenticationError, HTTPError, OSError, ValueError) as e:
        error_message = ""
        log_level = logging.ERROR
        if isinstance(e, MCPAtlassianAuthenticationError):
            error_message = f"Authentication/Permission Error: {str(e)}"
        elif isinstance(e, OSError | HTTPError):
            error_message = f"Network or API Error: {str(e)}"
        elif isinstance(e, ValueError):
            error_message = f"Configuration Error: {str(e)}"

        error_result = {
            "success": False,
            "error": error_message,
        }
        logger.log(log_level, f"get_all_projects failed: {error_message}")
        return json.dumps(error_result, indent=2, ensure_ascii=False)

    # Ensure all project keys are uppercase
    for project in projects:
        if "key" in project:
            project["key"] = project["key"].upper()

    # Apply project filter if configured
    if jira.config.projects_filter:
        # Split projects filter by commas and handle possible whitespace
        allowed_project_keys = {
            p.strip().upper() for p in jira.config.projects_filter.split(",")
        }
        projects = [
            project
            for project in projects
            if project.get("key") in allowed_project_keys
        ]

    return json.dumps(projects, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={
        "title": "Get Service Desk For Project",
        "readOnlyHint": True,
    },
)
async def get_service_desk_for_project(
    ctx: Context,
    project_key: Annotated[
        str,
        Field(
            description="Jira project key (e.g., 'SUP')",
            pattern=PROJECT_KEY_PATTERN,
        ),
    ],
) -> str:
    """
    Get the Jira Service Desk associated with a project key.

    Server/Data Center only. Not available on Jira Cloud.

    Args:
        ctx: The FastMCP context.
        project_key: Jira project key.

    Returns:
        JSON string with project key and service desk data (or null if not found).

    Raises:
        NotImplementedError: If connected to Jira Cloud (Server/DC only).
    """
    jira = await get_jira_fetcher(ctx)
    service_desk = jira.get_service_desk_for_project(project_key=project_key)
    result = {
        "project_key": project_key.upper(),
        "service_desk": service_desk.to_simplified_dict() if service_desk else None,
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Service Desk Queues", "readOnlyHint": True},
)
async def get_service_desk_queues(
    ctx: Context,
    service_desk_id: Annotated[
        str,
        Field(description="Service desk ID (e.g., '4')"),
    ],
    start_at: Annotated[
        int,
        Field(description="Starting index for pagination (0-based)", default=0, ge=0),
    ] = 0,
    limit: Annotated[
        int,
        Field(description="Maximum number of results (1-50)", default=50, ge=1, le=50),
    ] = 50,
) -> str:
    """
    Get queues for a Jira Service Desk.

    Server/Data Center only. Not available on Jira Cloud.

    Args:
        ctx: The FastMCP context.
        service_desk_id: Service desk ID.
        start_at: Starting index for pagination.
        limit: Maximum number of queues to return.

    Returns:
        JSON string with queue list and pagination metadata.

    Raises:
        NotImplementedError: If connected to Jira Cloud (Server/DC only).
    """
    jira = await get_jira_fetcher(ctx)
    result = jira.get_service_desk_queues(
        service_desk_id=service_desk_id,
        start_at=start_at,
        limit=limit,
        include_count=True,
    )
    return json.dumps(result.to_simplified_dict(), indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Queue Issues", "readOnlyHint": True},
)
async def get_queue_issues(
    ctx: Context,
    service_desk_id: Annotated[
        str,
        Field(description="Service desk ID (e.g., '4')"),
    ],
    queue_id: Annotated[
        str,
        Field(description="Queue ID (e.g., '47')"),
    ],
    start_at: Annotated[
        int,
        Field(description="Starting index for pagination (0-based)", default=0, ge=0),
    ] = 0,
    limit: Annotated[
        int,
        Field(description="Maximum number of results (1-50)", default=50, ge=1),
    ] = 50,
) -> str:
    """
    Get issues from a Jira Service Desk queue.

    Server/Data Center only. Not available on Jira Cloud.

    Args:
        ctx: The FastMCP context.
        service_desk_id: Service desk ID.
        queue_id: Queue ID.
        start_at: Starting index for pagination.
        limit: Maximum number of issues to return.

    Returns:
        JSON string with queue metadata, issues, and pagination metadata.

    Raises:
        NotImplementedError: If connected to Jira Cloud (Server/DC only).
    """
    jira = await get_jira_fetcher(ctx)
    result = jira.get_queue_issues(
        service_desk_id=service_desk_id,
        queue_id=queue_id,
        start_at=start_at,
        limit=limit,
    )
    return json.dumps(result.to_simplified_dict(), indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Create Version", "destructiveHint": True},
)
@check_write_access
async def create_version(
    ctx: Context,
    project_key: Annotated[
        str,
        Field(
            description="Jira project key (e.g., 'PROJ', 'ACV2')",
            pattern=PROJECT_KEY_PATTERN,
        ),
    ],
    name: Annotated[str, Field(description="Name of the version")],
    start_date: Annotated[
        str | None, Field(description="Start date (YYYY-MM-DD)", default=None)
    ] = None,
    release_date: Annotated[
        str | None, Field(description="Release date (YYYY-MM-DD)", default=None)
    ] = None,
    description: Annotated[
        str | None, Field(description="Description of the version", default=None)
    ] = None,
) -> str:
    """Create a new fix version in a Jira project.

    Args:
        ctx: The FastMCP context.
        project_key: The project key.
        name: Name of the version.
        start_date: Start date (optional).
        release_date: Release date (optional).
        description: Description (optional).

    Returns:
        JSON string of the created version object.
    """
    jira = await get_jira_fetcher(ctx)
    try:
        version = jira.create_project_version(
            project_key=project_key,
            name=name,
            start_date=start_date,
            release_date=release_date,
            description=description,
        )
        return json.dumps(version, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(
            f"Error creating version in project {project_key}: {str(e)}", exc_info=True
        )
        return json.dumps(
            {"success": False, "error": str(e)}, indent=2, ensure_ascii=False
        )


@jira_mcp.tool(
    name="batch_create_versions",
    tags={"jira", "write"},
    annotations={"title": "Batch Create Versions", "destructiveHint": True},
)
@check_write_access
async def batch_create_versions(
    ctx: Context,
    project_key: Annotated[
        str,
        Field(
            description="Jira project key (e.g., 'PROJ', 'ACV2')",
            pattern=PROJECT_KEY_PATTERN,
        ),
    ],
    versions: Annotated[
        str,
        Field(
            description=(
                "JSON array of version objects. Each object should contain:\n"
                "- name (required): Name of the version\n"
                "- startDate (optional): Start date (YYYY-MM-DD)\n"
                "- releaseDate (optional): Release date (YYYY-MM-DD)\n"
                "- description (optional): Description of the version\n"
                "Example: [\n"
                '  {"name": "v1.0", "startDate": "2025-01-01", "releaseDate": "2025-02-01", "description": "First release"},\n'
                '  {"name": "v2.0"}\n'
                "]"
            )
        ),
    ],
) -> str:
    """Batch create multiple versions in a Jira project.

    Args:
        ctx: The FastMCP context.
        project_key: The project key.
        versions: JSON array string of version objects.

    Returns:
        JSON array of results, each with success flag, version or error.
    """
    jira = await get_jira_fetcher(ctx)
    try:
        version_list = json.loads(versions)
        if not isinstance(version_list, list):
            raise ValueError("Input 'versions' must be a JSON array string.")
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON in versions")
    except Exception as e:
        raise ValueError(f"Invalid input for versions: {e}") from e

    results = []
    if not version_list:
        return json.dumps(results, indent=2, ensure_ascii=False)

    for idx, v in enumerate(version_list):
        # Defensive: ensure v is a dict and has a name
        if not isinstance(v, dict) or not v.get("name"):
            results.append(
                {
                    "success": False,
                    "error": f"Item {idx}: Each version must be an object with at least a 'name' field.",
                }
            )
            continue
        try:
            version = jira.create_project_version(
                project_key=project_key,
                name=v["name"],
                start_date=v.get("startDate"),
                release_date=v.get("releaseDate"),
                description=v.get("description"),
            )
            results.append({"success": True, "version": version})
        except Exception as e:
            logger.error(
                f"Error creating version in batch for project {project_key}: {str(e)}",
                exc_info=True,
            )
            results.append({"success": False, "error": str(e), "input": v})
    return json.dumps(results, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Issue Forms", "readOnlyHint": True},
)
async def get_issue_proforma_forms(
    ctx: Context,
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
) -> str:
    """
    Get all ProForma forms associated with a Jira issue.

    Uses the new Jira Forms REST API. Form IDs are returned as UUIDs.

    Args:
        ctx: The FastMCP context.
        issue_key: The issue key to get forms for.

    Returns:
        JSON string representing the list of ProForma forms, or an error object if failed.
    """
    jira = await get_jira_fetcher(ctx)
    try:
        forms = jira.get_issue_forms(issue_key)
        forms_data = [form.to_simplified_dict() for form in forms]
        response_data = {"success": True, "forms": forms_data, "count": len(forms)}
    except Exception as e:
        error_message = ""
        log_level = logging.ERROR
        if isinstance(e, ValueError) and "not found" in str(e).lower():
            log_level = logging.WARNING
            error_message = str(e)
        elif isinstance(e, MCPAtlassianAuthenticationError):
            error_message = f"Authentication/Permission Error: {str(e)}"
        elif isinstance(e, OSError | HTTPError):
            error_message = f"Network or API Error: {str(e)}"
        else:
            error_message = (
                "An unexpected error occurred while fetching ProForma forms."
            )
            logger.exception(
                f"Unexpected error in get_issue_proforma_forms for '{issue_key}':"
            )
        error_result = {
            "success": False,
            "error": str(e),
            "issue_key": issue_key,
        }
        logger.log(
            log_level,
            f"get_issue_proforma_forms failed for '{issue_key}': {error_message}",
        )
        response_data = error_result
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read"},
    annotations={"title": "Get Form Details", "readOnlyHint": True},
)
async def get_proforma_form_details(
    ctx: Context,
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
    form_id: Annotated[
        str,
        Field(
            description="ProForma form UUID (e.g., '1946b8b7-8f03-4dc0-ac2d-5fac0d960c6a')"
        ),
    ],
) -> str:
    """
    Get detailed information about a specific ProForma form.

    Uses the new Jira Forms REST API. Returns form details including ADF design structure.

    Args:
        ctx: The FastMCP context.
        issue_key: The issue key containing the form.
        form_id: The form UUID identifier.

    Returns:
        JSON string representing the ProForma form details, or an error object if failed.
    """
    jira = await get_jira_fetcher(ctx)
    try:
        form = jira.get_form_details(issue_key, form_id)
        if form is None:
            response_data = {
                "success": False,
                "error": f"Form {form_id} not found for issue {issue_key}",
                "issue_key": issue_key,
                "form_id": form_id,
            }
        else:
            response_data = {"success": True, "form": form.to_simplified_dict()}
    except Exception as e:
        error_message = ""
        log_level = logging.ERROR
        if isinstance(e, ValueError) and "not found" in str(e).lower():
            log_level = logging.WARNING
            error_message = str(e)
        elif isinstance(e, MCPAtlassianAuthenticationError):
            error_message = f"Authentication/Permission Error: {str(e)}"
        elif isinstance(e, OSError | HTTPError):
            error_message = f"Network or API Error: {str(e)}"
        else:
            error_message = (
                "An unexpected error occurred while fetching ProForma form details."
            )
            logger.exception(
                f"Unexpected error in get_proforma_form_details for '{issue_key}/{form_id}':"
            )
        error_result = {
            "success": False,
            "error": str(e),
            "issue_key": issue_key,
            "form_id": form_id,
        }
        logger.log(
            log_level,
            f"get_proforma_form_details failed for '{issue_key}/{form_id}': {error_message}",
        )
        response_data = error_result
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "write"},
    annotations={"title": "Update Form Answers", "destructiveHint": True},
)
@check_write_access
async def update_proforma_form_answers(
    ctx: Context,
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
    form_id: Annotated[
        str,
        Field(
            description="ProForma form UUID (e.g., '1946b8b7-8f03-4dc0-ac2d-5fac0d960c6a')"
        ),
    ],
    answers: Annotated[
        list[dict],
        Field(
            description="List of answer objects. Each answer must have: questionId (string), type (TEXT/NUMBER/SELECT/etc), value (any)"
        ),
    ],
) -> str:
    """
    Update form field answers using the Jira Forms REST API.

    This is the primary method for updating form data. Each answer object
    must specify the question ID, answer type, and value.

    **⚠️ KNOWN LIMITATION - DATETIME fields:**
    The Jira Forms API does NOT properly preserve time components in DATETIME fields.
    Only the date portion is stored; times are reset to midnight (00:00:00).

    **Workaround for DATETIME fields:**
    Use jira_update_issue to directly update the underlying custom fields instead:
    1. Get the custom field ID from the form details (question's "jiraField" property)
    2. Use jira_update_issue with fields like: {"customfield_XXXXX": "2026-01-09T11:50:00-08:00"}

    Example:
    ```python
    # Instead of updating via form (loses time):
    # jira_update_proforma_form_answers(issue_key, form_id, [{"questionId": "91", "type": "DATETIME", "value": "..."}])

    # Use direct field update (preserves time):
    jira_update_issue(issue_key, {"customfield_10542": "2026-01-09T11:50:00-08:00"})
    ```

    **Automatic DateTime Conversion:**
    For DATE and DATETIME fields, you can provide values as:
    - ISO 8601 strings (e.g., "2024-12-17T19:00:00Z", "2024-12-17")
    - Unix timestamps in milliseconds (e.g., 1734465600000)

    The tool automatically converts ISO 8601 strings to Unix timestamps.

    Example answers:
    [
        {"questionId": "q1", "type": "TEXT", "value": "Updated description"},
        {"questionId": "q2", "type": "SELECT", "value": "Product A"},
        {"questionId": "q3", "type": "NUMBER", "value": 42},
        {"questionId": "q4", "type": "DATE", "value": "2024-12-17"}
    ]

    Common answer types:
    - TEXT: String values
    - NUMBER: Numeric values
    - DATE: Date values (ISO 8601 string or Unix timestamp in ms)
    - DATETIME: DateTime values - ⚠️ USE WORKAROUND ABOVE
    - SELECT: Single selection from options
    - MULTI_SELECT: Multiple selections (value as list)
    - CHECKBOX: Boolean values

    Args:
        ctx: The FastMCP context.
        issue_key: The issue key containing the form.
        form_id: The form UUID (get from get_issue_proforma_forms).
        answers: List of answer objects with questionId, type, and value.

    Returns:
        JSON string with operation result.
    """
    jira = await get_jira_fetcher(ctx)
    try:
        # Convert datetime strings to Unix timestamps for DATE/DATETIME fields
        processed_answers = []
        for answer in answers:
            processed_answer = answer.copy()
            if "type" in answer and "value" in answer:
                processed_answer["value"] = convert_datetime_to_timestamp(
                    answer["value"], answer["type"]
                )
            processed_answers.append(processed_answer)

        result = jira.update_form_answers(issue_key, form_id, processed_answers)
        response_data = {
            "success": True,
            "message": f"Successfully updated form {form_id} for issue {issue_key}",
            "issue_key": issue_key,
            "form_id": form_id,
            "updated_fields": len(answers),
            "result": result,
        }
    except Exception as e:
        error_message = ""
        log_level = logging.ERROR
        if isinstance(e, ValueError) and "not found" in str(e).lower():
            log_level = logging.WARNING
            error_message = str(e)
        elif isinstance(e, MCPAtlassianAuthenticationError):
            error_message = f"Authentication/Permission Error: {str(e)}"
        elif isinstance(e, OSError | HTTPError):
            error_message = f"Network or API Error: {str(e)}"
        else:
            error_message = (
                "An unexpected error occurred while updating ProForma form answers."
            )
            logger.exception(
                f"Unexpected error in update_proforma_form_answers for '{issue_key}/{form_id}':"
            )
        error_result = {
            "success": False,
            "error": str(e),
            "issue_key": issue_key,
            "form_id": form_id,
        }
        logger.log(
            log_level,
            f"update_proforma_form_answers failed for '{issue_key}/{form_id}': {error_message}",
        )
        response_data = error_result
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read", "metrics"},
    annotations={"title": "Get Issue Dates", "readOnlyHint": True},
)
async def get_issue_dates(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    include_status_changes: Annotated[
        bool,
        Field(
            description="Include status change history with timestamps and durations"
        ),
    ] = True,
    include_status_summary: Annotated[
        bool,
        Field(description="Include aggregated time spent in each status"),
    ] = True,
) -> str:
    """
    Get date information and status transition history for a Jira issue.

    Returns dates (created, updated, due date, resolution date) and optionally
    status change history with time tracking for workflow analysis.

    Args:
        ctx: The FastMCP context.
        issue_key: The Jira issue key.
        include_status_changes: Whether to include status change history.
        include_status_summary: Whether to include aggregated time per status.

    Returns:
        JSON string with issue dates and optional status tracking data.
    """
    jira = await get_jira_fetcher(ctx)
    try:
        result = jira.get_issue_dates(
            issue_key=issue_key,
            include_created=True,
            include_updated=True,
            include_due_date=True,
            include_resolution_date=True,
            include_status_changes=include_status_changes,
            include_status_summary=include_status_summary,
        )
        return json.dumps(result.to_simplified_dict(), indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error getting issue dates for {issue_key}: {str(e)}")
        error_result = {"success": False, "error": str(e), "issue_key": issue_key}
        return json.dumps(error_result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read", "metrics", "sla"},
    annotations={"title": "Get Issue SLA", "readOnlyHint": True},
)
async def get_issue_sla(
    ctx: Context,
    issue_key: Annotated[
        str,
        Field(
            description="Jira issue key (e.g., 'PROJ-123', 'ACV2-642')",
            pattern=ISSUE_KEY_PATTERN,
        ),
    ],
    metrics: Annotated[
        str | None,
        Field(
            description=(
                "Comma-separated list of SLA metrics to calculate. "
                "Available: cycle_time, lead_time, time_in_status, due_date_compliance, "
                "resolution_time, first_response_time. "
                "Defaults to configured metrics or 'cycle_time,time_in_status'."
            )
        ),
    ] = None,
    working_hours_only: Annotated[
        bool | None,
        Field(
            description=(
                "Calculate using working hours only (excludes weekends/non-business hours). "
                "Defaults to value from JIRA_SLA_WORKING_HOURS_ONLY environment variable."
            )
        ),
    ] = None,
    include_raw_dates: Annotated[
        bool,
        Field(description="Include raw date values in the response"),
    ] = False,
) -> str:
    """
    Calculate SLA metrics for a Jira issue.

    Computes various time-based metrics including cycle time, lead time,
    time spent in each status, due date compliance, and more.

    Working hours can be configured via environment variables:
    - JIRA_SLA_WORKING_HOURS_ONLY: Enable working hours filtering (true/false)
    - JIRA_SLA_WORKING_HOURS_START: Start time (e.g., "09:00")
    - JIRA_SLA_WORKING_HOURS_END: End time (e.g., "17:00")
    - JIRA_SLA_WORKING_DAYS: Working days (e.g., "1,2,3,4,5" for Mon-Fri)
    - JIRA_SLA_TIMEZONE: Timezone for calculations (e.g., "America/New_York")

    Args:
        ctx: The FastMCP context.
        issue_key: The Jira issue key.
        metrics: Comma-separated list of metrics to calculate.
        working_hours_only: Use working hours only for calculations.
        include_raw_dates: Include raw date values in response.

    Returns:
        JSON string with calculated SLA metrics.
    """
    jira = await get_jira_fetcher(ctx)
    try:
        # Parse metrics from comma-separated string
        metrics_list = None
        if metrics:
            metrics_list = [m.strip() for m in metrics.split(",") if m.strip()]

        result = jira.get_issue_sla(
            issue_key=issue_key,
            metrics=metrics_list,
            working_hours_only=working_hours_only,
            include_raw_dates=include_raw_dates,
        )
        return json.dumps(result.to_simplified_dict(), indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error calculating SLA for {issue_key}: {str(e)}")
        error_result = {"success": False, "error": str(e), "issue_key": issue_key}
        return json.dumps(error_result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read", "development"},
    annotations={"title": "Get Issue Development Info", "readOnlyHint": True},
)
async def get_issue_development_info(
    ctx: Context,
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
    application_type: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Filter by application type. "
                "Examples: 'stash' (Bitbucket Server), 'bitbucket', 'github', 'gitlab'"
            )
        ),
    ] = None,
    data_type: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Filter by data type. "
                "Examples: 'pullrequest', 'branch', 'repository'"
            )
        ),
    ] = None,
) -> str:
    """
    Get development information (PRs, commits, branches) linked to a Jira issue.

    This retrieves the development panel information that shows linked
    pull requests, branches, and commits from connected source control systems
    like Bitbucket, GitHub, or GitLab.

    Args:
        ctx: The FastMCP context.
        issue_key: The Jira issue key.
        application_type: Optional filter by source control type.
        data_type: Optional filter by data type (pullrequest, branch, etc.).

    Returns:
        JSON string with development information including:
        - pullRequests: List of linked pull requests with status, author, reviewers
        - branches: List of linked branches
        - commits: List of linked commits
        - repositories: List of repositories involved
    """
    jira = await get_jira_fetcher(ctx)
    try:
        result = jira.get_issue_development_info(
            issue_key=issue_key,
            application_type=application_type,
            data_type=data_type,
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error getting development info for {issue_key}: {str(e)}")
        error_result = {"success": False, "error": str(e), "issue_key": issue_key}
        return json.dumps(error_result, indent=2, ensure_ascii=False)


@jira_mcp.tool(
    tags={"jira", "read", "development"},
    annotations={"title": "Get Issues Development Info", "readOnlyHint": True},
)
async def get_issues_development_info(
    ctx: Context,
    issue_keys: Annotated[
        str,
        Field(
            description="Comma-separated list of Jira issue keys (e.g., 'PROJ-123,PROJ-456')"
        ),
    ],
    application_type: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Filter by application type. "
                "Examples: 'stash' (Bitbucket Server), 'bitbucket', 'github', 'gitlab'"
            )
        ),
    ] = None,
    data_type: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Filter by data type. "
                "Examples: 'pullrequest', 'branch', 'repository'"
            )
        ),
    ] = None,
) -> str:
    """
    Get development information for multiple Jira issues.

    Batch retrieves development panel information (PRs, commits, branches)
    for multiple issues at once.

    Args:
        ctx: The FastMCP context.
        issue_keys: List of Jira issue keys.
        application_type: Optional filter by source control type.
        data_type: Optional filter by data type.

    Returns:
        JSON string with list of development information for each issue.
    """
    jira = await get_jira_fetcher(ctx)
    # Parse CSV string into list
    keys_list = [k.strip() for k in issue_keys.split(",") if k.strip()]
    try:
        results = jira.get_issues_development_info(
            issue_keys=keys_list,
            application_type=application_type,
            data_type=data_type,
        )
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error getting development info for issues: {str(e)}")
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, indent=2, ensure_ascii=False)
