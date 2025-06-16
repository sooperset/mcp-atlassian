# Confluence Markdown Sync Integration

This document describes the markdown synchronization features added to the mcp-atlassian server as part of Phase 1 integration.

## Overview

The markdown sync integration adds bidirectional synchronization capabilities between local markdown files and Confluence pages. This allows users to:

- Sync markdown files to Confluence pages with frontmatter support
- Export Confluence pages to markdown with metadata preservation
- Batch process multiple files with intelligent conflict resolution
- Maintain directory structure as page hierarchy

## Features Added

### New MCP Tools

1. **`sync_markdown_to_page`** - Sync a markdown file to a Confluence page
2. **`sync_page_to_markdown`** - Export a Confluence page to markdown
3. **`sync_markdown_batch`** - Batch sync multiple markdown files

### Core Components

- **MarkdownConverter** - Handles conversion between markdown and Confluence storage format
- **PageMatcher** - Intelligent matching between markdown files and Confluence pages
- **MarkdownSyncEngine** - Main synchronization engine with conflict resolution
- **MarkdownSyncConfig** - Configuration management for sync features

## Configuration

### Environment Variables

The following environment variables can be used to configure markdown sync:

```bash
# Enable markdown sync features
ATLASSIAN_MARKDOWN_SYNC_ENABLED=true

# Directory containing markdown files
ATLASSIAN_MARKDOWN_SYNC_DIR=./docs

# File to store page mappings
ATLASSIAN_MARKDOWN_MAPPING_FILE=.confluence-mappings.json

# Preserve directory structure as page hierarchy
ATLASSIAN_MARKDOWN_PRESERVE_HIERARCHY=true

# Automatically create new pages
ATLASSIAN_MARKDOWN_AUTO_CREATE=true

# Include metadata in exports
ATLASSIAN_MARKDOWN_INCLUDE_METADATA=true

# Fuzzy matching threshold (0-100)
ATLASSIAN_MARKDOWN_MATCH_THRESHOLD=85.0

# Preserve formatting during conversion
ATLASSIAN_MARKDOWN_PRESERVE_FORMAT=true

# Convert links during sync
ATLASSIAN_MARKDOWN_CONVERT_LINKS=true

# Handle attachments (experimental)
ATLASSIAN_MARKDOWN_HANDLE_ATTACHMENTS=false
```

## Usage Examples

### 1. Sync a Single Markdown File

```json
{
  "method": "tools/call",
  "params": {
    "name": "sync_markdown_to_page",
    "arguments": {
      "file_path": "./docs/project-overview.md",
      "space_key": "DOCS",
      "sync_mode": "auto",
      "dry_run": false
    }
  }
}
```

### 2. Export a Confluence Page to Markdown

```json
{
  "method": "tools/call",
  "params": {
    "name": "sync_page_to_markdown",
    "arguments": {
      "page_id": "123456789",
      "output_path": "./docs/exported-page.md",
      "include_attachments": false,
      "dry_run": false
    }
  }
}
```

### 3. Batch Sync Multiple Files

```json
{
  "method": "tools/call",
  "params": {
    "name": "sync_markdown_batch",
    "arguments": {
      "files": "./docs/*.md,./guides/setup.md",
      "space_key": "DOCS",
      "sync_mode": "auto",
      "conflict_strategy": "prompt",
      "preserve_hierarchy": true,
      "dry_run": true
    }
  }
}
```

## Frontmatter Support

Markdown files can include YAML frontmatter with Confluence metadata:

```markdown
---
title: Project Overview
confluence_page_id: "123456789"
confluence_space_key: DOCS
confluence_parent_id: "987654321"
tags: [documentation, project]
labels: [important, review-needed]
---

# Project Overview

This is the main project documentation...
```

### Supported Frontmatter Fields

- `title` - Page title (overrides H1 heading)
- `confluence_page_id` - Existing page ID for updates
- `confluence_space_key` - Target space (overrides tool parameter)
- `confluence_parent_id` - Parent page ID
- `tags` - List of tags to apply
- `labels` - List of labels to apply

## Sync Modes

### Create Only (`create`)
- Only creates new pages
- Fails if page already exists

### Update Only (`update`)
- Only updates existing pages
- Fails if page doesn't exist

### Auto (`auto`) - Default
- Creates new pages or updates existing ones
- Uses intelligent matching to find existing pages

## Conflict Resolution Strategies

### Overwrite (`overwrite`)
- Always overwrites remote changes with local content
- Use with caution

### Skip (`skip`)
- Skips files with conflicts
- Safe but may leave content out of sync

### Prompt (`prompt`) - Default
- Would prompt user in interactive mode
- Currently defaults to overwrite with warning

### Merge (`merge`)
- Attempts to merge changes
- Not yet implemented

## File Mapping

The system maintains a mapping file (`.confluence-mappings.json`) that tracks:

```json
{
  "./docs/project-overview.md": {
    "page_id": "123456789",
    "content_hash": "abc123...",
    "last_sync": "2023-12-01T10:00:00.000Z"
  }
}
```

This enables:
- Conflict detection
- Incremental sync
- Relationship tracking

## Integration Architecture

The markdown sync features are integrated as optional tools within the existing mcp-atlassian structure:

```
src/mcp_atlassian/
├── confluence/
│   ├── markdown_sync/          # NEW: Markdown sync module
│   │   ├── __init__.py
│   │   ├── converter.py        # Markdown ↔ Confluence conversion
│   │   ├── matcher.py          # Page matching logic
│   │   ├── sync.py            # Main sync engine
│   │   ├── config.py          # Configuration management
│   │   └── tools.py           # MCP tool implementations
│   └── ...                    # Existing confluence modules
└── servers/
    └── confluence.py          # MODIFIED: Added markdown sync tools
```

## Error Handling

All markdown sync operations use the existing mcp-atlassian error handling patterns:

- `MarkdownSyncError` - Specific to sync operations
- Inherits from `MCPAtlassianError` for consistency
- Includes error codes and detailed context
- Follows FastMCP error response format

## Testing

Basic tests are included for core functionality:

```bash
# Run markdown sync tests
pytest tests/unit/confluence/markdown_sync/

# Run specific test
pytest tests/unit/confluence/markdown_sync/test_converter.py
```

## Limitations and Future Enhancements

### Current Limitations

1. **Simplified Markdown Conversion** - Basic conversion that may not handle all Confluence macros
2. **No Attachment Handling** - Attachments are not yet supported
3. **Limited Merge Strategy** - Merge conflict resolution not implemented
4. **No Real-time Sync** - Manual sync operations only

### Planned Enhancements

1. **Enhanced Conversion** - Better handling of Confluence-specific content
2. **Attachment Support** - Download and sync file attachments
3. **Advanced Merge** - Intelligent merge conflict resolution
4. **Watch Mode** - Automatic sync on file changes
5. **Template Support** - Page templates for consistent formatting

## Contributing

This integration follows the established mcp-atlassian patterns:

1. **Error Handling** - Use `MarkdownSyncError` with appropriate codes
2. **Logging** - Use structured logging with appropriate levels
3. **Configuration** - Follow environment variable patterns
4. **Testing** - Include unit tests for new functionality
5. **Documentation** - Update docstrings and examples

## Migration from Standalone Implementation

If migrating from a standalone markdown sync implementation:

1. **Update Imports** - Change import paths to mcp-atlassian structure
2. **Configuration** - Use new environment variables
3. **Error Handling** - Update exception handling for new error types
4. **Tool Calls** - Use new MCP tool names and parameters

## Support

For issues related to markdown sync functionality:

1. Check the logs for detailed error messages
2. Verify configuration and environment variables
3. Test with `dry_run: true` to preview changes
4. Ensure proper Confluence permissions for target spaces

The markdown sync features are designed to be backward compatible and optional, so existing mcp-atlassian functionality remains unchanged.