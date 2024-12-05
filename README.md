# mcp-atlassian

MCP server to interact with Atlassian products. This integration is designed specifically for Atlassian Cloud instances and does not support Atlassian Server or Data Center deployments.


## Features

### Tools

- search_confluence: Search Confluence content using natural language
- get_page_content: Get content of a specific Confluence page
- get_page_comments: Get comments for a specific page

### Example prompts

- "Search for all documentation related to authentication and summarize the key points"
- "Get the content of the onboarding guide and create a checklist from it"
- "Find all comments on the project requirements page and highlight any concerns raised"

## Installation

```bash
# Using pip
pip install mcp-atlassian

# Or using uv (recommended)
uv pip install mcp-atlassian
```

## Setup

### Requirements

Create a `.env` file with:
```
CONFLUENCE_CLOUD_URL=your_confluence_url
CONFLUENCE_CLOUD_USER=your_username
CONFLUENCE_CLOUD_TOKEN=your_api_token
```

To get an API token:
1. Log in to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click Create API token
3. Enter a memorable Label for your token and click Create
4. Click Copy to clipboard to save your token securely

### Claude Desktop Configuration

Location:
- MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%/Claude/claude_desktop_config.json`

### Configuration

<details>
  <summary>Development/Unpublished Servers Configuration</summary>
  
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uv",
      "args": [
        "--directory",
        "<dir_to>/mcp-atlassian",
        "run",
        "mcp-atlassian"
      ],
      "env": {
        "CONFLUENCE_CLOUD_URL": "your_confluence_url",
        "CONFLUENCE_CLOUD_USER": "your_username",
        "CONFLUENCE_CLOUD_TOKEN": "your_api_token"
      }
    }
  }
}
```

</details>

<details>
  <summary>Published Servers Configuration</summary>
  
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": [
        "mcp-atlassian"
      ],
      "env": {
        "CONFLUENCE_CLOUD_URL": "your_confluence_url",
        "CONFLUENCE_CLOUD_USER": "your_username",
        "CONFLUENCE_CLOUD_TOKEN": "your_api_token"
      }
    }
  }
}
```

</details>

## Development

### Building

```bash
# Install dependencies
uv sync

# Build package
uv build

# Publish to PyPI
uv publish
```

### Debugging

Use MCP Inspector:
```bash
npx @modelcontextprotocol/inspector mcp-atlassian
```

View logs:
```bash
tail -n 20 -f ~/Library/Logs/Claude/mcp-server-mcp-atlassian.log
```

## Todo

- [ ] Jira integration

### Configuration

<details>
  <summary>Development/Unpublished Servers Configuration</summary>
  
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uv",
      "args": [
        "--directory",
        "<dir_to>/mcp-atlassian",
        "run",
        "mcp-atlassian"
      ],
      "env": {
        "CONFLUENCE_CLOUD_URL": "your_confluence_url",
        "CONFLUENCE_CLOUD_USER": "your_username",
        "CONFLUENCE_CLOUD_TOKEN": "your_api_token"
      }
    }
  }
}
```

</details>

<details>
  <summary>Published Servers Configuration</summary>
  
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": [
        "mcp-atlassian"
      ],
      "env": {
        "CONFLUENCE_CLOUD_URL": "your_confluence_url",
        "CONFLUENCE_CLOUD_USER": "your_username",
        "CONFLUENCE_CLOUD_TOKEN": "your_api_token"
      }
    }
  }
}
```

</details>

## Legal & Security

This is not an official Atlassian product. Licensed under MIT - see [LICENSE](LICENSE) file.

### Security
- Never share API tokens
- Keep .env files secure and private
- See [SECURITY.md](SECURITY.md) for best practices

For security issues, please email [security contact].
