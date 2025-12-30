# Configuration

This guide covers IDE integration, environment variables, and advanced configuration options.

## IDE Integration

### Configuration File Locations

| IDE | Location |
|-----|----------|
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Linux) | `~/.config/Claude/claude_desktop_config.json` |
| Cursor | Settings → MCP → + Add new global MCP server |

### Basic Configuration (uvx)

The simplest configuration using uvx:

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

### Docker Configuration

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
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

### Docker with Environment File

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--env-file", "/path/to/your/mcp-atlassian.env",
        "ghcr.io/sooperset/mcp-atlassian:latest"
      ]
    }
  }
}
```

### Server/Data Center Configuration

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "JIRA_URL": "https://jira.your-company.com",
        "JIRA_PERSONAL_TOKEN": "your_pat",
        "JIRA_SSL_VERIFY": "false",
        "CONFLUENCE_URL": "https://confluence.your-company.com",
        "CONFLUENCE_PERSONAL_TOKEN": "your_pat",
        "CONFLUENCE_SSL_VERIFY": "false"
      }
    }
  }
}
```

### OAuth 2.0 Configuration

For standard OAuth flow (after running setup wizard):

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "/path/to/home/.mcp-atlassian:/home/app/.mcp-atlassian",
        "-e", "JIRA_URL",
        "-e", "CONFLUENCE_URL",
        "-e", "ATLASSIAN_OAUTH_CLIENT_ID",
        "-e", "ATLASSIAN_OAUTH_CLIENT_SECRET",
        "-e", "ATLASSIAN_OAUTH_REDIRECT_URI",
        "-e", "ATLASSIAN_OAUTH_SCOPE",
        "-e", "ATLASSIAN_OAUTH_CLOUD_ID",
        "ghcr.io/sooperset/mcp-atlassian:latest"
      ],
      "env": {
        "JIRA_URL": "https://your-company.atlassian.net",
        "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
        "ATLASSIAN_OAUTH_CLIENT_ID": "your_client_id",
        "ATLASSIAN_OAUTH_CLIENT_SECRET": "your_client_secret",
        "ATLASSIAN_OAUTH_REDIRECT_URI": "http://localhost:8080/callback",
        "ATLASSIAN_OAUTH_SCOPE": "read:jira-work write:jira-work read:confluence-content.all write:confluence-content offline_access",
        "ATLASSIAN_OAUTH_CLOUD_ID": "your_cloud_id"
      }
    }
  }
}
```

### Single Service Configuration

**Confluence only:**
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

**Jira only:**
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

## Environment Variables

### Connection Settings

| Variable | Description |
|----------|-------------|
| `JIRA_URL` | Jira instance URL |
| `JIRA_USERNAME` | Jira username (email for Cloud) |
| `JIRA_API_TOKEN` | Jira API token (Cloud) |
| `JIRA_PERSONAL_TOKEN` | Jira Personal Access Token (Server/DC) |
| `JIRA_SSL_VERIFY` | SSL verification (`true`/`false`) |
| `CONFLUENCE_URL` | Confluence instance URL |
| `CONFLUENCE_USERNAME` | Confluence username (email for Cloud) |
| `CONFLUENCE_API_TOKEN` | Confluence API token (Cloud) |
| `CONFLUENCE_PERSONAL_TOKEN` | Confluence Personal Access Token (Server/DC) |
| `CONFLUENCE_SSL_VERIFY` | SSL verification (`true`/`false`) |

### Filtering Options

| Variable | Description | Example |
|----------|-------------|---------|
| `JIRA_PROJECTS_FILTER` | Limit to specific Jira projects | `PROJ,DEV,SUPPORT` |
| `CONFLUENCE_SPACES_FILTER` | Limit to specific Confluence spaces | `DEV,TEAM,DOC` |
| `ENABLED_TOOLS` | Enable only specific tools | `confluence_search,jira_get_issue` |

### Server Options

| Variable | Description |
|----------|-------------|
| `READ_ONLY_MODE` | Disable write operations (`true`/`false`) |
| `MCP_VERBOSE` | Enable verbose logging (`true`/`false`) |
| `MCP_VERY_VERBOSE` | Enable debug logging (`true`/`false`) |
| `MCP_LOGGING_STDOUT` | Log to stdout instead of stderr (`true`/`false`) |

See [.env.example](https://github.com/sooperset/mcp-atlassian/blob/main/.env.example) for all available options.

## Proxy Configuration

MCP Atlassian supports routing API requests through HTTP/HTTPS/SOCKS proxies.

| Variable | Description |
|----------|-------------|
| `HTTP_PROXY` | HTTP proxy URL |
| `HTTPS_PROXY` | HTTPS proxy URL |
| `SOCKS_PROXY` | SOCKS proxy URL |
| `NO_PROXY` | Hosts to bypass proxy |
| `JIRA_HTTPS_PROXY` | Jira-specific HTTPS proxy |
| `CONFLUENCE_HTTPS_PROXY` | Confluence-specific HTTPS proxy |

Service-specific variables override global ones.

**Example:**
```json
{
  "env": {
    "HTTPS_PROXY": "http://proxy.internal:8080",
    "NO_PROXY": "localhost,.your-company.com"
  }
}
```

## Custom HTTP Headers

Add custom HTTP headers to all API requests. Useful in corporate environments requiring additional headers for security or routing.

| Variable | Description |
|----------|-------------|
| `JIRA_CUSTOM_HEADERS` | Custom headers for Jira requests |
| `CONFLUENCE_CUSTOM_HEADERS` | Custom headers for Confluence requests |

**Format:** Comma-separated `key=value` pairs.

**Example:**
```bash
JIRA_CUSTOM_HEADERS=X-Forwarded-User=service-account,X-Custom-Auth=token
CONFLUENCE_CUSTOM_HEADERS=X-Service=mcp-integration,X-ALB-Token=secret
```

**Security notes:**
- Header values are masked in debug logs
- Avoid conflicts with standard HTTP or Atlassian API headers
- Headers are sent with every API request

## Tool Filtering

Control which tools are available:

1. **Enable specific tools:**
   ```bash
   ENABLED_TOOLS="confluence_search,jira_get_issue,jira_search"
   ```

2. **Read-only mode:** Disables all write operations regardless of `ENABLED_TOOLS`:
   ```bash
   READ_ONLY_MODE=true
   ```

Command-line alternative:
```bash
uvx mcp-atlassian --enabled-tools "confluence_search,jira_get_issue"
```
