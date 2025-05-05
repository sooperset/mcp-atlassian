"""Jira FastMCP server instance and tool definitions."""

import json
import logging
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from mcp_atlassian.jira.constants import DEFAULT_READ_JIRA_FIELDS

from .context import MainAppContext

logger = logging.getLogger(__name__)

jira_mcp = FastMCP(
    name="Jira MCP Service",
    description="Provides tools for interacting with Atlassian Jira.",
)


@jira_mcp.tool(tags={"jira", "read"})
async def get_issue(
    ctx: Context[Any, MainAppContext],
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
    fields: Annotated[
        str | None,
        Field(
            description=(
                "Fields to return. Can be a comma-separated list (e.g., 'summary,status,customfield_10010'), "
                "'*all' for all fields (including custom fields), or omitted for essential fields only."
            ),
            default=",".join(DEFAULT_READ_JIRA_FIELDS),
        ),
    ] = ",".join(DEFAULT_READ_JIRA_FIELDS),
    expand: Annotated[
        str | None,
        Field(
            description=(
                "Optional fields to expand. Examples: 'renderedFields' (for rendered content), "
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
            description="A comma-separated list of issue properties to return",
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
        fields: Fields to return.
        expand: Optional fields to expand.
        comment_limit: Maximum number of comments.
        properties: Issue properties to return.
        update_history: Whether to update issue view history.

    Returns:
        JSON string representing the Jira issue object.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

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


@jira_mcp.tool(tags={"jira", "read"})
async def search(
    ctx: Context[Any, MainAppContext],
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
        str | None,
        Field(
            description=(
                "Comma-separated fields to return in the results. "
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
                "Comma-separated list of project keys to filter results by. "
                "Overrides the environment variable JIRA_PROJECTS_FILTER if provided."
            ),
        ),
    ] = None,
    expand: Annotated[
        str | None,
        Field(
            description=(
                "Optional fields to expand. Examples: 'renderedFields', 'transitions', 'changelog'"
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

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


@jira_mcp.tool(tags={"jira", "read"})
async def search_fields(
    ctx: Context[Any, MainAppContext],
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    result = jira.search_fields(keyword, limit=limit, refresh=refresh)
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "read"})
async def get_project_issues(
    ctx: Context[Any, MainAppContext],
    project_key: Annotated[str, Field(description="The project key")],
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    search_result = jira.get_project_issues(
        project_key=project_key, start=start_at, limit=limit
    )
    result = search_result.to_simplified_dict()
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "read"})
async def get_transitions(
    ctx: Context[Any, MainAppContext],
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
) -> str:
    """Get available status transitions for a Jira issue.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.

    Returns:
        JSON string representing a list of available transitions.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    # Underlying method returns list[dict] in the desired format
    transitions = jira.get_available_transitions(issue_key)
    return json.dumps(transitions, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "read"})
async def get_worklog(
    ctx: Context[Any, MainAppContext],
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
) -> str:
    """Get worklog entries for a Jira issue.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.

    Returns:
        JSON string representing the worklog entries.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    worklogs = jira.get_worklogs(issue_key)
    result = {"worklogs": worklogs}
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "read"})
async def download_attachments(
    ctx: Context[Any, MainAppContext],
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
    target_dir: Annotated[
        str, Field(description="Directory where attachments should be saved")
    ],
) -> str:
    """Download attachments from a Jira issue.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.
        target_dir: Directory to save attachments.

    Returns:
        JSON string indicating the result of the download operation.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    result = jira.download_issue_attachments(issue_key=issue_key, target_dir=target_dir)
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "read"})
async def get_agile_boards(
    ctx: Context[Any, MainAppContext],
    board_name: Annotated[
        str | None, Field(description="The name of board, support fuzzy search")
    ] = None,
    project_key: Annotated[
        str | None, Field(description="Jira project key (e.g., 'PROJ-123')")
    ] = None,
    board_type: Annotated[
        str | None,
        Field(description="The type of jira board (e.g., 'scrum', 'kanban')"),
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    boards = jira.get_all_agile_boards_model(
        board_name=board_name,
        project_key=project_key,
        board_type=board_type,
        start=start_at,
        limit=limit,
    )
    result = [board.to_simplified_dict() for board in boards]
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "read"})
async def get_board_issues(
    ctx: Context[Any, MainAppContext],
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
        str | None,
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
        str | None,
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

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


@jira_mcp.tool(tags={"jira", "read"})
async def get_sprints_from_board(
    ctx: Context[Any, MainAppContext],
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    sprints = jira.get_all_sprints_from_board_model(
        board_id=board_id, state=state, start=start_at, limit=limit
    )
    result = [sprint.to_simplified_dict() for sprint in sprints]
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "read"})
async def get_sprint_issues(
    ctx: Context[Any, MainAppContext],
    sprint_id: Annotated[str, Field(description="The id of sprint (e.g., '10001')")],
    fields: Annotated[
        str | None,
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    fields_list: str | list[str] | None = fields
    if fields and fields != "*all":
        fields_list = [f.strip() for f in fields.split(",")]

    search_result = jira.get_sprint_issues(
        sprint_id=sprint_id, fields=fields_list, start=start_at, limit=limit
    )
    result = search_result.to_simplified_dict()
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "read"})
async def get_link_types(ctx: Context[Any, MainAppContext]) -> str:
    """Get all available issue link types.

    Args:
        ctx: The FastMCP context.

    Returns:
        JSON string representing a list of issue link type objects.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    link_types = jira.get_issue_link_types()
    formatted_link_types = [link_type.to_simplified_dict() for link_type in link_types]
    return json.dumps(formatted_link_types, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "write"})
async def create_issue(
    ctx: Context[Any, MainAppContext],
    project_key: Annotated[
        str,
        Field(
            description=(
                "The JIRA project key (e.g. 'PROJ', 'DEV', 'SUPPORT'). "
                "This is the prefix of issue keys in your project. "
                "Never assume what it might be, always ask the user."
            )
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
            )
        ),
    ],
    assignee: Annotated[
        str | None,
        Field(
            description="Assignee of the ticket (accountID, full name or e-mail)",
            default=None,
        ),
    ] = None,
    description: Annotated[
        str, Field(description="Issue description", default="")
    ] = "",
    components: Annotated[
        str | None,
        Field(
            description="Comma-separated list of component names to assign (e.g., 'Frontend,API')",
            default=None,
        ),
    ] = None,
    additional_fields: Annotated[
        dict[str, Any] | None,
        Field(
            description=(
                "Optional dictionary of additional fields to set. Examples:\n"
                "- Set priority: {'priority': {'name': 'High'}}\n"
                "- Add labels: {'labels': ['frontend', 'urgent']}\n"
                "- Link to parent (for any issue type): {'parent': 'PROJ-123'}\n"
                "- Set Fix Version/s: {'fixVersions': [{'id': '10020'}]}\n"
                "- Custom fields: {'customfield_10010': 'value'}"
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
        assignee: Assignee of the ticket (accountID, full name or e-mail).
        description: Issue description.
        components: Comma-separated list of component names.
        additional_fields: Dictionary of additional fields.

    Returns:
        JSON string representing the created issue object.

    Raises:
        ValueError: If in read-only mode or Jira client is unavailable.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call create_issue in read-only mode.")
        raise ValueError("Cannot create issue in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    # Parse components from comma-separated string to list
    components_list = None
    if components and isinstance(components, str):
        components_list = [
            comp.strip() for comp in components.split(",") if comp.strip()
        ]

    # Use additional_fields directly as dict
    extra_fields = additional_fields or {}
    if not isinstance(extra_fields, dict):
        raise ValueError("additional_fields must be a dictionary.")

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


@jira_mcp.tool(tags={"jira", "write"})
async def batch_create_issues(
    ctx: Context[Any, MainAppContext],
    issues: Annotated[
        str,
        Field(
            description=(
                "JSON array of issue objects. Each object should contain:\n"
                "- project_key (required): The project key (e.g., 'PROJ')\n"
                "- summary (required): Issue summary/title\n"
                "- issue_type (required): Type of issue (e.g., 'Task', 'Bug')\n"
                "- description (optional): Issue description\n"
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call batch_create_issues in read-only mode.")
        raise ValueError("Cannot create issues in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

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


@jira_mcp.tool(tags={"jira", "read"})
async def batch_get_changelogs(
    ctx: Context[Any, MainAppContext],
    issue_ids_or_keys: Annotated[
        list[str],
        Field(
            description="List of Jira issue IDs or keys, e.g. ['PROJ-123', 'PROJ-124']"
        ),
    ],
    fields: Annotated[
        list[str] | None,
        Field(
            description="Filter the changelogs by fields, e.g. ['status', 'assignee']. Default to [] for all fields.",
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    # Ensure this runs only on Cloud, as per original function docstring
    if not jira.config.is_cloud:
        raise NotImplementedError(
            "Batch get issue changelogs is only available on Jira Cloud."
        )

    # Call the underlying method
    issues_with_changelogs = jira.batch_get_changelogs(
        issue_ids_or_keys=issue_ids_or_keys, fields=fields
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


@jira_mcp.tool(tags={"jira", "write"})
async def update_issue(
    ctx: Context[Any, MainAppContext],
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
    fields: Annotated[
        dict[str, Any],
        Field(
            description=(
                "A valid dictionary of fields to update. "
                "Example: {'summary': 'New title', 'description': 'Updated description', "
                "'priority': {'name': 'High'}, 'assignee': 'john.doe'}"
            )
        ),
    ],
    additional_fields: Annotated[
        dict[str, Any] | None,
        Field(
            description="Optional dictionary of additional fields to update. Use this for custom fields or more complex updates.",
            default=None,
        ),
    ] = None,
    attachments: Annotated[
        str | None,
        Field(
            description=(
                "Optional JSON string array or comma-separated list of file paths to attach to the issue. "
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
        fields: Dictionary of fields to update.
        additional_fields: Optional dictionary of additional fields.
        attachments: Optional JSON array string or comma-separated list of file paths.

    Returns:
        JSON string representing the updated issue object and attachment results.

    Raises:
        ValueError: If in read-only mode, Jira client unavailable, or invalid input.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call update_issue in read-only mode.")
        raise ValueError("Cannot update issue in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    # Use fields directly as dict
    if not isinstance(fields, dict):
        raise ValueError("fields must be a dictionary.")
    update_fields = fields

    # Use additional_fields directly as dict
    extra_fields = additional_fields or {}
    if not isinstance(extra_fields, dict):
        raise ValueError("additional_fields must be a dictionary.")

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


@jira_mcp.tool(tags={"jira", "write"})
async def delete_issue(
    ctx: Context[Any, MainAppContext],
    issue_key: Annotated[str, Field(description="Jira issue key (e.g. PROJ-123)")],
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call delete_issue in read-only mode.")
        raise ValueError("Cannot delete issue in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    deleted = jira.delete_issue(issue_key)
    result = {"message": f"Issue {issue_key} has been deleted successfully."}
    # The underlying method raises on failure, so if we reach here, it's success.
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "write"})
async def add_comment(
    ctx: Context[Any, MainAppContext],
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
    comment: Annotated[str, Field(description="Comment text in Markdown format")],
) -> str:
    """Add a comment to a Jira issue.

    Args:
        ctx: The FastMCP context.
        issue_key: Jira issue key.
        comment: Comment text in Markdown.

    Returns:
        JSON string representing the added comment object.

    Raises:
        ValueError: If in read-only mode or Jira client unavailable.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call add_comment in read-only mode.")
        raise ValueError("Cannot add comment in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    # add_comment returns dict
    result = jira.add_comment(issue_key, comment)
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "write"})
async def add_worklog(
    ctx: Context[Any, MainAppContext],
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
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
        Field(description="Optional comment for the worklog in Markdown format"),
    ] = None,
    started: Annotated[
        str | None,
        Field(
            description=(
                "Optional start time in ISO format. If not provided, the current time will be used. "
                "Example: '2023-08-01T12:00:00.000+0000'"
            )
        ),
    ] = None,
    # Add original_estimate and remaining_estimate as per original tool
    original_estimate: Annotated[
        str | None, Field(description="Optional new value for the original estimate")
    ] = None,
    remaining_estimate: Annotated[
        str | None, Field(description="Optional new value for the remaining estimate")
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call add_worklog in read-only mode.")
        raise ValueError("Cannot add worklog in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

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


@jira_mcp.tool(tags={"jira", "write"})
async def link_to_epic(
    ctx: Context[Any, MainAppContext],
    issue_key: Annotated[
        str, Field(description="The key of the issue to link (e.g., 'PROJ-123')")
    ],
    epic_key: Annotated[
        str, Field(description="The key of the epic to link to (e.g., 'PROJ-456')")
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call link_to_epic in read-only mode.")
        raise ValueError("Cannot link issue to epic in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    issue = jira.link_issue_to_epic(issue_key, epic_key)
    result = {
        "message": f"Issue {issue_key} has been linked to epic {epic_key}.",
        "issue": issue.to_simplified_dict(),
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "write"})
async def create_issue_link(
    ctx: Context[Any, MainAppContext],
    link_type: Annotated[
        str,
        Field(
            description="The type of link to create (e.g., 'Duplicate', 'Blocks', 'Relates to')"
        ),
    ],
    inward_issue_key: Annotated[
        str, Field(description="The key of the inward issue (e.g., 'PROJ-123')")
    ],
    outward_issue_key: Annotated[
        str, Field(description="The key of the outward issue (e.g., 'PROJ-456')")
    ],
    comment: Annotated[
        str | None, Field(description="Optional comment to add to the link")
    ] = None,
    comment_visibility: Annotated[
        dict[str, str] | None,
        Field(
            description="Optional visibility settings for the comment (e.g., {'type': 'group', 'value': 'jira-users'})",
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
        comment_visibility: Optional dictionary for comment visibility.

    Returns:
        JSON string indicating success or failure.

    Raises:
        ValueError: If required fields are missing, invalid input, in read-only mode, or Jira client unavailable.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call create_issue_link in read-only mode.")
        raise ValueError("Cannot create issue link in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    if not all([link_type, inward_issue_key, outward_issue_key]):
        raise ValueError(
            "link_type, inward_issue_key, and outward_issue_key are required."
        )

    link_data = {
        "type": {"name": link_type},
        "inwardIssue": {"key": inward_issue_key},
        "outwardIssue": {"key": outward_issue_key},
    }

    if comment:
        comment_obj = {"body": comment}
        if comment_visibility and isinstance(comment_visibility, dict):
            if "type" in comment_visibility and "value" in comment_visibility:
                comment_obj["visibility"] = comment_visibility
            else:
                logger.warning("Invalid comment_visibility dictionary structure.")
        link_data["comment"] = comment_obj

    result = jira.create_issue_link(link_data)
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "write"})
async def remove_issue_link(
    ctx: Context[Any, MainAppContext],
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call remove_issue_link in read-only mode.")
        raise ValueError("Cannot remove issue link in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    if not link_id:
        raise ValueError("link_id is required")

    result = jira.remove_issue_link(link_id)  # Returns dict on success
    return json.dumps(result, indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "write"})
async def transition_issue(
    ctx: Context[Any, MainAppContext],
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
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
        dict[str, Any] | None,
        Field(
            description=(
                "Optional dictionary of fields to update during the transition. "
                "Some transitions require specific fields to be set (e.g., resolution). "
                "Example: {'resolution': {'name': 'Fixed'}}"
            ),
            default=None,
        ),
    ] = None,
    comment: Annotated[
        str | None,
        Field(
            description=(
                "Comment to add during the transition (optional). "
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
        fields: Optional dictionary of fields to update during transition.
        comment: Optional comment for the transition.

    Returns:
        JSON string representing the updated issue object.

    Raises:
        ValueError: If required fields missing, invalid input, in read-only mode, or Jira client unavailable.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call transition_issue in read-only mode.")
        raise ValueError("Cannot transition issue in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    if not issue_key or not transition_id:
        raise ValueError("issue_key and transition_id are required.")

    # Use fields directly as dict
    update_fields = fields or {}
    if not isinstance(update_fields, dict):
        raise ValueError("fields must be a dictionary.")

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


@jira_mcp.tool(tags={"jira", "write"})
async def create_sprint(
    ctx: Context[Any, MainAppContext],
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
    goal: Annotated[str | None, Field(description="Goal of the sprint")] = None,
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call create_sprint in read-only mode.")
        raise ValueError("Cannot create sprint in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

    sprint = jira.create_sprint(
        board_id=board_id,
        sprint_name=sprint_name,
        start_date=start_date,
        end_date=end_date,
        goal=goal,
    )
    return json.dumps(sprint.to_simplified_dict(), indent=2, ensure_ascii=False)


@jira_mcp.tool(tags={"jira", "write"})
async def update_sprint(
    ctx: Context[Any, MainAppContext],
    sprint_id: Annotated[str, Field(description="The id of sprint (e.g., '10001')")],
    sprint_name: Annotated[
        str | None, Field(description="Optional: New name for the sprint")
    ] = None,
    state: Annotated[
        str | None,
        Field(description="Optional: New state for the sprint (future|active|closed)"),
    ] = None,
    start_date: Annotated[
        str | None, Field(description="Optional: New start date for the sprint")
    ] = None,
    end_date: Annotated[
        str | None, Field(description="Optional: New end date for the sprint")
    ] = None,
    goal: Annotated[
        str | None, Field(description="Optional: New goal for the sprint")
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
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call update_sprint in read-only mode.")
        raise ValueError("Cannot update sprint in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.jira:
        raise ValueError("Jira client is not configured or available.")
    jira = lifespan_ctx.jira

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
