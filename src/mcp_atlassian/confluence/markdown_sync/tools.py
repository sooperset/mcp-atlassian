"""Confluence Markdown Sync tools for FastMCP server."""

import json
import logging
from typing import Annotated, List, Optional

from fastmcp import Context
from pydantic import Field

from ...servers.dependencies import get_confluence_fetcher
from ...utils.decorators import check_write_access, convert_empty_defaults_to_none
from ..client import ConfluenceClient
from .sync import ConflictStrategy, MarkdownSyncEngine, SyncMode

logger = logging.getLogger("mcp-atlassian.confluence.markdown_sync")


@convert_empty_defaults_to_none
async def confluence_sync_markdown_to_page(
    ctx: Context,
    file_path: Annotated[
        str,
        Field(
            description=(
                "Path to the markdown file to sync. The file should contain valid markdown content "
                "and optionally YAML frontmatter with Confluence metadata. "
                "Example: './docs/project-overview.md'"
            )
        ),
    ],
    space_key: Annotated[
        str,
        Field(
            description=(
                "The key of the target Confluence space (e.g., 'DEV', 'DOCS'). "
                "The page will be created or updated in this space."
            )
        ),
    ],
    parent_id: Annotated[
        str,
        Field(
            description=(
                "(Optional) ID of the parent page under which to create the new page. "
                "If not provided and preserve_hierarchy is enabled, the system will "
                "attempt to determine the parent based on the file's directory structure."
            ),
            default="",
        ),
    ] = "",
    sync_mode: Annotated[
        str,
        Field(
            description=(
                "Synchronization mode: 'create' (only create new pages), "
                "'update' (only update existing pages), or 'auto' (create or update as needed). "
                "Default is 'auto'."
            ),
            default="auto",
        ),
    ] = "auto",
    conflict_strategy: Annotated[
        str,
        Field(
            description=(
                "How to handle conflicts when both local and remote content have changed: "
                "'overwrite' (overwrite remote changes), 'skip' (skip conflicted files), "
                "'prompt' (prompt for resolution), or 'merge' (attempt to merge changes). "
                "Default is 'prompt'."
            ),
            default="prompt",
        ),
    ] = "prompt",
    dry_run: Annotated[
        bool,
        Field(
            description=(
                "If true, preview the changes without actually applying them. "
                "Useful for testing sync operations before committing."
            ),
            default=False,
        ),
    ] = False,
) -> str:
    """
    Sync a markdown file to a Confluence page with frontmatter support.
    
    This tool converts markdown content to Confluence storage format and creates
    or updates pages based on the sync mode. It supports YAML frontmatter for
    metadata and can intelligently match existing pages.
    
    Args:
        ctx: The FastMCP context
        file_path: Path to the markdown file
        space_key: Target Confluence space key
        parent_id: Optional parent page ID
        sync_mode: How to handle create/update decisions
        conflict_strategy: How to handle conflicts
        dry_run: Preview changes without applying
        
    Returns:
        JSON string with sync operation results
    """
    # Log function entry with parameters
    logger.info(f"Starting confluence_sync_markdown_to_page: file_path={file_path}, space_key={space_key}, parent_id={parent_id}, sync_mode={sync_mode}, conflict_strategy={conflict_strategy}, dry_run={dry_run}")
    
    try:
        # Get the Confluence client
        logger.debug("Retrieving Confluence client from context")
        confluence_fetcher = await get_confluence_fetcher(ctx)
        confluence_client = ConfluenceClient(confluence_fetcher.config)
        logger.debug(f"Confluence client initialized with URL: {confluence_fetcher.config.url}")
        
        # Initialize sync engine with default config
        sync_config = {
            'sync_directory': './docs',
            'mapping_file': '.confluence-mappings.json',
            'preserve_hierarchy': True,
            'match_threshold': 85
        }
        logger.debug(f"Initializing sync engine with config: {sync_config}")
        sync_engine = MarkdownSyncEngine(confluence_client, sync_config)
        
        # Convert string parameters to enums
        logger.debug(f"Converting parameters to enums: sync_mode={sync_mode}, conflict_strategy={conflict_strategy}")
        sync_mode_enum = SyncMode(sync_mode)
        conflict_strategy_enum = ConflictStrategy(conflict_strategy)
        
        # Perform the sync
        logger.debug(f"About to call sync_markdown_to_page with parameters: file_path={file_path}, space_key={space_key}, parent_id={parent_id if parent_id else None}, sync_mode={sync_mode_enum}, conflict_strategy={conflict_strategy_enum}, dry_run={dry_run}")
        result = sync_engine.sync_markdown_to_page(
            file_path=file_path,
            space_key=space_key,
            parent_id=parent_id if parent_id else None,
            sync_mode=sync_mode_enum,
            conflict_strategy=conflict_strategy_enum,
            dry_run=dry_run
        )
        logger.debug(f"Sync operation completed with result: success={result.success}, message={result.message}, page_id={result.page_id}")
        
        # Format response
        response = {
            "success": result.success,
            "message": result.message,
            "page_id": result.page_id,
            "details": result.details
        }
        
        if result.success:
            logger.info(f"Markdown sync completed: {file_path} -> {space_key}")
        else:
            logger.warning(f"Markdown sync failed: {result.message}")
        
        return json.dumps(response, indent=2, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"Failed to sync markdown file {file_path}: {e}", exc_info=True)
        error_response = {
            "success": False,
            "message": f"Sync operation failed: {str(e)}",
            "page_id": None,
            "details": {"error": str(e), "file_path": file_path}
        }
        return json.dumps(error_response, indent=2, ensure_ascii=False)


@convert_empty_defaults_to_none
async def confluence_sync_page_to_markdown(
    ctx: Context,
    page_id: Annotated[
        str,
        Field(
            description=(
                "Confluence page ID to export to markdown. "
                "For example, in the URL 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title', "
                "the page ID is '123456789'."
            )
        ),
    ],
    output_path: Annotated[
        str,
        Field(
            description=(
                "Path where the markdown file should be saved. "
                "The directory will be created if it doesn't exist. "
                "Example: './docs/exported-page.md'"
            )
        ),
    ],
    include_attachments: Annotated[
        bool,
        Field(
            description=(
                "Whether to download and include page attachments. "
                "Attachments will be saved in a subdirectory next to the markdown file."
            ),
            default=False,
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        Field(
            description=(
                "If true, preview the export without actually creating files. "
                "Useful for testing export operations before committing."
            ),
            default=False,
        ),
    ] = False,
) -> str:
    """
    Export a Confluence page to markdown with metadata.
    
    This tool converts Confluence storage format to markdown and includes
    page metadata as YAML frontmatter. The resulting file can be used
    for bidirectional sync.
    
    Args:
        ctx: The FastMCP context
        page_id: Confluence page ID to export
        output_path: Path for the output markdown file
        include_attachments: Whether to download attachments
        dry_run: Preview export without creating files
        
    Returns:
        JSON string with export operation results
    """
    try:
        # Get the Confluence client
        confluence_fetcher = await get_confluence_fetcher(ctx)
        confluence_client = ConfluenceClient(confluence_fetcher.config)
        
        # Initialize sync engine
        sync_config = {
            'sync_directory': './docs',
            'mapping_file': '.confluence-mappings.json'
        }
        sync_engine = MarkdownSyncEngine(confluence_client, sync_config)
        
        # Perform the export
        result = sync_engine.sync_page_to_markdown(
            page_id=page_id,
            output_path=output_path,
            include_attachments=include_attachments,
            dry_run=dry_run
        )
        
        # Format response
        response = {
            "success": result.success,
            "message": result.message,
            "page_id": result.page_id,
            "details": result.details
        }
        
        if result.success:
            logger.info(f"Page export completed: {page_id} -> {output_path}")
        else:
            logger.warning(f"Page export failed: {result.message}")
        
        return json.dumps(response, indent=2, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"Failed to export page {page_id}: {e}")
        error_response = {
            "success": False,
            "message": f"Export operation failed: {str(e)}",
            "page_id": page_id,
            "details": {"error": str(e), "output_path": output_path}
        }
        return json.dumps(error_response, indent=2, ensure_ascii=False)


@convert_empty_defaults_to_none
async def confluence_sync_markdown_batch(
    ctx: Context,
    files: Annotated[
        List[str],
        Field(
            description=(
                "List of markdown file paths or glob patterns to sync. "
                "Examples: ['./docs/*.md', './guides/setup.md'] or "
                "['./docs/project-overview.md', './docs/api-reference.md']"
            )
        ),
    ],
    space_key: Annotated[
        str,
        Field(
            description=(
                "The key of the target Confluence space for all files. "
                "Individual files can override this with frontmatter."
            )
        ),
    ],
    sync_mode: Annotated[
        str,
        Field(
            description=(
                "Synchronization mode for all files: 'create', 'update', or 'auto'. "
                "Default is 'auto'."
            ),
            default="auto",
        ),
    ] = "auto",
    conflict_strategy: Annotated[
        str,
        Field(
            description=(
                "How to handle conflicts: 'overwrite', 'skip', 'prompt', or 'merge'. "
                "Default is 'prompt'."
            ),
            default="prompt",
        ),
    ] = "prompt",
    preserve_hierarchy: Annotated[
        bool,
        Field(
            description=(
                "Whether to maintain directory structure as page hierarchy. "
                "If true, pages will be organized based on file directory structure."
            ),
            default=True,
        ),
    ] = True,
    dry_run: Annotated[
        bool,
        Field(
            description=(
                "If true, preview all changes without applying them. "
                "Shows what would be synced for each file."
            ),
            default=False,
        ),
    ] = False,
) -> str:
    """
    Sync multiple markdown files to Confluence pages in batch.
    
    This tool processes multiple markdown files and syncs them to Confluence
    pages, maintaining directory hierarchy and handling conflicts consistently.
    
    Args:
        ctx: The FastMCP context
        files: List of file paths or glob patterns
        space_key: Target Confluence space key
        sync_mode: How to handle create/update decisions
        conflict_strategy: How to handle conflicts
        preserve_hierarchy: Whether to maintain directory structure
        dry_run: Preview changes without applying
        
    Returns:
        JSON string with batch sync operation results
    """
    # Log function entry with parameters
    logger.info(f"Starting confluence_sync_markdown_batch: files={files}, space_key={space_key}, sync_mode={sync_mode}, conflict_strategy={conflict_strategy}, preserve_hierarchy={preserve_hierarchy}, dry_run={dry_run}")
    
    try:
        import glob
        import os
        
        # Get the Confluence client
        logger.debug("Retrieving Confluence client from context for batch sync")
        confluence_fetcher = await get_confluence_fetcher(ctx)
        confluence_client = ConfluenceClient(confluence_fetcher.config)
        logger.debug(f"Confluence client initialized with URL: {confluence_fetcher.config.url}")
        
        # Initialize sync engine
        sync_config = {
            'sync_directory': './docs',
            'mapping_file': '.confluence-mappings.json',
            'preserve_hierarchy': preserve_hierarchy,
            'match_threshold': 85
        }
        logger.debug(f"Initializing sync engine with config: {sync_config}")
        sync_engine = MarkdownSyncEngine(confluence_client, sync_config)
        
        # Expand file patterns
        logger.debug(f"Expanding file patterns: {files}")
        expanded_files = []
        for file_pattern in files:
            if '*' in file_pattern or '?' in file_pattern:
                # It's a glob pattern
                logger.debug(f"Processing glob pattern: {file_pattern}")
                # Check if the pattern is absolute, if not make it relative to VS Code workspace
                if not os.path.isabs(file_pattern):
                    # Make pattern relative to VS Code workspace directory
                    absolute_pattern = os.path.join('/Users/tdyar/ws/async_iris', file_pattern)
                    logger.debug(f"Converting relative pattern {file_pattern} to absolute: {absolute_pattern}")
                else:
                    absolute_pattern = file_pattern
                matched_files = glob.glob(absolute_pattern, recursive=True)
                logger.debug(f"Glob pattern {absolute_pattern} matched {len(matched_files)} files: {matched_files}")
                expanded_files.extend(matched_files)
            else:
                # It's a direct file path
                logger.debug(f"Processing direct file path: {file_pattern}")
                # Check if the path is absolute, if not make it relative to VS Code workspace
                if not os.path.isabs(file_pattern):
                    absolute_file_path = os.path.join('/Users/tdyar/ws/async_iris', file_pattern)
                    logger.debug(f"Converting relative path {file_pattern} to absolute: {absolute_file_path}")
                else:
                    absolute_file_path = file_pattern
                if os.path.exists(absolute_file_path):
                    expanded_files.append(absolute_file_path)
                    logger.debug(f"File exists: {absolute_file_path}")
                else:
                    logger.warning(f"File not found: {absolute_file_path}")
        
        # Remove duplicates and sort
        expanded_files = sorted(list(set(expanded_files)))
        logger.info(f"Final expanded file list: {len(expanded_files)} files - {expanded_files}")
        
        if not expanded_files:
            logger.warning("No files found matching the provided patterns")
            return json.dumps({
                "success": False,
                "message": "No files found matching the provided patterns",
                "results": [],
                "summary": {"total": 0, "successful": 0, "failed": 0}
            }, indent=2)
        
        # Convert string parameters to enums
        logger.debug(f"Converting parameters to enums: sync_mode={sync_mode}, conflict_strategy={conflict_strategy}")
        sync_mode_enum = SyncMode(sync_mode)
        conflict_strategy_enum = ConflictStrategy(conflict_strategy)
        
        # Process each file
        results = []
        successful = 0
        failed = 0
        
        for file_path in expanded_files:
            try:
                logger.info(f"Processing file {successful + failed + 1}/{len(expanded_files)}: {file_path}")
                logger.debug(f"About to call sync_markdown_to_page for file: {file_path} with space_key={space_key}, sync_mode={sync_mode_enum}, conflict_strategy={conflict_strategy_enum}, dry_run={dry_run}")
                
                result = sync_engine.sync_markdown_to_page(
                    file_path=file_path,
                    space_key=space_key,
                    sync_mode=sync_mode_enum,
                    conflict_strategy=conflict_strategy_enum,
                    dry_run=dry_run
                )
                
                logger.debug(f"Sync result for {file_path}: success={result.success}, message={result.message}, page_id={result.page_id}")
                
                file_result = {
                    "file_path": file_path,
                    "success": result.success,
                    "message": result.message,
                    "page_id": result.page_id,
                    "details": result.details
                }
                results.append(file_result)
                
                if result.success:
                    successful += 1
                    logger.info(f"Successfully synced file: {file_path} -> page_id: {result.page_id}")
                else:
                    failed += 1
                    logger.warning(f"Failed to sync file: {file_path} - {result.message}")
                    
            except Exception as e:
                logger.error(f"Failed to sync file {file_path}: {e}", exc_info=True)
                file_result = {
                    "file_path": file_path,
                    "success": False,
                    "message": f"Sync failed: {str(e)}",
                    "page_id": None,
                    "details": {"error": str(e)}
                }
                results.append(file_result)
                failed += 1
        
        # Format response
        response = {
            "success": failed == 0,
            "message": f"Batch sync completed: {successful} successful, {failed} failed",
            "results": results,
            "summary": {
                "total": len(expanded_files),
                "successful": successful,
                "failed": failed,
                "files_processed": expanded_files
            }
        }
        
        logger.info(f"Batch sync completed: {successful}/{len(expanded_files)} files successful")
        return json.dumps(response, indent=2, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"Failed to perform batch sync: {e}", exc_info=True)
        error_response = {
            "success": False,
            "message": f"Batch sync operation failed: {str(e)}",
            "results": [],
            "summary": {"total": 0, "successful": 0, "failed": 0},
            "details": {"error": str(e)}
        }
        return json.dumps(error_response, indent=2, ensure_ascii=False)