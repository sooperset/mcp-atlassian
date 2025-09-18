I want to extend the functionality of this MCP so that it support fetching different versions of a given Confluence page. The current implementation of the tool has a function "get_page_content" which just fetches the latest version of the page. 
However, the Atlassian API that's used does support fetching a previous version of the page with the same API Call. The Atlassian documentation can be found at https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/#api-pages-id-get

We first need to contemplate whether it's better to extend the functionality of the existing tool "get_page_content" by specifying an optional page version number, or whether it's better to create a new tool "get_page_content_with_version". 

All the development must happen in a new branch of the current git repository to keep it clean and separate from the main branch. Make sure that each usable iteration is checked into git. 
