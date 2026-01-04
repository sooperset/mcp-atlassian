"""Confluence FastMCP server instance and tool definitions."""

import json
import logging
from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import BeforeValidator, Field

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.servers.dependencies import get_confluence_fetcher
from mcp_atlassian.utils.decorators import (
    check_write_access,
)

logger = logging.getLogger(__name__)

confluence_mcp = FastMCP(
    name="Confluence MCP Service",
    instructions="Provides tools for interacting with Atlassian Confluence.",
)


@confluence_mcp.tool(
    tags={"confluence", "read"},
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
    tags={"confluence", "read"},
    annotations={"title": "Get Page", "readOnlyHint": True},
)
async def get_page(
    ctx: Context,
    page_id: Annotated[
        str | int | None,
        Field(
            description=(
                "Confluence page ID (numeric ID, can be found in the page URL). "
                "For example, in the URL 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title', "
                "the page ID is '123456789'. "
                "Provide this OR both 'title' and 'space_key'. If page_id is provided, title and space_key will be ignored."
            ),
            default=None,
        ),
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
    tags={"confluence", "read"},
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
    tags={"confluence", "read"},
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
    tags={"confluence", "read"},
    annotations={"title": "Get Labels", "readOnlyHint": True},
)
async def get_labels(
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
    """Get labels for a specific Confluence page.

    Args:
        ctx: The FastMCP context.
        page_id: Confluence page ID.

    Returns:
        JSON string representing a list of label objects.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)
    labels = confluence_fetcher.get_page_labels(page_id)
    formatted_labels = [label.to_simplified_dict() for label in labels]
    return json.dumps(formatted_labels, indent=2, ensure_ascii=False)


@confluence_mcp.tool(
    tags={"confluence", "read", "analytics"},
    annotations={"title": "Get Page Views", "readOnlyHint": True},
)
async def get_page_views(
    ctx: Context,
    page_id: Annotated[
        str | None,
        Field(
            description=(
                "Confluence page ID to get view analytics for. "
                "Provide either this OR page_ids for batch operations."
            ),
            default=None,
        ),
    ] = None,
    page_ids: Annotated[
        str | None,
        Field(
            description=(
                "Comma-separated list of page IDs for batch view analytics. "
                "Use this for getting views for multiple pages at once."
            ),
            default=None,
        ),
    ] = None,
    from_date: Annotated[
        str | None,
        Field(
            description=(
                "Start date for the analytics period (ISO format: YYYY-MM-DD). "
                "If not provided, returns all-time views."
            ),
            default=None,
        ),
    ] = None,
    include_viewers: Annotated[
        bool,
        Field(
            description="Whether to include unique viewer count (default: True)",
            default=True,
        ),
    ] = True,
) -> str:
    """Get page view analytics for Confluence pages.

    Returns the total number of views and unique viewers for one or more pages.

    IMPORTANT: This tool is only available on Confluence Cloud. Server/Data Center
    deployments do not support the Analytics API.

    Args:
        ctx: The FastMCP context.
        page_id: Single page ID to get views for.
        page_ids: Comma-separated list of page IDs for batch operations.
        from_date: Start date for analytics period (YYYY-MM-DD).
        include_viewers: Whether to include unique viewer count.

    Returns:
        JSON string containing view counts and metadata.
    """
    from mcp_atlassian.models.confluence import AnalyticsNotAvailableError

    confluence_fetcher = await get_confluence_fetcher(ctx)

    # Validate input - need either page_id or page_ids
    if not page_id and not page_ids:
        return json.dumps(
            {"error": "Either 'page_id' or 'page_ids' must be provided."},
            indent=2,
            ensure_ascii=False,
        )

    if page_id and page_ids:
        logger.warning(
            "Both page_id and page_ids provided; page_id will be used for single-page query."
        )

    try:
        if page_id:
            # Single page query
            result = confluence_fetcher.get_page_views(
                page_id=page_id,
                from_date=from_date,
                include_viewers=include_viewers,
            )
            return json.dumps(result.to_simplified_dict(), indent=2, ensure_ascii=False)
        else:
            # Batch query
            ids_list = [pid.strip() for pid in page_ids.split(",") if pid.strip()]
            if not ids_list:
                return json.dumps(
                    {"error": "No valid page IDs found in page_ids parameter."},
                    indent=2,
                    ensure_ascii=False,
                )

            result = confluence_fetcher.batch_get_page_views(
                page_ids=ids_list,
                from_date=from_date,
                include_viewers=include_viewers,
            )
            return json.dumps(result.to_simplified_dict(), indent=2, ensure_ascii=False)

    except AnalyticsNotAvailableError as e:
        logger.warning(f"Analytics not available: {e}")
        return json.dumps(
            {
                "error": "Analytics not available",
                "message": str(e),
                "hint": "The Confluence Analytics API is only available on Cloud instances.",
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"Error getting page views: {e}", exc_info=True)
        return json.dumps(
            {"error": f"Failed to get page views: {e}"},
            indent=2,
            ensure_ascii=False,
        )


@confluence_mcp.tool(
    tags={"confluence", "read", "analytics"},
    annotations={"title": "Get Page Analytics", "readOnlyHint": True},
)
async def get_page_analytics(
    ctx: Context,
    page_id: Annotated[
        str | None,
        Field(
            description=(
                "Confluence page ID to get analytics for. "
                "Provide either this OR page_ids for batch operations."
            ),
            default=None,
        ),
    ] = None,
    page_ids: Annotated[
        str | None,
        Field(
            description=(
                "Comma-separated list of page IDs for batch analytics. "
                "Use this for getting analytics for multiple pages at once."
            ),
            default=None,
        ),
    ] = None,
    metrics: Annotated[
        str | None,
        Field(
            description=(
                "Comma-separated list of metrics to calculate. "
                "Available: engagement_score, view_velocity, staleness, viewer_diversity. "
                "If not provided, uses environment defaults (engagement_score, staleness)."
            ),
            default=None,
        ),
    ] = None,
    period_days: Annotated[
        int,
        Field(
            description="Analysis period in days (default: 30)",
            default=30,
            ge=1,
            le=365,
        ),
    ] = 30,
    include_raw_data: Annotated[
        bool,
        Field(
            description="Whether to include raw view data alongside calculated metrics",
            default=False,
        ),
    ] = False,
) -> str:
    """Get calculated engagement analytics for Confluence pages.

    Calculates engagement metrics like engagement score, view velocity (trending),
    staleness, and viewer diversity based on page view data.

    IMPORTANT: This tool is only available on Confluence Cloud. Server/Data Center
    deployments do not support the Analytics API.

    Available metrics:
    - engagement_score: Composite rating (0-100) based on views, viewers, and recency
    - view_velocity: Trend in view activity (increasing/decreasing/stable)
    - staleness: Content freshness (active/stale/abandoned)
    - viewer_diversity: Breadth of audience (narrow/moderate/broad)

    Args:
        ctx: The FastMCP context.
        page_id: Single page ID to analyze.
        page_ids: Comma-separated list of page IDs for batch operations.
        metrics: Comma-separated list of metrics to calculate.
        period_days: Analysis period in days (1-365).
        include_raw_data: Whether to include raw view counts.

    Returns:
        JSON string containing calculated metrics and optional raw data.
    """
    from mcp_atlassian.models.confluence import AnalyticsNotAvailableError

    confluence_fetcher = await get_confluence_fetcher(ctx)

    # Validate input - need either page_id or page_ids
    if not page_id and not page_ids:
        return json.dumps(
            {"error": "Either 'page_id' or 'page_ids' must be provided."},
            indent=2,
            ensure_ascii=False,
        )

    if page_id and page_ids:
        logger.warning(
            "Both page_id and page_ids provided; page_id will be used for single-page query."
        )

    # Parse metrics list
    metrics_list = None
    if metrics:
        metrics_list = [m.strip() for m in metrics.split(",") if m.strip()]

    try:
        if page_id:
            # Single page query
            result = confluence_fetcher.get_page_analytics(
                page_id=page_id,
                metrics=metrics_list,
                period_days=period_days,
                include_raw_data=include_raw_data,
            )
            return json.dumps(result.to_simplified_dict(), indent=2, ensure_ascii=False)
        else:
            # Batch query
            ids_list = [pid.strip() for pid in page_ids.split(",") if pid.strip()]
            if not ids_list:
                return json.dumps(
                    {"error": "No valid page IDs found in page_ids parameter."},
                    indent=2,
                    ensure_ascii=False,
                )

            result = confluence_fetcher.batch_get_page_analytics(
                page_ids=ids_list,
                metrics=metrics_list,
                period_days=period_days,
                include_raw_data=include_raw_data,
            )
            return json.dumps(result.to_simplified_dict(), indent=2, ensure_ascii=False)

    except AnalyticsNotAvailableError as e:
        logger.warning(f"Analytics not available: {e}")
        return json.dumps(
            {
                "error": "Analytics not available",
                "message": str(e),
                "hint": "The Confluence Analytics API is only available on Cloud instances.",
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"Error getting page analytics: {e}", exc_info=True)
        return json.dumps(
            {"error": f"Failed to get page analytics: {e}"},
            indent=2,
            ensure_ascii=False,
        )


@confluence_mcp.tool(
    tags={"confluence", "read", "analytics"},
    annotations={"title": "Get Space Analytics", "readOnlyHint": True},
)
async def get_space_analytics(
    ctx: Context,
    space_key: Annotated[
        str,
        Field(
            description=(
                "The key of the Confluence space to analyze (e.g., 'DEV', 'TEAM'). "
                "Space keys are typically short uppercase identifiers."
            ),
        ),
    ],
    period_days: Annotated[
        int,
        Field(
            description="Analysis period in days (default: 30)",
            default=30,
            ge=1,
            le=365,
        ),
    ] = 30,
    limit: Annotated[
        int,
        Field(
            description="Max pages to return in each category (default: 10)",
            default=10,
            ge=1,
            le=50,
        ),
    ] = 10,
    stale_threshold_days: Annotated[
        int,
        Field(
            description="Days without views to consider a page stale (default: 90)",
            default=90,
            ge=7,
            le=365,
        ),
    ] = 90,
    include_summary: Annotated[
        bool,
        Field(
            description="Include space-level summary statistics",
            default=True,
        ),
    ] = True,
    include_popular_pages: Annotated[
        bool,
        Field(
            description="Include top pages by view count",
            default=True,
        ),
    ] = True,
    include_trending_pages: Annotated[
        bool,
        Field(
            description="Include pages with increasing view velocity",
            default=True,
        ),
    ] = True,
    include_stale_pages: Annotated[
        bool,
        Field(
            description="Include pages that haven't been viewed recently",
            default=True,
        ),
    ] = True,
) -> str:
    """Get aggregated analytics for a Confluence space.

    Analyzes all pages in a space to provide insights on:
    - Summary: Overall space statistics (total pages, views, engagement)
    - Popular pages: Top pages by view count
    - Trending pages: Pages with increasing view velocity
    - Stale pages: Content that hasn't been viewed recently

    IMPORTANT: This tool is only available on Confluence Cloud. Server/Data Center
    deployments do not support the Analytics API.

    Args:
        ctx: The FastMCP context.
        space_key: The space key to analyze.
        period_days: Analysis period in days (1-365).
        limit: Maximum pages per category.
        stale_threshold_days: Days without views to mark as stale.
        include_summary: Include space summary statistics.
        include_popular_pages: Include popular pages list.
        include_trending_pages: Include trending pages list.
        include_stale_pages: Include stale pages list.

    Returns:
        JSON string containing space analytics with requested sections.
    """
    from mcp_atlassian.models.confluence import AnalyticsNotAvailableError

    confluence_fetcher = await get_confluence_fetcher(ctx)

    try:
        result = confluence_fetcher.get_space_analytics(
            space_key=space_key,
            period_days=period_days,
            limit=limit,
            stale_threshold_days=stale_threshold_days,
            include_summary=include_summary,
            include_popular_pages=include_popular_pages,
            include_trending_pages=include_trending_pages,
            include_stale_pages=include_stale_pages,
        )
        return json.dumps(result.to_simplified_dict(), indent=2, ensure_ascii=False)

    except AnalyticsNotAvailableError as e:
        logger.warning(f"Analytics not available: {e}")
        return json.dumps(
            {
                "error": "Analytics not available",
                "message": str(e),
                "hint": "The Confluence Analytics API is only available on Cloud instances.",
            },
            indent=2,
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"Error getting space analytics: {e}", exc_info=True)
        return json.dumps(
            {"error": f"Failed to get space analytics: {e}"},
            indent=2,
            ensure_ascii=False,
        )


@confluence_mcp.tool(
    tags={"confluence", "write"},
    annotations={"title": "Add Label", "destructiveHint": True},
)
@check_write_access
async def add_label(
    ctx: Context,
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
    confluence_fetcher = await get_confluence_fetcher(ctx)
    labels = confluence_fetcher.add_page_label(page_id, name)
    formatted_labels = [label.to_simplified_dict() for label in labels]
    return json.dumps(formatted_labels, indent=2, ensure_ascii=False)


@confluence_mcp.tool(
    tags={"confluence", "write"},
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
    )
    result = page.to_simplified_dict()
    return json.dumps(
        {"message": "Page created successfully", "page": result},
        indent=2,
        ensure_ascii=False,
    )


@confluence_mcp.tool(
    tags={"confluence", "write"},
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
    )
    page_data = updated_page.to_simplified_dict()
    return json.dumps(
        {"message": "Page updated successfully", "page": page_data},
        indent=2,
        ensure_ascii=False,
    )


@confluence_mcp.tool(
    tags={"confluence", "write"},
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
    tags={"confluence", "write"},
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
    tags={"confluence", "read"},
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
