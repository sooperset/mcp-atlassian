# MCP Atlassian

Model Context Protocol (MCP) server for Atlassian products (Confluence and Jira). This integration supports both Atlassian Cloud and Jira Server/Data Center deployments.

### Feature Demo
![Jira Demo](https://github.com/user-attachments/assets/61573853-c8a8-45c9-be76-575f2b651984)

<details>
<summary>Confluence Demo</summary>

![Confluence Demo](https://github.com/user-attachments/assets/8a203391-795a-474f-8123-9c11f13a780e)
</details>

### Compatibility

| Product | Deployment Type | Support Status              |
|---------|----------------|-----------------------------|
| **Confluence** | Cloud | ✅ Fully supported           |
| **Confluence** | Server/Data Center | ✅ Supported (version 7.9+)  |
| **Jira** | Cloud | ✅ Fully supported           |
| **Jira** | Server/Data Center | ✅ Supported (version 8.14+) |

## Setup Guide

### 1. Authentication Setup

First, generate the necessary authentication tokens:

#### For Atlassian Cloud
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **Create API token**, name it
3. Copy the token immediately

#### For Server/Data Center
1. Go to your profile (avatar) → **Profile** → **Personal Access Tokens**
2. Click **Create token**, name it, set expiry
3. Copy the token immediately

### 2. Installation

Choose one of these installation methods:

#### Using uv (recommended)
```bash
# Install uv on macOS
brew install uv

# Run directly with uvx
uvx mcp-atlassian
```

#### Using PIP
```bash
pip install mcp-atlassian
```

#### Using Docker
```bash
git clone https://github.com/sooperset/mcp-atlassian.git
cd mcp-atlassian
docker build -t mcp/atlassian .
```

### 3. Configuration

The integration supports using either Confluence, Jira, or both services. You only need to configure the service(s) you want to use.

#### Configuration Variables

| Setting | Environment Variable | CLI Argument | Cloud | Server/DC |
|---------|-------------------|--------------|:-----:|:---------:|
| **Confluence** |
| URL | `CONFLUENCE_URL` | `--confluence-url` | O | O |
| Email | `CONFLUENCE_USERNAME` | `--confluence-username` | O | X |
| API Token | `CONFLUENCE_API_TOKEN` | `--confluence-token` | O | X |
| PAT | `CONFLUENCE_PERSONAL_TOKEN` | `--confluence-personal-token` | X | O |
| **Jira** |
| URL | `JIRA_URL` | `--jira-url` | O | O |
| Email | `JIRA_USERNAME` | `--jira-username` | O | X |
| API Token | `JIRA_API_TOKEN` | `--jira-token` | O | X |
| PAT | `JIRA_PERSONAL_TOKEN` | `--jira-personal-token` | X | O |
| **Common** |
| SSL Verify | `*_SSL_VERIFY` | `--[no-]*-ssl-verify` | X | Optional |
| Transport | - | `--transport stdio\|sse` | Optional | Optional |
| Port | - | `--port INTEGER` | Required for SSE | Required for SSE |

#### Quick Start Examples

```bash
# For Cloud (stdio transport)
uvx mcp-atlassian \
  --confluence-url=https://your.atlassian.net/wiki \
  --confluence-username=email \
  --confluence-token=token \
  --jira-url=https://your.atlassian.net \
  --jira-username=email \
  --jira-token=token

# For Server/DC (SSE transport)
uvx mcp-atlassian \
  --confluence-url=https://confluence.company.com \
  --confluence-personal-token=token \
  --jira-url=https://jira.company.com \
  --jira-personal-token=token \
  --transport sse \
  --port 8000
```

### 4. IDE Integration

#### Cursor IDE Setup

1. Open Cursor Settings
2. Navigate to `Features` > `MCP Servers`
3. Click `Add new MCP server`

- For stdio transport, enter the configuration:
   ```yaml
   name: mcp-atlassian
   type: command
   command: uvx mcp-atlassian --confluence-url=https://your-domain.atlassian.net/wiki --confluence-username=email --confluence-token=token --jira-url=https://your-domain.atlassian.net --jira-username=email --jira-token=token
   ```

![Image](https://github.com/user-attachments/assets/41658cb1-a1ab-4724-89f1-a7a00819947a)

- For SSE transport:

   First, start the MCP server in a terminal:
   ```bash
   uvx mcp-atlassian ... --transport sse --port 8000
   ```

   Then configure Cursor to connect to it:
   ```yaml
   name: mcp-atlassian
   type: sse
   Server URL: http://localhost:8000/sse
   ```
   Note: The SSE server must be running before you can connect Cursor to it.

![Image](https://github.com/user-attachments/assets/ff8a911b-d0e9-48cc-b7a1-3d3497743a98)

4. Switch to Agent mode in the Composer to use MCP tools

![image](https://github.com/user-attachments/assets/13c7ba94-d96b-4e40-a00d-13d3bbffe944)

#### Claude Desktop Setup

<details>
<summary>Using uvx</summary>

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

For Confluence/Jira Server/Data Center:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "CONFLUENCE_URL": "https://confluence.your-company.com",
        "CONFLUENCE_PERSONAL_TOKEN": "your_personal_access_token",
        "JIRA_URL": "https://jira.your-company.com",
        "JIRA_PERSONAL_TOKEN": "your_personal_access_token"
      }
    }
  }
}
```

</details>

<details>
<summary>Using pip</summary>

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "python",
      "args": ["-m", "mcp-atlassian"],
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
# Confluence Cloud
CONFLUENCE_URL=https://your-domain.atlassian.net/wiki  # Your Confluence cloud URL
CONFLUENCE_USERNAME=your.email@domain.com              # Your Atlassian account email
CONFLUENCE_API_TOKEN=your_api_token                    # API token for Confluence

# Confluence Server/Data Center (alternative to CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN)
# CONFLUENCE_URL=https://confluence.your-company.com        # Your Confluence Server/Data Center URL
# CONFLUENCE_PERSONAL_TOKEN=your_personal_access_token      # Personal Access Token for Confluence Server/Data Center
# CONFLUENCE_SSL_VERIFY=true                                # Set to 'false' for self-signed certificates

# Jira Cloud
JIRA_URL=https://your-domain.atlassian.net            # Your Jira cloud URL
JIRA_USERNAME=your.email@domain.com                   # Your Atlassian account email
JIRA_API_TOKEN=your_api_token                         # API token for Jira Cloud

# Jira Server/Data Center (alternative to JIRA_USERNAME and JIRA_API_TOKEN)
# JIRA_URL=https://jira.your-company.com              # Your Jira Server/Data Center URL
# JIRA_PERSONAL_TOKEN=your_personal_access_token      # Personal Access Token for Jira Server/Data Center
# JIRA_SSL_VERIFY=true                                # Set to 'false' for self-signed certificates
```

</details>

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
| `jira_get_issue` | Get details of a specific Jira issue |
| `jira_search` | Search Jira issues using JQL |
| `jira_get_project_issues` | Get all issues for a specific Jira project |
| `jira_create_issue` | Create a new issue in Jira |
| `jira_update_issue` | Update an existing Jira issue |
| `jira_delete_issue` | Delete an existing Jira issue |
| `jira_get_transitions` | Get available status transitions for a Jira issue |
| `jira_transition_issue` | Transition a Jira issue to a new status |
| `jira_add_worklog` | Add a worklog entry to a Jira issue |
| `jira_get_worklog` | Get worklog entries for a Jira issue |
| `jira_link_to_epic` | Link an issue to an Epic |
| `jira_get_epic_issues` | Get all issues linked to a specific Epic |

## Development & Debugging

### Local Development Setup

If you've cloned the repository and want to run a local version:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/your/mcp-atlassian",
        "run", "mcp-atlassian",
        "--confluence-url=https://your-domain.atlassian.net/wiki",
        "--confluence-username=your.email@domain.com",
        "--confluence-token=your_api_token",
        "--jira-url=https://your-domain.atlassian.net",
        "--jira-username=your.email@domain.com",
        "--jira-token=your_api_token"
      ]
    }
  }
}
```

### Debugging Tools

- MCP Inspector:
  ```bash
  # For standard installation
  npx @modelcontextprotocol/inspector uvx mcp-atlassian

  # For development installation
  cd path/to/mcp-atlassian
  npx @modelcontextprotocol/inspector uv run mcp-atlassian
  ```

- View logs:
  ```bash
  tail -n 20 -f ~/Library/Logs/Claude/mcp*.log
  ```

## Security

- Never share API tokens
- Keep .env files secure and private
- See [SECURITY.md](SECURITY.md) for best practices

## License

Licensed under MIT - see [LICENSE](LICENSE) file. This is not an official Atlassian product.
