import json
import logging
from collections.abc import Sequence
from typing import Any

from mcp.server import Server
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl

from .confluence import ConfluenceFetcher
from .jira import JiraFetcher

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-atlassian")

# Initialize the content fetchers
confluence_fetcher = ConfluenceFetcher()
jira_fetcher = JiraFetcher()
app = Server("mcp-atlassian")


@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available Confluence spaces and Jira projects as resources."""
    resources = []

    # Add Confluence spaces
    spaces_response = confluence_fetcher.get_spaces()
    if isinstance(spaces_response, dict) and "results" in spaces_response:
        spaces = spaces_response["results"]
        resources.extend(
            [
                Resource(
                    uri=AnyUrl(f"confluence://{space['key']}"),
                    name=f"Confluence Space: {space['name']}",
                    mimeType="text/plain",
                    description=space.get("description", {}).get("plain", {}).get("value", ""),
                )
                for space in spaces
            ]
        )

    # Add Jira projects
    try:
        projects = jira_fetcher.jira.projects()
        resources.extend(
            [
                Resource(
                    uri=AnyUrl(f"jira://{project['key']}"),
                    name=f"Jira Project: {project['name']}",
                    mimeType="text/plain",
                    description=project.get("description", ""),
                )
                for project in projects
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
        parts = uri_str.replace("confluence://", "").split("/")

        # Handle space listing
        if len(parts) == 1:
            space_key = parts[0]
            documents = confluence_fetcher.get_space_pages(space_key)
            content = []
            for doc in documents:
                content.append(f"# {doc.metadata['title']}\n\n{doc.page_content}\n---")
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
        parts = uri_str.replace("jira://", "").split("/")

        # Handle project listing
        if len(parts) == 1:
            project_key = parts[0]
            issues = jira_fetcher.get_project_issues(project_key)
            content = []
            for issue in issues:
                content.append(f"# {issue.metadata['key']}: {issue.metadata['title']}\n\n{issue.page_content}\n---")
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
    return [
        Tool(
            name="confluence_search",
            description="Search Confluence content using CQL",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "CQL query string (e.g. 'type=page AND space=DEV')"},
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
                    "page_id": {"type": "string", "description": "Confluence page ID"},
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
                "properties": {"page_id": {"type": "string", "description": "Confluence page ID"}},
                "required": ["page_id"],
            },
        ),
        Tool(
            name="jira_get_issue",
            description="Get details of a specific Jira issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Jira issue key (e.g., 'PROJ-123')"},
                    "expand": {"type": "string", "description": "Optional fields to expand", "default": None},
                },
                "required": ["issue_key"],
            },
        ),
        Tool(
            name="jira_search",
            description="Search Jira issues using JQL",
            inputSchema={
                "type": "object",
                "properties": {
                    "jql": {"type": "string", "description": "JQL query string"},
                    "fields": {"type": "string", "description": "Comma-separated fields to return", "default": "*all"},
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
                    "project_key": {"type": "string", "description": "The project key"},
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
            description="Create a new Jira issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_key": {
                        "type": "string",
                        "description": "The JIRA project key. Never assume what it might be, always ask the user.",
                    },
                    "fields": {
                        "type": "string",
                        "description": "A valid JSON object of fields to create the issue. It must adhere with Jira API documentation.",
                    },
                },
                "required": ["project_key", "fields"],
            },
        ),
        Tool(
            name="jira_update_issue",
            description="Update an existing Jira issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Jira issue key"},
                    "fields": {
                        "type": "string",
                        "description": "A valid JSON object of fields to update. It must adhere with Jira API documentation. If there are no specific instructions, assume that most likely it is to update the summary or description.",
                    },
                },
                "required": ["issue_key", "fields"],
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """Handle tool calls for Confluence and Jira operations."""
    try:
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

        elif name == "jira_get_issue":
            doc = jira_fetcher.get_issue(arguments["issue_key"], expand=arguments.get("expand"))
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
            doc = jira_fetcher.create_issue(arguments["project_key"], json.loads(arguments["fields"]))
            result = json.dumps({"content": doc.page_content, "metadata": doc.metadata}, indent=2)
            return [TextContent(type="text", text=f"Issue created successfully:\n{result}")]

        elif name == "jira_update_issue":
            doc = jira_fetcher.update_issue(arguments["issue_key"], json.loads(arguments["fields"]))
            result = json.dumps({"content": doc.page_content, "metadata": doc.metadata}, indent=2)
            return [TextContent(type="text", text=f"Issue updated successfully:\n{result}")]

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
