"""Confluence FastMCP server instance and tool definitions."""

import base64
import json
import logging
import mimetypes
from typing import Annotated

from fastmcp import Context, FastMCP
from mcp.types import BlobResourceContents, EmbeddedResource, ImageContent, TextContent
from pydantic import BeforeValidator, Field

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.models.confluence import ConfluenceAttachment
from mcp_atlassian.servers.dependencies import get_confluence_fetcher
from mcp_atlassian.utils.decorators import (
    check_write_access,
)
from mcp_atlassian.utils.media import is_image_attachment

logger = logging.getLogger(__name__)

_ATTACHMENT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB

confluence_mcp = FastMCP(
    name="Confluence MCP Service",
    instructions="Provides tools for interacting with Atlassian Confluence.",
)


@confluence_mcp.tool(
    tags={"confluence", "read", "toolset:confluence_pages"},
    annotations={"title": "Search Content", "readOnlyHint": True},
)
async def search(
    ctx: Context,
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
                "(Optional) Comma-separated list of space keys to filter results by. "
                "Overrides the environment variable CONFLUENCE_SPACES_FILTER if provided. "
                "Use empty string to disable filtering."
            ),
            default=None,
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
    confluence_fetcher = await get_confluence_fetcher(ctx)
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
            pages = confluence_fetcher.search(
                query, limit=limit, spaces_filter=spaces_filter
            )
        except Exception as e:
            logger.warning(f"siteSearch failed ('{e}'), falling back to text search.")
            query = f'text ~ "{original_query}"'
            logger.info(f"Falling back to text search with CQL: {query}")
            pages = confluence_fetcher.search(
                query, limit=limit, spaces_filter=spaces_filter
            )
    else:
        pages = confluence_fetcher.search(
            query, limit=limit, spaces_filter=spaces_filter
        )
    search_results = [page.to_simplified_dict() for page in pages]
    return json.dumps(search_results, indent=2, ensure_ascii=False)


@confluence_mcp.tool(
    tags={"confluence", "read", "toolset:confluence_pages"},
    annotations={"title": "Get Page", "readOnlyHint": True},
)
async def get_page(
    ctx: Context,
    page_id: Annotated[
        str | None,
        Field(
            description=(
                "Confluence page ID (numeric ID, can be found in the page URL). "
                "For example, in the URL 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title', "
                "the page ID is '123456789'. "
                "Provide this OR both 'title' and 'space_key'. If page_id is provided, title and space_key will be ignored."
            ),
            default=None,
        ),
        BeforeValidator(lambda x: str(x) if x is not None else None),
    ] = None,
    title: Annotated[
        str | None,
        Field(
            description=(
                "The exact title of the Confluence page. Use this with 'space_key' if 'page_id' is not known."
            ),
            default=None,
        ),
    ] = None,
    space_key: Annotated[
        str | None,
        Field(
            description=(
                "The key of the Confluence space where the page resides (e.g., 'DEV', 'TEAM'). Required if using 'title'."
            ),
            default=None,
        ),
    ] = None,
    include_metadata: Annotated[
        bool,
        Field(
            description="Whether to include page metadata such as creation date, last update, version, and labels.",
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
    """Get content of a specific Confluence page by its ID, or by its title and space key.

    Args:
        ctx: The FastMCP context.
        page_id: Confluence page ID. If provided, 'title' and 'space_key' are ignored.
        title: The exact title of the page. Must be used with 'space_key'.
        space_key: The key of the space. Must be used with 'title'.
        include_metadata: Whether to include page metadata.
        convert_to_markdown: Convert content to markdown (true) or keep raw HTML (false).

    Returns:
        JSON string representing the page content and/or metadata, or an error if not found or parameters are invalid.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)
    page_object = None

    if page_id:
        if title or space_key:
            logger.warning(
                "page_id was provided; title and space_key parameters will be ignored."
            )
        try:
            page_id_str = str(page_id)
            page_object = confluence_fetcher.get_page_content(
                page_id_str, convert_to_markdown=convert_to_markdown
            )
        except Exception as e:
            logger.error(f"Error fetching page by ID '{page_id}': {e}")
            return json.dumps(
                {"error": f"Failed to retrieve page by ID '{page_id}': {e}"},
                indent=2,
                ensure_ascii=False,
            )
    elif title and space_key:
        page_object = confluence_fetcher.get_page_by_title(
            space_key, title, convert_to_markdown=convert_to_markdown
        )
        if not page_object:
            return json.dumps(
                {
                    "error": f"Page with title '{title}' not found in space '{space_key}'."
                },
                indent=2,
                ensure_ascii=False,
            )
    else:
        raise ValueError(
            "Either 'page_id' OR both 'title' and 'space_key' must be provided."
        )

    if not page_object:
        return json.dumps(
            {"error": "Page not found with the provided identifiers."},
            indent=2,
            ensure_ascii=False,
        )

    if include_metadata:
        result = {"metadata": page_object.to_simplified_dict()}
    else:
        result = {"content": {"value": page_object.content}}

    return json.dumps(result, indent=2, ensure_ascii=False)


@confluence_mcp.tool(
    tags={"confluence", "read", "toolset:confluence_pages"},
    annotations={"title": "Get Page Children", "readOnlyHint": True},
)
async def get_page_children(
    ctx: Context,
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
            description="Maximum number of child items to return (1-50)",
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
    include_folders: Annotated[
        bool,
        Field(
            description="Whether to include child folders in addition to child pages",
            default=True,
        ),
    ] = True,
) -> str:
    """Get child pages and folders of a specific Confluence page.

    Args:
        ctx: The FastMCP context.
        parent_id: The ID of the parent page.
        expand: Fields to expand.
        limit: Maximum number of child items.
        include_content: Whether to include page content.
        convert_to_markdown: Convert content to markdown if include_content is true.
        start: Starting index for pagination.
        include_folders: Whether to include child folders (default: True).

    Returns:
        JSON string representing a list of child page and folder objects.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)
    if include_content and "body" not in expand:
        expand = f"{expand},body.storage" if expand else "body.storage"

    try:
        pages = confluence_fetcher.get_page_children(
            page_id=parent_id,
            start=start,
            limit=limit,
            expand=expand,
            convert_to_markdown=convert_to_markdown,
            include_folders=include_folders,
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


@confluence_mcp.tool(
    tags={"confluence", "read", "toolset:confluence_comments"},
    annotations={"title": "Get Comments", "readOnlyHint": True},
)
async def get_comments(
    ctx: Context,
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
    confluence_fetcher = await get_confluence_fetcher(ctx)
    comments = confluence_fetcher.get_page_comments(page_id)
    formatted_comments = [comment.to_simplified_dict() for comment in comments]
    return json.dumps(formatted_comments, indent=2, ensure_ascii=False)


@confluence_mcp.tool(
    tags={"confluence", "read", "toolset:confluence_labels"},
    annotations={"title": "Get Labels", "readOnlyHint": True},
)
async def get_labels(
    ctx: Context,
    page_id: Annotated[
        str,
        Field(
            description=(
                "Confluence content ID (page, blog post, or attachment). "
                "For pages: numeric ID from URL (e.g., '123456789'). "
                "For attachments: ID with 'att' prefix (e.g., 'att123456789'). "
                "Works with any Confluence content type that supports labels."
            )
        ),
    ],
) -> str:
    """Get labels for Confluence content (pages, blog posts, or attachments).

    Args:
        ctx: The FastMCP context.
        page_id: Confluence content ID (page or attachment).

    Returns:
        JSON string representing a list of label objects.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)
    labels = confluence_fetcher.get_page_labels(page_id)
    formatted_labels = [label.to_simplified_dict() for label in labels]
    return json.dumps(formatted_labels, indent=2, ensure_ascii=False)


@confluence_mcp.tool(
    tags={"confluence", "write", "toolset:confluence_labels"},
    annotations={"title": "Add Label", "destructiveHint": True},
)
@check_write_access
async def add_label(
    ctx: Context,
    page_id: Annotated[
        str,
        Field(
            description=(
                "Confluence content ID to label. "
                "For pages/blogs: numeric ID (e.g., '123456789'). "
                "For attachments: ID with 'att' prefix (e.g., 'att123456789'). "
                "Use get_attachments to find attachment IDs."
            )
        ),
    ],
    name: Annotated[
        str,
        Field(
            description=(
                "Label name to add (lowercase, no spaces). "
                "Examples: 'draft', 'reviewed', 'confidential', 'v1.0'. "
                "Labels help organize and categorize content."
            )
        ),
    ],
) -> str:
    """Add label to Confluence content (pages, blog posts, or attachments).

    Useful for:
    - Categorizing attachments (e.g., 'screenshot', 'diagram', 'legal-doc')
    - Tracking status (e.g., 'approved', 'needs-review', 'archived')
    - Filtering content by topic or version

    Args:
        ctx: The FastMCP context.
        page_id: Content ID (page or attachment).
        name: Label name to add.

    Returns:
        JSON string representing the updated list of label objects.

    Raises:
        ValueError: If in read-only mode or Confluence client is unavailable.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)
    labels = confluence_fetcher.add_page_label(page_id, name)
    formatted_labels = [label.to_simplified_dict() for label in labels]
    return json.dumps(formatted_labels, indent=2, ensure_ascii=False)


@confluence_mcp.tool(
    tags={"confluence", "write", "toolset:confluence_pages"},
    annotations={"title": "Create Page", "destructiveHint": True},
)
@check_write_access
async def create_page(
    ctx: Context,
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
            description="The content of the page. Format depends on content_format parameter. Can be Markdown (default), wiki markup, or storage format"
        ),
    ],
    parent_id: Annotated[
        str | None,
        Field(
            description="(Optional) parent page ID. If provided, this page will be created as a child of the specified page",
            default=None,
        ),
        BeforeValidator(lambda x: str(x) if x is not None else None),
    ] = None,
    content_format: Annotated[
        str,
        Field(
            description="(Optional) The format of the content parameter. Options: 'markdown' (default), 'wiki', or 'storage'. Wiki format uses Confluence wiki markup syntax",
            default="markdown",
        ),
    ] = "markdown",
    enable_heading_anchors: Annotated[
        bool,
        Field(
            description="(Optional) Whether to enable automatic heading anchor generation. Only applies when content_format is 'markdown'",
            default=False,
        ),
    ] = False,
    emoji: Annotated[
        str | None,
        Field(
            description="(Optional) Page title emoji (icon shown in navigation). Can be any emoji character like '📝', '🚀', '📚'. Set to null/None to remove.",
            default=None,
        ),
    ] = None,
) -> str:
    """Create a new Confluence page.

    Args:
        ctx: The FastMCP context.
        space_key: The key of the space.
        title: The title of the page.
        content: The content of the page (format depends on content_format).
        parent_id: Optional parent page ID.
        content_format: The format of the content ('markdown', 'wiki', or 'storage').
        enable_heading_anchors: Whether to enable heading anchors (markdown only).
        emoji: Optional page title emoji (icon shown in navigation).

    Returns:
        JSON string representing the created page object.

    Raises:
        ValueError: If in read-only mode, Confluence client is unavailable, or invalid content_format.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)

    # Validate content_format
    if content_format not in ["markdown", "wiki", "storage"]:
        raise ValueError(
            f"Invalid content_format: {content_format}. Must be 'markdown', 'wiki', or 'storage'"
        )

    # Determine parameters based on content format
    if content_format == "markdown":
        is_markdown = True
        content_representation = None  # Will be converted to storage
    else:
        is_markdown = False
        content_representation = content_format  # Pass 'wiki' or 'storage' directly

    page = confluence_fetcher.create_page(
        space_key=space_key,
        title=title,
        body=content,
        parent_id=parent_id,
        is_markdown=is_markdown,
        enable_heading_anchors=enable_heading_anchors
        if content_format == "markdown"
        else False,
        content_representation=content_representation,
        emoji=emoji,
    )
    result = page.to_simplified_dict()
    return json.dumps(
        {"message": "Page created successfully", "page": result},
        indent=2,
        ensure_ascii=False,
    )


@confluence_mcp.tool(
    tags={"confluence", "write", "toolset:confluence_pages"},
    annotations={"title": "Update Page", "destructiveHint": True},
)
@check_write_access
async def update_page(
    ctx: Context,
    page_id: Annotated[str, Field(description="The ID of the page to update")],
    title: Annotated[str, Field(description="The new title of the page")],
    content: Annotated[
        str,
        Field(
            description="The new content of the page. Format depends on content_format parameter"
        ),
    ],
    is_minor_edit: Annotated[
        bool, Field(description="Whether this is a minor edit", default=False)
    ] = False,
    version_comment: Annotated[
        str | None, Field(description="Optional comment for this version", default=None)
    ] = None,
    parent_id: Annotated[
        str | None,
        Field(description="Optional the new parent page ID", default=None),
        BeforeValidator(lambda x: str(x) if x is not None else None),
    ] = None,
    content_format: Annotated[
        str,
        Field(
            description="(Optional) The format of the content parameter. Options: 'markdown' (default), 'wiki', or 'storage'. Wiki format uses Confluence wiki markup syntax",
            default="markdown",
        ),
    ] = "markdown",
    enable_heading_anchors: Annotated[
        bool,
        Field(
            description="(Optional) Whether to enable automatic heading anchor generation. Only applies when content_format is 'markdown'",
            default=False,
        ),
    ] = False,
    emoji: Annotated[
        str | None,
        Field(
            description="(Optional) Page title emoji (icon shown in navigation). Can be any emoji character like '📝', '🚀', '📚'. Set to null/None to remove.",
            default=None,
        ),
    ] = None,
) -> str:
    """Update an existing Confluence page.

    Args:
        ctx: The FastMCP context.
        page_id: The ID of the page to update.
        title: The new title of the page.
        content: The new content of the page (format depends on content_format).
        is_minor_edit: Whether this is a minor edit.
        version_comment: Optional comment for this version.
        parent_id: Optional new parent page ID.
        content_format: The format of the content ('markdown', 'wiki', or 'storage').
        enable_heading_anchors: Whether to enable heading anchors (markdown only).
        emoji: Optional page title emoji (icon shown in navigation).

    Returns:
        JSON string representing the updated page object.

    Raises:
        ValueError: If Confluence client is not configured, available, or invalid content_format.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)

    # Validate content_format
    if content_format not in ["markdown", "wiki", "storage"]:
        raise ValueError(
            f"Invalid content_format: {content_format}. Must be 'markdown', 'wiki', or 'storage'"
        )

    # Determine parameters based on content format
    if content_format == "markdown":
        is_markdown = True
        content_representation = None  # Will be converted to storage
    else:
        is_markdown = False
        content_representation = content_format  # Pass 'wiki' or 'storage' directly

    updated_page = confluence_fetcher.update_page(
        page_id=page_id,
        title=title,
        body=content,
        is_minor_edit=is_minor_edit,
        version_comment=version_comment,
        is_markdown=is_markdown,
        parent_id=parent_id,
        enable_heading_anchors=enable_heading_anchors
        if content_format == "markdown"
        else False,
        content_representation=content_representation,
        emoji=emoji,
    )
    page_data = updated_page.to_simplified_dict()
    return json.dumps(
        {"message": "Page updated successfully", "page": page_data},
        indent=2,
        ensure_ascii=False,
    )


@confluence_mcp.tool(
    tags={"confluence", "write", "toolset:confluence_pages"},
    annotations={"title": "Delete Page", "destructiveHint": True},
)
@check_write_access
async def delete_page(
    ctx: Context,
    page_id: Annotated[str, Field(description="The ID of the page to delete")],
) -> str:
    """Delete an existing Confluence page.

    Args:
        ctx: The FastMCP context.
        page_id: The ID of the page to delete.

    Returns:
        JSON string indicating success or failure.

    Raises:
        ValueError: If Confluence client is not configured or available.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)
    try:
        result = confluence_fetcher.delete_page(page_id=page_id)
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


@confluence_mcp.tool(
    tags={"confluence", "write", "toolset:confluence_comments"},
    annotations={"title": "Add Comment", "destructiveHint": True},
)
@check_write_access
async def add_comment(
    ctx: Context,
    page_id: Annotated[
        str, Field(description="The ID of the page to add a comment to")
    ],
    content: Annotated[
        str, Field(description="The comment content in Markdown format")
    ],
) -> str:
    """Add a comment to a Confluence page.

    Args:
        ctx: The FastMCP context.
        page_id: The ID of the page to add a comment to.
        content: The comment content in Markdown format.

    Returns:
        JSON string representing the created comment.

    Raises:
        ValueError: If in read-only mode or Confluence client is unavailable.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)
    try:
        comment = confluence_fetcher.add_comment(page_id=page_id, content=content)
        if comment:
            comment_data = comment.to_simplified_dict()
            response = {
                "success": True,
                "message": "Comment added successfully",
                "comment": comment_data,
            }
        else:
            response = {
                "success": False,
                "message": f"Unable to add comment to page {page_id}. API request completed but comment creation unsuccessful.",
            }
    except Exception as e:
        logger.error(f"Error adding comment to Confluence page {page_id}: {str(e)}")
        response = {
            "success": False,
            "message": f"Error adding comment to page {page_id}",
            "error": str(e),
        }

    return json.dumps(response, indent=2, ensure_ascii=False)


@confluence_mcp.tool(
    tags={"confluence", "read", "toolset:confluence_users"},
    annotations={"title": "Search User", "readOnlyHint": True},
)
async def search_user(
    ctx: Context,
    query: Annotated[
        str,
        Field(
            description=(
                "Search query - a CQL query string for user search. "
                "Examples of CQL:\n"
                "- Basic user lookup by full name: 'user.fullname ~ \"First Last\"'\n"
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
) -> str:
    """Search Confluence users using CQL.

    Args:
        ctx: The FastMCP context.
        query: Search query - a CQL query string for user search.
        limit: Maximum number of results (1-50).

    Returns:
        JSON string representing a list of simplified Confluence user search result objects.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)

    # If the query doesn't look like CQL, wrap it as a user fullname search
    if query and not any(
        x in query for x in ["=", "~", ">", "<", " AND ", " OR ", "user."]
    ):
        # Simple search term - search by fullname
        query = f'user.fullname ~ "{query}"'
        logger.info(f"Converting simple search term to user CQL: {query}")

    try:
        user_results = confluence_fetcher.search_user(query, limit=limit)
        search_results = [user.to_simplified_dict() for user in user_results]
        return json.dumps(search_results, indent=2, ensure_ascii=False)
    except MCPAtlassianAuthenticationError as e:
        logger.error(f"Authentication error during user search: {e}", exc_info=False)
        return json.dumps(
            {
                "error": "Authentication failed. Please check your credentials.",
                "details": str(e),
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"Error searching users: {str(e)}")
        return json.dumps(
            {
                "error": f"An unexpected error occurred while searching for users: {str(e)}"
            },
            indent=2,
            ensure_ascii=False,
        )


@confluence_mcp.tool(
    tags={"confluence", "read", "toolset:confluence_pages"},
    annotations={"title": "Get Page History", "readOnlyHint": True},
)
async def get_page_history(
    ctx: Context,
    page_id: Annotated[
        str,
        Field(
            description=(
                "Confluence page ID (numeric ID, can be found in the page URL). "
                "For example, in 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title', "
                "the page ID is '123456789'."
            )
        ),
    ],
    version: Annotated[
        int,
        Field(
            description="The version number of the page to retrieve",
            ge=1,
        ),
    ],
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
    """Get a historical version of a specific Confluence page.

    Args:
        ctx: The FastMCP context.
        page_id: Confluence page ID.
        version: The version number to retrieve.
        convert_to_markdown: Convert content to markdown (true) or keep raw HTML (false).

    Returns:
        JSON string representing the page content at the specified version.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)
    try:
        page = confluence_fetcher.get_page_history(
            page_id=page_id,
            version=version,
            convert_to_markdown=convert_to_markdown,
        )
        result = page.to_simplified_dict()
        return json.dumps(result, indent=2, ensure_ascii=False)
    except MCPAtlassianAuthenticationError as e:
        logger.error(f"Authentication error getting page history: {e}")
        return json.dumps(
            {
                "error": "Authentication failed. Please check your credentials.",
                "details": str(e),
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(
            f"Error getting page history for page {page_id} version {version}: {e}"
        )
        return json.dumps(
            {
                "error": f"Failed to get page history: {e}",
                "page_id": page_id,
                "version": version,
            },
            indent=2,
            ensure_ascii=False,
        )


@confluence_mcp.tool(
    tags={"confluence", "read", "analytics", "toolset:confluence_analytics"},
    annotations={"title": "Get Page Views", "readOnlyHint": True},
)
async def get_page_views(
    ctx: Context,
    page_id: Annotated[
        str,
        Field(
            description=(
                "Confluence page ID (numeric ID, can be found in the page URL). "
                "For example, in 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title', "
                "the page ID is '123456789'."
            )
        ),
    ],
    include_title: Annotated[
        bool,
        Field(description="Whether to fetch and include the page title"),
    ] = True,
) -> str:
    """Get view statistics for a Confluence page.

    Note: This tool is only available for Confluence Cloud. Server/Data Center
    instances do not support the Analytics API.

    Args:
        ctx: The FastMCP context.
        page_id: The Confluence page ID.
        include_title: Whether to include the page title in the response.

    Returns:
        JSON string with page view statistics including total views and last viewed date.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)
    try:
        result = confluence_fetcher.get_page_views(
            page_id=page_id,
            include_title=include_title,
        )
        return json.dumps(result.to_simplified_dict(), indent=2, ensure_ascii=False)
    except MCPAtlassianAuthenticationError as e:
        logger.error(f"Authentication error getting page views: {e}")
        return json.dumps(
            {
                "error": "Authentication failed. Please check your credentials.",
                "details": str(e),
            },
            indent=2,
            ensure_ascii=False,
        )
    except ValueError as e:
        logger.error(f"Error getting page views for {page_id}: {e}")
        return json.dumps(
            {"error": str(e), "page_id": page_id},
            indent=2,
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"Unexpected error getting page views for {page_id}: {e}")
        return json.dumps(
            {"error": f"Failed to get page views: {e}", "page_id": page_id},
            indent=2,
            ensure_ascii=False,
        )


# ===== Attachment Operations =====


@confluence_mcp.tool(
    tags={"confluence", "write", "attachments", "toolset:confluence_attachments"},
    annotations={"title": "Upload Attachment", "destructiveHint": True},
)
@check_write_access
async def upload_attachment(
    ctx: Context,
    content_id: Annotated[
        str,
        Field(
            description=(
                "The ID of the Confluence content (page or blog post) to attach the file to. "
                "Page IDs can be found in the page URL or by using the search/get_page tools. "
                "Example: '123456789'"
            )
        ),
    ],
    file_path: Annotated[
        str,
        Field(
            description=(
                "Full path to the file to upload. Can be absolute (e.g., '/home/user/document.pdf' or 'C:\\Users\\name\\file.docx') "
                "or relative to the current working directory (e.g., './uploads/document.pdf'). "
                "If a file with the same name already exists, a new version will be created."
            )
        ),
    ],
    comment: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) A comment describing this attachment or version. "
                "Visible in the attachment history. Example: 'Updated Q4 2024 figures'"
            ),
            default=None,
        ),
    ] = None,
    minor_edit: Annotated[
        bool,
        Field(
            description=(
                "(Optional) Whether this is a minor edit. If true, watchers are not notified. "
                "Default is false."
            ),
            default=False,
        ),
    ] = False,
) -> str:
    """Upload an attachment to Confluence content (page or blog post).

    If the attachment already exists (same filename), a new version is created.
    This is useful for:
    - Attaching documents, images, or files to a page
    - Updating existing attachments with new versions
    - Adding supporting materials to documentation

    Args:
        ctx: The FastMCP context.
        content_id: The ID of the content to attach to.
        file_path: Path to the file to upload.
        comment: Optional comment for the attachment.
        minor_edit: Whether this is a minor edit (no notifications).

    Returns:
        JSON string with upload confirmation and attachment metadata.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)

    result = confluence_fetcher.upload_attachment(
        content_id=content_id,
        file_path=file_path,
        comment=comment,
        minor_edit=minor_edit,
    )

    return json.dumps(
        {"message": "Attachment uploaded successfully", "attachment": result},
        indent=2,
        ensure_ascii=False,
    )


@confluence_mcp.tool(
    tags={"confluence", "write", "attachments", "toolset:confluence_attachments"},
    annotations={"title": "Upload Multiple Attachments", "destructiveHint": True},
)
@check_write_access
async def upload_attachments(
    ctx: Context,
    content_id: Annotated[
        str,
        Field(
            description=(
                "The ID of the Confluence content (page or blog post) to attach files to. "
                "Example: '123456789'. If uploading multiple files with the same names, "
                "new versions will be created automatically."
            )
        ),
    ],
    file_paths: Annotated[
        str,
        Field(
            description=(
                "Comma-separated list of file paths to upload. Can be absolute or relative paths. "
                "Examples: './file1.pdf,./file2.png' or 'C:\\docs\\report.docx,D:\\image.jpg'. "
                "All files uploaded with same comment/minor_edit settings."
            )
        ),
    ],
    comment: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Comment for all uploaded attachments. Visible in version history. "
                "Example: 'Q4 2024 batch upload'"
            ),
            default=None,
        ),
    ] = None,
    minor_edit: Annotated[
        bool,
        Field(
            description=(
                "(Optional) Whether this is a minor edit. If true, watchers are not notified. "
                "Default is false."
            ),
            default=False,
        ),
    ] = False,
) -> str:
    """Upload multiple attachments to Confluence content in a single operation.

    More efficient than calling upload_attachment multiple times. If files with the
    same names exist, new versions are created automatically.

    Useful for:
    - Bulk uploading documentation assets (diagrams, screenshots, etc.)
    - Adding multiple related files to a page at once
    - Batch updating existing attachments with new versions

    Args:
        ctx: The FastMCP context.
        content_id: The ID of the content to attach to.
        file_paths: List of file paths to upload.
        comment: Optional comment for the attachments.
        minor_edit: Whether this is a minor edit.

    Returns:
        JSON string with upload results for each file.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)

    paths_list = [p.strip() for p in file_paths.split(",") if p.strip()]

    results = confluence_fetcher.upload_attachments(
        content_id=content_id,
        file_paths=paths_list,
        comment=comment,
        minor_edit=minor_edit,
    )

    return json.dumps(
        {
            "message": f"Uploaded {len(results)} attachment(s) successfully",
            "attachments": results,
        },
        indent=2,
        ensure_ascii=False,
    )


@confluence_mcp.tool(
    tags={"confluence", "read", "attachments", "toolset:confluence_attachments"},
    annotations={"title": "Get Content Attachments", "readOnlyHint": True},
)
async def get_attachments(
    ctx: Context,
    content_id: Annotated[
        str,
        Field(
            description=(
                "The ID of the Confluence content (page or blog post) to list attachments for. "
                "Example: '123456789'"
            )
        ),
    ],
    start: Annotated[
        int,
        Field(
            description=(
                "(Optional) Starting index for pagination. Use 0 for the first page. "
                "To get the next page, add the 'limit' value to 'start'. Default: 0"
            ),
            default=0,
        ),
    ] = 0,
    limit: Annotated[
        int,
        Field(
            description=(
                "(Optional) Maximum number of attachments to return per request (1-100). "
                "Use pagination (start/limit) for large attachment lists. Default: 50"
            ),
            default=50,
            ge=1,
            le=100,
        ),
    ] = 50,
    filename: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Filter results to only attachments matching this filename. "
                "Exact match only. Example: 'report.pdf'"
            ),
            default=None,
        ),
    ] = None,
    media_type: Annotated[
        str | None,
        Field(
            description=(
                "(Optional) Filter by MIME type. "
                "**Note**: Confluence API returns 'application/octet-stream' for most binary files "
                "(PNG, JPG, PDF) instead of specific MIME types like 'image/png'. "
                "For more reliable filtering, use the 'filename' parameter. "
                "Examples: 'application/octet-stream' (binary files), 'application/pdf', "
                "'application/vnd.openxmlformats-officedocument.wordprocessingml.document' (for .docx)"
            ),
            default=None,
        ),
    ] = None,
) -> str:
    """List all attachments for a Confluence content item (page or blog post).

    Returns metadata about attachments including:
    - Attachment ID, title, and file type
    - File size and download URL
    - Creation/modification dates
    - Version information

    **Important**: Confluence API returns 'application/octet-stream' as the media type
    for most binary files (PNG, JPG, PDF) instead of specific types like 'image/png'.
    For filtering by file type, using the 'filename' parameter is more reliable
    (e.g., filename='*.png' pattern matching if supported, or exact filename).

    Useful for:
    - Discovering what files are attached to a page
    - Getting attachment IDs for download operations
    - Checking if a specific file exists
    - Listing images/documents for processing

    Args:
        ctx: The FastMCP context.
        content_id: The ID of the content.
        start: Starting index for pagination.
        limit: Maximum number of results (1-100).
        filename: Optional exact filename filter.
        media_type: Optional MIME type filter (note: most binaries return 'application/octet-stream').

    Returns:
        JSON string with list of attachments and metadata.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)

    result = confluence_fetcher.get_content_attachments(
        content_id=content_id,
        start=start,
        limit=limit,
        filename=filename,
        media_type=media_type,
    )

    return json.dumps(result, indent=2, ensure_ascii=False)


@confluence_mcp.tool(
    tags={"confluence", "read", "attachments", "toolset:confluence_attachments"},
    annotations={"title": "Download Attachment", "readOnlyHint": True},
)
async def download_attachment(
    ctx: Context,
    attachment_id: Annotated[
        str,
        Field(
            description=(
                "The ID of the attachment to download (e.g., 'att123456789'). "
                "Find attachment IDs using get_attachments tool. "
                "Example workflow: get_attachments(content_id) → use returned ID here."
            )
        ),
    ],
) -> TextContent | EmbeddedResource:
    """Download an attachment from Confluence as an embedded resource.

    Returns the attachment content as a base64-encoded embedded resource so
    that it is available over the MCP protocol without requiring filesystem
    access on the server. Files larger than 50 MB are not downloaded inline;
    a descriptive error message is returned instead.

    Args:
        ctx: The FastMCP context.
        attachment_id: The ID of the attachment.

    Returns:
        An EmbeddedResource with base64-encoded content, or a TextContent
        with an error or size-exceeded message.
    """

    confluence_fetcher = await get_confluence_fetcher(ctx)

    try:
        v2_adapter = confluence_fetcher._v2_adapter

        if v2_adapter:
            attachment_data = v2_adapter.get_attachment_by_id(attachment_id)
        else:
            base_url = confluence_fetcher.config.url.rstrip("/")
            url = f"{base_url}/rest/api/content/{attachment_id}"
            resp_meta = confluence_fetcher.confluence._session.get(url)
            resp_meta.raise_for_status()
            attachment_data = resp_meta.json()

        download_url = attachment_data.get("_links", {}).get("download")
        if not download_url:
            return TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": False,
                        "error": (
                            f"Could not find download URL for attachment {attachment_id}"
                        ),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )

        if download_url.startswith("/"):
            base_url = confluence_fetcher.config.url.rstrip("/")
            download_url = f"{base_url}{download_url}"

        filename = attachment_data.get("title") or attachment_id
        mime_type = (
            attachment_data.get("extensions", {}).get("mediaType")
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        file_size = attachment_data.get("extensions", {}).get("fileSize")

        if file_size is not None and file_size > _ATTACHMENT_MAX_BYTES:
            return TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": False,
                        "attachment_id": attachment_id,
                        "filename": filename,
                        "file_size": file_size,
                        "error": (
                            f"Attachment '{filename}' is {file_size} bytes which exceeds "
                            "the 50 MB inline limit. Retrieve it directly from Confluence."
                        ),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )

        data_bytes = confluence_fetcher.fetch_attachment_content(download_url)
        if data_bytes is None:
            return TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": False,
                        "error": (f"Failed to download attachment {attachment_id}"),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )

        if len(data_bytes) > _ATTACHMENT_MAX_BYTES:
            return TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": False,
                        "attachment_id": attachment_id,
                        "filename": filename,
                        "file_size": len(data_bytes),
                        "error": (
                            f"Attachment '{filename}' is {len(data_bytes)} bytes which "
                            "exceeds the 50 MB inline limit. Retrieve it directly from "
                            "Confluence."
                        ),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )

        encoded = base64.b64encode(data_bytes).decode("ascii")
        return EmbeddedResource(
            type="resource",
            resource=BlobResourceContents(
                uri=f"attachment:///{attachment_id}/{filename}",
                mimeType=mime_type,
                blob=encoded,
            ),
        )

    except Exception as e:
        return TextContent(
            type="text",
            text=json.dumps(
                {
                    "success": False,
                    "error": f"Error downloading attachment: {str(e)}",
                },
                indent=2,
                ensure_ascii=False,
            ),
        )


@confluence_mcp.tool(
    tags={"confluence", "read", "attachments", "toolset:confluence_attachments"},
    annotations={"title": "Download All Content Attachments", "readOnlyHint": True},
)
async def download_content_attachments(
    ctx: Context,
    content_id: Annotated[
        str,
        Field(
            description=(
                "The ID of the Confluence content (page or blog post) to download attachments from. "
                "Example: '123456789'"
            )
        ),
    ],
) -> list[TextContent | EmbeddedResource]:
    """Download all attachments for a Confluence content item as embedded resources.

    Returns attachment contents as base64-encoded embedded resources so that
    they are available over the MCP protocol without requiring filesystem
    access on the server. Files larger than 50 MB are skipped with an error
    entry in the summary.

    Args:
        ctx: The FastMCP context.
        content_id: The ID of the content.

    Returns:
        A list with a text summary followed by one EmbeddedResource per
        successfully downloaded attachment.
    """

    confluence_fetcher = await get_confluence_fetcher(ctx)
    contents: list[TextContent | EmbeddedResource] = []

    attachments_result = confluence_fetcher.get_content_attachments(content_id)

    if not attachments_result.get("success"):
        contents.append(
            TextContent(
                type="text",
                text=json.dumps(attachments_result, indent=2, ensure_ascii=False),
            )
        )
        return contents

    attachment_data = attachments_result.get("attachments", [])

    if not attachment_data:
        contents.append(
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": True,
                        "content_id": content_id,
                        "message": f"No attachments found for content {content_id}",
                        "downloaded": 0,
                        "failed": [],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )
        )
        return contents

    fetched: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []

    for att_dict in attachment_data:
        if not isinstance(att_dict, dict):
            continue
        attachment = ConfluenceAttachment.from_api_response(att_dict)

        if not attachment.download_url:
            failed.append(
                {
                    "filename": attachment.title or "unknown",
                    "error": "No download URL available",
                }
            )
            continue

        filename = attachment.title or "unknown"
        mime_type = (
            attachment.media_type
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )

        if (
            attachment.file_size is not None
            and attachment.file_size > _ATTACHMENT_MAX_BYTES
        ):
            failed.append(
                {
                    "filename": filename,
                    "error": (
                        f"File is {attachment.file_size} bytes which exceeds "
                        "the 50 MB inline limit."
                    ),
                }
            )
            continue

        download_url = attachment.download_url
        if download_url.startswith("/"):
            base_url = confluence_fetcher.config.url.rstrip("/")
            download_url = f"{base_url}{download_url}"

        data_bytes = confluence_fetcher.fetch_attachment_content(download_url)
        if data_bytes is None:
            failed.append({"filename": filename, "error": "Fetch failed"})
            continue

        if len(data_bytes) > _ATTACHMENT_MAX_BYTES:
            failed.append(
                {
                    "filename": filename,
                    "error": (
                        f"Downloaded size {len(data_bytes)} bytes exceeds "
                        "the 50 MB inline limit."
                    ),
                }
            )
            continue

        encoded = base64.b64encode(data_bytes).decode("ascii")
        fetched.append({"filename": filename, "size": len(data_bytes)})
        contents.append(
            EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(
                    uri=f"attachment:///{content_id}/{filename}",
                    mimeType=mime_type,
                    blob=encoded,
                ),
            )
        )

    summary: dict[str, object] = {
        "success": True,
        "content_id": content_id,
        "total": len(attachment_data),
        "downloaded": len(fetched),
        "failed": failed,
    }
    contents.insert(
        0,
        TextContent(
            type="text",
            text=json.dumps(summary, indent=2, ensure_ascii=False),
        ),
    )
    return contents


@confluence_mcp.tool(
    tags={"confluence", "write", "attachments", "toolset:confluence_attachments"},
    annotations={"title": "Delete Attachment", "destructiveHint": True},
)
@check_write_access
async def delete_attachment(
    ctx: Context,
    attachment_id: Annotated[
        str,
        Field(
            description=(
                "The ID of the attachment to delete. Attachment IDs can be found using the "
                "get_attachments tool. Example: 'att123456789'. "
                "**Warning**: This permanently deletes the attachment and all its versions."
            )
        ),
    ],
) -> str:
    """Permanently delete an attachment from Confluence.

    **Warning**: This action cannot be undone! The attachment and ALL its versions will be
    permanently deleted.

    Use this tool to:
    - Remove outdated or incorrect attachments
    - Clean up duplicate files
    - Delete sensitive information that was accidentally uploaded

    Best practices:
    - Verify the attachment ID before deletion using get_attachments
    - Consider downloading the attachment first as a backup
    - Check with content owners before deleting shared attachments

    Args:
        ctx: The FastMCP context.
        attachment_id: The ID of the attachment to delete.

    Returns:
        JSON string confirming deletion with attachment ID.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)

    confluence_fetcher.delete_attachment(attachment_id=attachment_id)

    return json.dumps(
        {
            "message": "Attachment deleted successfully",
            "attachment_id": attachment_id,
        },
        indent=2,
        ensure_ascii=False,
    )


@confluence_mcp.tool(
    tags={"confluence", "read", "attachments", "toolset:confluence_attachments"},
    annotations={"title": "Get Page Images", "readOnlyHint": True},
)
async def get_page_images(
    ctx: Context,
    content_id: Annotated[
        str,
        Field(
            description=(
                "The ID of the Confluence page or blog post to retrieve "
                "images from. Example: '123456789'"
            )
        ),
    ],
) -> list[TextContent | ImageContent]:
    """Get all images attached to a Confluence page as inline image content.

    Filters attachments to images only (PNG, JPEG, GIF, WebP, SVG, BMP)
    and returns them as base64-encoded ImageContent that clients can
    render directly. Non-image attachments are excluded.

    Files with ambiguous MIME types (application/octet-stream) are
    detected by filename extension as a fallback. Images larger than
    50 MB are skipped with an error entry in the summary.

    Args:
        ctx: The FastMCP context.
        content_id: The ID of the content.

    Returns:
        A list with a text summary followed by one ImageContent per
        successfully downloaded image.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)
    contents: list[TextContent | ImageContent] = []

    attachments_result = confluence_fetcher.get_content_attachments(content_id)

    if not attachments_result.get("success"):
        contents.append(
            TextContent(
                type="text",
                text=json.dumps(attachments_result, indent=2, ensure_ascii=False),
            )
        )
        return contents

    attachment_data = attachments_result.get("attachments", [])

    # Filter to image attachments
    image_attachments: list[tuple[dict[str, object], str]] = []
    for att_dict in attachment_data:
        if not isinstance(att_dict, dict):
            continue
        media_type = att_dict.get("extensions", {}).get("mediaType") or att_dict.get(
            "metadata", {}
        ).get("mediaType")
        filename = att_dict.get("title")
        is_img, resolved_mime = is_image_attachment(media_type, filename)
        if is_img:
            image_attachments.append((att_dict, resolved_mime))

    if not image_attachments:
        contents.append(
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": True,
                        "content_id": content_id,
                        "total_images": 0,
                        "downloaded": 0,
                        "failed": [],
                        "message": "No image attachments found",
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
            )
        )
        return contents

    fetched: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []

    for att_dict, resolved_mime in image_attachments:
        attachment = ConfluenceAttachment.from_api_response(att_dict)
        filename = attachment.title or "unknown"

        if (
            attachment.file_size is not None
            and attachment.file_size > _ATTACHMENT_MAX_BYTES
        ):
            failed.append(
                {
                    "filename": filename,
                    "error": (
                        f"Image is {attachment.file_size} bytes "
                        "which exceeds the 50 MB inline limit."
                    ),
                }
            )
            continue

        download_url = attachment.download_url or ""
        if not download_url:
            failed.append({"filename": filename, "error": "No download URL"})
            continue

        if download_url.startswith("/"):
            base_url = confluence_fetcher.config.url.rstrip("/")
            download_url = f"{base_url}{download_url}"

        data_bytes = confluence_fetcher.fetch_attachment_content(download_url)
        if data_bytes is None:
            failed.append({"filename": filename, "error": "Fetch failed"})
            continue

        if len(data_bytes) > _ATTACHMENT_MAX_BYTES:
            failed.append(
                {
                    "filename": filename,
                    "error": (
                        f"Downloaded size {len(data_bytes)} bytes "
                        "exceeds the 50 MB inline limit."
                    ),
                }
            )
            continue

        encoded = base64.b64encode(data_bytes).decode("ascii")
        fetched.append({"filename": filename, "size": len(data_bytes)})
        contents.append(
            ImageContent(
                type="image",
                data=encoded,
                mimeType=resolved_mime,
            )
        )

    summary: dict[str, object] = {
        "success": True,
        "content_id": content_id,
        "total_images": len(image_attachments),
        "downloaded": len(fetched),
        "failed": failed,
    }
    contents.insert(
        0,
        TextContent(
            type="text",
            text=json.dumps(summary, indent=2, ensure_ascii=False),
        ),
    )
    return contents
