# Idea
I'd like to extend this MCP server by tools to inspect and provide confluence page versions. The Atlassian API as documented at https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-version/#api-pages-page-id-versions-version-number-get seems to provide ways to get information about existing page versions ( example `GET /pages/{id}/versions` ) as well as information about a specific version (example `GET /pages/{page-id}/versions/{version-number}` ). 

## Task
Add a new tool named "confluence_get_page_versions" which returns various version information for a give page. If no specific version is requested, then it should just return the list of existing versions of a page. If a specific version for a page is requested, then detailed information about this specific version should be returned. The tool always requires the page ID as input parameter. 

## Development instructions
* execute the development in a a development branch of the current git repository. Check in working versions of the code during development.
* add respective tests for the new functionality similar to existing tests of the project
* update the documentation for the new functionality similar to the existing documentation 
* make sure you're following the MCP specifications as provided at https://modelcontextprotocol.io/specification/2025-06-18

## Implementation Status: ✅ COMPLETED

### What was implemented:

1. **Extended ConfluenceVersion model** (`src/mcp_atlassian/models/confluence/page.py`)
   - Added `minor_edit` field to track minor edits
   - Updated `from_api_response` method to handle new field

2. **Added version methods to PagesMixin** (`src/mcp_atlassian/confluence/pages.py`)
   - `get_page_versions(page_id: str) -> list[ConfluenceVersion]` - Get all versions
   - `get_page_version(page_id: str, version_number: int) -> ConfluenceVersion` - Get specific version
   - Supports both v1 and v2 API with automatic fallback

3. **Extended ConfluenceV2Adapter** (`src/mcp_atlassian/confluence/v2_adapter.py`)
   - `get_page_versions(page_id: str)` - v2 API endpoint for listing versions
   - `get_page_version(page_id: str, version_number: int)` - v2 API endpoint for specific version

4. **Added MCP tool** (`src/mcp_atlassian/servers/confluence.py`)
   - `confluence_get_page_versions` tool with:
     - Required parameter: `page_id: str`
     - Optional parameter: `version_number: int | None = None`
     - Returns JSON with version data or error details
     - Supports both listing all versions and getting specific version

5. **Comprehensive testing** (`tests/unit/confluence/test_page_versions.py`)
   - Tests for listing all versions
   - Tests for getting specific version
   - Tests for error handling
   - All tests pass with proper async/await patterns

6. **Updated documentation** (`README.md`)
   - Added `confluence_get_page_versions` to tool list
   - Updated tools comparison table

### API Endpoints Used:
- **v2 API (Cloud OAuth)**: `GET /api/v2/pages/{id}/versions` and `GET /api/v2/pages/{id}/versions/{version}`
- **v1 API (Token/Basic Auth)**: Uses existing page endpoints with version parameters

### Features:
- ✅ Lists all versions of a page
- ✅ Gets specific version details
- ✅ Supports both Cloud and Server/Data Center
- ✅ Automatic API version detection (v2 for OAuth, v1 for others)
- ✅ Proper error handling and authentication
- ✅ Follows existing code patterns and MCP specifications
- ✅ Comprehensive test coverage
- ✅ Updated documentation

### Usage Examples:
```json
// Get all versions
{"page_id": "123456"}

// Get specific version
{"page_id": "123456", "version_number": 5}
```

The implementation is complete and ready for use!
