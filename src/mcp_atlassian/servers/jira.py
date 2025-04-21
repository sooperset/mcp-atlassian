"""Jira server implementation."""

import json
import logging
import os
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import (
    Annotated,
    Any,
)

from fastmcp import Context, FastMCP
from mcp.types import TextContent
from pydantic import BeforeValidator, Field

from ..jira import JiraFetcher
from ..jira.config import JiraConfig
from ..utils.io import is_read_only_mode
from ..utils.logging import log_config_param
from ..utils.urls import is_atlassian_cloud_url
from ..utils.validation import ensure_json_string

logger = logging.getLogger("mcp-atlassian")


@asynccontextmanager
async def jira_lifespan(app: FastMCP) -> AsyncGenerator[dict[str, Any], None]:
    """Lifespan manager for the Jira FastMCP server.

    Creates and manages the JiraFetcher instance.
    """
    logger.info("Initializing Jira FastMCP server...")

    # Check read-only mode
    read_only = is_read_only_mode()
    logger.info(f"Read-only mode: {'ENABLED' if read_only else 'DISABLED'}")

    # Determine if Jira is configured
    jira_url = os.getenv("JIRA_URL")
    jira_is_setup = False

    if jira_url:
        is_cloud = is_atlassian_cloud_url(jira_url)

        if is_cloud:
            jira_is_setup = all(
                [jira_url, os.getenv("JIRA_USERNAME"), os.getenv("JIRA_API_TOKEN")]
            )
            logger.info("Using Jira Cloud authentication method")
        else:
            jira_is_setup = all([jira_url, os.getenv("JIRA_PERSONAL_TOKEN")])
            logger.info("Using Jira Server/Data Center authentication method")

    jira_fetcher = None

    if jira_is_setup:
        try:
            jira_config = JiraConfig.from_env()
            log_config_param(logger, "Jira", "URL", jira_config.url)
            log_config_param(logger, "Jira", "Auth Type", jira_config.auth_type)

            if jira_config.auth_type == "basic":
                log_config_param(logger, "Jira", "Username", jira_config.username)
                log_config_param(
                    logger, "Jira", "API Token", jira_config.api_token, sensitive=True
                )
            else:
                log_config_param(
                    logger,
                    "Jira",
                    "Personal Token",
                    jira_config.personal_token,
                    sensitive=True,
                )

            log_config_param(logger, "Jira", "SSL Verify", str(jira_config.ssl_verify))
            log_config_param(
                logger, "Jira", "Projects Filter", jira_config.projects_filter
            )

            jira_fetcher = JiraFetcher(config=jira_config)
            logger.info("Jira client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Jira client: {e}", exc_info=True)

    try:
        yield {"jira_fetcher": jira_fetcher, "read_only": read_only}
    finally:
        logger.info("Shutting down Jira FastMCP server...")


# Create the Jira FastMCP instance
jira_mcp = FastMCP(
    "Jira",
    description="Tools for interacting with Jira",
    lifespan=jira_lifespan,
)


# Tool implementations
@jira_mcp.tool()
async def get_issue(
    ctx: Context,
    issue_key: str,
    fields: Annotated[
        str,
        Field(
            description="Fields to return. Can be a comma-separated list (e.g., 'summary,status,customfield_10010'), '*all' for all fields (including custom fields), or omitted for essential fields only",
            default="summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
        ),
    ] = "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
    expand: Annotated[
        str | None,
        Field(
            description="Optional fields to expand. Examples: 'renderedFields' (for rendered content), 'transitions' (for available status transitions), 'changelog' (for history)",
        ),
    ] = None,
    comment_limit: Annotated[
        int,
        Field(
            description="Maximum number of comments to include (0 or null for no comments)",
            ge=0,
            le=100,
        ),
    ] = 10,
    properties: Annotated[
        str | None,
        Field(
            description="A comma-separated list of issue properties to return",
        ),
    ] = None,
    update_history: Annotated[
        bool,
        Field(
            description="Whether to update the issue view history for the requesting user",
        ),
    ] = True,
) -> Sequence[TextContent]:
    """Get details of a specific Jira issue including its Epic links and relationship information"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Get issue details
    issue = fetcher.get_issue(
        issue_key=issue_key,
        fields=fields,
        expand=expand,
        comment_limit=comment_limit,
        properties=properties,
        update_history=update_history,
    )

    # Get comments if requested
    if comment_limit > 0:
        comments = fetcher.get_issue_comments(issue_key, limit=comment_limit)
        issue.comments = comments

    # Return issue as JSON
    issue_data = issue.to_simplified_dict()

    return [
        TextContent(
            type="text", text=json.dumps(issue_data, indent=2, ensure_ascii=False)
        )
    ]


@jira_mcp.tool()
async def search(
    ctx: Context,
    jql: str,
    fields: Annotated[
        str,
        Field(
            description="Comma-separated fields to return in the results. Use '*all' for all fields, or specify individual fields like 'summary,status,assignee,priority'",
            default="summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
        ),
    ] = "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
    limit: Annotated[
        int,
        Field(
            description="Maximum number of results (1-50)",
            ge=1,
            le=50,
        ),
    ] = 10,
    start_at: Annotated[
        int,
        Field(
            description="Starting index for pagination (0-based)",
            ge=0,
        ),
    ] = 0,
    projects_filter: Annotated[
        str | None,
        Field(
            description="Comma-separated list of project keys to filter results by. Overrides the environment variable JIRA_PROJECTS_FILTER if provided.",
        ),
    ] = None,
) -> Sequence[TextContent]:
    """Search Jira issues using JQL (Jira Query Language)"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Search issues
    issues = fetcher.search_issues(
        jql=jql,
        fields=fields,
        start_at=start_at,
        limit=limit,
        projects_filter=projects_filter,
    )

    # Format results
    search_results = [issue.to_simplified_dict() for issue in issues]

    return [
        TextContent(
            type="text", text=json.dumps(search_results, indent=2, ensure_ascii=False)
        )
    ]


@jira_mcp.tool()
async def get_project_issues(
    ctx: Context,
    project_key: str,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of results (1-50)",
            ge=1,
            le=50,
        ),
    ] = 10,
    start_at: Annotated[
        int,
        Field(
            description="Starting index for pagination (0-based)",
            ge=0,
        ),
    ] = 0,
) -> Sequence[TextContent]:
    """Get all issues for a specific Jira project"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Get project issues
    issues = fetcher.get_project_issues(
        project_key=project_key,
        start_at=start_at,
        limit=limit,
    )

    # Format results
    issues_data = [issue.to_simplified_dict() for issue in issues]

    return [
        TextContent(
            type="text", text=json.dumps(issues_data, indent=2, ensure_ascii=False)
        )
    ]


@jira_mcp.tool()
async def get_epic_issues(
    ctx: Context,
    epic_key: str,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of issues to return (1-50)",
            ge=1,
            le=50,
        ),
    ] = 10,
    start_at: Annotated[
        int,
        Field(
            description="Starting index for pagination (0-based)",
            ge=0,
        ),
    ] = 0,
) -> Sequence[TextContent]:
    """Get all issues linked to a specific epic"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    try:
        # Get issues linked to the epic
        issues = fetcher.get_epic_issues(epic_key=epic_key, start=start_at, limit=limit)

        # Format the response
        response = {
            "total": len(issues),
            "start_at": start_at,
            "max_results": limit,
            "issues": [issue.to_simplified_dict() for issue in issues],
        }

        return [
            TextContent(
                type="text", text=json.dumps(response, indent=2, ensure_ascii=False)
            )
        ]
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error retrieving epic issues: {str(e)}",
            )
        ]


@jira_mcp.tool()
async def get_transitions(
    ctx: Context,
    issue_key: str,
) -> Sequence[TextContent]:
    """Get available status transitions for a Jira issue"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Get transitions
    transitions = fetcher.get_transitions(issue_key=issue_key)

    return [
        TextContent(
            type="text", text=json.dumps(transitions, indent=2, ensure_ascii=False)
        )
    ]


@jira_mcp.tool()
async def get_worklog(
    ctx: Context,
    issue_key: str,
) -> Sequence[TextContent]:
    """Get worklog entries for a Jira issue"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Get worklog
    worklog = fetcher.get_worklog(issue_key=issue_key)

    return [
        TextContent(type="text", text=json.dumps(worklog, indent=2, ensure_ascii=False))
    ]


@jira_mcp.tool()
async def download_attachments(
    ctx: Context,
    issue_key: str,
    target_dir: str,
) -> Sequence[TextContent]:
    """Download attachments from a Jira issue"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check read-only mode for safety
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only:
        raise ValueError("Cannot download attachments in read-only mode")

    # Download attachments
    result = fetcher.download_attachments(
        issue_key=issue_key,
        target_dir=target_dir,
    )

    # Format results
    return [
        TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
    ]


@jira_mcp.tool()
async def get_agile_boards(
    ctx: Context,
    board_name: Annotated[
        str | None,
        Field(
            description="The name of board, support fuzzy search",
        ),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(
            description="Jira project key (e.g., 'PROJ-123')",
        ),
    ] = None,
    board_type: Annotated[
        str | None,
        Field(
            description="The type of jira board (e.g., 'scrum', 'kanban')",
        ),
    ] = None,
    start_at: Annotated[
        int,
        Field(
            description="Starting index for pagination (0-based)",
            ge=0,
        ),
    ] = 0,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of results (1-50)",
            ge=1,
            le=50,
        ),
    ] = 10,
) -> Sequence[TextContent]:
    """Get jira agile boards by name, project key, or type"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Get boards
    boards = fetcher.get_boards(
        board_name=board_name,
        project_key=project_key,
        board_type=board_type,
        start_at=start_at,
        limit=limit,
    )

    # Format results
    return [
        TextContent(type="text", text=json.dumps(boards, indent=2, ensure_ascii=False))
    ]


@jira_mcp.tool()
async def get_board_issues(
    ctx: Context,
    board_id: str,
    jql: str,
    fields: Annotated[
        str,
        Field(
            description="Comma-separated fields to return in the results. Use '*all' for all fields, or specify individual fields like 'summary,status,assignee,priority'",
            default="*all",
        ),
    ] = "*all",
    start_at: Annotated[
        int,
        Field(
            description="Starting index for pagination (0-based)",
            ge=0,
        ),
    ] = 0,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of results (1-50)",
            ge=1,
            le=50,
        ),
    ] = 10,
    expand: Annotated[
        str,
        Field(
            description="Fields to expand in the response (e.g., 'version', 'body.storage')",
            default="version",
        ),
    ] = "version",
) -> Sequence[TextContent]:
    """Get all issues linked to a specific board"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Get board issues
    issues = fetcher.get_board_issues(
        board_id=board_id,
        jql=jql,
        fields=fields,
        start_at=start_at,
        limit=limit,
        expand=expand,
    )

    # Format results
    return [
        TextContent(type="text", text=json.dumps(issues, indent=2, ensure_ascii=False))
    ]


@jira_mcp.tool()
async def get_sprints_from_board(
    ctx: Context,
    board_id: str,
    state: Annotated[
        str | None,
        Field(
            description="Sprint state (e.g., 'active', 'future', 'closed')",
        ),
    ] = None,
    start_at: Annotated[
        int,
        Field(
            description="Starting index for pagination (0-based)",
            ge=0,
        ),
    ] = 0,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of results (1-50)",
            ge=1,
            le=50,
        ),
    ] = 10,
) -> Sequence[TextContent]:
    """Get jira sprints from board by state"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Get board sprints
    sprints = fetcher.get_sprints(
        board_id=board_id,
        state=state,
        start_at=start_at,
        limit=limit,
    )

    # Format results
    return [
        TextContent(type="text", text=json.dumps(sprints, indent=2, ensure_ascii=False))
    ]


@jira_mcp.tool()
async def get_sprint_issues(
    ctx: Context,
    sprint_id: str,
    fields: Annotated[
        str,
        Field(
            description="Comma-separated fields to return in the results. Use '*all' for all fields, or specify individual fields like 'summary,status,assignee,priority'",
            default="*all",
        ),
    ] = "*all",
    start_at: Annotated[
        int,
        Field(
            description="Starting index for pagination (0-based)",
            ge=0,
        ),
    ] = 0,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of results (1-50)",
            ge=1,
            le=50,
        ),
    ] = 10,
) -> Sequence[TextContent]:
    """Get jira issues from sprint"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Get sprint issues
    issues = fetcher.get_sprint_issues(
        sprint_id=sprint_id,
        fields=fields,
        start_at=start_at,
        limit=limit,
    )

    # Format results
    issues_data = [issue.to_simplified_dict() for issue in issues]

    return [
        TextContent(
            type="text", text=json.dumps(issues_data, indent=2, ensure_ascii=False)
        )
    ]


@jira_mcp.tool()
async def update_sprint(
    ctx: Context,
    sprint_id: str,
    sprint_name: Annotated[
        str | None,
        Field(
            description="Optional: New name for the sprint",
        ),
    ] = None,
    state: Annotated[
        str | None,
        Field(
            description="Optional: New state for the sprint (future|active|closed)",
        ),
    ] = None,
    start_date: Annotated[
        str | None,
        Field(
            description="Optional: New start date for the sprint",
        ),
    ] = None,
    end_date: Annotated[
        str | None,
        Field(
            description="Optional: New end date for the sprint",
        ),
    ] = None,
    goal: Annotated[
        str | None,
        Field(
            description="Optional: New goal for the sprint",
        ),
    ] = None,
) -> Sequence[TextContent]:
    """Update jira sprint"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check read-only mode
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only:
        raise ValueError("Cannot update sprint in read-only mode")

    # Update sprint
    result = fetcher.update_sprint(
        sprint_id=sprint_id,
        name=sprint_name,
        state=state,
        start_date=start_date,
        end_date=end_date,
        goal=goal,
    )

    # Format results
    return [
        TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
    ]


@jira_mcp.tool()
async def create_issue(
    ctx: Context,
    project_key: str,
    summary: str,
    issue_type: str,
    description: Annotated[
        str,
        Field(
            description="Issue description",
            default="",
        ),
    ] = "",
    assignee: Annotated[
        str | None,
        Field(
            description="Assignee of the ticket (accountID, full name or e-mail)",
        ),
    ] = None,
    components: Annotated[
        str | None,
        Field(
            description="Comma-separated list of component names to assign (e.g., 'Frontend,API')",
            default=None,
        ),
    ] = None,
    additional_fields: Annotated[
        str,
        Field(
            description=(
                "Optional JSON string of additional fields to set. "
                "Examples:\n"
                '- Set priority: {"priority": {"name": "High"}}\n'
                '- Add labels: {"labels": ["frontend", "urgent"]}\n'
                '- Link to parent (for any issue type): {"parent": "PROJ-123"}\n'
                '- Set Fix Version/s: {"fixVersions": [{"id": "10020"}]}\n'
                '- Custom fields: {"customfield_10010": "value"}'
            ),
            default="{}",
        ),
    ] = "{}",
) -> Sequence[TextContent]:
    """Create a new Jira issue with optional Epic link or parent for subtasks"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check read-only mode
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only:
        raise ValueError("Cannot create issue in read-only mode")

    # Create issue
    issue = fetcher.create_issue(
        project_key=project_key,
        summary=summary,
        issue_type=issue_type,
        description=description,
        assignee=assignee,
        components=components,
        additional_fields=additional_fields,
    )

    # Format results
    return [
        TextContent(
            type="text",
            text=json.dumps(
                issue.to_simplified_dict() if issue else {},
                indent=2,
                ensure_ascii=False,
            ),
        )
    ]


@jira_mcp.tool()
async def batch_create_issues(
    ctx: Context,
    issues: Annotated[
        str,
        BeforeValidator(ensure_json_string),
        Field(
            description="JSON array of issue objects. Each object should contain:\n"
            "- project_key (required): The project key (e.g., 'PROJ')\n"
            "- summary (required): Issue summary/title\n"
            "- issue_type (required): Type of issue (e.g., 'Task', 'Bug')\n"
            "- description (optional): Issue description\n"
            "- assignee (optional): Assignee username or email\n"
            "- components (optional): Array of component names\n"
            "Example: [\n"
            '  {"project_key": "PROJ", "summary": "Issue 1", "issue_type": "Task"},\n'
            '  {"project_key": "PROJ", "summary": "Issue 2", "issue_type": "Bug", "components": ["Frontend"]}\n'
            "]",
        ),
    ],
    validate_only: Annotated[
        bool,
        Field(
            description="If true, only validates the issues without creating them",
            default=False,
        ),
    ] = False,
) -> Sequence[TextContent]:
    """Create multiple Jira issues in a batch"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check if read-only mode is enabled
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only and not validate_only:
        return [
            TextContent(
                type="text",
                text="Error: Cannot create issues in read-only mode. The system is currently set to read-only.",
            )
        ]

    # Parse the issues JSON
    try:
        # Now, 'issues' should reliably be a string here due to the validator
        issues_data = json.loads(issues)
        if not isinstance(issues_data, list):
            # If parsing didn't result in a list, it's an invalid format
            raise ValueError("Parsed JSON is not a list of issue objects.")
    except json.JSONDecodeError:
        return [
            TextContent(
                type="text",
                text="Invalid JSON format for issues. Please provide a valid JSON array of issue objects.",
            )
        ]
    except (
        ValueError
    ) as e:  # Catch potential error from ensure_json_string or non-list JSON
        return [
            TextContent(
                type="text",
                text=f"Invalid input for issues: {e}",
            )
        ]

    try:
        # Create the issues
        created_issues = fetcher.batch_create_issues(
            issues=issues_data, validate_only=validate_only
        )

        # Format the response
        result = {
            "message": f"Successfully created {len(created_issues)} issues"
            if not validate_only and created_issues
            else "Validation successful"
            if validate_only
            else "No issues created",
            "issues": [issue.to_simplified_dict() for issue in created_issues],
        }

        return [
            TextContent(
                type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
            )
        ]
    except Exception as e:
        logger.error(f"Error during batch issue creation: {str(e)}", exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Error creating issues: {str(e)}",
            )
        ]


@jira_mcp.tool()
async def update_issue(
    ctx: Context,
    issue_key: str,
    fields: str,
    additional_fields: Annotated[
        str,
        Field(
            description="Optional JSON string of additional fields to update. Use this for custom fields or more complex updates.",
            default="{}",
        ),
    ] = "{}",
    attachments: Annotated[
        str | None,
        Field(
            description="Optional JSON string or comma-separated list of file paths to attach to the issue. "
            'Example: "/path/to/file1.txt,/path/to/file2.txt" or "["/path/to/file1.txt","/path/to/file2.txt"]"',
        ),
    ] = None,
) -> Sequence[TextContent]:
    """Update an existing Jira issue including changing status, adding Epic links, updating fields, etc."""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check read-only mode
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only:
        raise ValueError("Cannot update issue in read-only mode")

    # Update issue
    issue = fetcher.update_issue(
        issue_key=issue_key,
        fields=fields,
        additional_fields=additional_fields,
        attachments=attachments,
    )

    # Format results
    return [
        TextContent(
            type="text",
            text=json.dumps(
                issue.to_simplified_dict() if issue else {},
                indent=2,
                ensure_ascii=False,
            ),
        )
    ]


@jira_mcp.tool()
async def delete_issue(
    ctx: Context,
    issue_key: str,
) -> Sequence[TextContent]:
    """Delete an existing Jira issue"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check read-only mode
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only:
        raise ValueError("Cannot delete issue in read-only mode")

    # Delete issue
    result = fetcher.delete_issue(issue_key=issue_key)

    # Format results
    return [
        TextContent(
            type="text",
            text=json.dumps({"success": result}, indent=2, ensure_ascii=False),
        )
    ]


@jira_mcp.tool()
async def add_comment(
    ctx: Context,
    issue_key: str,
    comment: str,
) -> Sequence[TextContent]:
    """Add a comment to a Jira issue"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check read-only mode
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only:
        raise ValueError("Cannot add comment in read-only mode")

    # Add comment
    result = fetcher.add_comment(
        issue_key=issue_key,
        comment=comment,
    )

    # Format results
    return [
        TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
    ]


@jira_mcp.tool()
async def add_worklog(
    ctx: Context,
    issue_key: str,
    time_spent: str,
    comment: Annotated[
        str | None,
        Field(
            description="Optional comment for the worklog in Markdown format",
        ),
    ] = None,
    started: Annotated[
        str | None,
        Field(
            description=(
                "Optional start time in ISO format. "
                "If not provided, the current time will be used. "
                "Example: '2023-08-01T12:00:00.000+0000'"
            ),
        ),
    ] = None,
) -> Sequence[TextContent]:
    """Add a worklog entry to a Jira issue"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check read-only mode
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only:
        raise ValueError("Cannot add worklog in read-only mode")

    # Add worklog
    result = fetcher.add_worklog(
        issue_key=issue_key,
        time_spent=time_spent,
        comment=comment,
        started=started,
    )

    # Format results
    return [
        TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
    ]


@jira_mcp.tool()
async def link_to_epic(
    ctx: Context,
    issue_key: str,
    epic_key: str,
) -> Sequence[TextContent]:
    """Link an existing issue to an epic"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check read-only mode
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only:
        raise ValueError("Cannot link issue to epic in read-only mode")

    # Link issue to epic
    result = fetcher.link_to_epic(
        issue_key=issue_key,
        epic_key=epic_key,
    )

    # Format results
    return [
        TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
    ]


@jira_mcp.tool()
async def create_issue_link(
    ctx: Context,
    link_type: str,
    inward_issue_key: str,
    outward_issue_key: str,
    comment: Annotated[
        str | None,
        Field(
            description="Optional comment to add to the link",
        ),
    ] = None,
    comment_visibility: Annotated[
        dict[str, str] | None,
        Field(
            description="Optional visibility settings for the comment",
        ),
    ] = None,
) -> Sequence[TextContent]:
    """Create a link between two Jira issues"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check read-only mode
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only:
        raise ValueError("Cannot create issue link in read-only mode")

    # Create issue link
    result = fetcher.create_issue_link(
        link_type=link_type,
        inward_issue_key=inward_issue_key,
        outward_issue_key=outward_issue_key,
        comment=comment,
        comment_visibility=comment_visibility,
    )

    # Format results
    return [
        TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
    ]


@jira_mcp.tool()
async def remove_issue_link(
    ctx: Context,
    link_id: str,
) -> Sequence[TextContent]:
    """Remove a link between two Jira issues"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check read-only mode
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only:
        raise ValueError("Cannot remove issue link in read-only mode")

    # Remove issue link
    result = fetcher.remove_issue_link(link_id=link_id)

    # Format results
    return [
        TextContent(
            type="text",
            text=json.dumps({"success": result}, indent=2, ensure_ascii=False),
        )
    ]


@jira_mcp.tool()
async def transition_issue(
    ctx: Context,
    issue_key: str,
    transition_id: str,
    fields: Annotated[
        str,
        Field(
            description=(
                "JSON string of fields to update during the transition. "
                "Some transitions require specific fields to be set. "
                'Example: \'{"resolution": {"name": "Fixed"}}\''
            ),
            default="{}",
        ),
    ] = "{}",
    comment: Annotated[
        str | None,
        Field(
            description=(
                "Comment to add during the transition (optional). "
                "This will be visible in the issue history."
            ),
        ),
    ] = None,
) -> Sequence[TextContent]:
    """Transition a Jira issue to a new status"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Check read-only mode
    read_only = ctx.request_context.lifespan_context.get("read_only", False)
    if read_only:
        raise ValueError("Cannot transition issue in read-only mode")

    # Transition issue
    result = fetcher.transition_issue(
        issue_key=issue_key,
        transition_id=transition_id,
        fields=fields,
        comment=comment,
    )

    # Format results
    return [
        TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
    ]


@jira_mcp.tool()
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
        int,
        Field(
            description="Maximum number of results",
            ge=1,
            default=10,
        ),
    ] = 10,
    refresh: Annotated[
        bool,
        Field(
            description="Whether to force refresh the field list",
            default=False,
        ),
    ] = False,
) -> Sequence[TextContent]:
    """Search Jira fields by keyword with fuzzy match"""

    # Get the JiraFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("jira_fetcher")
    if not fetcher:
        raise ValueError("Jira is not configured. Please provide Jira credentials.")

    # Search fields
    result = fetcher.search_fields(
        keyword=keyword,
        limit=limit,
        refresh=refresh,
    )

    # Format results
    return [
        TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
    ]
