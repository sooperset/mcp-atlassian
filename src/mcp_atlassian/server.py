import json
import logging
import os
from collections.abc import Callable, Sequence
from typing import Any

from mcp.server import Server
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl

from .confluence import ConfluenceFetcher
from .document_types import Document
from .jira import JiraFetcher
from .preprocessing import markdown_to_confluence_storage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="mcp_atlassian_debug.log",
    filemode="a",
)
logger = logging.getLogger("mcp-atlassian")
logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.INFO)

# Type aliases for formatter functions
CommentFormatter = Callable[[dict[str, Any]], dict[str, Any]]
IssueFormatter = Callable[[Document], dict[str, Any]]
TransitionFormatter = Callable[[dict[str, Any]], dict[str, Any]]


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


# Initialize services based on available credentials
services = get_available_services()
confluence_fetcher = ConfluenceFetcher() if services["confluence"] else None
jira_fetcher = JiraFetcher() if services["jira"] else None
app = Server("mcp-atlassian")


@app.list_resources()
async def list_resources() -> list[Resource]:
    """List Confluence spaces and Jira projects the user is actively interacting with."""
    resources = []

    # Add Confluence spaces the user has contributed to
    if confluence_fetcher:
        try:
            # Get spaces the user has contributed to
            spaces = confluence_fetcher.get_user_contributed_spaces(limit=250)

            # Add spaces to resources
            resources.extend(
                [
                    Resource(
                        uri=AnyUrl(f"confluence://{space['key']}"),
                        name=f"Confluence Space: {space['name']}",
                        mimeType="text/plain",
                        description=(
                            f"A Confluence space containing documentation and knowledge base articles. "
                            f"Space Key: {space['key']}. "
                            f"{space.get('description', '')} "
                            f"Access content using: confluence://{space['key']}/pages/PAGE_TITLE"
                        ).strip(),
                    )
                    for space in spaces.values()
                ]
            )
        except KeyError as e:
            logger.error(f"Missing key in Confluence spaces data: {str(e)}")
        except ValueError as e:
            logger.error(f"Invalid value in Confluence spaces: {str(e)}")
        except TypeError as e:
            logger.error(f"Type error when processing Confluence spaces: {str(e)}")
        except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
            logger.error(f"Unexpected error fetching Confluence spaces: {str(e)}")
            logger.debug("Full exception details for Confluence spaces:", exc_info=True)

    # Add Jira projects the user is involved with
    if jira_fetcher:
        try:
            # Get current user's account ID
            account_id = jira_fetcher.get_current_user_account_id()

            # Use JQL to find issues the user is assigned to or reported
            jql = f"assignee = {account_id} OR reporter = {account_id} ORDER BY updated DESC"
            issues = jira_fetcher.jira.jql(jql, limit=250, fields=["project"])

            # Extract and deduplicate projects
            projects = {}
            for issue in issues.get("issues", []):
                project = issue.get("fields", {}).get("project", {})
                project_key = project.get("key")
                if project_key and project_key not in projects:
                    projects[project_key] = {
                        "key": project_key,
                        "name": project.get("name", project_key),
                        "description": project.get("description", ""),
                    }

            # Add projects to resources
            resources.extend(
                [
                    Resource(
                        uri=AnyUrl(f"jira://{project['key']}"),
                        name=f"Jira Project: {project['name']}",
                        mimeType="text/plain",
                        description=(
                            f"A Jira project tracking issues and tasks. Project Key: {project['key']}. "
                        ).strip(),
                    )
                    for project in projects.values()
                ]
            )
        except KeyError as e:
            logger.error(f"Missing key in Jira projects data: {str(e)}")
        except ValueError as e:
            logger.error(f"Invalid value in Jira projects: {str(e)}")
        except TypeError as e:
            logger.error(f"Type error when processing Jira projects: {str(e)}")
        except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
            logger.error(f"Unexpected error fetching Jira projects: {str(e)}")
            logger.debug("Full exception details for Jira projects:", exc_info=True)

    return resources


@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Read content from Confluence or Jira."""
    uri_str = str(uri)

    # Handle Confluence resources
    if uri_str.startswith("confluence://"):
        return _handle_confluence_resource(uri_str)

    # Handle Jira resources
    elif uri_str.startswith("jira://"):
        return _handle_jira_resource(uri_str)

    # Invalid resource URI
    error_msg = f"Invalid resource URI: {uri}"
    raise ValueError(error_msg)


def _handle_confluence_resource(uri_str: str) -> str:
    """
    Handle reading Confluence resources.

    Args:
        uri_str: The URI string for the Confluence resource

    Returns:
        The content of the resource

    Raises:
        ValueError: If Confluence is not configured or the resource is not found
    """
    if not services["confluence"]:
        error_msg = (
            "Confluence is not configured. Please provide Confluence credentials."
        )
        raise ValueError(error_msg)

    parts = uri_str.replace("confluence://", "").split("/")

    # Handle space listing
    if len(parts) == 1:
        return _handle_confluence_space(parts[0])

    # Handle specific page
    elif len(parts) >= 3 and parts[1] == "pages":
        return _handle_confluence_page(parts[0], parts[2])

    # Invalid Confluence resource
    error_msg = f"Invalid Confluence resource URI: {uri_str}"
    raise ValueError(error_msg)


def _handle_confluence_space(space_key: str) -> str:
    """
    Handle reading a Confluence space.

    Args:
        space_key: The key of the space to read

    Returns:
        Formatted content of pages in the space
    """
    # Use CQL to find recently updated pages in this space
    cql = f'space = "{space_key}" AND contributor = currentUser() ORDER BY lastmodified DESC'
    documents = confluence_fetcher.search(cql=cql, limit=20)

    if not documents:
        # Fallback to regular space pages if no user-contributed pages found
        documents = confluence_fetcher.get_space_pages(
            space_key, limit=10, convert_to_markdown=True
        )

    content = []
    for doc in documents:
        title = doc.metadata.get("title", "Untitled")
        url = doc.metadata.get("url", "")
        content.append(f"# [{title}]({url})\n\n{doc.page_content}\n\n---")

    return "\n\n".join(content)


def _handle_confluence_page(space_key: str, title: str) -> str:
    """
    Handle reading a specific Confluence page.

    Args:
        space_key: The key of the space containing the page
        title: The title of the page to read

    Returns:
        Content of the page

    Raises:
        ValueError: If the page is not found
    """
    doc = confluence_fetcher.get_page_by_title(space_key, title)
    if not doc:
        error_msg = f"Page not found: {title}"
        raise ValueError(error_msg)
    return doc.page_content


def _handle_jira_resource(uri_str: str) -> str:
    """
    Handle reading Jira resources.

    Args:
        uri_str: The URI string for the Jira resource

    Returns:
        The content of the resource

    Raises:
        ValueError: If Jira is not configured or the resource is not found
    """
    if not services["jira"]:
        error_msg = "Jira is not configured. Please provide Jira credentials."
        raise ValueError(error_msg)

    parts = uri_str.replace("jira://", "").split("/")

    # Handle project listing
    if len(parts) == 1:
        return _handle_jira_project(parts[0])

    # Handle specific issue
    elif len(parts) >= 3 and parts[1] == "issues":
        return _handle_jira_issue(parts[2])

    # Invalid Jira resource
    error_msg = f"Invalid Jira resource URI: {uri_str}"
    raise ValueError(error_msg)


def _handle_jira_project(project_key: str) -> str:
    """
    Handle reading a Jira project.

    Args:
        project_key: The key of the project to read

    Returns:
        Formatted content of issues in the project
    """
    # Get current user's account ID
    account_id = jira_fetcher.get_current_user_account_id()

    # Use JQL to find issues in this project that the user is involved with
    jql = f"project = {project_key} AND (assignee = {account_id} OR reporter = {account_id}) ORDER BY updated DESC"
    issues = jira_fetcher.search_issues(jql=jql, limit=20)

    if not issues:
        # Fallback to recent issues if no user-related issues found
        issues = jira_fetcher.get_project_issues(project_key, limit=10)

    content = []
    for issue in issues:
        key = issue.metadata.get("key", "")
        title = issue.metadata.get("title", "")
        url = issue.metadata.get("url", "")
        status = issue.metadata.get("status", "")
        content.append(
            f"# [{key}: {title}]({url})\nStatus: {status}\n\n{issue.page_content}\n\n---"
        )

    return "\n\n".join(content)


def _handle_jira_issue(issue_key: str) -> str:
    """
    Handle reading a specific Jira issue.

    Args:
        issue_key: The key of the issue to read

    Returns:
        Content of the issue
    """
    issue = jira_fetcher.get_issue(issue_key)
    return issue.page_content


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Confluence and Jira tools."""
    tools = []

    if confluence_fetcher:
        tools.extend(
            [
                Tool(
                    name="confluence_search",
                    description="Search Confluence content using CQL",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "CQL query string (e.g. 'type=page AND space=DEV')",
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="confluence_get_page",
                    description="Get content of a specific Confluence page by ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "Confluence page ID (numeric ID, can be parsed from URL, e.g. from 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title' -> '123456789')",
                            },
                            "include_metadata": {
                                "type": "boolean",
                                "description": "Whether to include page metadata",
                                "default": True,
                            },
                        },
                        "required": ["page_id"],
                    },
                ),
                Tool(
                    name="confluence_get_comments",
                    description="Get comments for a specific Confluence page",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "Confluence page ID (numeric ID, can be parsed from URL, e.g. from 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title' -> '123456789')",
                            }
                        },
                        "required": ["page_id"],
                    },
                ),
                Tool(
                    name="confluence_create_page",
                    description="Create a new Confluence page",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "space_key": {
                                "type": "string",
                                "description": "The key of the space to create the page in",
                            },
                            "title": {
                                "type": "string",
                                "description": "The title of the page",
                            },
                            "content": {
                                "type": "string",
                                "description": "The content of the page in Markdown format",
                            },
                            "parent_id": {
                                "type": "string",
                                "description": "Optional parent page ID",
                            },
                        },
                        "required": ["space_key", "title", "content"],
                    },
                ),
                Tool(
                    name="confluence_update_page",
                    description="Update an existing Confluence page",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "The ID of the page to update",
                            },
                            "title": {
                                "type": "string",
                                "description": "The new title of the page",
                            },
                            "content": {
                                "type": "string",
                                "description": "The new content of the page in Markdown format",
                            },
                            "minor_edit": {
                                "type": "boolean",
                                "description": "Whether this is a minor edit",
                                "default": False,
                            },
                            "version_comment": {
                                "type": "string",
                                "description": "Optional comment for this version",
                                "default": "",
                            },
                        },
                        "required": ["page_id", "title", "content"],
                    },
                ),
            ]
        )

    if jira_fetcher:
        tools.extend(
            [
                Tool(
                    name="jira_get_issue",
                    description="Get details of a specific Jira issue including its Epic links and relationship information",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {
                                "type": "string",
                                "description": "Jira issue key (e.g., 'PROJ-123')",
                            },
                            "expand": {
                                "type": "string",
                                "description": "Optional fields to expand. Examples: 'renderedFields' (for rendered content), 'transitions' (for available status transitions), 'changelog' (for history)",
                                "default": None,
                            },
                            "comment_limit": {
                                "type": "integer",
                                "description": "Maximum number of comments to include (0 or null for no comments)",
                                "minimum": 0,
                                "maximum": 100,
                                "default": None,
                            },
                        },
                        "required": ["issue_key"],
                    },
                ),
                Tool(
                    name="jira_search",
                    description="Search Jira issues using JQL (Jira Query Language)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "jql": {
                                "type": "string",
                                "description": "JQL query string. Examples:\n"
                                '- Find Epics: "issuetype = Epic AND project = PROJ"\n'
                                '- Find issues in Epic: "parent = PROJ-123"\n'
                                "- Find by status: \"status = 'In Progress' AND project = PROJ\"\n"
                                '- Find by assignee: "assignee = currentUser()"\n'
                                '- Find recently updated: "updated >= -7d AND project = PROJ"\n'
                                '- Find by label: "labels = frontend AND project = PROJ"',
                            },
                            "fields": {
                                "type": "string",
                                "description": "Comma-separated fields to return",
                                "default": "*all",
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                        },
                        "required": ["jql"],
                    },
                ),
                Tool(
                    name="jira_get_project_issues",
                    description="Get all issues for a specific Jira project",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_key": {
                                "type": "string",
                                "description": "The project key",
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                        },
                        "required": ["project_key"],
                    },
                ),
                Tool(
                    name="jira_create_issue",
                    description="Create a new Jira issue with optional Epic link",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_key": {
                                "type": "string",
                                "description": "The JIRA project key (e.g. 'PROJ'). Never assume what it might be, always ask the user.",
                            },
                            "summary": {
                                "type": "string",
                                "description": "Summary/title of the issue",
                            },
                            "issue_type": {
                                "type": "string",
                                "description": "Issue type (e.g. 'Task', 'Bug', 'Story')",
                            },
                            "assignee": {
                                "type": "string",
                                "description": "Assignee of the ticket (accountID, full name or e-mail)",
                            },
                            "description": {
                                "type": "string",
                                "description": "Issue description",
                                "default": "",
                            },
                            "additional_fields": {
                                "type": "string",
                                "description": "Optional JSON string of additional fields to set. Examples:\n"
                                '- Link to Epic: {"parent": {"key": "PROJ-123"}} - For linking to an Epic after creation, prefer using the jira_link_to_epic tool instead\n'
                                '- Set priority: {"priority": {"name": "High"}} or {"priority": null} for no priority (common values: High, Medium, Low, None)\n'
                                '- Add labels: {"labels": ["label1", "label2"]}\n'
                                '- Set due date: {"duedate": "2023-12-31"}\n'
                                '- Custom fields: {"customfield_10XXX": "value"}',
                                "default": "{}",
                            },
                        },
                        "required": ["project_key", "summary", "issue_type"],
                    },
                ),
                Tool(
                    name="jira_update_issue",
                    description="Update an existing Jira issue including changing status, adding Epic links, updating fields, etc.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {
                                "type": "string",
                                "description": "Jira issue key (e.g., 'PROJ-123')",
                            },
                            "fields": {
                                "type": "string",
                                "description": "A valid JSON object of fields to update. Examples:\n"
                                '- Add to Epic: {"parent": {"key": "PROJ-456"}} - Prefer using the dedicated jira_link_to_epic tool instead\n'
                                '- Change assignee: {"assignee": "user@email.com"} or {"assignee": null} to unassign\n'
                                '- Update summary: {"summary": "New title"}\n'
                                '- Update description: {"description": "New description"}\n'
                                "- Change status: requires transition IDs - use jira_get_transitions and jira_transition_issue instead\n"
                                '- Add labels: {"labels": ["label1", "label2"]}\n'
                                '- Set priority: {"priority": {"name": "High"}} or {"priority": null} for no priority (common values: High, Medium, Low, None)\n'
                                '- Update custom fields: {"customfield_10XXX": "value"}',
                            },
                            "additional_fields": {
                                "type": "string",
                                "description": "Optional JSON string of additional fields to update",
                                "default": "{}",
                            },
                        },
                        "required": ["issue_key", "fields"],
                    },
                ),
                Tool(
                    name="jira_delete_issue",
                    description="Delete an existing Jira issue",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {
                                "type": "string",
                                "description": "Jira issue key (e.g. PROJ-123)",
                            },
                        },
                        "required": ["issue_key"],
                    },
                ),
                Tool(
                    name="jira_add_comment",
                    description="Add a comment to a Jira issue",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {
                                "type": "string",
                                "description": "Jira issue key (e.g., 'PROJ-123')",
                            },
                            "comment": {
                                "type": "string",
                                "description": "Comment text in Markdown format",
                            },
                        },
                        "required": ["issue_key", "comment"],
                    },
                ),
                Tool(
                    name="jira_add_worklog",
                    description="Add a worklog entry to a Jira issue",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {
                                "type": "string",
                                "description": "Jira issue key (e.g., 'PROJ-123')",
                            },
                            "time_spent": {
                                "type": "string",
                                "description": "Time spent in Jira format (e.g., '1h 30m', '1d', '30m')",
                            },
                            "comment": {
                                "type": "string",
                                "description": "Optional comment for the worklog in Markdown format",
                            },
                            "started": {
                                "type": "string",
                                "description": "Optional start time in ISO format (e.g. '2023-08-01T12:00:00.000+0000'). If not provided, current time will be used.",
                            },
                            "original_estimate": {
                                "type": "string",
                                "description": "Optional original estimate in Jira format (e.g., '1h 30m', '1d'). This will update the original estimate for the issue.",
                            },
                            "remaining_estimate": {
                                "type": "string",
                                "description": "Optional remaining estimate in Jira format (e.g., '1h', '30m'). This will update the remaining estimate for the issue.",
                            },
                        },
                        "required": ["issue_key", "time_spent"],
                    },
                ),
                Tool(
                    name="jira_get_worklog",
                    description="Get worklog entries for a Jira issue",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {
                                "type": "string",
                                "description": "Jira issue key (e.g., 'PROJ-123')",
                            },
                        },
                        "required": ["issue_key"],
                    },
                ),
                Tool(
                    name="jira_link_to_epic",
                    description="Link an existing issue to an epic",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {
                                "type": "string",
                                "description": "The key of the issue to link (e.g., 'PROJ-123')",
                            },
                            "epic_key": {
                                "type": "string",
                                "description": "The key of the epic to link to (e.g., 'PROJ-456')",
                            },
                        },
                        "required": ["issue_key", "epic_key"],
                    },
                ),
                Tool(
                    name="jira_get_epic_issues",
                    description="Get all issues linked to a specific epic",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "epic_key": {
                                "type": "string",
                                "description": "The key of the epic (e.g., 'PROJ-123')",
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of issues to return (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                        },
                        "required": ["epic_key"],
                    },
                ),
                Tool(
                    name="jira_get_transitions",
                    description="Get available status transitions for a Jira issue",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {
                                "type": "string",
                                "description": "Jira issue key (e.g., 'PROJ-123')",
                            },
                        },
                        "required": ["issue_key"],
                    },
                ),
                Tool(
                    name="jira_transition_issue",
                    description="Transition a Jira issue to a new status",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {
                                "type": "string",
                                "description": "Jira issue key (e.g., 'PROJ-123')",
                            },
                            "transition_id": {
                                "type": "string",
                                "description": "ID of the transition to perform (get this from jira_get_transitions)",
                            },
                            "fields": {
                                "type": "string",
                                "description": "JSON string of fields to update during the transition (optional)",
                                "default": "{}",
                            },
                            "comment": {
                                "type": "string",
                                "description": "Comment to add during the transition (optional)",
                            },
                        },
                        "required": ["issue_key", "transition_id"],
                    },
                ),
            ]
        )

    return tools


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent]:
    """Handle tool calls for Confluence and Jira operations."""
    try:
        # Helper functions for formatting results
        def format_comment(comment: dict) -> dict:
            """
            Format a Jira comment for display.

            Args:
                comment: The raw comment dictionary from Jira

            Returns:
                Formatted comment dictionary with selected fields
            """
            return {
                "id": comment.get("id"),
                "author": comment.get("author", {}).get("displayName", "Unknown"),
                "created": comment.get("created"),
                "body": comment.get("body"),
            }

        def format_issue(doc: Document) -> dict:
            """
            Format a Jira issue document for display.

            Args:
                doc: The Document object containing issue data

            Returns:
                Formatted issue dictionary with selected fields
            """
            return {
                "key": doc.metadata.get("key", ""),
                "title": doc.metadata.get("title", ""),
                "type": doc.metadata.get("type", "Unknown"),
                "status": doc.metadata.get("status", "Unknown"),
                "created_date": doc.metadata.get("created_date", ""),
                "priority": doc.metadata.get("priority", "None"),
                "link": doc.metadata.get("link", ""),
            }

        def format_transition(transition: dict) -> dict:
            """
            Format a Jira transition for display.

            Args:
                transition: The raw transition dictionary from Jira

            Returns:
                Formatted transition dictionary with selected fields
            """
            return {
                "id": transition.get("id", ""),
                "name": transition.get("name", ""),
                "to_status": transition.get("to", {}).get("name", "Unknown"),
            }

        # Handle different tools
        if name.startswith("jira"):
            if jira_fetcher is None:
                error_msg = "Jira is not configured. Please set JIRA_URL, JIRA_USERNAME, and JIRA_API_TOKEN environment variables."
                logger.error(error_msg)
                return [TextContent(type="text", text=error_msg)]

        elif name.startswith("confluence"):
            if confluence_fetcher is None:
                error_msg = "Confluence is not configured. Please set CONFLUENCE_URL, CONFLUENCE_USERNAME, and CONFLUENCE_API_TOKEN environment variables."
                logger.error(error_msg)
                return [TextContent(type="text", text=error_msg)]

        # Tool routing
        if name == "jira_get_issue":
            return handle_jira_get_issue(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_search":
            return handle_jira_search(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_get_project_issues":
            return handle_jira_get_project_issues(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_create_issue":
            return handle_jira_create_issue(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_update_issue":
            return handle_jira_update_issue(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_delete_issue":
            return handle_jira_delete_issue(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_add_comment":
            return handle_jira_add_comment(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_add_worklog":
            return handle_jira_add_worklog(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_get_worklog":
            return handle_jira_get_worklog(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_get_transitions":
            return handle_jira_get_transitions(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_transition_issue":
            return handle_jira_transition_issue(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_link_to_epic":
            return handle_jira_link_to_epic(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "jira_get_epic_issues":
            return handle_jira_get_epic_issues(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "confluence_search":
            return handle_confluence_search(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "confluence_get_page":
            return handle_confluence_get_page(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "confluence_get_comments":
            return handle_confluence_get_comments(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "confluence_create_page":
            return handle_confluence_create_page(
                arguments, format_comment, format_issue, format_transition
            )
        elif name == "confluence_update_page":
            return handle_confluence_update_page(
                arguments, format_comment, format_issue, format_transition
            )
        else:
            error_msg = f"Unknown tool: {name}"
            logger.error(error_msg)
            return [TextContent(type="text", text=error_msg)]

    except Exception as e:
        error_msg = f"Error handling tool call: {str(e)}"
        logger.error(error_msg)
        logger.debug("Full exception details:", exc_info=True)
        return [TextContent(type="text", text=error_msg)]


def handle_confluence_search(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle confluence_search tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Search results
    """
    # Ensure Confluence is configured
    if confluence_fetcher is None:
        return [
            TextContent(
                text="Confluence is not configured. Please set CONFLUENCE_URL, CONFLUENCE_USERNAME, and CONFLUENCE_API_TOKEN environment variables.",
                type="text",
            )
        ]

    query = arguments["query"]
    limit = arguments.get("limit", 10)

    try:
        results = confluence_fetcher.search(query, limit=limit)
        # Convert results to a list of dictionaries for JSON serialization
        formatted_results = []
        for doc in results:
            formatted_results.append(
                {
                    "title": doc.metadata.get("title", ""),
                    "page_id": doc.metadata.get("page_id", ""),
                    "space": doc.metadata.get("space", ""),
                    "url": doc.metadata.get("url", ""),
                    "last_modified": doc.metadata.get("last_modified", ""),
                    "excerpt": doc.page_content,
                }
            )
        return [
            TextContent(
                type="text",
                text=json.dumps(formatted_results, indent=2, ensure_ascii=False),
            )
        ]
    except KeyError as e:
        error_msg = f"Missing key in search parameters or results: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]
    except ValueError as e:
        error_msg = f"Invalid search parameter: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]
    except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
        error_msg = f"Unexpected error searching Confluence: {str(e)}"
        logger.error(error_msg)
        logger.debug("Full exception details for Confluence search:", exc_info=True)
        return [TextContent(type="text", text=error_msg)]


def handle_confluence_get_page(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle confluence_get_page tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted page content
    """
    doc = confluence_fetcher.get_page_content(arguments["page_id"])
    include_metadata = arguments.get("include_metadata", True)

    if include_metadata:
        result = {"content": doc.page_content, "metadata": doc.metadata}
    else:
        result = {"content": doc.page_content}

    return [
        TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
    ]


def handle_confluence_get_comments(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle confluence_get_comments tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted comments
    """
    comments = confluence_fetcher.get_page_comments(
        page_id=arguments["page_id"], return_markdown=True
    )
    # Convert Document objects to dictionaries for the formatter
    formatted_comments = [format_comment(doc.metadata) for doc in comments]

    return [
        TextContent(
            type="text",
            text=json.dumps(formatted_comments, indent=2, ensure_ascii=False),
        )
    ]


def handle_confluence_create_page(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle confluence_create_page tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted page creation result
    """
    # Convert markdown content to HTML storage format
    space_key = arguments["space_key"]
    title = arguments["title"]
    content = arguments["content"]
    parent_id = arguments.get("parent_id")

    # Convert markdown to Confluence storage format
    storage_format = markdown_to_confluence_storage(content)

    # Handle parent_id - convert to string if not None
    parent_id_str: str | None = str(parent_id) if parent_id is not None else None

    # Create the page
    doc = confluence_fetcher.create_page(
        space_key=space_key,
        title=title,
        body=storage_format,  # Now using the converted storage format
        parent_id=parent_id_str,
    )

    result = {
        "page_id": doc.metadata["page_id"],
        "title": doc.metadata["title"],
        "space_key": doc.metadata["space_key"],
        "url": doc.metadata["url"],
        "version": doc.metadata["version"],
        "content": doc.page_content[:500] + "..."
        if len(doc.page_content) > 500
        else doc.page_content,
    }

    return [
        TextContent(
            type="text",
            text=f"Page created successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
        )
    ]


def handle_confluence_update_page(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle confluence_update_page tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted page update result
    """
    page_id = arguments["page_id"]
    title = arguments["title"]
    content = arguments["content"]
    minor_edit = arguments.get("minor_edit", False)
    version_comment = arguments.get("version_comment", "")

    # Convert markdown to Confluence storage format
    storage_format = markdown_to_confluence_storage(content)

    # Update the page
    doc = confluence_fetcher.update_page(
        page_id=page_id,
        title=title,
        body=storage_format,
        is_minor_edit=minor_edit,
        version_comment=version_comment,
    )

    result = {
        "page_id": doc.metadata["page_id"],
        "title": doc.metadata["title"],
        "space_key": doc.metadata["space_key"],
        "url": doc.metadata["url"],
        "version": doc.metadata["version"],
        "content": doc.page_content[:500] + "..."
        if len(doc.page_content) > 500
        else doc.page_content,
    }

    return [
        TextContent(
            type="text",
            text=f"Page updated successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
        )
    ]


def handle_jira_get_issue(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_get_issue tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted issue content
    """
    try:
        issue_key = arguments["issue_key"]
        doc = jira_fetcher.get_issue(issue_key=issue_key)
        return [TextContent(type="text", text=format_issue(doc))]
    except KeyError as e:
        error_msg = f"Missing required argument: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]
    except ValueError as e:
        error_msg = f"Invalid argument value: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]
    except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
        error_msg = f"Unexpected error getting Jira issue {arguments.get('issue_key')}: {str(e)}"
        logger.error(error_msg)
        logger.debug("Full exception details:", exc_info=True)
        return [TextContent(type="text", text=error_msg)]


def handle_jira_search(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_search tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted search results
    """
    try:
        jql = arguments["query"]
        limit = min(int(arguments.get("limit", 10)), 50)
        start = int(arguments.get("start", 0))

        documents = jira_fetcher.search_issues(jql=jql, limit=limit, start=start)
        results = [format_issue(doc) for doc in documents]

        return [
            TextContent(
                type="text", text=json.dumps(results, indent=2, ensure_ascii=False)
            )
        ]
    except KeyError as e:
        error_msg = f"Missing required parameter: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]
    except Exception as e:
        error_msg = f"Error executing JQL search: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


def handle_jira_get_project_issues(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_get_project_issues tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted project issues
    """
    project_key = arguments["project_key"]
    limit = min(int(arguments.get("limit", 10)), 50)
    start = int(arguments.get("start", 0))

    documents = jira_fetcher.get_project_issues(
        project_key=project_key, limit=limit, start=start
    )
    results = [format_issue(doc) for doc in documents]

    return [
        TextContent(type="text", text=json.dumps(results, indent=2, ensure_ascii=False))
    ]


def handle_jira_create_issue(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_create_issue tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted issue creation result
    """
    try:
        # Extract required arguments
        project_key = arguments["project_key"]
        summary = arguments["summary"]
        issue_type = arguments["issue_type"]

        # Extract optional arguments
        description = arguments.get("description", "")
        assignee = arguments.get("assignee")

        # Create a shallow copy of arguments without the standard fields
        # to pass any remaining ones as custom fields
        custom_fields = arguments.copy()
        for field in [
            "project_key",
            "summary",
            "issue_type",
            "description",
            "assignee",
        ]:
            custom_fields.pop(field, None)

        # Create the issue
        doc = jira_fetcher.create_issue(
            project_key=project_key,
            summary=summary,
            issue_type=issue_type,
            description=description,
            assignee=assignee,
            **custom_fields,
        )

        result = format_issue(doc)
        result["description"] = doc.page_content

        return [
            TextContent(
                type="text",
                text=f"Issue created successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
            )
        ]
    except KeyError as e:
        error_msg = f"Missing required parameter: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]
    except Exception as e:
        error_msg = f"Error creating issue: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


def handle_jira_update_issue(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_update_issue tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted issue update result
    """
    try:
        # Extract issue key
        issue_key = arguments["issue_key"]

        # Create a shallow copy of arguments without the issue_key
        fields = arguments.copy()
        fields.pop("issue_key", None)

        # Update the issue
        doc = jira_fetcher.update_issue(issue_key=issue_key, **fields)

        result = format_issue(doc)
        result["description"] = doc.page_content

        return [
            TextContent(
                type="text",
                text=f"Issue updated successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
            )
        ]
    except KeyError as e:
        error_msg = f"Missing required parameter: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]
    except Exception as e:
        error_msg = f"Error updating issue: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


def handle_jira_delete_issue(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_delete_issue tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Deletion confirmation
    """
    issue_key = arguments["issue_key"]
    success = jira_fetcher.delete_issue(issue_key)

    if success:
        return [
            TextContent(
                type="text",
                text=f"Issue {issue_key} deleted successfully.",
            )
        ]
    else:
        return [
            TextContent(
                type="text",
                text=f"Failed to delete issue {issue_key}.",
            )
        ]


def handle_jira_add_comment(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_add_comment tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Comment addition confirmation
    """
    try:
        issue_key = arguments["issue_key"]
        comment_text = arguments["comment"]

        result = jira_fetcher.add_comment(issue_key, comment_text)
        formatted_result = format_comment(result)

        return [
            TextContent(
                type="text",
                text=f"Comment added successfully:\n{json.dumps(formatted_result, indent=2, ensure_ascii=False)}",
            )
        ]
    except KeyError as e:
        error_msg = f"Missing required parameter: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]
    except Exception as e:
        error_msg = f"Error adding comment: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


def handle_jira_add_worklog(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_add_worklog tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Worklog addition confirmation
    """
    # Ensure Jira is configured
    if jira_fetcher is None:
        return [
            TextContent(
                text="Jira is not configured. Please set JIRA_URL, JIRA_USERNAME, and JIRA_API_TOKEN environment variables.",
                type="text",
            )
        ]

    issue_key = arguments["issue_key"]
    time_spent = arguments["time_spent"]

    # Process optional parameters with proper type checking
    comment = arguments.get("comment")
    if comment is not None and not isinstance(comment, str):
        comment = str(comment)

    started = arguments.get("started")
    if started is not None and not isinstance(started, str):
        started = str(started)

    original_estimate = arguments.get("original_estimate")
    if original_estimate is not None and not isinstance(original_estimate, str):
        original_estimate = str(original_estimate)

    remaining_estimate = arguments.get("remaining_estimate")
    if remaining_estimate is not None and not isinstance(remaining_estimate, str):
        remaining_estimate = str(remaining_estimate)

    try:
        result = jira_fetcher.add_worklog(
            issue_key=issue_key,
            time_spent=time_spent,
            comment=comment,
            started=started,
            original_estimate=original_estimate,
            remaining_estimate=remaining_estimate,
        )

        return [
            TextContent(
                type="text",
                text=f"Worklog added successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
            )
        ]
    except KeyError as e:
        error_msg = f"Missing required field for worklog on {issue_key}: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]
    except ValueError as e:
        error_msg = f"Invalid value for worklog parameter on {issue_key}: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]
    except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
        error_msg = f"Unexpected error adding worklog to {issue_key}: {str(e)}"
        logger.error(error_msg)
        logger.debug(
            f"Full exception details for worklog on {issue_key}:", exc_info=True
        )
        return [TextContent(type="text", text=error_msg)]


def handle_jira_get_worklog(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_get_worklog tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted worklog entries
    """
    issue_key = arguments["issue_key"]
    worklogs = jira_fetcher.get_worklogs(issue_key)

    return [
        TextContent(
            type="text",
            text=json.dumps(worklogs, indent=2, ensure_ascii=False),
        )
    ]


def handle_jira_get_transitions(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_get_transitions tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted transition options
    """
    issue_key = arguments["issue_key"]
    transitions = jira_fetcher.get_available_transitions(issue_key)
    formatted_transitions = [format_transition(t) for t in transitions]

    return [
        TextContent(
            type="text",
            text=json.dumps(formatted_transitions, indent=2, ensure_ascii=False),
        )
    ]


def handle_jira_transition_issue(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_transition_issue tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Transition confirmation
    """
    issue_key = arguments["issue_key"]
    transition_id = arguments["transition_id"]

    # Optional arguments
    fields = arguments.get("fields")
    comment = arguments.get("comment")

    # Transition the issue
    doc = jira_fetcher.transition_issue(
        issue_key=issue_key,
        transition_id=transition_id,
        fields=fields,
        comment=comment,
    )

    result = format_issue(doc)
    result["description"] = doc.page_content

    return [
        TextContent(
            type="text",
            text=f"Issue transitioned successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
        )
    ]


def handle_jira_link_to_epic(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_link_to_epic tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Link confirmation
    """
    issue_key = arguments["issue_key"]
    epic_key = arguments["epic_key"]

    doc = jira_fetcher.link_issue_to_epic(issue_key, epic_key)
    result = format_issue(doc)
    result["description"] = doc.page_content
    result["epic_key"] = epic_key

    return [
        TextContent(
            type="text",
            text=f"Issue linked to epic successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
        )
    ]


def handle_jira_get_epic_issues(
    arguments: dict[str, Any],
    format_comment: CommentFormatter,
    format_issue: IssueFormatter,
    format_transition: TransitionFormatter,
) -> Sequence[TextContent]:
    """
    Handle jira_get_epic_issues tool.

    Args:
        arguments: The tool arguments
        format_comment: Helper function for formatting comments
        format_issue: Helper function for formatting issues
        format_transition: Helper function for formatting transitions

    Returns:
        Formatted epic issues
    """
    epic_key = arguments["epic_key"]
    limit = min(int(arguments.get("limit", 50)), 100)

    documents = jira_fetcher.get_epic_issues(epic_key, limit)
    results = [format_issue(doc) for doc in documents]

    return [
        TextContent(
            type="text",
            text=json.dumps(results, indent=2, ensure_ascii=False),
        )
    ]


async def main() -> None:
    """
    Run the MCP server in stdio mode.

    This function creates and runs the MCP server using the stdio interface,
    which enables communication with the MCP client through standard input/output.

    Returns:
        None
    """
    # Import here to avoid issues with event loops
    from mcp.server.stdio import stdio_server

    try:
        # Log the startup information
        logger.info("Starting MCP Atlassian server")
        if confluence_fetcher:
            logger.info(f"Confluence URL: {confluence_fetcher.config.url}")
        if jira_fetcher:
            logger.info(f"Jira URL: {jira_fetcher.config.url}")

        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream, write_stream, app.create_initialization_options()
            )
    except Exception as err:
        logger.error(f"Error running server: {err}")
        error_msg = f"Failed to run server: {err}"
        raise RuntimeError(error_msg) from err


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
