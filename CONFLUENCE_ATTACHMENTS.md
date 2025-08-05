# Confluence Attachment Management Tools

This document describes the Confluence attachment management tools that have been added to the MCP Atlassian server.

## Overview

The attachment tools provide comprehensive functionality for managing file attachments on Confluence pages, including uploading, downloading, updating, and deleting attachments.

## Available Tools

### 📤 upload_attachment

Upload a file attachment to a Confluence page.

**Parameters:**
- `page_id` (required): Confluence page ID
- `file_path` (required): Path to the file to upload
- `comment` (optional): Comment for the attachment upload
- `minor_edit` (optional): Whether this is a minor edit (default: false)

**Example:**
```
@mcp-atlassian upload_attachment page_id="123456789" file_path="/Users/username/Documents/report.pdf" comment="Monthly report"
```

### 🔄 update_attachment

Update an existing attachment on a Confluence page.

**Parameters:**
- `page_id` (required): Confluence page ID
- `attachment_id` (required): ID of the attachment to update
- `file_path` (required): Path to the new file
- `comment` (optional): Comment for the update
- `minor_edit` (optional): Whether this is a minor edit (default: false)

**Example:**
```
@mcp-atlassian update_attachment page_id="123456789" attachment_id="att456789" file_path="/Users/username/Documents/updated_report.pdf"
```

### 📄 get_attachments

Get all attachments for a specific Confluence page.

**Parameters:**
- `page_id` (required): Confluence page ID
- `start` (optional): Starting index for pagination (default: 0)
- `limit` (optional): Maximum number of attachments to return (default: 25, max: 50)
- `expand` (optional): Fields to expand (e.g., "version,metadata")

**Example:**
```
@mcp-atlassian get_attachments page_id="123456789" limit=10 expand="version"
```

### 🔍 get_attachment

Get details for a specific attachment.

**Parameters:**
- `page_id` (required): Confluence page ID
- `attachment_id` (required): ID of the attachment
- `expand` (optional): Fields to expand (e.g., "version,metadata")

**Example:**
```
@mcp-atlassian get_attachment page_id="123456789" attachment_id="att456789" expand="version,metadata"
```

### 📥 download_attachment

Download an attachment from a Confluence page to your local machine.

**Parameters:**
- `page_id` (required): Confluence page ID
- `attachment_id` (required): ID of the attachment to download
- `download_path` (optional): Path to save the file (defaults to current directory with attachment name)

**Example:**
```
@mcp-atlassian download_attachment page_id="123456789" attachment_id="att456789" download_path="/Users/username/Downloads/"
```

### 🗑️ delete_attachment

Delete an attachment from a Confluence page.

**Parameters:**
- `page_id` (required): Confluence page ID
- `attachment_id` (required): ID of the attachment to delete

**Example:**
```
@mcp-atlassian delete_attachment page_id="123456789" attachment_id="att456789"
```

### 🏷️ get_attachment_properties

Get properties/metadata for a specific attachment.

**Parameters:**
- `page_id` (required): Confluence page ID
- `attachment_id` (required): ID of the attachment
- `start` (optional): Starting index for pagination (default: 0)
- `limit` (optional): Maximum number of properties to return (default: 25, max: 50)

**Example:**
```
@mcp-atlassian get_attachment_properties page_id="123456789" attachment_id="att456789"
```

## Finding Page IDs and Attachment IDs

### Page IDs
You can find Confluence page IDs in the URL when viewing a page:
```
https://confluence.example.com/wiki/spaces/SPACE/pages/123456789/Page+Title
                                                     ^^^^^^^^^
                                                     Page ID
```

### Attachment IDs
Attachment IDs are returned when you:
1. Upload an attachment (in the response)
2. List page attachments using `get_attachments`
3. Get attachment details

## Supported File Types

Confluence typically supports these file types for attachments:
- **Documents**: PDF, DOC, DOCX, TXT, RTF
- **Images**: PNG, JPG, GIF, SVG, BMP
- **Archives**: ZIP, RAR, 7Z, TAR, GZ
- **Spreadsheets**: XLS, XLSX, CSV
- **Presentations**: PPT, PPTX
- **Code files**: JS, PY, HTML, CSS, XML, JSON
- **And many more...**

## Error Handling

All tools include comprehensive error handling for common scenarios:
- **File not found**: When uploading/updating with invalid file paths
- **Authentication errors**: Invalid credentials or expired tokens
- **Permission errors**: Insufficient permissions for the operation
- **Network errors**: Connection issues or API timeouts

## API Reference

The attachment tools are based on the [Confluence REST API Attachments](https://developer.atlassian.com/server/confluence/rest/v1001/api-group-attachments/) endpoints:

- `POST /rest/api/content/{id}/child/attachment` - Upload attachment
- `POST /rest/api/content/{id}/child/attachment/{attachmentId}/data` - Update attachment
- `GET /rest/api/content/{id}/child/attachment` - Get attachments
- `GET /rest/api/content/{id}/child/attachment/{attachmentId}` - Get attachment
- `DELETE /rest/api/content/{id}/child/attachment/{attachmentId}` - Delete attachment

## Usage Tips

1. **File Paths**: Always use absolute file paths when uploading or updating attachments
2. **Page IDs**: You can get page IDs using the existing `get_page` or `search` tools
3. **Batch Operations**: Use `get_attachments` to get all attachment IDs for batch operations
4. **Large Files**: The tools support large file uploads, but be mindful of your Confluence instance's file size limits
5. **Permissions**: Ensure you have appropriate permissions for the Confluence space and page

## Integration

The attachment tools are integrated into the existing MCP Atlassian server structure:

- **Module**: `src/mcp_atlassian/confluence/attachments.py`
- **Mixin**: `AttachmentsMixin` - Contains the core attachment operations
- **Server Tools**: Registered in `src/mcp_atlassian/servers/confluence.py`
- **Integration**: Added to `ConfluenceFetcher` in `src/mcp_atlassian/confluence/__init__.py`

## Authentication

The attachment tools use the same authentication configuration as other Confluence tools:
- **Personal Access Tokens** (recommended for Confluence Cloud)
- **Username/Password** (for Confluence Server)
- **OAuth** (for advanced integrations)

Make sure your `CONFLUENCE_PERSONAL_TOKEN` environment variable is properly configured in your MCP setup.
