# MCP Atlassian

[![smithery badge](https://smithery.ai/badge/mcp-atlassian)](https://smithery.ai/server/mcp-atlassian)

Model Context Protocol (MCP) server for Atlassian Cloud products (Confluence and Jira). This integration is designed specifically for Atlassian Cloud instances and does not support Atlassian Server or Data Center deployments.

<a href="https://glama.ai/mcp/servers/kc33m1kh5m"><img width="380" height="200" src="https://glama.ai/mcp/servers/kc33m1kh5m/badge" alt="Atlassian MCP server" /></a>

### Feature Demo
![Demo](https://github.com/user-attachments/assets/995d96a8-4cf3-4a03-abe1-a9f6aea27ac0)

### Resources

- `confluence://{space_key}`: Access Confluence spaces and pages
- `confluence://{space_key}/pages/{title}`: Access specific Confluence pages
- `jira://{project_key}`: Access Jira project and its issues
- `jira://{project_key}/issues/{issue_key}`: Access specific Jira issues

### Tools

#### Confluence Tools

1. `confluence_search`
   - Search Confluence content using CQL
   - Inputs:
     - `query` (string): CQL query string
     - `limit` (number, optional): Results limit (1-50, default: 10)
   - Returns: Array of search results with page_id, title, space, url, last_modified, type, and excerpt

2. `confluence_get_page`
   - Get content of a specific Confluence page
   - Inputs:
     - `page_id` (string): Confluence page ID
     - `include_metadata` (boolean, optional): Include page metadata (default: true)
   - Returns: Page content and optional metadata

3. `confluence_get_comments`
   - Get comments for a specific Confluence page
   - Input:
     - `page_id` (string): Confluence page ID
   - Returns: Array of comments with author, creation date, and content

#### Jira Tools

1. `jira_get_issue`
   - Get details of a specific Jira issue
   - Inputs:
     - `issue_key` (string): Jira issue key (e.g., 'PROJ-123')
     - `expand` (string, optional): Fields to expand
   - Returns: Issue details including content and metadata

2. `jira_search`
   - Search Jira issues using JQL
   - Inputs:
     - `jql` (string): JQL query string
     - `fields` (string, optional): Comma-separated fields (default: "*all")
     - `limit` (number, optional): Results limit (1-50, default: 10)
   - Returns: Array of matching issues with metadata

3. `jira_get_project_issues`
   - Get all issues for a specific Jira project
   - Inputs:
     - `project_key` (string): Project key
     - `limit` (number, optional): Results limit (1-50, default: 10)
   - Returns: Array of project issues with metadata

4. `jira_create_issue`
   - Create a new issue in Jira
   - Inputs:
     - `project_key` (string): The JIRA project key (e.g. 'PROJ')
     - `summary` (string): Summary/title of the issue
     - `issue_type` (string): Issue type (e.g. 'Task', 'Bug', 'Story')
     - `description` (string, optional): Issue description
     - `additional_fields` (string, optional): JSON string of additional fields
   - Returns: Created issue details with metadata

5. `jira_update_issue`
   - Update an existing Jira issue
   - Inputs:
     - `issue_key` (string): Jira issue key
     - `fields` (string): JSON object of fields to update
     - `additional_fields` (string, optional): JSON string of additional fields
   - Returns: Updated issue details with metadata

6. `jira_delete_issue`
   - Delete an existing Jira issue
   - Inputs:
     - `issue_key` (string): Jira issue key (e.g. PROJ-123)
   - Returns: Success confirmation message

## Installation

### Using uv (recommended)

When using [`uv`](https://docs.astral.sh/uv/), use [`uvx`](https://docs.astral.sh/uv/guides/tools/) to directly run *mcp-atlassian*.

```bash
uvx mcp-atlassian
# or
uv pip install mcp-atlassian
```

### Using PIP

Alternatively you can install mcp-atlassian via pip:

```bash
pip install mcp-atlassian
```

### Installing via Smithery

To install Atlassian Integration for Claude Desktop automatically via [Smithery](https://smithery.ai/server/mcp-atlassian):

```bash
npx -y @smithery/cli install mcp-atlassian --client claude
```

## Configuration

The MCP Atlassian integration supports using either Confluence, Jira, or both services. You only need to provide the environment variables for the service(s) you want to use.

### Usage with Claude Desktop

1. Get API tokens from: https://id.atlassian.com/manage-profile/security/api-tokens

2. Add to your `claude_desktop_config.json` with only the services you need:

<details>
<summary>Using uvx</summary>

For Confluence only:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@domain.com",
        "CONFLUENCE_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

For Jira only:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "JIRA_URL": "https://your-domain.atlassian.net",
        "JIRA_USERNAME": "your.email@domain.com",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

For both services:
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
</details>

<details>
<summary>Using docker</summary>

There are two ways to configure the Docker environment:

1. Using environment variables directly in the config:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "mcp/atlassian"],
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

2. Using an environment file:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "/path/to/your/.env",
        "mcp/atlassian"
      ]
    }
  }
}
```

The .env file should contain:
```env
CONFLUENCE_URL=https://your-domain.atlassian.net/wiki
CONFLUENCE_USERNAME=your.email@domain.com
CONFLUENCE_API_TOKEN=your_api_token
JIRA_URL=https://your-domain.atlassian.net
JIRA_USERNAME=your.email@domain.com
JIRA_API_TOKEN=your_api_token
```

</details>

### Cursor IDE Configuration

To integrate the MCP server with Cursor IDE:

1. Install mcp-atlassian using uvx:
   ```bash
   uvx mcp-atlassian
   ```

2. Configure the server:
   - Open Cursor Settings
   - Navigate to `Features` > `MCP Servers`
   - Click `Add new MCP server`
   - Enter this configuration:
     ```yaml
     name: mcp-atlassian
     type: command
     command: uvx mcp-atlassian --confluence-url=https://your-domain.atlassian.net/wiki --confluence-username=your.email@domain.com --confluence-token=your_api_token --jira-url=https://your-domain.atlassian.net --jira-username=your.email@domain.com --jira-token=your_api_token
     ```

## Debugging

You can use the MCP inspector to debug the server:

```bash
npx @modelcontextprotocol/inspector uvx mcp-atlassian
```

For development installations:
```bash
cd path/to/mcp-atlassian
npx @modelcontextprotocol/inspector uv run mcp-atlassian
```

View logs with:
```bash
tail -n 20 -f ~/Library/Logs/Claude/mcp*.log
```

## Development

For local development testing:

1. Use the MCP inspector (see [Debugging](#debugging))
2. Test with Claude Desktop or Cursor IDE using the configuration above

## Build

Docker build:
```bash
docker build -t mcp/atlassian .
```

## Security

- Never share API tokens
- Keep .env files secure and private
- See [SECURITY.md](SECURITY.md) for best practices

## License

Licensed under MIT - see [LICENSE](LICENSE) file. This is not an official Atlassian product.
