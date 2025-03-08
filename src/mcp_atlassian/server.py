import json
import logging
import os
from collections.abc import Sequence
from typing import Any

from mcp.server import Server
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl

from .confluence import ConfluenceFetcher
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


def get_available_services():
    """Determine which services are available based on environment variables."""
    confluence_vars = all(
        [
            os.getenv("CONFLUENCE_URL"),
            os.getenv("CONFLUENCE_USERNAME"),
            os.getenv("CONFLUENCE_API_TOKEN"),
        ]
    )

    jira_vars = all([os.getenv("JIRA_URL"), os.getenv("JIRA_USERNAME"), os.getenv("JIRA_API_TOKEN")])

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
        except Exception as e:
            logger.error(f"Error fetching Confluence spaces: {str(e)}")

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
        except Exception as e:
            logger.error(f"Error fetching Jira projects: {str(e)}")

    return resources


@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Read content from Confluence or Jira."""
    uri_str = str(uri)

    # Handle Confluence resources
    if uri_str.startswith("confluence://"):
        if not services["confluence"]:
            raise ValueError("Confluence is not configured. Please provide Confluence credentials.")
        parts = uri_str.replace("confluence://", "").split("/")

        # Handle space listing
        if len(parts) == 1:
            space_key = parts[0]

            # Use CQL to find recently updated pages in this space
            cql = f'space = "{space_key}" AND contributor = currentUser() ORDER BY lastmodified DESC'
            documents = confluence_fetcher.search(cql=cql, limit=20)

            if not documents:
                # Fallback to regular space pages if no user-contributed pages found
                documents = confluence_fetcher.get_space_pages(space_key, limit=10)

            content = []
            for doc in documents:
                title = doc.metadata.get("title", "Untitled")
                url = doc.metadata.get("url", "")

                content.append(f"# [{title}]({url})\n\n{doc.page_content}\n\n---")

            return "\n\n".join(content)

        # Handle specific page
        elif len(parts) >= 3 and parts[1] == "pages":
            space_key = parts[0]
            title = parts[2]
            doc = confluence_fetcher.get_page_by_title(space_key, title)

            if not doc:
                raise ValueError(f"Page not found: {title}")

            return doc.page_content

    # Handle Jira resources
    elif uri_str.startswith("jira://"):
        if not services["jira"]:
            raise ValueError("Jira is not configured. Please provide Jira credentials.")
        parts = uri_str.replace("jira://", "").split("/")

        # Handle project listing
        if len(parts) == 1:
            project_key = parts[0]

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
                title = issue.metadata.get("title", "Untitled")
                url = issue.metadata.get("url", "")
                status = issue.metadata.get("status", "")

                content.append(f"# [{key}: {title}]({url})\nStatus: {status}\n\n{issue.page_content}\n\n---")

            return "\n\n".join(content)

        # Handle specific issue
        elif len(parts) >= 3 and parts[1] == "issues":
            issue_key = parts[2]
            issue = jira_fetcher.get_issue(issue_key)
            return issue.page_content

    raise ValueError(f"Invalid resource URI: {uri}")


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
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """Handle tool calls for Confluence and Jira operations."""
    try:
        # Helper functions for formatting results
        def format_comment(comment):
            return {
                "id": comment.get("id"),
                "author": comment.get("author", {}).get("displayName", "Unknown"),
                "created": comment.get("created"),
                "body": comment.get("body"),
            }

        def format_issue(doc):
            return {
                "key": doc.metadata["key"],
                "title": doc.metadata["title"],
                "type": doc.metadata["type"],
                "status": doc.metadata["status"],
                "created_date": doc.metadata["created_date"],
                "priority": doc.metadata["priority"],
                "link": doc.metadata["link"],
            }

        def format_transition(transition):
            return {
                "id": transition.get("id"),
                "name": transition.get("name"),
                "to_status": transition.get("to", {}).get("name"),
            }

        # Confluence operations
        if name == "confluence_search":
            limit = min(int(arguments.get("limit", 10)), 50)
            documents = confluence_fetcher.search(arguments["query"], limit)
            search_results = [
                {
                    "page_id": doc.metadata["page_id"],
                    "title": doc.metadata["title"],
                    "space": doc.metadata["space"],
                    "url": doc.metadata["url"],
                    "last_modified": doc.metadata["last_modified"],
                    "type": doc.metadata["type"],
                    "excerpt": doc.page_content,
                }
                for doc in documents
            ]

            return [TextContent(type="text", text=json.dumps(search_results, indent=2, ensure_ascii=False))]

        elif name == "confluence_get_page":
            doc = confluence_fetcher.get_page_content(arguments["page_id"])
            include_metadata = arguments.get("include_metadata", True)

            if include_metadata:
                result = {"content": doc.page_content, "metadata": doc.metadata}
            else:
                result = {"content": doc.page_content}

            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

        elif name == "confluence_get_comments":
            comments = confluence_fetcher.get_page_comments(arguments["page_id"])
            formatted_comments = [format_comment(comment) for comment in comments]

            return [TextContent(type="text", text=json.dumps(formatted_comments, indent=2, ensure_ascii=False))]

        elif name == "confluence_create_page":
            # Convert markdown content to HTML storage format
            space_key = arguments["space_key"]
            title = arguments["title"]
            content = arguments["content"]
            parent_id = arguments.get("parent_id")

            # Convert markdown to Confluence storage format
            storage_format = markdown_to_confluence_storage(content)

            # Create the page
            doc = confluence_fetcher.create_page(
                space_key=space_key,
                title=title,
                body=storage_format,  # Now using the converted storage format
                parent_id=parent_id,
            )

            result = {
                "page_id": doc.metadata["page_id"],
                "title": doc.metadata["title"],
                "space_key": doc.metadata["space_key"],
                "url": doc.metadata["url"],
                "version": doc.metadata["version"],
                "content": doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content,
            }

            return [
                TextContent(
                    type="text", text=f"Page created successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}"
                )
            ]

        elif name == "confluence_update_page":
            page_id = arguments["page_id"]
            title = arguments["title"]
            content = arguments["content"]
            minor_edit = arguments.get("minor_edit", False)

            # Convert markdown to Confluence storage format
            storage_format = markdown_to_confluence_storage(content)

            # Update the page
            doc = confluence_fetcher.update_page(
                page_id=page_id,
                title=title,
                body=storage_format,  # Now using the converted storage format
                minor_edit=minor_edit,
                version_comment=arguments.get("version_comment", ""),
            )

            result = {
                "page_id": doc.metadata["page_id"],
                "title": doc.metadata["title"],
                "space_key": doc.metadata["space_key"],
                "url": doc.metadata["url"],
                "version": doc.metadata["version"],
                "content": doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content,
            }

            return [
                TextContent(
                    type="text", text=f"Page updated successfully:\n{json.dumps(result, indent=2, ensure_ascii=False)}"
                )
            ]

        # Jira operations
        elif name == "jira_get_issue":
            doc = jira_fetcher.get_issue(
                arguments["issue_key"], expand=arguments.get("expand"), comment_limit=arguments.get("comment_limit")
            )
            result = {"content": doc.page_content, "metadata": doc.metadata}
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

        elif name == "jira_search":
            limit = min(int(arguments.get("limit", 10)), 50)
            documents = jira_fetcher.search_issues(
                arguments["jql"], fields=arguments.get("fields", "*all"), limit=limit
            )
            search_results = [format_issue(doc) for doc in documents]
            return [TextContent(type="text", text=json.dumps(search_results, indent=2, ensure_ascii=False))]

        elif name == "jira_get_project_issues":
            limit = min(int(arguments.get("limit", 10)), 50)
            documents = jira_fetcher.get_project_issues(arguments["project_key"], limit=limit)
            project_issues = [format_issue(doc) for doc in documents]
            return [TextContent(type="text", text=json.dumps(project_issues, indent=2, ensure_ascii=False))]

        elif name == "jira_create_issue":
            additional_fields = json.loads(arguments.get("additional_fields", "{}"))

            # If assignee is in additional_fields, move it to the main arguments
            if "assignee" in additional_fields:
                if not arguments.get("assignee"):  # Only if not already specified in main arguments
                    assignee_data = additional_fields.pop("assignee")
                    if isinstance(assignee_data, dict):
                        arguments["assignee"] = assignee_data.get("id") or assignee_data.get("accountId")
                    else:
                        arguments["assignee"] = str(assignee_data)

            # Handle Epic-specific settings
            issue_type = arguments["issue_type"]
            if issue_type.lower() == "epic":
                # If epic_name is directly specified, make sure it's passed along
                if "epic_name" in arguments:
                    additional_fields["epic_name"] = arguments.pop("epic_name")

                # If epic_color is directly specified, make sure it's passed along
                if "epic_color" in arguments or "epic_colour" in arguments:
                    color = arguments.pop("epic_color", None) or arguments.pop("epic_colour", None)
                    additional_fields["epic_color"] = color

                # Pass any customfield_* parameters directly
                for key, value in list(arguments.items()):
                    if key.startswith("customfield_"):
                        additional_fields[key] = arguments.pop(key)

            try:
                doc = jira_fetcher.create_issue(
                    project_key=arguments["project_key"],
                    summary=arguments["summary"],
                    issue_type=issue_type,
                    description=arguments.get("description", ""),
                    assignee=arguments.get("assignee"),
                    **additional_fields,
                )
                result = json.dumps(
                    {"content": doc.page_content, "metadata": doc.metadata}, indent=2, ensure_ascii=False
                )
                return [TextContent(type="text", text=f"Issue created successfully:\n{result}")]
            except Exception as e:
                error_msg = str(e)
                if "customfield_" in error_msg and issue_type.lower() == "epic":
                    # Provide a more helpful error message for Epic field issues
                    return [
                        TextContent(
                            type="text",
                            text=(
                                f"Error creating Epic: Your Jira instance has specific requirements for Epic creation. "
                                f"You may need to provide the specific custom field ID for Epic Name. "
                                f"Try using additional_fields with the correct customfield_* ID for your instance.\n\n"
                                f"Original error: {error_msg}"
                            ),
                        )
                    ]
                else:
                    # Re-raise the original exception for other errors
                    raise

        elif name == "jira_update_issue":
            fields = json.loads(arguments["fields"])
            additional_fields = json.loads(arguments.get("additional_fields", "{}"))

            doc = jira_fetcher.update_issue(issue_key=arguments["issue_key"], fields=fields, **additional_fields)
            result = json.dumps({"content": doc.page_content, "metadata": doc.metadata}, indent=2, ensure_ascii=False)
            return [TextContent(type="text", text=f"Issue updated successfully:\n{result}")]

        elif name == "jira_delete_issue":
            issue_key = arguments["issue_key"]
            deleted = jira_fetcher.delete_issue(issue_key)
            result = {"message": f"Issue {issue_key} has been deleted successfully."}
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

        elif name == "jira_add_comment":
            comment = jira_fetcher.add_comment(arguments["issue_key"], arguments["comment"])
            result = {"message": "Comment added successfully", "comment": comment}
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

        elif name == "jira_add_worklog":
            issue_key = arguments["issue_key"]
            time_spent = arguments["time_spent"]
            comment = arguments.get("comment")
            started = arguments.get("started")
            original_estimate = arguments.get("original_estimate")
            remaining_estimate = arguments.get("remaining_estimate")

            if not time_spent:
                raise ValueError("time_spent is required")

            if not issue_key:
                raise ValueError("issue_key is required")

            if not jira_fetcher:
                raise ValueError("Jira is not configured")

            try:
                worklog = jira_fetcher.add_worklog(
                    issue_key=issue_key,
                    time_spent=time_spent,
                    comment=comment,
                    started=started,
                    original_estimate=original_estimate,
                    remaining_estimate=remaining_estimate,
                )

                # Create a more detailed success message based on what was updated
                success_message = "Worklog added successfully"
                if worklog.get("original_estimate_updated"):
                    success_message += f" (original estimate updated to {original_estimate})"
                if worklog.get("remaining_estimate_updated"):
                    success_message += f" (remaining estimate updated to {remaining_estimate})"

                result = {"message": success_message, "worklog": worklog, "status": "success"}
                return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error adding worklog: {error_msg}")

                # Provide more context in the error message for better debugging
                if "originalEstimate" in error_msg or "timetracking" in error_msg:
                    error_detail = "There was an issue updating the original estimate. This may be due to permissions or invalid format."
                elif "adjustEstimate" in error_msg or "newEstimate" in error_msg:
                    error_detail = "There was an issue updating the remaining estimate. This may be due to permissions or invalid format."
                else:
                    error_detail = "There was an issue adding the worklog. Please check the issue exists and you have proper permissions."

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": f"Failed to add worklog: {error_msg}",
                                "error_detail": error_detail,
                                "status": "error",
                            },
                            indent=2,
                            ensure_ascii=False,
                        ),
                    )
                ]

        elif name == "jira_get_worklog":
            issue_key = arguments["issue_key"]

            if not issue_key:
                raise ValueError("issue_key is required")

            if not jira_fetcher:
                raise ValueError("Jira is not configured")

            try:
                worklogs = jira_fetcher.get_worklogs(issue_key)
                result = {"worklogs": json.dumps(worklogs)}
                return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error getting worklogs: {error_msg}")
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": f"Failed to get worklogs: {error_msg}",
                                "status": "error",
                            },
                            indent=2,
                            ensure_ascii=False,
                        ),
                    )
                ]

        elif name == "jira_link_to_epic":
            issue_key = arguments["issue_key"]
            epic_key = arguments["epic_key"]
            linked_issue = jira_fetcher.link_issue_to_epic(issue_key, epic_key)
            result = {
                "message": f"Issue {issue_key} has been linked to epic {epic_key}.",
                "issue": {
                    "key": linked_issue.metadata["key"],
                    "title": linked_issue.metadata["title"],
                    "type": linked_issue.metadata["type"],
                    "status": linked_issue.metadata["status"],
                    "link": linked_issue.metadata["link"],
                },
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

        elif name == "jira_get_epic_issues":
            epic_key = arguments["epic_key"]
            limit = min(int(arguments.get("limit", 10)), 50)
            documents = jira_fetcher.get_epic_issues(epic_key, limit=limit)
            epic_issues = [format_issue(doc) for doc in documents]
            return [TextContent(type="text", text=json.dumps(epic_issues, indent=2, ensure_ascii=False))]

        elif name == "jira_get_transitions":
            issue_key = arguments["issue_key"]
            transitions = jira_fetcher.get_available_transitions(issue_key)
            transitions_result = [format_transition(transition) for transition in transitions]
            return [TextContent(type="text", text=json.dumps(transitions_result, indent=2, ensure_ascii=False))]

        elif name == "jira_transition_issue":
            import base64

            import httpx

            issue_key = arguments["issue_key"]
            transition_id = arguments["transition_id"]

            # Convert transition_id to string if it's not already
            if not isinstance(transition_id, str):
                transition_id = str(transition_id)

            # Get Jira API credentials from environment/config
            jira_url = jira_fetcher.config.url.rstrip("/")
            username = jira_fetcher.config.username
            api_token = jira_fetcher.config.api_token

            # Construct minimal transition payload
            payload = {"transition": {"id": transition_id}}

            # Add fields if provided
            if "fields" in arguments:
                try:
                    fields = json.loads(arguments.get("fields", "{}"))
                    if fields and isinstance(fields, dict):
                        payload["fields"] = fields
                except Exception as e:
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(
                                {"error": f"Invalid fields format: {str(e)}", "status": "error"},
                                indent=2,
                                ensure_ascii=False,
                            ),
                        )
                    ]

            # Add comment if provided
            if "comment" in arguments and arguments["comment"]:
                comment = arguments["comment"]
                if not isinstance(comment, str):
                    comment = str(comment)

                payload["update"] = {"comment": [{"add": {"body": comment}}]}

            # Create auth header
            auth_str = f"{username}:{api_token}"
            auth_bytes = auth_str.encode("ascii")
            auth_b64 = base64.b64encode(auth_bytes).decode("ascii")

            # Prepare headers
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            # Log entire request for debugging
            logger.info(f"Sending transition request to {jira_url}/rest/api/2/issue/{issue_key}/transitions")
            logger.info(f"Headers: {headers}")
            logger.info(f"Payload: {payload}")

            try:
                # Make direct HTTP request
                transition_url = f"{jira_url}/rest/api/2/issue/{issue_key}/transitions"
                response = httpx.post(transition_url, json=payload, headers=headers, timeout=30.0)

                # Check response
                if response.status_code >= 400:
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(
                                {
                                    "error": f"Jira API error: {response.status_code} - {response.text}",
                                    "status": "error",
                                },
                                indent=2,
                                ensure_ascii=False,
                            ),
                        )
                    ]

                # Now fetch the updated issue - also using direct HTTP
                issue_url = f"{jira_url}/rest/api/2/issue/{issue_key}"
                issue_response = httpx.get(issue_url, headers=headers, timeout=30.0)

                if issue_response.status_code >= 400:
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(
                                {
                                    "error": f"Failed to fetch updated issue: {issue_response.status_code} - {issue_response.text}",
                                    "status": "error",
                                },
                                indent=2,
                                ensure_ascii=False,
                            ),
                        )
                    ]

                # Parse and return issue data
                issue_data = issue_response.json()

                # Extract essential issue information
                status = issue_data["fields"]["status"]["name"]
                summary = issue_data["fields"].get("summary", "")
                issue_type = issue_data["fields"]["issuetype"]["name"]

                # Clean and process description text if available
                description = ""
                if issue_data["fields"].get("description"):
                    description = jira_fetcher.preprocessor.clean_jira_text(issue_data["fields"]["description"])

                result = {
                    "message": f"Successfully transitioned issue {issue_key} to {status}",
                    "issue": {
                        "key": issue_key,
                        "title": summary,
                        "type": issue_type,
                        "status": status,
                        "description": description,
                    },
                }

                return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

            except Exception as e:
                error_message = str(e)
                logger.error(f"Exception in direct transition API call: {error_message}")
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": f"Network or API error: {error_message}",
                                "status": "error",
                                "details": f"Full error: {repr(e)}",
                            },
                            indent=2,
                            ensure_ascii=False,
                        ),
                    )
                ]

        raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}")
        raise RuntimeError(f"Tool execution failed: {str(e)}")


async def main():
    # Import here to avoid issues with event loops
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
