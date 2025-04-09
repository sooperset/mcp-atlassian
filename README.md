# MCP Atlassian

![PyPI Version](https://img.shields.io/pypi/v/mcp-atlassian)
![PyPI - Downloads](https://img.shields.io/pypi/dm/mcp-atlassian)
![PePy - Total Downloads](https://static.pepy.tech/personalized-badge/mcp-atlassian?period=total&units=international_system&left_color=grey&right_color=blue&left_text=Total%20Downloads)
[![Run Tests](https://github.com/sooperset/mcp-atlassian/actions/workflows/tests.yml/badge.svg)](https://github.com/sooperset/mcp-atlassian/actions/workflows/tests.yml)
![License](https://img.shields.io/github/license/sooperset/mcp-atlassian)

Model Context Protocol (MCP) server for Atlassian products (Confluence and Jira). This integration supports both Confluence & Jira Cloud and Server/Data Center deployments.

## Example Usage

Ask your AI assistant to:

- **📝 Automatic Jira Updates** - "Update Jira from our meeting notes"
- **🔍 AI-Powered Confluence Search** - "Find our OKR guide in Confluence and summarize it"
- **🐛 Smart Jira Issue Filtering** - "Show me urgent bugs in PROJ project from last week"
- **📄 Content Creation & Management** - "Create a tech design doc for XYZ feature"

### Feature Demo

https://github.com/user-attachments/assets/35303504-14c6-4ae4-913b-7c25ea511c3e

<details> <summary>Confluence Demo</summary>

https://github.com/user-attachments/assets/7fe9c488-ad0c-4876-9b54-120b666bb785

</details>

### Compatibility

|Product|Deployment Type|Support Status|
|---|---|---|
|**Confluence**|Cloud|✅ Fully supported|
|**Confluence**|Server/Data Center|✅ Supported (version 6.0+)|
|**Jira**|Cloud|✅ Fully supported|
|**Jira**|Server/Data Center|✅ Supported (version 8.14+)|

## Quick Start Guide

### 1. Authentication Setup

First, generate the necessary authentication tokens for Confluence & Jira:

#### For Cloud

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **Create API token**, name it
3. Copy the token immediately

#### For Server/Data Center

1. Go to your profile (avatar) → **Profile** → **Personal Access Tokens**
2. Click **Create token**, name it, set expiry
3. Copy the token immediately

### 2. Installation

MCP Atlassian is distributed as a Docker image. This is the recommended way to run the server, especially for IDE integration. Ensure you have Docker installed.

```bash
# Pull Pre-built Image
docker pull ghcr.io/sooperset/mcp-atlassian:latest
```

## IDE Integration

MCP Atlassian is designed to be used with AI assistants through IDE integration.

> [!TIP]
> **To apply the configuration in Claude Desktop:**
>
> **Method 1 (Recommended)**: Click hamburger menu (☰) > Settings > Developer > "Edit Config" button
>
> **Method 2**: Locate and edit the configuration file directly:
> - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
> - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
> - **Linux**: `~/.config/Claude/claude_desktop_config.json`
>
> **For Cursor**: Open Settings → Features → MCP Servers → + Add new global MCP server

### Configuration Methods

There are two main approaches to configure the Docker container:

1. **Passing Variables Directly** (shown in examples below)
2. **Using an Environment File** with `--env-file` flag (shown in collapsible sections)

> [!NOTE]
> Common environment variables include:
>
> - `CONFLUENCE_SPACES_FILTER`: Filter by space keys (e.g., "DEV,TEAM,DOC")
> - `JIRA_PROJECTS_FILTER`: Filter by project keys (e.g., "PROJ,DEV,SUPPORT")
> - `READ_ONLY_MODE`: Set to "true" to disable write operations
> - `MCP_VERBOSE`: Set to "true" for more detailed logging
>
> See the [.env.example](https://github.com/sooperset/mcp-atlassian/blob/main/.env.example) file for all available options.

### Configuration Examples

**Method 1 (Passing Variables Directly):**
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e", "CONFLUENCE_URL",
        "-e", "CONFLUENCE_USERNAME",
        "-e", "CONFLUENCE_API_TOKEN",
        "-e", "JIRA_URL",
        "-e", "JIRA_USERNAME",
        "-e", "JIRA_API_TOKEN",
        "ghcr.io/sooperset/mcp-atlassian:latest"
      ],
      "env": {
        "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@company.com",
        "CONFLUENCE_API_TOKEN": "your_confluence_api_token",
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your.email@company.com",
        "JIRA_API_TOKEN": "your_jira_api_token"
      }
    }
  }
}
```

<details>
<summary>Alternative: Using Environment File</summary>

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
        "/path/to/your/mcp-atlassian.env",
        "ghcr.io/sooperset/mcp-atlassian:latest"
      ]
    }
  }
}
```
</details>

<details>
<summary>Server/Data Center Configuration</summary>

For Server/Data Center deployments, use direct variable passing:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-e", "CONFLUENCE_URL",
        "-e", "CONFLUENCE_PERSONAL_TOKEN",
        "-e", "CONFLUENCE_SSL_VERIFY",
        "-e", "JIRA_URL",
        "-e", "JIRA_PERSONAL_TOKEN",
        "-e", "JIRA_SSL_VERIFY",
        "ghcr.io/sooperset/mcp-atlassian:latest"
      ],
      "env": {
        "CONFLUENCE_URL": "https://confluence.your-company.com",
        "CONFLUENCE_PERSONAL_TOKEN": "your_confluence_pat",
        "CONFLUENCE_SSL_VERIFY": "false",
        "JIRA_URL": "https://jira.your-company.com",
        "JIRA_PERSONAL_TOKEN": "your_jira_pat",
        "JIRA_SSL_VERIFY": "false"
      }
    }
  }
}
```

> [!NOTE]
> Set `CONFLUENCE_SSL_VERIFY` and `JIRA_SSL_VERIFY` to "false" only if you have self-signed certificates.

</details>

<details> <summary>Single Service Configurations</summary>

**For Confluence Cloud only:**

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-e", "CONFLUENCE_URL",
        "-e", "CONFLUENCE_USERNAME",
        "-e", "CONFLUENCE_API_TOKEN",
        "ghcr.io/sooperset/mcp-atlassian:latest"
      ],
      "env": {
        "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@company.com",
        "CONFLUENCE_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

For Confluence Server/DC, use:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-e", "CONFLUENCE_URL",
        "-e", "CONFLUENCE_PERSONAL_TOKEN",
        "ghcr.io/sooperset/mcp-atlassian:latest"
      ],
      "env": {
        "CONFLUENCE_URL": "https://confluence.your-company.com",
        "CONFLUENCE_PERSONAL_TOKEN": "your_personal_token"
      }
    }
  }
}
```

**For Jira Cloud only:**

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-e", "JIRA_URL",
        "-e", "JIRA_USERNAME",
        "-e", "JIRA_API_TOKEN",
        "ghcr.io/sooperset/mcp-atlassian:latest"
      ],
      "env": {
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your.email@company.com",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

For Jira Server/DC, use:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-e", "JIRA_URL",
        "-e", "JIRA_PERSONAL_TOKEN",
        "ghcr.io/sooperset/mcp-atlassian:latest"
      ],
      "env": {
        "JIRA_URL": "https://jira.your-company.com",
        "JIRA_PERSONAL_TOKEN": "your_personal_token"
      }
    }
  }
}
```

</details>

### SSE Transport Configuration

For SSE transport, first start the server with its configuration provided via command-line arguments or server-side environment variables (e.g., from a `.env` file):
```bash
# Example starting the server with Cloud configuration
uvx mcp-atlassian --transport sse --port 9000 \
  --confluence-url https://your-company.atlassian.net/wiki \
  --confluence-username your.email@company.com \
  --confluence-token your_api_token \
  --jira-url https://your-company.atlassian.net \
  --jira-username your.email@company.com \
  --jira-token your_api_token
```

Then configure *only the URL* in Cursor's `~/.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "mcp-atlassian-sse": {
      "url": "http://localhost:9000/sse"
    }
  }
}
```

## Resources

> **Note:** The MCP server filters resources to only show Confluence spaces and Jira projects that the user is actively interacting with, based on their contributions and assignments.

- `confluence://{space_key}`: Access Confluence spaces
- `jira://{project_key}`: Access Jira projects

## Available Tools

| Tool | Description |
|------|-------------|
| `confluence_search` | Search Confluence content using CQL |
| `confluence_get_page` | Get content of a specific Confluence page |
| `confluence_get_page_children` | Get child pages of a specific Confluence page |
| `confluence_get_page_ancestors` | Get parent pages of a specific Confluence page |
| `confluence_get_comments` | Get comments for a specific Confluence page |
| `confluence_create_page` | Create a new Confluence page |
| `confluence_update_page` | Update an existing Confluence page |
| `confluence_delete_page` | Delete an existing Confluence page |
| `confluence_attach_content` | Attach content to a Confluence page |
| `jira_get_issue` | Get details of a specific Jira issue |
| `jira_search` | Search Jira issues using JQL |
| `jira_get_project_issues` | Get all issues for a specific Jira project |
| `jira_get_epic_issues` | Get all issues linked to a specific Epic |
| `jira_create_issue` | Create a new issue in Jira |
| `jira_update_issue` | Update an existing Jira issue |
| `jira_delete_issue` | Delete an existing Jira issue |
| `jira_get_transitions` | Get available status transitions for a Jira issue |
| `jira_transition_issue` | Transition a Jira issue to a new status |
| `jira_add_comment` | Add a comment to a Jira issue |
| `jira_add_worklog` | Add a worklog entry to a Jira issue |
| `jira_get_worklog` | Get worklog entries for a Jira issue |
| `jira_download_attachments` | Download attachments from a Jira issue |
| `jira_link_to_epic` | Link an issue to an Epic |
| `jira_get_agile_boards` | Get Jira agile boards by name, project key, or type |
| `jira_get_board_issues` | Get all issues linked to a specific board |
| `jira_get_sprints_from_board` | Get Jira sprints from board by state |
| `jira_create_sprint` | Create Jira sprint for a board |
| `jira_get_sprint_issues` | Get Jira issues from sprint |

## Development & Debugging

### Common Issues

- **Authentication Failures**:
    - For Cloud: Check your API tokens (not your account password)
    - For Server/Data Center: Verify your personal access token is valid and not expired
    - For older Confluence servers: Some older versions require basic authentication with `CONFLUENCE_USERNAME` and `CONFLUENCE_API_TOKEN` (where token is your password)
- **SSL Certificate Issues**: If using Server/Data Center and encounter SSL errors, set `CONFLUENCE_SSL_VERIFY=false` or `JIRA_SSL_VERIFY=false`
- **Permission Errors**: Ensure your Atlassian account has sufficient permissions to access the spaces/projects

### Debugging Tools

```bash
# Using MCP Inspector for testing
npx @modelcontextprotocol/inspector uvx mcp-atlassian ...

# For local development version
npx @modelcontextprotocol/inspector uv --directory /path/to/your/mcp-atlassian run mcp-atlassian ...

# View logs
# macOS
tail -n 20 -f ~/Library/Logs/Claude/mcp*.log
# Windows
type %APPDATA%\Claude\logs\mcp*.log | more
```

## Security

- Never share API tokens
- Keep .env files secure and private
- See [SECURITY.md](SECURITY.md) for best practices

## Contributing

We welcome contributions to MCP Atlassian! If you'd like to contribute:

1. Check out our [CONTRIBUTING.md](CONTRIBUTING.md) guide for detailed development setup instructions.
2. Make changes and submit a pull request.

We use pre-commit hooks for code quality and follow semantic versioning for releases.

## License

Licensed under MIT - see [LICENSE](LICENSE) file. This is not an official Atlassian product.
