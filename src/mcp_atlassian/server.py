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
logging.basicConfig(level=logging.WARNING)
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
                    description="Get details of a specific Jira issue including its Epic links",
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
                                '- Link to Epic: {"parent": {"key": "PROJ-123"}}\n'
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
                                '- Add to Epic: {"parent": {"key": "PROJ-456"}}\n'
                                '- Change assignee: {"assignee": "user@email.com"} or {"assignee": null} to unassign\n'
                                '- Update summary: {"summary": "New title"}\n'
                                '- Update description: {"description": "New description"}\n'
                                "- Change status: requires transition IDs - use jira_get_issue first to see available statuses\n"
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
                                "description": "Comment text to add",
                            },
                        },
                        "required": ["issue_key", "comment"],
                    },
                ),
            ]
        )

    return tools


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """Handle tool calls for Confluence and Jira operations."""
    try:
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

            return [TextContent(type="text", text=json.dumps(search_results, indent=2))]

        elif name == "confluence_get_page":
            doc = confluence_fetcher.get_page_content(arguments["page_id"])
            include_metadata = arguments.get("include_metadata", True)

            if include_metadata:
                result = {"content": doc.page_content, "metadata": doc.metadata}
            else:
                result = {"content": doc.page_content}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "confluence_get_comments":
            comments = confluence_fetcher.get_page_comments(arguments["page_id"])
            formatted_comments = [
                {
                    "author": comment.metadata["author_name"],
                    "created": comment.metadata["last_modified"],
                    "content": comment.page_content,
                }
                for comment in comments
            ]

            return [TextContent(type="text", text=json.dumps(formatted_comments, indent=2))]

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

            return [TextContent(type="text", text=f"Page created successfully:\n{json.dumps(result, indent=2)}")]

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

            return [TextContent(type="text", text=f"Page updated successfully:\n{json.dumps(result, indent=2)}")]

        # Jira operations
        elif name == "jira_get_issue":
            doc = jira_fetcher.get_issue(
                arguments["issue_key"], expand=arguments.get("expand"), comment_limit=arguments.get("comment_limit")
            )
            result = {"content": doc.page_content, "metadata": doc.metadata}
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "jira_search":
            limit = min(int(arguments.get("limit", 10)), 50)
            documents = jira_fetcher.search_issues(
                arguments["jql"], fields=arguments.get("fields", "*all"), limit=limit
            )
            search_results = [
                {
                    "key": doc.metadata["key"],
                    "title": doc.metadata["title"],
                    "type": doc.metadata["type"],
                    "status": doc.metadata["status"],
                    "created_date": doc.metadata["created_date"],
                    "priority": doc.metadata["priority"],
                    "link": doc.metadata["link"],
                    "excerpt": doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content,
                }
                for doc in documents
            ]
            return [TextContent(type="text", text=json.dumps(search_results, indent=2))]

        elif name == "jira_get_project_issues":
            limit = min(int(arguments.get("limit", 10)), 50)
            documents = jira_fetcher.get_project_issues(arguments["project_key"], limit=limit)
            project_issues = [
                {
                    "key": doc.metadata["key"],
                    "title": doc.metadata["title"],
                    "type": doc.metadata["type"],
                    "status": doc.metadata["status"],
                    "created_date": doc.metadata["created_date"],
                    "link": doc.metadata["link"],
                }
                for doc in documents
            ]
            return [TextContent(type="text", text=json.dumps(project_issues, indent=2))]

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

            doc = jira_fetcher.create_issue(
                project_key=arguments["project_key"],
                summary=arguments["summary"],
                issue_type=arguments["issue_type"],
                description=arguments.get("description", ""),
                assignee=arguments.get("assignee"),
                **additional_fields,
            )
            result = json.dumps({"content": doc.page_content, "metadata": doc.metadata}, indent=2)
            return [TextContent(type="text", text=f"Issue created successfully:\n{result}")]

        elif name == "jira_update_issue":
            fields = json.loads(arguments["fields"])
            additional_fields = json.loads(arguments.get("additional_fields", "{}"))

            doc = jira_fetcher.update_issue(issue_key=arguments["issue_key"], fields=fields, **additional_fields)
            result = json.dumps({"content": doc.page_content, "metadata": doc.metadata}, indent=2)
            return [TextContent(type="text", text=f"Issue updated successfully:\n{result}")]

        elif name == "jira_delete_issue":
            issue_key = arguments["issue_key"]
            deleted = jira_fetcher.delete_issue(issue_key)
            result = {"message": f"Issue {issue_key} has been deleted successfully."}
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "jira_add_comment":
            comment = jira_fetcher.add_comment(arguments["issue_key"], arguments["comment"])
            return [TextContent(type="text", text=json.dumps(comment, indent=2))]

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
