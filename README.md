# MCP Atlassian

[![smithery badge](https://smithery.ai/badge/mcp-atlassian)](https://smithery.ai/server/mcp-atlassian)

Model Context Protocol (MCP) server for Atlassian Cloud products (Confluence and Jira). This integration is designed specifically for Atlassian Cloud instances and does not support Atlassian Server or Data Center deployments.

<a href="https://glama.ai/mcp/servers/kc33m1kh5m"><img width="380" height="200" src="https://glama.ai/mcp/servers/kc33m1kh5m/badge" alt="Atlassian MCP server" /></a>

## Feature Demo
![Demo](https://github.com/user-attachments/assets/995d96a8-4cf3-4a03-abe1-a9f6aea27ac0)

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

- **confluence_search**
  - Search Confluence content using CQL
  - Inputs:
    - `query` (string): CQL query string
    - `limit` (number, optional): Results limit (1-50, default: 10)
  - Returns:
    - Array of search results with page_id, title, space, url, last_modified, type, and excerpt

- **confluence_get_page**
  - Get content of a specific Confluence page
  - Inputs:
    - `page_id` (string): Confluence page ID
    - `include_metadata` (boolean, optional): Include page metadata (default: true)

- **confluence_get_comments**
  - Get comments for a specific Confluence page
  - Input: `page_id` (string)

#### Jira Tools

- **jira_get_issue**
  - Get details of a specific Jira issue
  - Inputs:
    - `issue_key` (string): Jira issue key (e.g., 'PROJ-123')
    - `expand` (string, optional): Fields to expand

- **jira_search**
  - Search Jira issues using JQL
  - Inputs:
    - `jql` (string): JQL query string
    - `fields` (string, optional): Comma-separated fields (default: "*all")
    - `limit` (number, optional): Results limit (1-50, default: 10)

- **jira_get_project_issues**
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
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@domain.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "JIRA_URL": "https://your-domain.atlassian.net",
        "JIRA_USERNAME": "your.email@domain.com",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

<details>
<summary>Alternative configuration using <code>uv</code></summary>

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/mcp-atlassian",
        "run",
        "mcp-atlassian"
      ],
      "env": {
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@domain.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "JIRA_URL": "https://your-domain.atlassian.net",
        "JIRA_USERNAME": "your.email@domain.com",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```
Replace `/path/to/mcp-atlassian` with the actual path where you've cloned the repository.
</details>

### Installing via Smithery

To install Atlassian Integration for Claude Desktop automatically via [Smithery](https://smithery.ai/server/mcp-atlassian):

```bash
npx -y @smithery/cli install mcp-atlassian --client claude
```

## Security

- Never share API tokens
- Keep .env files secure and private
- See [SECURITY.md](SECURITY.md) for best practices

## License

Licensed under MIT - see [LICENSE](LICENSE) file. This is not an official Atlassian product.
