"""Confluence server implementation."""

import json
import logging
import os
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from mcp.types import TextContent
from pydantic import Field

from ..confluence import ConfluenceFetcher
from ..confluence.config import ConfluenceConfig
from ..utils.io import is_read_only_mode
from ..utils.logging import log_config_param
from ..utils.urls import is_atlassian_cloud_url

logger = logging.getLogger("mcp-atlassian")


@asynccontextmanager
async def confluence_lifespan(app: FastMCP) -> AsyncGenerator[dict[str, Any], None]:
    """Lifespan manager for the Confluence FastMCP server.

    Creates and manages the ConfluenceFetcher instance.
    """
    logger.info("Initializing Confluence FastMCP server...")

    # Check for read-only mode
    read_only = is_read_only_mode()
    logger.info(f"Read-only mode: {'ENABLED' if read_only else 'DISABLED'}")

    # Determine if Confluence is configured
    confluence_url = os.getenv("CONFLUENCE_URL")
    confluence_is_setup = False

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

    confluence_fetcher = None

    if confluence_is_setup:
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

            confluence_fetcher = ConfluenceFetcher(config=confluence_config)
            logger.info("Confluence client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Confluence client: {e}", exc_info=True)

    try:
        yield {"confluence_fetcher": confluence_fetcher, "read_only": read_only}
    finally:
        logger.info("Shutting down Confluence FastMCP server...")


# Create the Confluence FastMCP instance
confluence_mcp = FastMCP(
    "Confluence",
    description="Tools for interacting with Confluence",
    lifespan=confluence_lifespan,
)


# Tool implementations
@confluence_mcp.tool()
async def search(
    ctx: Context,
    query: str,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of results (1-50)",
            ge=1,
            le=50,
            default=10,
        ),
    ] = 10,
    spaces_filter: Annotated[
        str | None,
        Field(
            description="Comma-separated list of space keys to filter results by. Overrides the environment variable CONFLUENCE_SPACES_FILTER if provided.",
        ),
    ] = None,
) -> Sequence[TextContent]:
    """Search Confluence content using simple terms or CQL.

    Search query - can be either a simple text (e.g. 'project documentation') or a CQL query string. Simple queries use 'siteSearch' by default, to mimic the WebUI search, with an automatic fallback to 'text' search if not supported. Examples of CQL:
    - Basic search: 'type=page AND space=DEV'
    - Personal space search: 'space="~username"' (note: personal space keys starting with ~ must be quoted)
    - Search by title: 'title~"Meeting Notes"'
    - Use siteSearch: 'siteSearch ~ "important concept"'
    - Use text search: 'text ~ "important concept"'
    - Recent content: 'created >= "2023-01-01"'
    - Content with specific label: 'label=documentation'
    - Recently modified content: 'lastModified > startOfMonth("-1M")'
    - Content modified this year: 'creator = currentUser() AND lastModified > startOfYear()'
    - Content you contributed to recently: 'contributor = currentUser() AND lastModified > startOfWeek()'
    - Content watched by user: 'watcher = "user@domain.com" AND type = page'
    - Exact phrase in content: 'text ~ "\"Urgent Review Required\"" AND label = "pending-approval"'
    - Title wildcards: 'title ~ "Minutes*" AND (space = "HR" OR space = "Marketing")'
    Note: Special identifiers need proper quoting in CQL: personal space keys (e.g., "~username"), reserved words, numeric IDs, and identifiers with special characters.
    """
    # Get the ConfluenceFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("confluence_fetcher")
    if not fetcher:
        raise ValueError(
            "Confluence is not configured. Please provide Confluence credentials."
        )

    # Check if the query is a simple search term or already a CQL query
    if query and not any(
        x in query for x in ["=", "~", ">", "<", " AND ", " OR ", "currentUser()"]
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
            pages = fetcher.search(query, limit=limit, spaces_filter=spaces_filter)
        except Exception as e:
            # If siteSearch fails (possibly not supported in this Confluence version),
            # fall back to text search which is supported in all versions
            logger.warning(f"siteSearch failed, falling back to text search: {str(e)}")
            query = f'text ~ "{original_query}"'
            logger.info(f"Falling back to text search with CQL: {query}")
            pages = fetcher.search(query, limit=limit, spaces_filter=spaces_filter)
    else:
        # Using direct CQL query as provided
        pages = fetcher.search(query, limit=limit, spaces_filter=spaces_filter)

    # Format results using the to_simplified_dict method
    search_results = [page.to_simplified_dict() for page in pages]

    return [
        TextContent(
            type="text",
            text=json.dumps(search_results, indent=2, ensure_ascii=False),
        )
    ]


@confluence_mcp.tool()
async def get_page(
    ctx: Context,
    page_id: str,
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
            description="Whether to convert page to markdown (true) or keep it in raw HTML format (false). Raw HTML can reveal macros (like dates) not visible in markdown, but CAUTION: using HTML significantly increases token usage in AI responses.",
            default=True,
        ),
    ] = True,
) -> Sequence[TextContent]:
    """Get content of a specific Confluence page by ID.

    Confluence page ID (numeric ID, can be found in the page URL). For example, in the URL 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title', the page ID is '123456789'
    """
    # Get the ConfluenceFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("confluence_fetcher")
    if not fetcher:
        raise ValueError(
            "Confluence is not configured. Please provide Confluence credentials."
        )

    page = fetcher.get_page_content(page_id, convert_to_markdown=convert_to_markdown)

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
        TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
    ]


@confluence_mcp.tool()
async def get_page_children(
    ctx: Context,
    parent_id: str,
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
            ge=1,
            le=50,
            default=25,
        ),
    ] = 25,
    include_content: Annotated[
        bool,
        Field(
            description="Whether to include the page content in the response",
            default=False,
        ),
    ] = False,
) -> Sequence[TextContent]:
    """Get child pages of a specific Confluence page."""
    # Get the ConfluenceFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("confluence_fetcher")
    if not fetcher:
        raise ValueError(
            "Confluence is not configured. Please provide Confluence credentials."
        )

    # Add body.storage to expand if content is requested
    if include_content and "body" not in expand:
        expand = f"{expand},body.storage" if expand else "body.storage"

    try:
        pages = fetcher.get_page_children(
            page_id=parent_id,
            start=0,
            limit=limit,
            expand=expand,
            convert_to_markdown=True,
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


@confluence_mcp.tool()
async def get_page_ancestors(
    ctx: Context,
    page_id: str,
) -> Sequence[TextContent]:
    """Get ancestor (parent) pages of a specific Confluence page."""
    # Get the ConfluenceFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("confluence_fetcher")
    if not fetcher:
        raise ValueError(
            "Confluence is not configured. Please provide Confluence credentials."
        )

    # Get the ancestor pages
    ancestors = fetcher.get_page_ancestors(page_id)

    # Format results
    ancestor_pages = [page.to_simplified_dict() for page in ancestors]

    return [
        TextContent(
            type="text",
            text=json.dumps(ancestor_pages, indent=2, ensure_ascii=False),
        )
    ]


@confluence_mcp.tool()
async def get_comments(
    ctx: Context,
    page_id: str,
) -> Sequence[TextContent]:
    """Get comments for a specific Confluence page.

    Confluence page ID (numeric ID, can be parsed from URL, e.g. from 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title' -> '123456789')
    """
    # Get the ConfluenceFetcher instance from the context
    fetcher = ctx.request_context.lifespan_context.get("confluence_fetcher")
    if not fetcher:
        raise ValueError(
            "Confluence is not configured. Please provide Confluence credentials."
        )

    comments = fetcher.get_page_comments(page_id)

    # Format comments
    def format_comment(comment: Any) -> dict[str, Any]:
        if hasattr(comment, "to_simplified_dict"):
            return comment.to_simplified_dict()
        return {
            "id": comment.get("id"),
            "author": comment.get("author", {}).get("displayName", "Unknown"),
            "created": comment.get("created"),
            "body": comment.get("body"),
        }

    # Format comments using their to_simplified_dict method if available
    formatted_comments = [format_comment(comment) for comment in comments]

    return [
        TextContent(
            type="text",
            text=json.dumps(formatted_comments, indent=2, ensure_ascii=False),
        )
    ]


@confluence_mcp.tool()
async def create_page(
    ctx: Context,
    space_key: str,
    title: str,
    content: str,
    parent_id: Annotated[
        str | None,
        Field(
            description="Optional parent page ID. If provided, this page will be created as a child of the specified page",
        ),
    ] = None,
) -> Sequence[TextContent]:
    """Create a new Confluence page.

    The content of the page in Markdown format. Supports headings, lists, tables, code blocks, and other Markdown syntax.
    """
    # Get the ConfluenceFetcher instance and read-only mode from the context
    fetcher = ctx.request_context.lifespan_context.get("confluence_fetcher")
    read_only = ctx.request_context.lifespan_context.get("read_only", False)

    if not fetcher:
        raise ValueError(
            "Confluence is not configured. Please provide Confluence credentials."
        )

    # Write operation - check read-only mode
    if read_only:
        return [
            TextContent(
                type="text",
                text="Operation 'confluence_create_page' is not available in read-only mode.",
            )
        ]

    # Create the page (with automatic markdown conversion)
    page = fetcher.create_page(
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


@confluence_mcp.tool()
async def update_page(
    ctx: Context,
    page_id: str,
    title: str,
    content: str,
    is_minor_edit: Annotated[
        bool,
        Field(
            description="Whether this is a minor edit",
            default=False,
        ),
    ] = False,
    version_comment: Annotated[
        str,
        Field(
            description="Optional comment for this version",
            default="",
        ),
    ] = "",
    parent_id: Annotated[
        str | None,
        Field(
            description="Optional the new parent page ID",
        ),
    ] = None,
) -> Sequence[TextContent]:
    """Update an existing Confluence page."""
    # Get the ConfluenceFetcher instance and read-only mode from the context
    fetcher = ctx.request_context.lifespan_context.get("confluence_fetcher")
    read_only = ctx.request_context.lifespan_context.get("read_only", False)

    if not fetcher:
        raise ValueError(
            "Confluence is not configured. Please provide Confluence credentials."
        )

    # Write operation - check read-only mode
    if read_only:
        return [
            TextContent(
                type="text",
                text="Operation 'confluence_update_page' is not available in read-only mode.",
            )
        ]

    if not page_id or not title or not content:
        raise ValueError(
            "Missing required parameters: page_id, title, and content are required."
        )

    # Update the page (with automatic markdown conversion)
    updated_page = fetcher.update_page(
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


@confluence_mcp.tool()
async def delete_page(
    ctx: Context,
    page_id: str,
) -> Sequence[TextContent]:
    """Delete an existing Confluence page."""
    # Get the ConfluenceFetcher instance and read-only mode from the context
    fetcher = ctx.request_context.lifespan_context.get("confluence_fetcher")
    read_only = ctx.request_context.lifespan_context.get("read_only", False)

    if not fetcher:
        raise ValueError(
            "Confluence is not configured. Please provide Confluence credentials."
        )

    # Write operation - check read-only mode
    if read_only:
        return [
            TextContent(
                type="text",
                text="Operation 'confluence_delete_page' is not available in read-only mode.",
            )
        ]

    if not page_id:
        raise ValueError("Missing required parameter: page_id is required.")

    try:
        # Delete the page
        result = fetcher.delete_page(page_id=page_id)

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
