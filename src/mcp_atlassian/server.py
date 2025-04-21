import json
import logging
import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

from mcp.server import Server
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl

from .confluence import ConfluenceFetcher
from .confluence.config import ConfluenceConfig
from .confluence.utils import quote_cql_identifier_if_needed
from .utils.io import is_read_only_mode
from .utils.logging import log_config_param
from .utils.urls import is_atlassian_cloud_url

# Configure logging
logger = logging.getLogger("mcp-atlassian")


@dataclass
class AppContext:
    """Application context for MCP Atlassian."""

    confluence: ConfluenceFetcher | None = None


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

    return {"confluence": confluence_is_setup}


@asynccontextmanager
async def server_lifespan(server: Server) -> AsyncIterator[AppContext]:
    """Initialize and clean up application resources."""
    # Get available services
    services = get_available_services()

    try:
        # Log the startup information
        logger.info("Starting MCP Atlassian server")

        # Log read-only mode status
        read_only = is_read_only_mode()
        logger.info(f"Read-only mode: {'ENABLED' if read_only else 'DISABLED'}")

        confluence = None

        # Initialize Confluence if configured
        if services["confluence"]:
            logger.info("Attempting to initialize Confluence client...")
            try:
                confluence_config = ConfluenceConfig.from_env()
                log_config_param(logger, "Confluence", "URL", confluence_config.url)
                log_config_param(
                    logger, "Confluence", "Auth Type", confluence_config.auth_type
                )
                if confluence_config.auth_type == "basic":
                    log_config_param(
                        logger, "Confluence", "Username", confluence_config.username
                    )
                    log_config_param(
                        logger,
                        "Confluence",
                        "API Token",
                        confluence_config.api_token,
                        sensitive=True,
                    )
                else:
                    log_config_param(
                        logger,
                        "Confluence",
                        "Personal Token",
                        confluence_config.personal_token,
                        sensitive=True,
                    )
                log_config_param(
                    logger,
                    "Confluence",
                    "SSL Verify",
                    str(confluence_config.ssl_verify),
                )
                log_config_param(
                    logger,
                    "Confluence",
                    "Spaces Filter",
                    confluence_config.spaces_filter,
                )

                confluence = ConfluenceFetcher(config=confluence_config)
                logger.info("Confluence client initialized successfully.")
            except Exception as e:
                logger.error(
                    f"Failed to initialize Confluence client: {e}", exc_info=True
                )

        # Provide context to the application
        yield AppContext(confluence=confluence)
    finally:
        # Cleanup resources if needed
        pass


# Create server instance
app = Server("mcp-atlassian", lifespan=server_lifespan)


# Implement server handlers
@app.list_resources()
async def list_resources() -> list[Resource]:
    """List Confluence spaces the user is actively interacting with."""
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

    raise ValueError(f"Invalid resource URI: {uri}")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Confluence tools."""
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
                                "description": "Search query - can be either a simple text (e.g. 'project documentation') or a CQL query string. Simple queries use 'siteSearch' by default, to mimic the WebUI search, with an automatic fallback to 'text' search if not supported. Examples of CQL:\n"
                                "- Basic search: 'type=page AND space=DEV'\n"
                                "- Personal space search: 'space=\"~username\"' (note: personal space keys starting with ~ must be quoted)\n"
                                "- Search by title: 'title~\"Meeting Notes\"'\n"
                                "- Use siteSearch: 'siteSearch ~ \"important concept\"'\n"
                                "- Use text search: 'text ~ \"important concept\"'\n"
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
                                "parent_id": {
                                    "type": "string",
                                    "description": "Optional the new parent page ID",
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
                ]
            )

    return tools


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """Handle tool calls for Confluence operations."""
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
                # Convert simple search term to CQL siteSearch (previously it was a 'text' search)
                # This will use the same search mechanism as the WebUI and give much more relevant results
                original_query = query  # Store the original query for fallback
                try:
                    # Try siteSearch first - it's available in newer versions and provides better results
                    query = f'siteSearch ~ "{original_query}"'
                    logger.info(
                        f"Converting simple search term to CQL using siteSearch: {query}"
                    )
                    pages = ctx.confluence.search(
                        query, limit=limit, spaces_filter=spaces_filter
                    )
                except Exception as e:
                    # If siteSearch fails (possibly not supported in this Confluence version),
                    # fall back to text search which is supported in all versions
                    logger.warning(
                        f"siteSearch failed, falling back to text search: {str(e)}"
                    )
                    query = f'text ~ "{original_query}"'
                    logger.info(f"Falling back to text search with CQL: {query}")
                    pages = ctx.confluence.search(
                        query, limit=limit, spaces_filter=spaces_filter
                    )
            else:
                # Using direct CQL query as provided
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
            convert_to_markdown = arguments.get("convert_to_markdown", True)
            start = arguments.get("start", 0)

            # Add body.storage to expand if content is requested
            if include_content and "body" not in expand:
                expand = f"{expand},body.storage" if expand else "body.storage"

            pages = None  # Initialize pages to None before try block

            try:
                pages = ctx.confluence.get_page_children(
                    page_id=parent_id,
                    start=start,
                    limit=limit,
                    expand=expand,
                    convert_to_markdown=convert_to_markdown,
                )

                child_pages = [page.to_simplified_dict() for page in pages]

                result = {
                    "parent_id": parent_id,
                    "total": len(child_pages),
                    "limit": limit,
                    "results": child_pages,
                }

            except Exception as e:
                # --- Error Handling ---
                logger.error(
                    f"Error getting/processing children for page ID {parent_id}: {e}",
                    exc_info=True,
                )
                result = {"error": f"Failed to get child pages: {e}"}

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        result,
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
            parent_id = arguments.get("parent_id")

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
                parent_id=parent_id,
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
