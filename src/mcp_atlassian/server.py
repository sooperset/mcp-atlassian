import json
import logging
import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

from atlassian.errors import ApiError
from mcp.server import Server
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl
from requests.exceptions import RequestException

from .confluence import ConfluenceFetcher
from .confluence.utils import quote_cql_identifier_if_needed
from .jira import JiraFetcher
from .jira.utils import escape_jql_string
from .utils.io import is_read_only_mode
from .utils.urls import is_atlassian_cloud_url

# Configure logging
logger = logging.getLogger("mcp-atlassian")


@dataclass
class AppContext:
    """Application context for MCP Atlassian."""

    confluence: ConfluenceFetcher | None = None
    jira: JiraFetcher | None = None


def get_available_services() -> dict[str, bool | None]:
    """Determine which services are available based on environment variables."""

    # Check for either cloud authentication (URL + username + API token)
    # or server/data center authentication (URL + ( personal token or username + API token ))
    confluence_url = os.getenv("CONFLUENCE_URL")
    if confluence_url:
        is_cloud = is_atlassian_cloud_url(confluence_url)

        if is_cloud:
            confluence_is_setup = all(
                [
                    confluence_url,
                    os.getenv("CONFLUENCE_USERNAME"),
                    os.getenv("CONFLUENCE_API_TOKEN"),
                ]
            )
            logger.info("Using Confluence Cloud authentication method")
        else:
            confluence_is_setup = all(
                [
                    confluence_url,
                    os.getenv("CONFLUENCE_PERSONAL_TOKEN")
                    # Some on prem/data center use username and api token too.
                    or (
                        os.getenv("CONFLUENCE_USERNAME")
                        and os.getenv("CONFLUENCE_API_TOKEN")
                    ),
                ]
            )
            logger.info("Using Confluence Server/Data Center authentication method")
    else:
        confluence_is_setup = False

    # Check for either cloud authentication (URL + username + API token)
    # or server/data center authentication (URL + personal token)
    jira_url = os.getenv("JIRA_URL")
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
    else:
        jira_is_setup = False

    return {"confluence": confluence_is_setup, "jira": jira_is_setup}


@asynccontextmanager
async def server_lifespan(server: Server) -> AsyncIterator[AppContext]:
    """Initialize and clean up application resources."""
    # Get available services
    services = get_available_services()

    try:
        # Initialize services
        confluence = ConfluenceFetcher() if services["confluence"] else None
        jira = JiraFetcher() if services["jira"] else None

        # Log the startup information
        logger.info("Starting MCP Atlassian server")

        # Log read-only mode status
        read_only = is_read_only_mode()
        logger.info(f"Read-only mode: {'ENABLED' if read_only else 'DISABLED'}")

        if confluence:
            confluence_url = confluence.config.url
            logger.info(f"Confluence URL: {confluence_url}")
        if jira:
            jira_url = jira.config.url
            logger.info(f"Jira URL: {jira_url}")

        # Provide context to the application
        yield AppContext(confluence=confluence, jira=jira)
    finally:
        # Cleanup resources if needed
        pass


# Create server instance
app = Server("mcp-atlassian", lifespan=server_lifespan)


# Implement server handlers
@app.list_resources()
async def list_resources() -> list[Resource]:
    """List Confluence spaces and Jira projects the user is actively interacting with."""
    resources = []

    ctx = app.request_context.lifespan_context

    # Add Confluence spaces the user has contributed to
    if ctx and ctx.confluence:
        try:
            # Get spaces the user has contributed to
            spaces = ctx.confluence.get_user_contributed_spaces(limit=250)

            # Add spaces to resources
            resources.extend(
                [
                    Resource(
                        uri=f"confluence://{space['key']}",
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
        except Exception as e:
            logger.error(f"Error fetching Confluence spaces: {str(e)}")

    # Add Jira projects the user is involved with
    if ctx and ctx.jira:
        try:
            # Get current user's account ID
            account_id = ctx.jira.get_current_user_account_id()

            # Escape the account ID for safe JQL insertion
            escaped_account_id = escape_jql_string(account_id)

            # Use JQL to find issues the user is assigned to or reported, using the escaped ID
            # Note: We use the escaped_account_id directly, as it already includes the necessary quotes.
            jql = f"assignee = {escaped_account_id} OR reporter = {escaped_account_id} ORDER BY updated DESC"
            logger.debug(f"Executing JQL for list_resources: {jql}")
            issues = ctx.jira.jira.jql(jql, limit=250, fields=["project"])

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
                        uri=f"jira://{project['key']}",
                        name=f"Jira Project: {project['name']}",
                        mimeType="text/plain",
                        description=(
                            f"A Jira project tracking issues and tasks. Project Key: {project['key']}. "
                        ).strip(),
                    )
                    for project in projects.values()
                ]
            )
        except Exception as e:
            logger.error(f"Error fetching Jira projects: {e}", exc_info=True)

    return resources


@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Read content from Confluence based on the resource URI."""

    # Get application context
    ctx = app.request_context.lifespan_context

    # Handle Confluence resources
    if str(uri).startswith("confluence://"):
        if not ctx or not ctx.confluence:
            raise ValueError(
                "Confluence is not configured. Please provide Confluence credentials."
            )
        parts = str(uri).replace("confluence://", "").split("/")

        # Handle space listing
        if len(parts) == 1:
            space_key = parts[0]

            # Apply the fix here - properly quote the space key
            quoted_space_key = quote_cql_identifier_if_needed(space_key)

            # Use CQL to find recently updated pages in this space
            cql = f"space = {quoted_space_key} AND contributor = currentUser() ORDER BY lastmodified DESC"
            pages = ctx.confluence.search(cql=cql, limit=20)

            if not pages:
                # Fallback to regular space pages if no user-contributed pages found
                pages = ctx.confluence.get_space_pages(space_key, limit=10)

            content = []
            for page in pages:
                page_dict = page.to_simplified_dict()
                title = page_dict.get("title", "Untitled")
                url = page_dict.get("url", "")

                content.append(f"# [{title}]({url})\n\n{page.page_content}\n\n---")

            return "\n\n".join(content)

        # Handle specific page
        elif len(parts) >= 3 and parts[1] == "pages":
            space_key = parts[0]
            title = parts[2]
            page = ctx.confluence.get_page_by_title(space_key, title)

            if not page:
                raise ValueError(f"Page not found: {title}")

            return page.page_content

    # Handle Jira resources
    elif str(uri).startswith("jira://"):
        if not ctx or not ctx.jira:
            raise ValueError("Jira is not configured. Please provide Jira credentials.")
        parts = str(uri).replace("jira://", "").split("/")

        # Handle project listing
        if len(parts) == 1:
            project_key = parts[0]

            # Get current user's account ID
            account_id = ctx.jira.get_current_user_account_id()

            # Use JQL to find issues in this project that the user is involved with
            jql = f"project = {project_key} AND (assignee = {account_id} OR reporter = {account_id}) ORDER BY updated DESC"
            issues = ctx.jira.search_issues(jql=jql, limit=20)

            if not issues:
                # Fallback to recent issues if no user-related issues found
                issues = ctx.jira.get_project_issues(project_key, limit=10)

            content = []
            for issue in issues:
                issue_dict = issue.to_simplified_dict()
                key = issue_dict.get("key", "")
                summary = issue_dict.get("summary", "Untitled")
                url = issue_dict.get("url", "")
                status = issue_dict.get("status", {})
                status_name = status.get("name", "Unknown") if status else "Unknown"

                # Create a markdown representation of the issue
                issue_content = (
                    f"# [{key}: {summary}]({url})\nStatus: {status_name}\n\n"
                )
                if issue_dict.get("description"):
                    issue_content += f"{issue_dict.get('description')}\n\n"

                content.append(f"{issue_content}---")

            return "\n\n".join(content)

        # Handle specific issue
        elif len(parts) >= 2:
            issue_key = parts[1] if len(parts) > 1 else parts[0]
            issue = ctx.jira.get_issue(issue_key)

            if not issue:
                raise ValueError(f"Issue not found: {issue_key}")

            issue_dict = issue.to_simplified_dict()
            markdown = f"# {issue_dict.get('key')}: {issue_dict.get('summary')}\n\n"

            if issue_dict.get("status"):
                status_name = issue_dict.get("status", {}).get("name", "Unknown")
                markdown += f"**Status:** {status_name}\n\n"

            if issue_dict.get("description"):
                markdown += f"{issue_dict.get('description')}\n\n"

            return markdown

    raise ValueError(f"Invalid resource URI: {uri}")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Confluence and Jira tools."""
    tools = []
    ctx = app.request_context.lifespan_context

    # Check if we're in read-only mode
    read_only = is_read_only_mode()

    # Add Confluence tools if Confluence is configured
    if ctx and ctx.confluence:
        # Always add read operations
        tools.extend(
            [
                Tool(
                    name="confluence_search",
                    description="Search Confluence content using simple terms or CQL",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query - can be either a simple text (e.g. 'project documentation') or a CQL query string. Examples of CQL:\n"
                                "- Basic search: 'type=page AND space=DEV'\n"
                                "- Personal space search: 'space=\"~username\"' (note: personal space keys starting with ~ must be quoted)\n"
                                "- Search by title: 'title~\"Meeting Notes\"'\n"
                                "- Recent content: 'created >= \"2023-01-01\"'\n"
                                "- Content with specific label: 'label=documentation'\n"
                                "- Recently modified content: 'lastModified > startOfMonth(\"-1M\")'\n"
                                "- Content modified this year: 'creator = currentUser() AND lastModified > startOfYear()'\n"
                                "- Content you contributed to recently: 'contributor = currentUser() AND lastModified > startOfWeek()'\n"
                                "- Content watched by user: 'watcher = \"user@domain.com\" AND type = page'\n"
                                '- Exact phrase in content: \'text ~ "\\"Urgent Review Required\\"" AND label = "pending-approval"\'\n'
                                '- Title wildcards: \'title ~ "Minutes*" AND (space = "HR" OR space = "Marketing")\'\n'
                                'Note: Special identifiers need proper quoting in CQL: personal space keys (e.g., "~username"), reserved words, numeric IDs, and identifiers with special characters.',
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                            "spaces_filter": {
                                "type": "string",
                                "description": "Comma-separated list of space keys to filter results by. Overrides the environment variable CONFLUENCE_SPACES_FILTER if provided.",
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
                                "description": "Confluence page ID (numeric ID, can be found in the page URL). "
                                "For example, in the URL 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title', "
                                "the page ID is '123456789'",
                            },
                            "include_metadata": {
                                "type": "boolean",
                                "description": "Whether to include page metadata such as creation date, last update, version, and labels",
                                "default": True,
                            },
                            "convert_to_markdown": {
                                "type": "boolean",
                                "description": "Whether to convert page to markdown (true) or keep it in raw HTML format (false). Raw HTML can reveal macros (like dates) not visible in markdown, but CAUTION: using HTML significantly increases token usage in AI responses.",
                                "default": True,
                            },
                        },
                        "required": ["page_id"],
                    },
                ),
                Tool(
                    name="confluence_get_page_children",
                    description="Get child pages of a specific Confluence page",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "parent_id": {
                                "type": "string",
                                "description": "The ID of the parent page whose children you want to retrieve",
                            },
                            "expand": {
                                "type": "string",
                                "description": "Fields to expand in the response (e.g., 'version', 'body.storage')",
                                "default": "version",
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of child pages to return (1-50)",
                                "default": 25,
                                "minimum": 1,
                                "maximum": 50,
                            },
                            "include_content": {
                                "type": "boolean",
                                "description": "Whether to include the page content in the response",
                                "default": False,
                            },
                        },
                        "required": ["parent_id"],
                    },
                ),
                Tool(
                    name="confluence_get_page_ancestors",
                    description="Get ancestor (parent) pages of a specific Confluence page",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "The ID of the page whose ancestors you want to retrieve",
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
                                "description": "Confluence page ID (numeric ID, can be parsed from URL, "
                                "e.g. from 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title' "
                                "-> '123456789')",
                            }
                        },
                        "required": ["page_id"],
                    },
                ),
            ]
        )

        # Only add write operations if not in read-only mode
        if not read_only:
            tools.extend(
                [
                    Tool(
                        name="confluence_create_page",
                        description="Create a new Confluence page",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "space_key": {
                                    "type": "string",
                                    "description": "The key of the space to create the page in "
                                    "(usually a short uppercase code like 'DEV', 'TEAM', or 'DOC')",
                                },
                                "title": {
                                    "type": "string",
                                    "description": "The title of the page",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "The content of the page in Markdown format. "
                                    "Supports headings, lists, tables, code blocks, and other "
                                    "Markdown syntax",
                                },
                                "parent_id": {
                                    "type": "string",
                                    "description": "Optional parent page ID. If provided, this page "
                                    "will be created as a child of the specified page",
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
                                "is_minor_edit": {
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
                    Tool(
                        name="confluence_delete_page",
                        description="Delete an existing Confluence page",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "page_id": {
                                    "type": "string",
                                    "description": "The ID of the page to delete",
                                },
                            },
                            "required": ["page_id"],
                        },
                    ),
                    Tool(
                        name="confluence_attach_content",
                        description="Attach content to a Confluence page",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "format": "binary",
                                    "description": "The content to attach (bytes)",
                                },
                                "name": {
                                    "type": "string",
                                    "description": "The name of the attachment",
                                },
                                "page_id": {
                                    "type": "string",
                                    "description": "The ID of the page to attach the content to",
                                },
                            },
                            "required": ["content", "name", "page_id"],
                        },
                    ),
                ]
            )

    # Add Jira tools if Jira is configured
    if ctx and ctx.jira:
        # Always add read operations
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
                            "fields": {
                                "type": "string",
                                "description": "Fields to return. Can be a comma-separated list (e.g., 'summary,status,customfield_10010'), '*all' for all fields (including custom fields), or omitted for essential fields only",
                                "default": "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
                            },
                            "expand": {
                                "type": "string",
                                "description": (
                                    "Optional fields to expand. Examples: 'renderedFields' "
                                    "(for rendered content), 'transitions' (for available "
                                    "status transitions), 'changelog' (for history)"
                                ),
                                "default": None,
                            },
                            "comment_limit": {
                                "type": "integer",
                                "description": (
                                    "Maximum number of comments to include "
                                    "(0 or null for no comments)"
                                ),
                                "minimum": 0,
                                "maximum": 100,
                                "default": 10,
                            },
                            "properties": {
                                "type": "string",
                                "description": "A comma-separated list of issue properties to return",
                                "default": None,
                            },
                            "update_history": {
                                "type": "boolean",
                                "description": "Whether to update the issue view history for the requesting user",
                                "default": True,
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
                                "description": "JQL query string (Jira Query Language). Examples:\n"
                                '- Find Epics: "issuetype = Epic AND project = PROJ"\n'
                                '- Find issues in Epic: "parent = PROJ-123"\n'
                                "- Find by status: \"status = 'In Progress' AND project = PROJ\"\n"
                                '- Find by assignee: "assignee = currentUser()"\n'
                                '- Find recently updated: "updated >= -7d AND project = PROJ"\n'
                                '- Find by label: "labels = frontend AND project = PROJ"\n'
                                '- Find by priority: "priority = High AND project = PROJ"',
                            },
                            "fields": {
                                "type": "string",
                                "description": (
                                    "Comma-separated fields to return in the results. "
                                    "Use '*all' for all fields, or specify individual "
                                    "fields like 'summary,status,assignee,priority'"
                                ),
                                "default": "*all",
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                            "startAt": {
                                "type": "number",
                                "description": "Starting index for pagination (0-based)",
                                "default": 0,
                                "minimum": 0,
                            },
                            "projects_filter": {
                                "type": "string",
                                "description": "Comma-separated list of project keys to filter results by. Overrides the environment variable JIRA_PROJECTS_FILTER if provided.",
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
                            "startAt": {
                                "type": "number",
                                "description": "Starting index for pagination (0-based)",
                                "default": 0,
                                "minimum": 0,
                            },
                        },
                        "required": ["project_key"],
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
                            "startAt": {
                                "type": "number",
                                "description": "Starting index for pagination (0-based)",
                                "default": 0,
                                "minimum": 0,
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
                    name="jira_download_attachments",
                    description="Download attachments from a Jira issue",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {
                                "type": "string",
                                "description": "Jira issue key (e.g., 'PROJ-123')",
                            },
                            "target_dir": {
                                "type": "string",
                                "description": "Directory where attachments should be saved",
                            },
                        },
                        "required": ["issue_key", "target_dir"],
                    },
                ),
                Tool(
                    name="jira_get_agile_boards",
                    description="Get jira agile boards by name, project key, or type",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "board_name": {
                                "type": "string",
                                "description": "The name of board, support fuzzy search",
                            },
                            "project_key": {
                                "type": "string",
                                "description": "Jira project key (e.g., 'PROJ-123')",
                            },
                            "board_type": {
                                "type": "string",
                                "description": "The type of jira board (e.g., 'scrum', 'kanban')",
                            },
                            "startAt": {
                                "type": "number",
                                "description": "Starting index for pagination (0-based)",
                                "default": 0,
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                        },
                    },
                ),
                Tool(
                    name="jira_get_board_issues",
                    description="Get all issues linked to a specific board",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "board_id": {
                                "type": "string",
                                "description": "The id of the board (e.g., '1001')",
                            },
                            "jql": {
                                "type": "string",
                                "description": "JQL query string (Jira Query Language). Examples:\n"
                                '- Find Epics: "issuetype = Epic AND project = PROJ"\n'
                                '- Find issues in Epic: "parent = PROJ-123"\n'
                                "- Find by status: \"status = 'In Progress' AND project = PROJ\"\n"
                                '- Find by assignee: "assignee = currentUser()"\n'
                                '- Find recently updated: "updated >= -7d AND project = PROJ"\n'
                                '- Find by label: "labels = frontend AND project = PROJ"\n'
                                '- Find by priority: "priority = High AND project = PROJ"',
                            },
                            "fields": {
                                "type": "string",
                                "description": (
                                    "Comma-separated fields to return in the results. "
                                    "Use '*all' for all fields, or specify individual "
                                    "fields like 'summary,status,assignee,priority'"
                                ),
                                "default": "*all",
                            },
                            "startAt": {
                                "type": "number",
                                "description": "Starting index for pagination (0-based)",
                                "default": 0,
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                            "expand": {
                                "type": "string",
                                "description": "Fields to expand in the response (e.g., 'version', 'body.storage')",
                                "default": "version",
                            },
                        },
                        "required": ["board_id", "jql"],
                    },
                ),
                Tool(
                    name="jira_get_sprints_from_board",
                    description="Get jira sprints from board by state",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "board_id": {
                                "type": "string",
                                "description": "The id of board (e.g., '1000')",
                            },
                            "state": {
                                "type": "string",
                                "description": "Sprint state (e.g., 'active', 'future', 'closed')",
                            },
                            "startAt": {
                                "type": "number",
                                "description": "Starting index for pagination (0-based)",
                                "default": 0,
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                        },
                    },
                ),
                Tool(
                    name="jira_get_sprint_issues",
                    description="Get jira issues from sprint",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "sprint_id": {
                                "type": "string",
                                "description": "The id of sprint (e.g., '10001')",
                            },
                            "fields": {
                                "type": "string",
                                "description": (
                                    "Comma-separated fields to return in the results. "
                                    "Use '*all' for all fields, or specify individual "
                                    "fields like 'summary,status,assignee,priority'"
                                ),
                                "default": "*all",
                            },
                            "startAt": {
                                "type": "number",
                                "description": "Starting index for pagination (0-based)",
                                "default": 0,
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                        },
                        "required": ["sprint_id"],
                    },
                ),
            ]
        )

        # Only add write operations if not in read-only mode
        if not read_only:
            tools.extend(
                [
                    Tool(
                        name="jira_create_issue",
                        description="Create a new Jira issue with optional Epic link or parent for subtasks",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "project_key": {
                                    "type": "string",
                                    "description": (
                                        "The JIRA project key (e.g. 'PROJ', 'DEV', 'SUPPORT'). "
                                        "This is the prefix of issue keys in your project. "
                                        "Never assume what it might be, always ask the user."
                                    ),
                                },
                                "summary": {
                                    "type": "string",
                                    "description": "Summary/title of the issue",
                                },
                                "issue_type": {
                                    "type": "string",
                                    "description": (
                                        "Issue type (e.g. 'Task', 'Bug', 'Story', 'Epic', 'Subtask'). "
                                        "The available types depend on your project configuration. "
                                        "For subtasks, use 'Subtask' (not 'Sub-task') and include parent in additional_fields."
                                    ),
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
                                    "description": (
                                        "Optional JSON string of additional fields to set. "
                                        "Examples:\n"
                                        '- Set priority: {"priority": {"name": "High"}}\n'
                                        '- Add labels: {"labels": ["frontend", "urgent"]}\n'
                                        '- Add components: {"components": [{"name": "UI"}]}\n'
                                        '- Link to parent (for any issue type): {"parent": "PROJ-123"}\n'
                                        '- Custom fields: {"customfield_10010": "value"}'
                                    ),
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
                                    "description": (
                                        "A valid JSON object of fields to update as a string. "
                                        'Example: \'{"summary": "New title", "description": "Updated description", '
                                        '"priority": {"name": "High"}, "assignee": {"name": "john.doe"}}\''
                                    ),
                                },
                                "additional_fields": {
                                    "type": "string",
                                    "description": "Optional JSON string of additional fields to update. Use this for custom fields or more complex updates.",
                                    "default": "{}",
                                },
                                "attachments": {
                                    "type": "string",
                                    "description": "Optional JSON string or comma-separated list of file paths to attach to the issue. "
                                    'Example: "/path/to/file1.txt,/path/to/file2.txt" or "["/path/to/file1.txt","/path/to/file2.txt"]"',
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
                                    "description": (
                                        "Time spent in Jira format. Examples: "
                                        "'1h 30m' (1 hour and 30 minutes), "
                                        "'1d' (1 day), '30m' (30 minutes), "
                                        "'4h' (4 hours)"
                                    ),
                                },
                                "comment": {
                                    "type": "string",
                                    "description": "Optional comment for the worklog in Markdown format",
                                },
                                "started": {
                                    "type": "string",
                                    "description": (
                                        "Optional start time in ISO format. "
                                        "If not provided, the current time will be used. "
                                        "Example: '2023-08-01T12:00:00.000+0000'"
                                    ),
                                },
                            },
                            "required": ["issue_key", "time_spent"],
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
                                    "description": (
                                        "ID of the transition to perform. Use the jira_get_transitions tool first "
                                        "to get the available transition IDs for the issue. "
                                        "Example values: '11', '21', '31'"
                                    ),
                                },
                                "fields": {
                                    "type": "string",
                                    "description": (
                                        "JSON string of fields to update during the transition. "
                                        "Some transitions require specific fields to be set. "
                                        'Example: \'{"resolution": {"name": "Fixed"}}\''
                                    ),
                                    "default": "{}",
                                },
                                "comment": {
                                    "type": "string",
                                    "description": (
                                        "Comment to add during the transition (optional). "
                                        "This will be visible in the issue history."
                                    ),
                                },
                            },
                            "required": ["issue_key", "transition_id"],
                        },
                    ),
                ]
            )

    return tools


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """Handle tool calls for Confluence and Jira operations."""
    ctx = app.request_context.lifespan_context

    # Check if we're in read-only mode for write operations
    read_only = is_read_only_mode()

    try:
        # Helper functions for formatting results
        def format_comment(comment: Any) -> dict[str, Any]:
            if hasattr(comment, "to_simplified_dict"):
                # Cast the return value to dict[str, Any] to satisfy the type checker
                return cast(dict[str, Any], comment.to_simplified_dict())
            return {
                "id": comment.get("id"),
                "author": comment.get("author", {}).get("displayName", "Unknown"),
                "created": comment.get("created"),
                "body": comment.get("body"),
            }

        # Confluence operations
        if name == "confluence_search" and ctx and ctx.confluence:
            if not ctx or not ctx.confluence:
                raise ValueError("Confluence is not configured.")

            query = arguments.get("query", "")
            limit = min(int(arguments.get("limit", 10)), 50)
            spaces_filter = arguments.get("spaces_filter")

            # Check if the query is a simple search term or already a CQL query
            if query and not any(
                x in query
                for x in ["=", "~", ">", "<", " AND ", " OR ", "currentUser()"]
            ):
                # Convert simple search term to CQL text search
                # This will search in all content (title, body, etc.)
                query = f'text ~ "{query}"'
                logger.info(f"Converting simple search term to CQL: {query}")

            pages = ctx.confluence.search(
                query, limit=limit, spaces_filter=spaces_filter
            )

            # Format results using the to_simplified_dict method
            search_results = [page.to_simplified_dict() for page in pages]

            return [
                TextContent(
                    type="text",
                    text=json.dumps(search_results, indent=2, ensure_ascii=False),
                )
            ]

        elif name == "confluence_get_page" and ctx and ctx.confluence:
            if not ctx or not ctx.confluence:
                raise ValueError("Confluence is not configured.")

            page_id = arguments.get("page_id")
            include_metadata = arguments.get("include_metadata", True)
            convert_to_markdown = arguments.get("convert_to_markdown", True)

            page = ctx.confluence.get_page_content(
                page_id, convert_to_markdown=convert_to_markdown
            )

            if include_metadata:
                # The to_simplified_dict method already includes the content,
                # so we don't need to include it separately at the root level
                result = {
                    "metadata": page.to_simplified_dict(),
                }
            else:
                # For backward compatibility, keep returning content directly
                result = {"content": page.content}

            return [
                TextContent(
                    type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
                )
            ]

        elif name == "confluence_get_page_children" and ctx and ctx.confluence:
            if not ctx or not ctx.confluence:
                raise ValueError("Confluence is not configured.")

            parent_id = arguments.get("parent_id")
            expand = arguments.get("expand", "version")
            limit = min(int(arguments.get("limit", 25)), 50)
            include_content = arguments.get("include_content", False)

            # Add body.storage to expand if content is requested
            if include_content and "body" not in expand:
                expand = f"{expand},body.storage"

            # Format results using the to_simplified_dict method
            child_pages = [page.to_simplified_dict() for page in pages]

            # Return the formatted results
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "parent_id": parent_id,
                            "total": len(child_pages),
                            "limit": limit,
                            "results": child_pages,
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                )
            ]

        elif name == "confluence_get_page_ancestors" and ctx and ctx.confluence:
            if not ctx or not ctx.confluence:
                raise ValueError("Confluence is not configured.")

            page_id = arguments.get("page_id")

            # Get the ancestor pages
            ancestors = ctx.confluence.get_page_ancestors(page_id)

            # Format results
            ancestor_pages = [page.to_simplified_dict() for page in ancestors]

            return [
                TextContent(
                    type="text",
                    text=json.dumps(ancestor_pages, indent=2, ensure_ascii=False),
                )
            ]

        elif name == "confluence_get_comments" and ctx and ctx.confluence:
            if not ctx or not ctx.confluence:
                raise ValueError("Confluence is not configured.")

            page_id = arguments.get("page_id")
            comments = ctx.confluence.get_page_comments(page_id)

            # Format comments using their to_simplified_dict method if available
            formatted_comments = [format_comment(comment) for comment in comments]

            return [
                TextContent(
                    type="text",
                    text=json.dumps(formatted_comments, indent=2, ensure_ascii=False),
                )
            ]

        elif name == "confluence_create_page":
            if not ctx or not ctx.confluence:
                raise ValueError("Confluence is not configured.")

            # Write operation - check read-only mode
            if read_only:
                return [
                    TextContent(
                        "Operation 'confluence_create_page' is not available in read-only mode."
                    )
                ]

            # Extract arguments
            space_key = arguments.get("space_key")
            title = arguments.get("title")
            content = arguments.get("content")
            parent_id = arguments.get("parent_id")

            # Create the page (with automatic markdown conversion)
            page = ctx.confluence.create_page(
                space_key=space_key,
                title=title,
                body=content,
                parent_id=parent_id,
                is_markdown=True,
            )

            # Format the result
            result = page.to_simplified_dict()

            return [
                TextContent(
                    type="text",
                    text=f"Page created successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
                )
            ]

        elif name == "confluence_update_page":
            if not ctx or not ctx.confluence:
                raise ValueError("Confluence is not configured.")

            # Write operation - check read-only mode
            if read_only:
                return [
                    TextContent(
                        "Operation 'confluence_update_page' is not available in read-only mode."
                    )
                ]

            page_id = arguments.get("page_id")
            title = arguments.get("title")
            content = arguments.get("content")
            is_minor_edit = arguments.get("is_minor_edit", False)
            version_comment = arguments.get("version_comment", "")

            if not page_id or not title or not content:
                raise ValueError(
                    "Missing required parameters: page_id, title, and content are required."
                )

            # Update the page (with automatic markdown conversion)
            updated_page = ctx.confluence.update_page(
                page_id=page_id,
                title=title,
                body=content,
                is_minor_edit=is_minor_edit,
                version_comment=version_comment,
                is_markdown=True,
            )

            # Format results
            page_data = updated_page.to_simplified_dict()

            return [TextContent(type="text", text=json.dumps({"page": page_data}))]

        elif name == "confluence_delete_page":
            if not ctx or not ctx.confluence:
                raise ValueError("Confluence is not configured.")

            # Write operation - check read-only mode
            if read_only:
                return [
                    TextContent(
                        "Operation 'confluence_delete_page' is not available in read-only mode."
                    )
                ]

            page_id = arguments.get("page_id")

            if not page_id:
                raise ValueError("Missing required parameter: page_id is required.")

            try:
                # Delete the page
                result = ctx.confluence.delete_page(page_id=page_id)

                # Format results - our fixed implementation now correctly returns True on success
                if result:
                    response = {
                        "success": True,
                        "message": f"Page {page_id} deleted successfully",
                    }
                else:
                    # This branch should rarely be hit with our updated implementation
                    # but we keep it for safety
                    response = {
                        "success": False,
                        "message": f"Unable to delete page {page_id}. The API request completed but deletion was unsuccessful.",
                    }

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(response, indent=2, ensure_ascii=False),
                    )
                ]
            except Exception as e:
                # API call failed with an exception
                logger.error(f"Error deleting Confluence page {page_id}: {str(e)}")
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "success": False,
                                "message": f"Error deleting page {page_id}",
                                "error": str(e),
                            },
                            indent=2,
                            ensure_ascii=False,
                        ),
                    )
                ]

        elif name == "confluence_attach_content":
            if not ctx or not ctx.confluence:
                raise ValueError("Confluence is not configured.")

            # Write operation - check read-only mode
            if read_only:
                return [
                    TextContent(
                        "Operation 'confluence_attach_content' is not available in read-only mode."
                    )
                ]

            content = arguments.get("content")
            name = arguments.get("name")
            page_id = arguments.get("page_id")

            if not content or not name or not page_id:
                return [
                    TextContent(
                        type="text",
                        text="Error: Missing required parameters: content, name, and page_id are required.",
                    )
                ]

            try:
                page = ctx.confluence.attach_content(
                    content=content, name=name, page_id=page_id
                )
                page_data = page.to_simplified_dict()
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            page_data,
                            indent=2,
                            ensure_ascii=False,
                        ),
                    )
                ]
            except ApiError as e:
                return [
                    TextContent(
                        type="text",
                        text=f"Confluence API Error when trying to attach content {name} to page {page_id}: {str(e)}",
                    )
                ]
            except RequestException as e:
                return [
                    TextContent(
                        type="text",
                        text=f"Network error when trying to attach content {name} to page {page_id}: {str(e)}",
                    )
                ]

        # Jira operations
        elif name == "jira_get_issue" and ctx and ctx.jira:
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            issue_key = arguments.get("issue_key")
            fields = arguments.get(
                "fields",
                "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
            )
            expand = arguments.get("expand")
            comment_limit = arguments.get("comment_limit", 10)
            properties = arguments.get("properties")
            update_history = arguments.get("update_history", True)

            issue = ctx.jira.get_issue(
                issue_key,
                fields=fields,
                expand=expand,
                comment_limit=comment_limit,
                properties=properties,
                update_history=update_history,
            )

            result = {"content": issue.to_simplified_dict()}

            return [
                TextContent(
                    type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
                )
            ]

        elif name == "jira_search" and ctx and ctx.jira:
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            jql = arguments.get("jql")
            fields = arguments.get(
                "fields",
                "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
            )
            limit = min(int(arguments.get("limit", 10)), 50)
            projects_filter = arguments.get("projects_filter")
            start_at = int(arguments.get("startAt", 0))  # Get startAt, default to 0

            issues = ctx.jira.search_issues(
                jql,
                fields=fields,
                limit=limit,
                start=start_at,  # Pass start_at here
                projects_filter=projects_filter,
            )

            # Format results using the to_simplified_dict method
            search_results = [issue.to_simplified_dict() for issue in issues]

            return [
                TextContent(
                    type="text",
                    text=json.dumps(search_results, indent=2, ensure_ascii=False),
                )
            ]

        elif name == "jira_get_project_issues" and ctx and ctx.jira:
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            project_key = arguments.get("project_key")
            limit = min(int(arguments.get("limit", 10)), 50)
            start_at = int(arguments.get("startAt", 0))  # Get startAt

            issues = ctx.jira.get_project_issues(
                project_key, start=start_at, limit=limit
            )

            # Format results
            project_issues = [issue.to_simplified_dict() for issue in issues]

            return [
                TextContent(
                    type="text",
                    text=json.dumps(project_issues, indent=2, ensure_ascii=False),
                )
            ]

        elif name == "jira_get_epic_issues" and ctx and ctx.jira:
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            epic_key = arguments.get("epic_key")
            limit = min(int(arguments.get("limit", 10)), 50)
            start_at = int(arguments.get("startAt", 0))  # Get startAt

            # Get issues linked to the epic
            issues = ctx.jira.get_epic_issues(epic_key, start=start_at, limit=limit)

            # Format results
            epic_issues = [issue.to_simplified_dict() for issue in issues]

            return [
                TextContent(
                    type="text",
                    text=json.dumps(epic_issues, indent=2, ensure_ascii=False),
                )
            ]

        elif name == "jira_get_transitions" and ctx and ctx.jira:
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            issue_key = arguments.get("issue_key")

            # Get available transitions
            transitions = ctx.jira.get_available_transitions(issue_key)

            # Format transitions
            formatted_transitions = []
            for transition in transitions:
                formatted_transitions.append(
                    {
                        "id": transition.get("id"),
                        "name": transition.get("name"),
                        "to_status": transition.get("to", {}).get("name"),
                    }
                )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        formatted_transitions, indent=2, ensure_ascii=False
                    ),
                )
            ]

        elif name == "jira_get_worklog" and ctx and ctx.jira:
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            issue_key = arguments.get("issue_key")

            # Get worklogs
            worklogs = ctx.jira.get_worklogs(issue_key)

            result = {"worklogs": worklogs}

            return [
                TextContent(
                    type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
                )
            ]

        elif name == "jira_download_attachments" and ctx and ctx.jira:
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            issue_key = arguments.get("issue_key")
            target_dir = arguments.get("target_dir")

            if not issue_key:
                raise ValueError("Missing required parameter: issue_key")
            if not target_dir:
                raise ValueError("Missing required parameter: target_dir")

            # Download the attachments
            result = ctx.jira.download_issue_attachments(
                issue_key=issue_key, target_dir=target_dir
            )

            return [
                TextContent(
                    type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
                )
            ]

        elif name == "jira_get_agile_boards" and ctx and ctx.jira:
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            board_name = arguments.get("board_name")
            project_key = arguments.get("project_key")
            board_type = arguments.get("board_type")
            start_at = int(arguments.get("startAt", 0))
            limit = min(int(arguments.get("limit", 10)), 50)

            boards = ctx.jira.get_all_agile_boards_model(
                board_name=board_name,
                project_key=project_key,
                board_type=board_type,
                start=start_at,
                limit=limit,
            )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        [board.to_simplified_dict() for board in boards],
                        indent=2,
                        ensure_ascii=False,
                    ),
                )
            ]

        elif name == "jira_get_board_issues" and ctx and ctx.jira:
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            board_id = arguments.get("board_id")
            jql = arguments.get("jql")
            fields = arguments.get("fields", "*all")

            start_at = int(arguments.get("startAt", 0))
            limit = min(int(arguments.get("limit", 10)), 50)
            expand = arguments.get("expand", "version")

            issues = ctx.jira.get_board_issues(
                board_id=board_id,
                jql=jql,
                fields=fields,
                start=start_at,
                limit=limit,
                expand=expand,
            )

            # Format results
            board_issues = [issue.to_simplified_dict() for issue in issues]

            return [
                TextContent(
                    type="text",
                    text=json.dumps(board_issues, indent=2, ensure_ascii=False),
                )
            ]

        elif name == "jira_get_sprints_from_board" and ctx and ctx.jira:
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            board_id = arguments.get("board_id")
            state = arguments.get("state", "active")
            start_at = int(arguments.get("startAt", 0))
            limit = min(int(arguments.get("limit", 10)), 50)

            sprints = ctx.jira.get_all_sprints_from_board_model(
                board_id=board_id, state=state, start=start_at, limit=limit
            )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        [sprint.to_simplified_dict() for sprint in sprints],
                        indent=2,
                        ensure_ascii=False,
                    ),
                )
            ]

        elif name == "jira_get_sprint_issues" and ctx and ctx.jira:
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            sprint_id = arguments.get("sprint_id")
            fields = arguments.get("fields", "*all")
            start_at = int(arguments.get("startAt", 0))
            limit = min(int(arguments.get("limit", 10)), 50)

            issues = ctx.jira.get_sprint_issues(
                sprint_id=sprint_id, fields=fields, start=start_at, limit=limit
            )

            # Format results
            sprint_issues = [issue.to_simplified_dict() for issue in issues]

            return [
                TextContent(
                    type="text",
                    text=json.dumps(sprint_issues, indent=2, ensure_ascii=False),
                )
            ]

        elif name == "jira_create_issue":
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            # Write operation - check read-only mode
            if read_only:
                return [
                    TextContent(
                        "Operation 'jira_create_issue' is not available in read-only mode."
                    )
                ]

            # Extract required arguments
            project_key = arguments.get("project_key")
            summary = arguments.get("summary")
            issue_type = arguments.get("issue_type")

            # Extract optional arguments
            description = arguments.get("description", "")
            assignee = arguments.get("assignee")

            # Parse additional fields
            additional_fields = {}
            if arguments.get("additional_fields"):
                try:
                    additional_fields = json.loads(arguments.get("additional_fields"))
                except json.JSONDecodeError:
                    raise ValueError("Invalid JSON in additional_fields")

            # Create the issue
            issue = ctx.jira.create_issue(
                project_key=project_key,
                summary=summary,
                issue_type=issue_type,
                description=description,
                assignee=assignee,
                **additional_fields,
            )

            result = issue.to_simplified_dict()

            return [
                TextContent(
                    type="text",
                    text=f"Issue created successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
                )
            ]

        elif name == "jira_update_issue":
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            # Write operation - check read-only mode
            if read_only:
                return [
                    TextContent(
                        "Operation 'jira_update_issue' is not available in read-only mode."
                    )
                ]

            # Extract arguments
            issue_key = arguments.get("issue_key")

            # Parse fields JSON
            fields = {}
            if arguments.get("fields"):
                try:
                    fields = json.loads(arguments.get("fields"))
                except json.JSONDecodeError:
                    raise ValueError("Invalid JSON in fields")

            # Parse additional fields JSON
            additional_fields = {}
            if arguments.get("additional_fields"):
                try:
                    additional_fields = json.loads(arguments.get("additional_fields"))
                except json.JSONDecodeError:
                    raise ValueError("Invalid JSON in additional_fields")

            # Handle attachments if provided
            attachments = []
            if arguments.get("attachments"):
                # Parse attachments - can be a single string or a list of strings
                if isinstance(arguments.get("attachments"), str):
                    try:
                        # Try to parse as JSON array
                        parsed_attachments = json.loads(arguments.get("attachments"))
                        if isinstance(parsed_attachments, list):
                            attachments = parsed_attachments
                        else:
                            # Single file path as a JSON string
                            attachments = [parsed_attachments]
                    except json.JSONDecodeError:
                        # Handle non-JSON string formats
                        if "," in arguments.get("attachments"):
                            # Split by comma and strip whitespace (supporting comma-separated list format)
                            attachments = [
                                path.strip()
                                for path in arguments.get("attachments").split(",")
                            ]
                        else:
                            # Plain string - single file path
                            attachments = [arguments.get("attachments")]
                elif isinstance(arguments.get("attachments"), list):
                    # Already a list
                    attachments = arguments.get("attachments")

                # Validate all paths exist
                for path in attachments[:]:
                    if not os.path.exists(path):
                        logger.warning(f"Attachment file not found: {path}")
                        attachments.remove(path)

            try:
                # Add attachments to additional_fields if any valid paths were found
                if attachments:
                    additional_fields["attachments"] = attachments

                # Update the issue - directly pass fields to JiraFetcher.update_issue
                # instead of using fields as a parameter name
                issue = ctx.jira.update_issue(
                    issue_key=issue_key, **fields, **additional_fields
                )

                result = issue.to_simplified_dict()

                # Include attachment results if available
                if (
                    hasattr(issue, "custom_fields")
                    and "attachment_results" in issue.custom_fields
                ):
                    result["attachment_results"] = issue.custom_fields[
                        "attachment_results"
                    ]

                return [
                    TextContent(
                        type="text",
                        text=f"Issue updated successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}",
                    )
                ]
            except Exception as e:
                return [
                    TextContent(
                        type="text",
                        text=f"Error updating issue {issue_key}: {str(e)}",
                    )
                ]

        elif name == "jira_delete_issue":
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            # Write operation - check read-only mode
            if read_only:
                return [
                    TextContent(
                        "Operation 'jira_delete_issue' is not available in read-only mode."
                    )
                ]

            issue_key = arguments.get("issue_key")

            # Delete the issue
            deleted = ctx.jira.delete_issue(issue_key)

            result = {"message": f"Issue {issue_key} has been deleted successfully."}

            return [
                TextContent(
                    type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
                )
            ]

        elif name == "jira_add_comment":
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            # Write operation - check read-only mode
            if read_only:
                return [
                    TextContent(
                        "Operation 'jira_add_comment' is not available in read-only mode."
                    )
                ]

            issue_key = arguments.get("issue_key")
            comment = arguments.get("comment")

            # Add the comment
            result = ctx.jira.add_comment(issue_key, comment)

            return [
                TextContent(
                    type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
                )
            ]

        elif name == "jira_add_worklog":
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            # Write operation - check read-only mode
            if read_only:
                return [
                    TextContent(
                        "Operation 'jira_add_worklog' is not available in read-only mode."
                    )
                ]

            # Extract arguments
            issue_key = arguments.get("issue_key")
            time_spent = arguments.get("time_spent")
            comment = arguments.get("comment")
            started = arguments.get("started")

            # Add the worklog
            worklog = ctx.jira.add_worklog(
                issue_key=issue_key,
                time_spent=time_spent,
                comment=comment,
                started=started,
            )

            result = {"message": "Worklog added successfully", "worklog": worklog}

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, ensure_ascii=False),
                )
            ]

        elif name == "jira_link_to_epic":
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            # Write operation - check read-only mode
            if read_only:
                return [
                    TextContent(
                        "Operation 'jira_link_to_epic' is not available in read-only mode."
                    )
                ]

            issue_key = arguments.get("issue_key")
            epic_key = arguments.get("epic_key")

            # Link the issue to the epic
            issue = ctx.jira.link_issue_to_epic(issue_key, epic_key)

            result = {
                "message": f"Issue {issue_key} has been linked to epic {epic_key}.",
                "issue": issue.to_simplified_dict(),
            }

            return [
                TextContent(
                    type="text", text=json.dumps(result, indent=2, ensure_ascii=False)
                )
            ]

        elif name == "jira_transition_issue":
            if not ctx or not ctx.jira:
                raise ValueError("Jira is not configured.")

            # Write operation - check read-only mode
            if read_only:
                return [
                    TextContent(
                        "Operation 'jira_transition_issue' is not available in read-only mode."
                    )
                ]

            # Extract arguments
            issue_key = arguments.get("issue_key")
            transition_id = arguments.get("transition_id")
            comment = arguments.get("comment")

            # Validate required parameters
            if not issue_key:
                raise ValueError("issue_key is required")
            if not transition_id:
                raise ValueError("transition_id is required")

            # Convert transition_id to integer if it's a numeric string
            # This ensures compatibility with the Jira API which expects integers
            if isinstance(transition_id, str) and transition_id.isdigit():
                transition_id = int(transition_id)
                logger.debug(
                    f"Converted string transition_id to integer: {transition_id}"
                )

            # Parse fields JSON
            fields = {}
            if arguments.get("fields"):
                try:
                    fields = json.loads(arguments.get("fields"))
                except json.JSONDecodeError:
                    raise ValueError("Invalid JSON in fields")

            try:
                # Transition the issue
                issue = ctx.jira.transition_issue(
                    issue_key=issue_key,
                    transition_id=transition_id,
                    fields=fields,
                    comment=comment,
                )

                result = {
                    "message": f"Issue {issue_key} transitioned successfully",
                    "issue": issue.to_simplified_dict() if issue else None,
                }

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, ensure_ascii=False),
                    )
                ]
            except Exception as e:
                # Provide a clear error message, especially for transition ID type issues
                error_msg = str(e)
                if "'transition' identifier must be an integer" in error_msg:
                    error_msg = (
                        f"Error transitioning issue {issue_key}: The Jira API requires transition IDs to be integers. "
                        f"Received transition ID '{transition_id}' of type {type(transition_id).__name__}. "
                        f"Please use the numeric ID value from jira_get_transitions."
                    )
                else:
                    error_msg = f"Error transitioning issue {issue_key} with transition ID {transition_id}: {error_msg}"

                logger.error(error_msg)
                return [
                    TextContent(
                        type="text",
                        text=error_msg,
                    )
                ]

        raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def run_server(transport: str = "stdio", port: int = 8000) -> None:
    """Run the MCP Atlassian server with the specified transport."""
    if transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.routing import Mount, Route

        sse = SseServerTransport("/messages/")

        async def handle_sse(request: Request) -> None:
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await app.run(
                    streams[0], streams[1], app.create_initialization_options()
                )

        starlette_app = Starlette(
            debug=True,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

        import uvicorn

        # Set up uvicorn config
        config = uvicorn.Config(starlette_app, host="0.0.0.0", port=port)  # noqa: S104
        server = uvicorn.Server(config)
        # Use server.serve() instead of run() to stay in the same event loop
        await server.serve()
    else:
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream, write_stream, app.create_initialization_options()
            )
