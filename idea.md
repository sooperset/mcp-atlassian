# Idea
I'd like to extend this MCP server by tools to inspect and provide confluence page versions. The Atlassian API as documented at https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-version/#api-pages-page-id-versions-version-number-get seems to provide ways to get information about existing page versions ( example `GET /pages/{id}/versions` ) as well as information about a specific version (example `GET /pages/{page-id}/versions/{version-number}` ). 
## Task
Add a new tool named "confluence_get_page_versions" which returns various version information for a give page. If no specific version is requested, then it should just return the list of existing versions of a page. If a specific version for a page is requested, then detailed information about this specific version should be returned. The tool always requires the page ID as input parameter. 

## Development instructions
* execute the development in a a development branch of the current git repository. Check in working versions of the code during development.
* add respective tests for the new functionality similar to existing tests of the project
* update the documentation for the new functionality similar to the existing documentation 
* make sure you're following the MCP specifications as provided at https://modelcontextprotocol.io/specification/2025-06-18
 
