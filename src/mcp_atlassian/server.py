import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from mcp_atlassian.models.confluence import (
    ConfluenceComment,
    ConfluenceSearchResult,
)
from mcp_atlassian.models.jira import JiraSearchResult

from .confluence import ConfluenceFetcher
from .jira import JiraFetcher
from .preprocessing import markdown_to_confluence_storage

# Configure logging
logger = logging.getLogger("mcp-atlassian")


@dataclass
class AppContext:
    """Application context for MCP Atlassian."""

    confluence: ConfluenceFetcher | None = None
    jira: JiraFetcher | None = None


def get_available_services() -> dict[str, bool | None]:
    """Determine which services are available based on environment variables."""
    confluence_vars = all(
        [
            os.getenv("CONFLUENCE_URL"),
            os.getenv("CONFLUENCE_USERNAME"),
            os.getenv("CONFLUENCE_API_TOKEN"),
        ]
    )

    # Check for either cloud authentication (URL + username + API token)
    # or server/data center authentication (URL + personal token)
    jira_url = os.getenv("JIRA_URL")
    if jira_url:
        is_cloud = "atlassian.net" in jira_url
        if is_cloud:
            jira_vars = all(
                [jira_url, os.getenv("JIRA_USERNAME"), os.getenv("JIRA_API_TOKEN")]
            )
            logger.info("Using Jira Cloud authentication method")
        else:
            jira_vars = all([jira_url, os.getenv("JIRA_PERSONAL_TOKEN")])
            logger.info("Using Jira Server/Data Center authentication method")
    else:
        jira_vars = False

    return {"confluence": confluence_vars, "jira": jira_vars}


@asynccontextmanager
async def app_lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize and clean up application resources."""
    # Get available services
    services = get_available_services()

    try:
        # Initialize services
        confluence = ConfluenceFetcher() if services["confluence"] else None
        jira = JiraFetcher() if services["jira"] else None

        # Log the startup information
        logger.info("Starting MCP Atlassian server")
        if confluence:
            logger.info(f"Confluence URL: {confluence.config.url}")
        if jira:
            logger.info(f"Jira URL: {jira.config.url}")

        # Provide context to the application
        yield AppContext(confluence=confluence, jira=jira)
    finally:
        # Cleanup resources if needed
        pass


# Create the FastMCP application
app = FastMCP("mcp-atlassian", lifespan=app_lifespan)


# Resource handlers
@app.resource("confluence://{space_key}")
def get_confluence_space(space_key: str) -> str:
    """
    Get information about a Confluence space.

    Args:
        space_key: The key of the Confluence space

    Returns:
        Information about the space
    """
    confluence = app.lifespan_context.confluence
    if not confluence:
        return "Confluence is not configured."

    try:
        space_info = confluence.get_space_info(space_key)
        return f"""# {space_info.get("name", "Unknown Space")}

**Key**: {space_key}
**Description**: {space_info.get("description", {}).get("plain", {}).get("value", "No description")}

## Recent Pages

{space_info.get("recent_pages_markdown", "No recent pages found.")}
"""
    except Exception as e:
        logger.error(f"Error fetching Confluence space {space_key}: {e}")
        return f"Error fetching Confluence space {space_key}: {str(e)}"


@app.resource("confluence://{space_key}/{title}")
def get_confluence_page(space_key: str, title: str) -> str:
    """
    Get a specific Confluence page by space key and title.

    Args:
        space_key: The key of the Confluence space
        title: The title of the page

    Returns:
        The page content
    """
    confluence = app.lifespan_context.confluence
    if not confluence:
        return "Confluence is not configured."

    try:
        page_info = confluence.get_page_by_title(space_key, title)

        if not page_info:
            return f"Page '{title}' not found in space '{space_key}'."

        return f"""# {page_info.get("title", "Unknown Page")}

**Space**: {space_key}
**Created**: {page_info.get("created_formatted", "Unknown")}
**Last Updated**: {page_info.get("updated_formatted", "Unknown")}
**Created By**: {page_info.get("author", {}).get("displayName", "Unknown")}

{page_info.get("body_markdown", "No content available.")}
"""
    except Exception as e:
        logger.error(
            f"Error fetching Confluence page {title} in space {space_key}: {e}"
        )
        return f"Error fetching Confluence page: {str(e)}"


@app.resource("jira://{project_key}")
def get_jira_project(project_key: str) -> str:
    """
    Get information about a Jira project.

    Args:
        project_key: The key of the Jira project

    Returns:
        Information about the project
    """
    jira = app.lifespan_context.jira
    if not jira:
        return "Jira is not configured."

    try:
        project_info = jira.get_project_info(project_key)
        return f"""# {project_info.get("name", "Unknown Project")}

**Key**: {project_key}
**Description**: {project_info.get("description", "No description")}
**Lead**: {project_info.get("lead", {}).get("displayName", "Unknown")}

## Project Statistics

**Total Issues**: {project_info.get("total_issues", 0)}
**Open Issues**: {project_info.get("open_issues", 0)}
**Issue Types**: {", ".join(project_info.get("issue_types", []))}
**Components**: {", ".join(project_info.get("components", []))}

## Recent Activity

{project_info.get("recent_activity_markdown", "No recent activity found.")}
"""
    except Exception as e:
        logger.error(f"Error fetching Jira project {project_key}: {e}")
        return f"Error fetching Jira project {project_key}: {str(e)}"


@app.resource("jira://{project_key}/{issue_key}")
def get_jira_issue(project_key: str, issue_key: str) -> str:
    """
    Get information about a specific Jira issue.

    Args:
        project_key: The key of the Jira project
        issue_key: The key of the issue (e.g. PROJECT-123)

    Returns:
        Information about the issue
    """
    jira = app.lifespan_context.jira
    if not jira:
        return "Jira is not configured."

    try:
        issue_info = jira.get_issue_info(issue_key)
        return f"""# {issue_info.get("summary", "Unknown Issue")}

**Key**: {issue_key}
**Type**: {issue_info.get("issuetype", {}).get("name", "Unknown")}
**Status**: {issue_info.get("status", {}).get("name", "Unknown")}
**Priority**: {issue_info.get("priority", {}).get("name", "Unknown")}
**Reporter**: {issue_info.get("reporter", {}).get("displayName", "Unknown")}
**Assignee**: {issue_info.get("assignee", {}).get("displayName", "Unassigned") if issue_info.get("assignee") else "Unassigned"}
**Created**: {issue_info.get("created_formatted", "Unknown")}
**Updated**: {issue_info.get("updated_formatted", "Unknown")}

**Description**:
{issue_info.get("description_markdown", "No description provided.")}

## Comments

{issue_info.get("comments_markdown", "No comments found.")}

## Attachments

{issue_info.get("attachments_markdown", "No attachments found.")}
"""
    except Exception as e:
        logger.error(f"Error fetching Jira issue {issue_key}: {e}")
        return f"Error fetching Jira issue: {str(e)}"


# Tool implementations
@app.tool()
async def confluence_search(
    query: str,
    ctx: Context,
    limit: int = Field(10, description="Maximum number of results (1-50)", ge=1, le=50),
) -> list[dict[str, Any]]:
    """
    Search for Confluence content using CQL.

    Args:
        query: Confluence Query Language (CQL) search string
        ctx: The request context
        limit: Maximum number of results to return (1-50)

    Returns:
        List of matching pages with metadata
    """
    if not ctx.lifespan_context.confluence:
        return [{"error": "Confluence is not configured"}]

    try:
        # Log the search query
        logger.info(f"Searching Confluence with query: {query}")

        # Execute the search
        results_data = await ctx.lifespan_context.confluence.search_content(
            query, limit=limit
        )

        if not results_data or not results_data.get("results"):
            return [{"info": "No matching content found"}]

        # Convert to ConfluenceSearchResult model
        base_url = ctx.lifespan_context.confluence.config.url
        search_result = ConfluenceSearchResult.from_api_response(
            results_data, base_url=base_url
        )

        # Return simplified pages
        return [page.to_simplified_dict() for page in search_result.results]
    except Exception as e:
        logger.error(f"Error searching Confluence: {e}")
        return [{"error": f"Error searching Confluence: {str(e)}"}]


@app.tool()
async def confluence_get_page(
    page_id: str,
    ctx: Context,
    include_metadata: bool = Field(
        default=True, description="Whether to include page metadata"
    ),
) -> dict[str, Any]:
    """
    Get content of a specific Confluence page.

    Args:
        page_id: The ID of the page to retrieve
        ctx: The request context
        include_metadata: Whether to include page metadata

    Returns:
        Page content with metadata if requested
    """
    if not ctx.lifespan_context.confluence:
        return {"error": "Confluence is not configured"}

    try:
        # Log the page ID
        logger.info(f"Fetching Confluence page: {page_id}")

        # Get the page
        doc = await ctx.lifespan_context.confluence.get_page_content(page_id)

        # Format the result
        result = doc.to_simplified_dict()

        # Add the content field which is not included in the simplified dict
        result["content"] = doc.content

        if include_metadata:
            return result
        else:
            # If metadata is not requested, only return content
            return {"content": doc.content}
    except Exception as e:
        logger.error(f"Error getting Confluence page: {e}")
        return {"error": f"Error getting Confluence page: {str(e)}"}


@app.tool()
async def confluence_create_page(
    space_key: str,
    title: str,
    content: str,
    parent_id: str | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """
    Create a new Confluence page.

    Args:
        space_key: The key of the Confluence space
        title: Title for the new page
        content: Page content in markdown format
        parent_id: Optional ID of the parent page
        ctx: The request context

    Returns:
        Details of the created page
    """
    if not ctx.lifespan_context.confluence:
        return {"error": "Confluence is not configured"}

    try:
        # Log the page creation request
        logger.info(f"Creating Confluence page '{title}' in space {space_key}")

        # Convert markdown to Confluence storage format
        storage_format = markdown_to_confluence_storage(content)

        # Handle parent_id - convert to string if not None
        parent_id_str: str | None = str(parent_id) if parent_id is not None else None

        # Create the page
        doc = ctx.lifespan_context.confluence.create_page(
            space_key=space_key,
            title=title,
            body=storage_format,
            parent_id=parent_id_str,
        )

        # Format the result
        result = doc.to_simplified_dict()

        # Add extra fields not included in the simplified dict
        result["content_preview"] = (
            doc.content[:500] + "..." if len(doc.content) > 500 else doc.content
        )
        result["message"] = "Page created successfully"

        return result
    except Exception as e:
        error_msg = f"Error creating Confluence page: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}


@app.tool()
async def confluence_update_page(
    page_id: str,
    title: str,
    content: str,
    minor_edit: bool = Field(default=False, description="Whether this is a minor edit"),
    version_comment: str = Field(
        default="", description="Optional comment for the update"
    ),
    ctx: Context = None,
) -> dict[str, Any]:
    """
    Update an existing Confluence page.

    Args:
        page_id: ID of the page to update
        title: New title for the page
        content: New page content in markdown format
        minor_edit: Whether this update is a minor edit
        version_comment: Optional comment for this version
        ctx: The request context

    Returns:
        Updated page details
    """
    if not ctx.lifespan_context.confluence:
        return {"error": "Confluence is not configured"}

    try:
        # Log the page update request
        logger.info(f"Updating Confluence page with ID: {page_id}")

        # Convert markdown to Confluence storage format
        storage_format = markdown_to_confluence_storage(content)

        # Update the page
        doc = ctx.lifespan_context.confluence.update_page(
            page_id=page_id,
            title=title,
            body=storage_format,
            is_minor_edit=minor_edit,
            version_comment=version_comment,
        )

        # Format the result
        result = doc.to_simplified_dict()

        # Add extra fields not included in the simplified dict
        result["content_preview"] = (
            doc.content[:500] + "..." if len(doc.content) > 500 else doc.content
        )
        result["message"] = "Page updated successfully"

        return result
    except Exception as e:
        error_msg = f"Error updating Confluence page: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}


@app.tool()
async def jira_get_issue(issue_key: str, ctx: Context) -> dict[str, Any]:
    """
    Get details of a specific Jira issue.

    Args:
        issue_key: Jira issue key (e.g. 'PROJECT-123')
        ctx: The request context

    Returns:
        Issue details with metadata
    """
    if not ctx.lifespan_context.jira:
        return {"error": "Jira is not configured"}

    try:
        # Log the issue key
        logger.info(f"Fetching Jira issue: {issue_key}")

        # Get the issue
        doc = await ctx.lifespan_context.jira.get_issue(issue_key)

        if not doc:
            return {"error": f"Issue {issue_key} not found"}

        # Format the result using the simplified dict
        result = doc.to_simplified_dict()

        # Add description if it's not included in the simplified dict
        if "description" not in result and doc.description:
            result["description"] = doc.description

        return result
    except Exception as e:
        logger.error(f"Error getting Jira issue: {e}")
        return {"error": f"Error getting Jira issue: {str(e)}"}


@app.tool()
async def jira_create_issue(
    project_key: str,
    summary: str,
    issue_type: str,
    description: str = "",
    assignee: str | None = None,
    priority: str | None = None,
    labels: list[str] | None = None,
    components: list[str] | None = None,
    epic_link: str | None = None,
    custom_fields: dict[str, Any] | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """
    Create a new issue in Jira.

    Args:
        project_key: The key of the Jira project (e.g., 'PROJ')
        summary: Issue summary/title
        issue_type: Type of issue (e.g., 'Bug', 'Task', 'Story')
        description: Issue description in plain text or Jira markdown
        assignee: Username of assignee (typically email address)
        priority: Issue priority (e.g., 'High', 'Medium', 'Low')
        labels: List of labels to apply to the issue
        components: List of components to associate with the issue
        epic_link: Key of the epic to link the issue to
        custom_fields: Additional custom fields for the issue
        ctx: The request context

    Returns:
        Created issue details
    """
    if not ctx.lifespan_context.jira:
        return {"error": "Jira is not configured"}

    try:
        # Log the issue creation request
        logger.info(f"Creating Jira issue in project {project_key}: {summary}")

        # Prepare additional fields if provided
        kwargs = {}
        if priority:
            kwargs["priority"] = priority
        if labels:
            kwargs["labels"] = labels
        if components:
            kwargs["components"] = components
        if epic_link:
            kwargs["epic_link"] = epic_link
        if custom_fields:
            kwargs.update(custom_fields)

        # Create the issue
        doc = ctx.lifespan_context.jira.create_issue(
            project_key=project_key,
            summary=summary,
            issue_type=issue_type,
            description=description,
            assignee=assignee,
            **kwargs,
        )

        # Format the result
        result = doc.to_simplified_dict()

        # Add description field if not in simplified dict
        if "description" not in result and doc.description:
            result["description"] = doc.description

        # Add message field
        result["message"] = "Issue created successfully"

        return result
    except KeyError as e:
        error_msg = f"Missing required parameter: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}
    except Exception as e:
        error_msg = f"Error creating issue: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}


@app.tool()
async def jira_update_issue(
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    labels: list[str] | None = None,
    components: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """
    Update an existing Jira issue.

    Args:
        issue_key: Key of the issue to update (e.g., 'PROJECT-123')
        summary: New issue summary/title
        description: New issue description
        assignee: Username to assign the issue to
        priority: New priority (e.g., 'High', 'Medium', 'Low')
        status: New status (e.g., 'In Progress', 'Done')
        labels: List of labels to set (replaces existing labels)
        components: List of components to set (replaces existing components)
        custom_fields: Additional custom fields to update
        ctx: The request context

    Returns:
        Updated issue details
    """
    if not ctx.lifespan_context.jira:
        return {"error": "Jira is not configured"}

    try:
        # Log the issue update request
        logger.info(f"Updating Jira issue: {issue_key}")

        # Prepare fields for the update
        fields = {}
        if summary is not None:
            fields["summary"] = summary
        if description is not None:
            fields["description"] = description
        if assignee is not None:
            fields["assignee"] = assignee
        if priority is not None:
            fields["priority"] = priority
        if status is not None:
            fields["status"] = status
        if labels is not None:
            fields["labels"] = labels
        if components is not None:
            fields["components"] = components
        if custom_fields is not None:
            fields.update(custom_fields)

        # Make sure we have something to update
        if not fields:
            return {"error": "No fields provided for update", "success": False}

        # Update the issue
        doc = ctx.lifespan_context.jira.update_issue(issue_key=issue_key, **fields)

        # Format the result
        result = doc.to_simplified_dict()

        # Add extra fields not included in the simplified dict
        if doc.description:
            result["description"] = doc.description
        result["message"] = "Issue updated successfully"

        return result
    except KeyError as e:
        error_msg = f"Missing required parameter: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}
    except Exception as e:
        error_msg = f"Error updating issue: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}


@app.tool()
async def jira_add_comment(
    issue_key: str, comment: str, ctx: Context = None
) -> dict[str, Any]:
    """
    Add a comment to a Jira issue.

    Args:
        issue_key: Key of the issue to comment on (e.g., 'PROJECT-123')
        comment: Comment text in plain text or Jira markdown format
        ctx: The request context

    Returns:
        Added comment details
    """
    if not ctx.lifespan_context.jira:
        return {"error": "Jira is not configured"}

    try:
        # Log the comment addition request
        logger.info(f"Adding comment to Jira issue: {issue_key}")

        # Add the comment
        result = ctx.lifespan_context.jira.add_comment(issue_key, comment)

        # Format the response
        formatted_result = {
            "id": result.get("id", ""),
            "author": result.get("author", {}).get("displayName", "Unknown"),
            "created": result.get("created", ""),
            "body": result.get("body", ""),
            "issue_key": issue_key,
            "message": "Comment added successfully",
        }

        return formatted_result
    except Exception as e:
        error_msg = f"Error adding comment to issue {issue_key}: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}


@app.tool()
async def jira_get_transitions(
    issue_key: str, ctx: Context = None
) -> list[dict[str, Any]]:
    """
    Get available transitions for a Jira issue.

    Args:
        issue_key: Key of the issue to get transitions for (e.g., 'PROJECT-123')
        ctx: The request context

    Returns:
        List of available transitions with IDs and names
    """
    if not ctx.lifespan_context.jira:
        return [{"error": "Jira is not configured"}]

    try:
        # Log the request
        logger.info(f"Fetching available transitions for Jira issue: {issue_key}")

        # Get transitions
        transitions = ctx.lifespan_context.jira.get_available_transitions(issue_key)

        # Format the response
        formatted_transitions = []
        for transition in transitions:
            formatted_transitions.append(
                {
                    "id": transition.get("id", ""),
                    "name": transition.get("name", ""),
                    "to_status": transition.get("to", {}).get("name", "Unknown"),
                    "has_screen": transition.get("hasScreen", False),
                    "is_global": transition.get("isGlobal", False),
                    "is_initial": transition.get("isInitial", False),
                    "is_available": transition.get("isAvailable", True),
                }
            )

        return formatted_transitions
    except Exception as e:
        error_msg = f"Error getting transitions for issue {issue_key}: {str(e)}"
        logger.error(error_msg)
        return [{"error": error_msg, "success": False}]


@app.tool()
async def jira_transition_issue(
    issue_key: str,
    transition_id: str,
    fields: dict[str, Any] | None = None,
    comment: str | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """
    Transition a Jira issue to a new status.

    Args:
        issue_key: Key of the issue to transition (e.g., 'PROJECT-123')
        transition_id: ID of the transition to perform (use jira_get_transitions to find available transitions)
        fields: Optional fields to update during the transition
        comment: Optional comment to add with the transition
        ctx: The request context

    Returns:
        Updated issue details after transition
    """
    if not ctx.lifespan_context.jira:
        return {"error": "Jira is not configured"}

    try:
        # Log the transition request
        logger.info(
            f"Transitioning Jira issue {issue_key} with transition ID: {transition_id}"
        )

        # Transition the issue
        doc = ctx.lifespan_context.jira.transition_issue(
            issue_key=issue_key,
            transition_id=transition_id,
            fields=fields,
            comment=comment,
        )

        # Format the result
        result = doc.to_simplified_dict()

        # Add extra fields not included in the simplified dict
        if doc.description:
            result["description"] = doc.description
        result["message"] = "Issue transitioned successfully"

        return result
    except KeyError as e:
        error_msg = f"Missing required parameter: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}
    except Exception as e:
        error_msg = f"Error transitioning issue {issue_key}: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "success": False}


@app.tool()
async def jira_search(
    query: str,
    ctx: Context,
    limit: int = Field(10, description="Maximum number of results (1-50)", ge=1, le=50),
) -> list[dict[str, Any]]:
    """
    Search for Jira issues using JQL.

    Args:
        query: Jira Query Language (JQL) search string
        ctx: The request context
        limit: Maximum number of results to return (1-50)

    Returns:
        List of matching issues with metadata
    """
    if not ctx.lifespan_context.jira:
        return [{"error": "Jira is not configured"}]

    try:
        # Log the search query
        logger.info(f"Searching Jira with query: {query}")

        # Execute the search
        results_data = await ctx.lifespan_context.jira.search_issues(query, limit=limit)

        if not results_data or not results_data.get("issues"):
            return [{"info": "No matching issues found"}]

        # Convert to JiraSearchResult model
        base_url = ctx.lifespan_context.jira.config.url
        search_result = JiraSearchResult.from_api_response(
            results_data, base_url=base_url
        )

        # Return simplified issues
        return [issue.to_simplified_dict() for issue in search_result.issues]
    except Exception as e:
        logger.error(f"Error searching Jira: {e}")
        return [{"error": f"Error searching Jira: {str(e)}"}]


@app.tool()
async def confluence_get_comments(
    page_id: str,
    ctx: Context,
    include_metadata: bool = Field(
        default=True, description="Whether to include comment metadata"
    ),
) -> list[dict[str, Any]]:
    """
    Get all comments for a specific Confluence page.

    Args:
        page_id: The ID of the page to get comments from
        ctx: The request context
        include_metadata: Whether to include comment metadata

    Returns:
        List of comments with metadata
    """
    if not ctx.lifespan_context.confluence:
        return [{"error": "Confluence is not configured"}]

    try:
        # Log the request
        logger.info(f"Fetching comments for Confluence page: {page_id}")

        # Get the comments
        comments_data = await ctx.lifespan_context.confluence.get_page_comments(page_id)

        if not comments_data or not comments_data.get("results"):
            return [{"info": "No comments found for this page"}]

        # Process each comment
        comments = []
        for comment_data in comments_data.get("results", []):
            # Convert to ConfluenceComment model
            comment = ConfluenceComment.from_api_response(comment_data)
            comments.append(comment.to_simplified_dict())

        return comments
    except Exception as e:
        logger.error(f"Error getting Confluence comments: {e}")
        return [{"error": f"Error getting Confluence comments: {str(e)}"}]


@app.tool()
async def jira_get_project_issues(
    project_key: str,
    ctx: Context,
    limit: int = Field(
        10, description="Maximum number of issues to return (1-50)", ge=1, le=50
    ),
    start: int = Field(0, description="Start index for pagination"),
) -> list[dict[str, Any]]:
    """
    Get issues for a specific Jira project.

    Args:
        project_key: The key of the Jira project (e.g., 'PROJ')
        ctx: The request context
        limit: Maximum number of issues to return (1-50)
        start: Start index for pagination

    Returns:
        List of project issues with metadata
    """
    if not ctx.lifespan_context.jira:
        return [{"error": "Jira is not configured"}]

    try:
        # Log the request
        logger.info(f"Getting issues for Jira project: {project_key}")

        # Get the issues
        documents = await ctx.lifespan_context.jira.get_project_issues(
            project_key=project_key, limit=limit, start=start
        )

        # Format the results
        results = []
        for doc in documents:
            results.append(doc.to_simplified_dict())

        return results
    except Exception as e:
        logger.error(f"Error getting Jira project issues: {e}")
        return [{"error": f"Error getting Jira project issues: {str(e)}"}]


@app.tool()
async def jira_delete_issue(issue_key: str, ctx: Context) -> dict[str, Any]:
    """
    Delete a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. 'PROJECT-123')
        ctx: The request context

    Returns:
        Status of the delete operation
    """
    if not ctx.lifespan_context.jira:
        return {"error": "Jira is not configured"}

    try:
        # Log the request
        logger.info(f"Deleting Jira issue: {issue_key}")

        # Delete the issue
        result = await ctx.lifespan_context.jira.delete_issue(issue_key=issue_key)

        if result:
            return {
                "success": True,
                "message": f"Issue {issue_key} deleted successfully",
            }
        else:
            return {"success": False, "error": f"Failed to delete issue {issue_key}"}
    except Exception as e:
        logger.error(f"Error deleting Jira issue {issue_key}: {e}")
        return {"error": f"Error deleting Jira issue: {str(e)}"}


@app.tool()
async def jira_add_worklog(
    issue_key: str,
    time_spent: str,
    ctx: Context,
    comment: str = "",
    start_time: str = Field(
        "",
        description="Optional start time in ISO format (e.g., '2023-01-01T09:00:00.000+0000')",
    ),
) -> dict[str, Any]:
    """
    Add a worklog entry to a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. 'PROJECT-123')
        time_spent: Time spent in Jira format (e.g., '1h 30m', '1d 2h', etc.)
        ctx: The request context
        comment: Optional comment for the worklog
        start_time: Optional start time in ISO format

    Returns:
        Status of the worklog addition
    """
    if not ctx.lifespan_context.jira:
        return {"error": "Jira is not configured"}

    try:
        # Log the request
        logger.info(f"Adding worklog to Jira issue {issue_key}: {time_spent}")

        # Add the worklog
        result = await ctx.lifespan_context.jira.add_worklog(
            issue_key=issue_key,
            time_spent=time_spent,
            comment=comment,
            start_time=start_time or None,
        )

        return {
            "success": True,
            "worklog_id": result.get("id", ""),
            "issue_key": issue_key,
            "time_spent": time_spent,
        }
    except Exception as e:
        logger.error(f"Error adding worklog to Jira issue {issue_key}: {e}")
        return {"error": f"Error adding worklog to Jira issue: {str(e)}"}


@app.tool()
async def jira_get_worklog(issue_key: str, ctx: Context) -> list[dict[str, Any]]:
    """
    Get all worklog entries for a Jira issue.

    Args:
        issue_key: Jira issue key (e.g. 'PROJECT-123')
        ctx: The request context

    Returns:
        List of worklog entries with metadata
    """
    if not ctx.lifespan_context.jira:
        return [{"error": "Jira is not configured"}]

    try:
        # Log the request
        logger.info(f"Getting worklogs for Jira issue: {issue_key}")

        # Get the worklogs
        worklogs = await ctx.lifespan_context.jira.get_worklogs(issue_key=issue_key)

        # Format the results
        formatted_worklogs = []
        for worklog in worklogs:
            formatted_worklogs.append(
                {
                    "id": worklog.get("id", ""),
                    "author": worklog.get("author", {}).get("displayName", "Unknown"),
                    "time_spent": worklog.get("timeSpent", ""),
                    "time_spent_seconds": worklog.get("timeSpentSeconds", 0),
                    "created": worklog.get("created", ""),
                    "updated": worklog.get("updated", ""),
                    "comment": worklog.get("comment", ""),
                }
            )

        return formatted_worklogs
    except Exception as e:
        logger.error(f"Error getting Jira worklogs for {issue_key}: {e}")
        return [{"error": f"Error getting Jira worklogs: {str(e)}"}]


@app.tool()
async def jira_link_to_epic(
    issue_key: str, epic_key: str, ctx: Context
) -> dict[str, Any]:
    """
    Link an issue to an epic in Jira.

    Args:
        issue_key: The issue key to link (e.g., 'PROJ-123')
        epic_key: The epic key to link to (e.g., 'PROJ-456')
        ctx: The request context

    Returns:
        Status of the linking operation
    """
    if not ctx.lifespan_context.jira:
        return {"error": "Jira is not configured"}

    try:
        # Log the request
        logger.info(f"Linking issue {issue_key} to epic {epic_key}")

        # Link the issue to the epic
        result = await ctx.lifespan_context.jira.link_issue_to_epic(
            issue_key=issue_key, epic_key=epic_key
        )

        return {
            "success": True,
            "issue_key": issue_key,
            "epic_key": epic_key,
            "link_type": "Epic-Story Link",
            "issue_title": result.metadata.get("title", ""),
            "status": result.metadata.get("status", ""),
        }
    except Exception as e:
        logger.error(f"Error linking issue {issue_key} to epic {epic_key}: {e}")
        return {"error": f"Error linking issue to epic: {str(e)}"}


@app.tool()
async def jira_get_epic_issues(
    epic_key: str,
    ctx: Context,
    limit: int = Field(
        10, description="Maximum number of issues to return (1-50)", ge=1, le=50
    ),
    start: int = Field(0, description="Start index for pagination"),
) -> list[dict[str, Any]]:
    """
    Get all issues linked to a specific epic in Jira.

    Args:
        epic_key: The epic key (e.g., 'PROJ-123')
        ctx: The request context
        limit: Maximum number of issues to return (1-50)
        start: Start index for pagination

    Returns:
        List of issues linked to the epic
    """
    if not ctx.lifespan_context.jira:
        return [{"error": "Jira is not configured"}]

    try:
        # Log the request
        logger.info(f"Getting issues for Jira epic: {epic_key}")

        # Get the epic issues
        documents = await ctx.lifespan_context.jira.get_epic_issues(
            epic_key=epic_key, limit=limit, start=start
        )

        # Format the results
        results = []
        for doc in documents:
            results.append(doc.to_simplified_dict())

        return results
    except Exception as e:
        logger.error(f"Error getting Jira epic issues for {epic_key}: {e}")
        return [{"error": f"Error getting Jira epic issues: {str(e)}"}]


# This is the entry point that will be called from __init__.py
def run_server() -> None:
    """Run the FastMCP server."""
    app.run()


if __name__ == "__main__":
    run_server()
