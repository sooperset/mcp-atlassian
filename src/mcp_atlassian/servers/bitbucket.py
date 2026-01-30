"""Bitbucket FastMCP server instance and tool definitions."""

import json
import logging
from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.models.bitbucket import BitbucketProject, BitbucketPullRequest
from mcp_atlassian.servers.dependencies import get_bitbucket_fetcher
from mcp_atlassian.utils.decorators import check_write_access

logger = logging.getLogger(__name__)

bitbucket_mcp = FastMCP(
    name="Bitbucket MCP Service",
    instructions="Provides tools for interacting with Atlassian Bitbucket.",
)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read"},
    annotations={"title": "List Bitbucket Projects", "readOnlyHint": True},
)
async def bitbucket_list_projects(
    ctx: Context,
    workspace: Annotated[
        str | None,
        Field(
            description="Workspace slug (required for Bitbucket Cloud). For example: 'my-workspace'"
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of projects to return (default: 100, max: 1000)",
            ge=1,
            le=1000,
        ),
    ] = 100,
) -> str:
    """
    List all projects accessible to the authenticated user.

    For Bitbucket Cloud: workspace parameter is required
    For Bitbucket Server: workspace parameter is ignored

    Args:
        ctx: The FastMCP context.
        workspace: Workspace slug (Cloud only, required for Cloud)
        limit: Maximum number of projects to return

    Returns:
        JSON string with list of projects or error information

    Raises:
        ValueError: If the Bitbucket client is not configured or workspace is missing for Cloud
    """
    bitbucket = await get_bitbucket_fetcher(ctx)
    try:
        projects: list[BitbucketProject] = bitbucket.list_projects(
            workspace=workspace,
            limit=limit,
        )

        result = [project.to_simplified_dict() for project in projects]
        response_data = {
            "success": True,
            "count": len(result),
            "projects": result,
        }
        return json.dumps(response_data, indent=2)

    except Exception as e:
        error_message = ""
        log_level = logging.ERROR

        if isinstance(e, ValueError):
            log_level = logging.WARNING
            error_message = str(e)
        elif isinstance(e, MCPAtlassianAuthenticationError):
            error_message = f"Authentication/Permission Error: {str(e)}"
        elif isinstance(e, OSError | HTTPError):
            error_message = f"Network or API Error: {str(e)}"
        else:
            error_message = "An unexpected error occurred while listing projects."
            logger.exception("Unexpected error in bitbucket_list_projects:")

        error_result = {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }
        logger.log(log_level, f"bitbucket_list_projects failed: {error_message}")
        return json.dumps(error_result, indent=2)


@bitbucket_mcp.tool(
    tags={"bitbucket", "write"},
    annotations={"title": "Create Pull Request", "readOnlyHint": False},
)
@check_write_access
async def bitbucket_create_pr(
    ctx: Context,
    repository: Annotated[
        str,
        Field(description="Repository slug (e.g., 'my-repo')"),
    ],
    title: Annotated[
        str,
        Field(description="Pull request title"),
    ],
    source_branch: Annotated[
        str,
        Field(description="Source branch name (e.g., 'feature/new-feature')"),
    ],
    destination_branch: Annotated[
        str,
        Field(description="Destination branch name (e.g., 'main' or 'master')"),
    ],
    workspace: Annotated[
        str | None,
        Field(
            description="Workspace slug (required for Bitbucket Cloud, e.g., 'my-workspace')"
        ),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (required for Bitbucket Server, e.g., 'PROJ')"),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="Pull request description (optional)"),
    ] = None,
    reviewers: Annotated[
        list[str] | None,
        Field(
            description="List of reviewer usernames or UUIDs (optional). For Cloud: use UUID format, for Server: use usernames"
        ),
    ] = None,
    close_source_branch: Annotated[
        bool,
        Field(
            description="Whether to close source branch after merge (Cloud only, default: false)"
        ),
    ] = False,
) -> str:
    """
    Create a new pull request in a Bitbucket repository.

    For Bitbucket Cloud: workspace is required
    For Bitbucket Server: project_key is required

    Args:
        ctx: The FastMCP context.
        repository: Repository slug
        title: Pull request title
        source_branch: Source branch name
        destination_branch: Destination branch name
        workspace: Workspace slug (Cloud only)
        project_key: Project key (Server only)
        description: Pull request description
        reviewers: List of reviewer identifiers
        close_source_branch: Whether to close source branch after merge

    Returns:
        JSON string with created pull request information or error

    Raises:
        ValueError: If required parameters are missing
    """
    bitbucket = await get_bitbucket_fetcher(ctx)
    try:
        pr: BitbucketPullRequest = bitbucket.create_pr(
            repository=repository,
            title=title,
            source_branch=source_branch,
            destination_branch=destination_branch,
            description=description,
            workspace=workspace,
            project_key=project_key,
            reviewers=reviewers,
            close_source_branch=close_source_branch,
        )

        result = pr.to_simplified_dict()
        response_data = {
            "success": True,
            "pull_request": result,
        }
        return json.dumps(response_data, indent=2)

    except Exception as e:
        error_message = ""
        log_level = logging.ERROR

        if isinstance(e, ValueError):
            log_level = logging.WARNING
            error_message = str(e)
        elif isinstance(e, MCPAtlassianAuthenticationError):
            error_message = f"Authentication/Permission Error: {str(e)}"
        elif isinstance(e, OSError | HTTPError):
            error_message = f"Network or API Error: {str(e)}"
        else:
            error_message = (
                "An unexpected error occurred while creating the pull request."
            )
            logger.exception("Unexpected error in bitbucket_create_pr:")

        error_result = {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }
        logger.log(log_level, f"bitbucket_create_pr failed: {error_message}")
        return json.dumps(error_result, indent=2)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read"},
    annotations={"title": "Get Pull Request", "readOnlyHint": True},
)
async def bitbucket_get_pr(
    ctx: Context,
    repository: Annotated[
        str,
        Field(description="Repository slug (e.g., 'my-repo')"),
    ],
    pr_id: Annotated[
        int,
        Field(description="Pull request ID", ge=1),
    ],
    workspace: Annotated[
        str | None,
        Field(
            description="Workspace slug (required for Bitbucket Cloud, e.g., 'my-workspace')"
        ),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (required for Bitbucket Server, e.g., 'PROJ')"),
    ] = None,
) -> str:
    """
    Get detailed information about a specific pull request.

    Args:
        ctx: The FastMCP context.
        repository: Repository slug
        pr_id: Pull request ID
        workspace: Workspace slug (Cloud only)
        project_key: Project key (Server only)

    Returns:
        JSON string with pull request information or error
    """
    bitbucket = await get_bitbucket_fetcher(ctx)
    try:
        pr = bitbucket.get_pull_request(
            repository=repository,
            pr_id=pr_id,
            workspace=workspace,
            project_key=project_key,
        )

        if pr:
            result = pr.to_simplified_dict()
            response_data = {
                "success": True,
                "pull_request": result,
            }
        else:
            response_data = {
                "success": False,
                "error": f"Pull request #{pr_id} not found",
            }

        return json.dumps(response_data, indent=2)

    except Exception as e:
        error_message = ""
        log_level = logging.ERROR

        if isinstance(e, ValueError):
            log_level = logging.WARNING
            error_message = str(e)
        elif isinstance(e, MCPAtlassianAuthenticationError):
            error_message = f"Authentication/Permission Error: {str(e)}"
        elif isinstance(e, OSError | HTTPError):
            error_message = f"Network or API Error: {str(e)}"
        else:
            error_message = (
                "An unexpected error occurred while fetching the pull request."
            )
            logger.exception("Unexpected error in bitbucket_get_pr:")

        error_result = {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }
        logger.log(log_level, f"bitbucket_get_pr failed: {error_message}")
        return json.dumps(error_result, indent=2)


@bitbucket_mcp.tool(
    tags={"bitbucket", "read"},
    annotations={"title": "List Pull Requests", "readOnlyHint": True},
)
async def bitbucket_list_prs(
    ctx: Context,
    repository: Annotated[
        str,
        Field(description="Repository slug (e.g., 'my-repo')"),
    ],
    workspace: Annotated[
        str | None,
        Field(
            description="Workspace slug (required for Bitbucket Cloud, e.g., 'my-workspace')"
        ),
    ] = None,
    project_key: Annotated[
        str | None,
        Field(description="Project key (required for Bitbucket Server, e.g., 'PROJ')"),
    ] = None,
    state: Annotated[
        str | None,
        Field(description="Filter by state: OPEN, MERGED, DECLINED, or ALL (optional)"),
    ] = None,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of pull requests to return (default: 50, max: 1000)",
            ge=1,
            le=1000,
        ),
    ] = 50,
) -> str:
    """
    List pull requests for a repository.

    Args:
        ctx: The FastMCP context.
        repository: Repository slug
        workspace: Workspace slug (Cloud only)
        project_key: Project key (Server only)
        state: Filter by state (OPEN, MERGED, DECLINED, ALL)
        limit: Maximum number of pull requests to return

    Returns:
        JSON string with list of pull requests or error information
    """
    bitbucket = await get_bitbucket_fetcher(ctx)
    try:
        prs: list[BitbucketPullRequest] = bitbucket.list_pull_requests(
            repository=repository,
            workspace=workspace,
            project_key=project_key,
            state=state,
            limit=limit,
        )

        result = [pr.to_simplified_dict() for pr in prs]
        response_data = {
            "success": True,
            "count": len(result),
            "pull_requests": result,
        }
        return json.dumps(response_data, indent=2)

    except Exception as e:
        error_message = ""
        log_level = logging.ERROR

        if isinstance(e, ValueError):
            log_level = logging.WARNING
            error_message = str(e)
        elif isinstance(e, MCPAtlassianAuthenticationError):
            error_message = f"Authentication/Permission Error: {str(e)}"
        elif isinstance(e, OSError | HTTPError):
            error_message = f"Network or API Error: {str(e)}"
        else:
            error_message = "An unexpected error occurred while listing pull requests."
            logger.exception("Unexpected error in bitbucket_list_prs:")

        error_result = {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }
        logger.log(log_level, f"bitbucket_list_prs failed: {error_message}")
        return json.dumps(error_result, indent=2)
