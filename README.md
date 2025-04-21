# MCP Atlassian

![PyPI Version](https://img.shields.io/pypi/v/mcp-atlassian)
![PyPI - Downloads](https://img.shields.io/pypi/dm/mcp-atlassian)
![PePy - Total Downloads](https://static.pepy.tech/personalized-badge/mcp-atlassian?period=total&units=international_system&left_color=grey&right_color=blue&left_text=Total%20Downloads)
![License](https://img.shields.io/github/license/sooperset/mcp-atlassian)
[![smithery badge](https://smithery.ai/badge/mcp-atlassian)](https://smithery.ai/server/mcp-atlassian)

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

The primary way to use MCP Atlassian is through IDE integration:

**Option 1: Using uvx (Recommended)**

Install uv first:

**macOS/Linux:**

```bash
# Using the official installer
curl -LsSf https://astral.sh/uv/install.sh | sh

# Alternatively, on macOS you can use Homebrew
brew install uv
```

**Windows:**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

With `uv` installed, you can use `uvx mcp-atlassian` directly in your IDE configuration without installing the package separately.

**Option 2: Using pip**

```bash
pip install mcp-atlassian
```

**Option 3: Using Smithery**

```bash
npx -y @smithery/cli install mcp-atlassian --client claude
```

**Option 4: Using Docker**

1. Clone the repository:
   ```bash
   git clone https://github.com/sooperset/mcp-atlassian.git
   cd mcp-atlassian
   ```
2. Build the Docker image:
   ```bash
   docker build -t mcp/atlassian .
   ```

### 3. Key Configuration Options

When configuring in your IDE, you can use these optional environment variables:

- `CONFLUENCE_SPACES_FILTER`: Filter by space keys (e.g., "DEV,TEAM,DOC")
- `JIRA_PROJECTS_FILTER`: Filter by project keys (e.g., "PROJ,DEV,SUPPORT")
- `READ_ONLY_MODE`: Set to "true" to disable write operations
- `MCP_VERBOSE`: Set to "true" for more detailed logging

> **Note:** You can configure just Confluence, just Jira, or both services by including only the variables for the services you need.

See the [.env.example](https://github.com/sooperset/mcp-atlassian/blob/main/.env.example) file for all available options.

## IDE Integration

MCP Atlassian is designed to be used with AI assistants through IDE integration.

> **Note**: To apply the configuration in Claude Desktop:
>
> **Method 1 (Recommended)**: Click hamburger menu (☰) > Settings > Developer > "Edit Config" button
>
> **Method 2**: Locate and edit the configuration file directly:
> - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
> - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
> - **Linux**: `~/.config/Claude/claude_desktop_config.json`
>
> **For Cursor**: Open Settings → Features → MCP Servers → + Add new global MCP server

Here's how to set it up based on your installation method:

### Using uvx (Recommended)

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@company.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your.email@company.com",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

<details>
<summary>Server/Data Center Configuration</summary>

For Server/Data Center deployments, use these environment variables instead:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "CONFLUENCE_URL": "https://confluence.your-company.com",
        "CONFLUENCE_PERSONAL_TOKEN": "your_token",
        "JIRA_URL": "https://jira.your-company.com",
        "JIRA_PERSONAL_TOKEN": "your_token"
      }
    }
  }
}
```
</details>

<details> <summary>Single Service Configurations</summary>

For Confluence only:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@company.com",
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
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your.email@company.com",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

</details>

<details> <summary>Alternative: Using CLI Arguments</summary>

You can also use command-line arguments instead of environment variables:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": [
        "mcp-atlassian",
        "--confluence-url=https://your-company.atlassian.net/wiki",
        "--confluence-username=your.email@company.com",
        "--confluence-token=your_api_token",
        "--jira-url=https://your-company.atlassian.net",
        "--jira-username=your.email@company.com",
        "--jira-token=your_api_token"
      ]
    }
  }
}
```
</details>

<details> <summary>Using pip</summary>

If you've installed mcp-atlassian with pip, use this configuration instead:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "mcp-atlassian",
      "env": {
        "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@company.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your.email@company.com",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```
</details>

<details> <summary>Using Docker</summary>

If you've built the Docker image, use this configuration:

**Method 1: Using Environment Variables**

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "mcp/atlassian",
        "--confluence-url=https://your-company.atlassian.net/wiki",
        "--confluence-username=your.email@company.com",
        "--confluence-token=your_api_token",
        "--jira-url=https://your-company.atlassian.net",
        "--jira-username=your.email@company.com",
        "--jira-token=your_api_token"
      ]
    }
  }
}
```

**Method 2: Using an Environment File**

Create a `.env` file based on the `.env.example` template in the repository and populate it with your variables, then use:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "--env-file", "/path/to/your/.env", "mcp/atlassian"]
    }
  }
}
```

</details>

### SSE Transport Configuration

<details> <summary>Using SSE Instead of stdio</summary>

1. Start the server with:

```bash
uvx mcp-atlassian --transport sse --port 9000 \
  --confluence-url https://your-company.atlassian.net/wiki \
  --confluence-username your.email@company.com \
  --confluence-token your_api_token \
  --jira-url https://your-company.atlassian.net \
  --jira-username your.email@company.com \
  --jira-token your_api_token
```

2. Configure in your IDE:

```json
{
  "mcpServers": {
    "mcp-atlassian-sse": {
      "url": "http://localhost:9000/sse"
    }
  }
}
```
</details>

## Resources and Tools

### Resources

- `confluence://{space_key}`: Access Confluence spaces
- `jira://{project_key}`: Access Jira projects

> **Note:** The MCP server filters resources to only show Confluence spaces and Jira projects that the user is actively interacting with, based on their contributions and assignments.

### Key Tools

#### Confluence Tools

- `confluence_search`: Search Confluence content using CQL
- `confluence_get_page`: Get content of a specific page
- `confluence_create_page`: Create a new page
- `confluence_update_page`: Update an existing page

#### Jira Tools

- `jira_get_issue`: Get details of a specific issue
- `jira_search`: Search issues using JQL
- `jira_create_issue`: Create a new issue
- `jira_update_issue`: Update an existing issue
- `jira_transition_issue`: Transition an issue to a new status
- `jira_add_comment`: Add a comment to an issue

<details> <summary>View All Tools</summary>

|Confluence Tools|Jira Tools|
|---|---|
|`confluence_search`|`jira_get_issue`|
|`confluence_get_page`|`jira_search`|
|`confluence_get_page_children`|`jira_get_project_issues`|
|`confluence_get_page_ancestors`|`jira_get_epic_issues`|
|`confluence_get_comments`|`jira_create_issue`|
|`confluence_create_page`|`jira_batch_create_issues`|
|`confluence_update_page`|`jira_update_issue`|
|`confluence_delete_page`|`jira_delete_issue`|
||`jira_get_transitions`|
||`jira_transition_issue`|
||`jira_add_comment`|
||`jira_add_worklog`|
||`jira_get_worklog`|
||`jira_download_attachments`|
||`jira_link_to_epic`|
||`jira_get_agile_boards`|
||`jira_get_board_issues`|
||`jira_get_sprints_from_board`|
||`jira_get_sprint_issues`|
||`jira_update_sprint`|
||`jira_create_issue_link`|
||`jira_remove_issue_link`|

</details>

## Troubleshooting & Debugging

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

1. Check out our [CONTRIBUTING.md](CONTRIBUTING.md) guide
2. Set up your development environment:
   ```bash
   uv sync --frozen --all-extras --dev
   pre-commit install
   ```
3. Make changes and submit a pull request

We use pre-commit hooks for code quality and follow semantic versioning for releases.

## License

Licensed under MIT - see [LICENSE](LICENSE) file. This is not an official Atlassian product.
