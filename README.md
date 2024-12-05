# MCP Atlassian

Model Context Protocol (MCP) server for Atlassian Cloud products (Confluence and Jira). This integration is designed specifically for Atlassian Cloud instances and does not support Atlassian Server or Data Center deployments.

## Features

- Search and read Confluence spaces/pages
- Get Confluence page comments
- Search and read Jira issues
- Get project issues and metadata

## API

### Resources

- `confluence://{space_key}`: Access Confluence spaces and pages
- `confluence://{space_key}/pages/{title}`: Access specific Confluence pages
- `jira://{project_key}`: Access Jira project and its issues
- `jira://{project_key}/issues/{issue_key}`: Access specific Jira issues

### Tools

#### Confluence Tools

- **confluence.search**
  - Search Confluence content using CQL
  - Inputs:
    - `query` (string): CQL query string
    - `limit` (number, optional): Results limit (1-50, default: 10)

- **confluence.get_page**
  - Get content of a specific Confluence page
  - Inputs:
    - `page_id` (string): Confluence page ID
    - `include_metadata` (boolean, optional): Include page metadata (default: true)

- **confluence.get_comments**
  - Get comments for a specific Confluence page
  - Input: `page_id` (string)

#### Jira Tools

- **jira.get_issue**
  - Get details of a specific Jira issue
  - Inputs:
    - `issue_key` (string): Jira issue key (e.g., 'PROJ-123')
    - `expand` (string, optional): Fields to expand

- **jira.search**
  - Search Jira issues using JQL
  - Inputs:
    - `jql` (string): JQL query string
    - `fields` (string, optional): Comma-separated fields (default: "*all")
    - `limit` (number, optional): Results limit (1-50, default: 10)

- **jira.get_project_issues**
  - Get all issues for a specific Jira project
  - Inputs:
    - `project_key` (string): Project key
    - `limit` (number, optional): Results limit (1-50, default: 10)

## Usage with Claude Desktop

1. Get API tokens from: https://id.atlassian.com/manage-profile/security/api-tokens

2. Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uv",
      "args": ["mcp-atlassian"],
      "env": {
        "CONFLUENCE_URL": "your_confluence_url",
        "CONFLUENCE_USERNAME": "your_username",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "JIRA_URL": "your_jira_url",
        "JIRA_USERNAME": "your_username",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

## Security

- Never share API tokens
- Keep .env files secure and private
- See [SECURITY.md](SECURITY.md) for best practices

## License

Licensed under MIT - see [LICENSE](LICENSE) file. This is not an official Atlassian product.
