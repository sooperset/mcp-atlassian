"""Confluence FastMCP server instance and tool definitions."""

import json
import logging
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from .context import MainAppContext

logger = logging.getLogger(__name__)

confluence_mcp = FastMCP(
    name="Confluence MCP Service",
    description="Provides tools for interacting with Atlassian Confluence.",
)


@confluence_mcp.tool(tags={"confluence", "read"})
async def search(
    ctx: Context[Any, MainAppContext],
    query: Annotated[
        str,
        Field(
            description=(
                "Search query - can be either a simple text (e.g. 'project documentation') or a CQL query string. "
                "Simple queries use 'siteSearch' by default, to mimic the WebUI search, with an automatic fallback "
                "to 'text' search if not supported. Examples of CQL:\n"
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
                'Note: Special identifiers need proper quoting in CQL: personal space keys (e.g., "~username"), '
                "reserved words, numeric IDs, and identifiers with special characters."
            )
        ),
    ],
    limit: Annotated[
        int,
        Field(
            description="Maximum number of results (1-50)",
            default=10,
            ge=1,
            le=50,
        ),
    ] = 10,
    spaces_filter: Annotated[
        str | None,
        Field(
            description=(
                "Comma-separated list of space keys to filter results by. "
                "Overrides the environment variable CONFLUENCE_SPACES_FILTER if provided."
            ),
        ),
    ] = None,
) -> str:
    """Search Confluence content using simple terms or CQL.

    Args:
        ctx: The FastMCP context.
        query: Search query - can be simple text or a CQL query string.
        limit: Maximum number of results (1-50).
        spaces_filter: Comma-separated list of space keys to filter by.

    Returns:
        JSON string representing a list of simplified Confluence page objects.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.confluence:
        raise ValueError("Confluence client is not configured or available.")
    confluence = lifespan_ctx.confluence

    # Check if the query is a simple search term or already a CQL query
    if query and not any(
        x in query for x in ["=", "~", ">", "<", " AND ", " OR ", "currentUser()"]
    ):
        original_query = query
        try:
            query = f'siteSearch ~ "{original_query}"'
            logger.info(
                f"Converting simple search term to CQL using siteSearch: {query}"
            )
            pages = confluence.search(query, limit=limit, spaces_filter=spaces_filter)
        except Exception as e:
            logger.warning(f"siteSearch failed ('{e}'), falling back to text search.")
            query = f'text ~ "{original_query}"'
            logger.info(f"Falling back to text search with CQL: {query}")
            pages = confluence.search(query, limit=limit, spaces_filter=spaces_filter)
    else:
        pages = confluence.search(query, limit=limit, spaces_filter=spaces_filter)

    search_results = [page.to_simplified_dict() for page in pages]
    return json.dumps(search_results, indent=2, ensure_ascii=False)


@confluence_mcp.tool(tags={"confluence", "read"})
async def get_page(
    ctx: Context[Any, MainAppContext],
    page_id: Annotated[
        str,
        Field(
            description=(
                "Confluence page ID (numeric ID, can be found in the page URL). "
                "For example, in the URL 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title', "
                "the page ID is '123456789'"
            )
        ),
    ],
    include_metadata: Annotated[
        bool,
        Field(
            description="Whether to include page metadata such as creation date, last update, version, and labels",
            default=True,
        ),
    ] = True,
    convert_to_markdown: Annotated[
        bool,
        Field(
            description=(
                "Whether to convert page to markdown (true) or keep it in raw HTML format (false). "
                "Raw HTML can reveal macros (like dates) not visible in markdown, but CAUTION: "
                "using HTML significantly increases token usage in AI responses."
            ),
            default=True,
        ),
    ] = True,
) -> str:
    """Get content of a specific Confluence page by ID.

    Args:
        ctx: The FastMCP context.
        page_id: Confluence page ID.
        include_metadata: Whether to include page metadata.
        convert_to_markdown: Convert content to markdown (true) or keep raw HTML (false).

    Returns:
        JSON string representing the page content and/or metadata.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.confluence:
        raise ValueError("Confluence client is not configured or available.")
    confluence = lifespan_ctx.confluence

    page = confluence.get_page_content(page_id, convert_to_markdown=convert_to_markdown)

    if include_metadata:
        result = {"metadata": page.to_simplified_dict()}
    else:
        result = {"content": page.content}

    return json.dumps(result, indent=2, ensure_ascii=False)


@confluence_mcp.tool(tags={"confluence", "read"})
async def get_page_children(
    ctx: Context[Any, MainAppContext],
    parent_id: Annotated[
        str,
        Field(
            description="The ID of the parent page whose children you want to retrieve"
        ),
    ],
    expand: Annotated[
        str,
        Field(
            description="Fields to expand in the response (e.g., 'version', 'body.storage')",
            default="version",
        ),
    ] = "version",
    limit: Annotated[
        int,
        Field(
            description="Maximum number of child pages to return (1-50)",
            default=25,
            ge=1,
            le=50,
        ),
    ] = 25,
    include_content: Annotated[
        bool,
        Field(
            description="Whether to include the page content in the response",
            default=False,
        ),
    ] = False,
    convert_to_markdown: Annotated[
        bool,
        Field(
            description="Whether to convert page content to markdown (true) or keep it in raw HTML format (false). Only relevant if include_content is true.",
            default=True,
        ),
    ] = True,
    start: Annotated[
        int,
        Field(description="Starting index for pagination (0-based)", default=0, ge=0),
    ] = 0,
) -> str:
    """Get child pages of a specific Confluence page.

    Args:
        ctx: The FastMCP context.
        parent_id: The ID of the parent page.
        expand: Fields to expand.
        limit: Maximum number of child pages.
        include_content: Whether to include page content.
        convert_to_markdown: Convert content to markdown if include_content is true.
        start: Starting index for pagination.

    Returns:
        JSON string representing a list of child page objects.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.confluence:
        raise ValueError("Confluence client is not configured or available.")
    confluence = lifespan_ctx.confluence

    if include_content and "body" not in expand:
        expand = f"{expand},body.storage" if expand else "body.storage"

    try:
        pages = confluence.get_page_children(
            page_id=parent_id,
            start=start,
            limit=limit,
            expand=expand,
            convert_to_markdown=convert_to_markdown,
        )
        child_pages = [page.to_simplified_dict() for page in pages]
        result = {
            "parent_id": parent_id,
            "count": len(child_pages),
            "limit_requested": limit,
            "start_requested": start,
            "results": child_pages,
        }
    except Exception as e:
        logger.error(
            f"Error getting/processing children for page ID {parent_id}: {e}",
            exc_info=True,
        )
        result = {"error": f"Failed to get child pages: {e}"}

    return json.dumps(result, indent=2, ensure_ascii=False)


@confluence_mcp.tool(tags={"confluence", "read"})
async def get_comments(
    ctx: Context[Any, MainAppContext],
    page_id: Annotated[
        str,
        Field(
            description=(
                "Confluence page ID (numeric ID, can be parsed from URL, "
                "e.g. from 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title' "
                "-> '123456789')"
            )
        ),
    ],
) -> str:
    """Get comments for a specific Confluence page.

    Args:
        ctx: The FastMCP context.
        page_id: Confluence page ID.

    Returns:
        JSON string representing a list of comment objects.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.confluence:
        raise ValueError("Confluence client is not configured or available.")
    confluence = lifespan_ctx.confluence

    comments = confluence.get_page_comments(page_id)
    formatted_comments = [comment.to_simplified_dict() for comment in comments]
    return json.dumps(formatted_comments, indent=2, ensure_ascii=False)


@confluence_mcp.tool(tags={"confluence", "read"})
async def get_labels(
    ctx: Context[Any, MainAppContext],
    page_id: Annotated[
        str,
        Field(
            description=(
                "Confluence page ID (numeric ID, can be parsed from URL, "
                "e.g. from 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title' "
                "-> '123456789')"
            )
        ),
    ],
) -> str:
    """Get labels for a specific Confluence page.

    Args:
        ctx: The FastMCP context.
        page_id: Confluence page ID.

    Returns:
        JSON string representing a list of label objects.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if not lifespan_ctx or not lifespan_ctx.confluence:
        raise ValueError("Confluence client is not configured or available.")
    confluence = lifespan_ctx.confluence

    labels = confluence.get_page_labels(page_id)
    formatted_labels = [label.to_simplified_dict() for label in labels]
    return json.dumps(formatted_labels, indent=2, ensure_ascii=False)


@confluence_mcp.tool(tags={"confluence", "write"})
async def add_label(
    ctx: Context[Any, MainAppContext],
    page_id: Annotated[str, Field(description="The ID of the page to update")],
    name: Annotated[str, Field(description="The name of the label")],
) -> str:
    """Add label to an existing Confluence page.

    Args:
        ctx: The FastMCP context.
        page_id: The ID of the page to update.
        name: The name of the label.

    Returns:
        JSON string representing the updated list of label objects for the page.

    Raises:
        ValueError: If in read-only mode or Confluence client is unavailable.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call add_label in read-only mode.")
        raise ValueError("Cannot add label in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.confluence:
        raise ValueError("Confluence client is not configured or available.")
    confluence = lifespan_ctx.confluence

    labels = confluence.add_page_label(page_id, name)
    formatted_labels = [label.to_simplified_dict() for label in labels]
    return json.dumps(formatted_labels, indent=2, ensure_ascii=False)


@confluence_mcp.tool(tags={"confluence", "write"})
async def create_page(
    ctx: Context[Any, MainAppContext],
    space_key: Annotated[
        str,
        Field(
            description="The key of the space to create the page in (usually a short uppercase code like 'DEV', 'TEAM', or 'DOC')"
        ),
    ],
    title: Annotated[str, Field(description="The title of the page")],
    content: Annotated[
        str,
        Field(
            description="The content of the page in Markdown format. Supports headings, lists, tables, code blocks, and other Markdown syntax"
        ),
    ],
    parent_id: Annotated[
        str | None,
        Field(
            description="Optional parent page ID. If provided, this page will be created as a child of the specified page"
        ),
    ] = None,
) -> str:
    """Create a new Confluence page.

    Args:
        ctx: The FastMCP context.
        space_key: The key of the space.
        title: The title of the page.
        content: The content in Markdown format.
        parent_id: Optional parent page ID.

    Returns:
        JSON string representing the created page object.

    Raises:
        ValueError: If in read-only mode or Confluence client is unavailable.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call create_page in read-only mode.")
        raise ValueError("Cannot create page in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.confluence:
        raise ValueError("Confluence client is not configured or available.")
    confluence = lifespan_ctx.confluence

    page = confluence.create_page(
        space_key=space_key,
        title=title,
        body=content,
        parent_id=parent_id,
        is_markdown=True,
    )
    result = page.to_simplified_dict()
    return json.dumps(
        {"message": "Page created successfully", "page": result},
        indent=2,
        ensure_ascii=False,
    )


@confluence_mcp.tool(tags={"confluence", "write"})
async def update_page(
    ctx: Context[Any, MainAppContext],
    page_id: Annotated[str, Field(description="The ID of the page to update")],
    title: Annotated[str, Field(description="The new title of the page")],
    content: Annotated[
        str, Field(description="The new content of the page in Markdown format")
    ],
    is_minor_edit: Annotated[
        bool, Field(description="Whether this is a minor edit", default=False)
    ] = False,
    version_comment: Annotated[
        str, Field(description="Optional comment for this version", default="")
    ] = "",
    parent_id: Annotated[
        str | None, Field(description="Optional the new parent page ID")
    ] = None,
) -> str:
    """Update an existing Confluence page.

    Args:
        ctx: The FastMCP context.
        page_id: The ID of the page to update.
        title: The new title of the page.
        content: The new content in Markdown format.
        is_minor_edit: Whether this is a minor edit.
        version_comment: Optional comment for this version.
        parent_id: Optional new parent page ID.

    Returns:
        JSON string representing the updated page object.

    Raises:
        ValueError: If in read-only mode or Confluence client is unavailable.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call update_page in read-only mode.")
        raise ValueError("Cannot update page in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.confluence:
        raise ValueError("Confluence client is not configured or available.")
    confluence = lifespan_ctx.confluence

    updated_page = confluence.update_page(
        page_id=page_id,
        title=title,
        body=content,
        is_minor_edit=is_minor_edit,
        version_comment=version_comment,
        is_markdown=True,
        parent_id=parent_id,
    )
    page_data = updated_page.to_simplified_dict()
    return json.dumps(
        {"message": "Page updated successfully", "page": page_data},
        indent=2,
        ensure_ascii=False,
    )


@confluence_mcp.tool(tags={"confluence", "write"})
async def delete_page(
    ctx: Context[Any, MainAppContext],
    page_id: Annotated[str, Field(description="The ID of the page to delete")],
) -> str:
    """Delete an existing Confluence page.

    Args:
        ctx: The FastMCP context.
        page_id: The ID of the page to delete.

    Returns:
        JSON string indicating success or failure.

    Raises:
        ValueError: If in read-only mode or Confluence client is unavailable.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx.read_only:
        logger.warning("Attempted to call delete_page in read-only mode.")
        raise ValueError("Cannot delete page in read-only mode.")
    if not lifespan_ctx or not lifespan_ctx.confluence:
        raise ValueError("Confluence client is not configured or available.")
    confluence = lifespan_ctx.confluence

    try:
        result = confluence.delete_page(page_id=page_id)
        if result:
            response = {
                "success": True,
                "message": f"Page {page_id} deleted successfully",
            }
        else:
            response = {
                "success": False,
                "message": f"Unable to delete page {page_id}. API request completed but deletion unsuccessful.",
            }
    except Exception as e:
        logger.error(f"Error deleting Confluence page {page_id}: {str(e)}")
        response = {
            "success": False,
            "message": f"Error deleting page {page_id}",
            "error": str(e),
        }

    return json.dumps(response, indent=2, ensure_ascii=False)
