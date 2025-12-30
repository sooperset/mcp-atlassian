# Troubleshooting

## Common Issues

### Authentication Failures

**Cloud:**
- Ensure you're using API tokens, not your account password
- Verify the token hasn't expired
- Check that `JIRA_USERNAME` / `CONFLUENCE_USERNAME` is your email address

**Server/Data Center:**
- Verify your Personal Access Token is valid and not expired
- For older Confluence servers, try basic auth with `CONFLUENCE_USERNAME` and `CONFLUENCE_API_TOKEN` (where token is your password)

### SSL Certificate Issues

For Server/Data Center with self-signed certificates:

```bash
JIRA_SSL_VERIFY=false
CONFLUENCE_SSL_VERIFY=false
```

### Permission Errors

Ensure your Atlassian account has sufficient permissions to access the spaces/projects you're targeting.

### Python Version Issues

Python 3.14 is not yet supported due to upstream pydantic-core/PyO3 limitations.

**Workaround with uvx:**
```bash
uvx --python=3.12 mcp-atlassian
```

**In IDE configuration:**
```json
{
  "args": ["--python=3.12", "mcp-atlassian"]
}
```

## Debugging

### Enable Verbose Logging

```bash
# Standard verbose
MCP_VERBOSE=true

# Debug level (includes request details)
MCP_VERY_VERBOSE=true

# Log to stdout instead of stderr
MCP_LOGGING_STDOUT=true
```

### View Logs

**macOS:**
```bash
tail -n 20 -f ~/Library/Logs/Claude/mcp*.log
```

**Windows:**
```cmd
type %APPDATA%\Claude\logs\mcp*.log | more
```

### MCP Inspector

Test your configuration interactively:

```bash
# With uvx
npx @modelcontextprotocol/inspector uvx mcp-atlassian

# With local development version
npx @modelcontextprotocol/inspector uv --directory /path/to/mcp-atlassian run mcp-atlassian
```

## Debugging Custom Headers

### Verify Headers Are Applied

1. Enable debug logging:
   ```bash
   MCP_VERY_VERBOSE=true
   MCP_LOGGING_STDOUT=true
   ```

2. Check logs for header confirmation:
   ```
   DEBUG Custom headers applied: {'X-Forwarded-User': '***', 'X-ALB-Token': '***'}
   ```

### Correct Header Format

```bash
# Correct
JIRA_CUSTOM_HEADERS=X-Custom=value1,X-Other=value2

# Incorrect (extra quotes)
JIRA_CUSTOM_HEADERS="X-Custom=value1,X-Other=value2"

# Incorrect (colon instead of equals)
JIRA_CUSTOM_HEADERS=X-Custom: value1,X-Other: value2

# Incorrect (spaces around equals)
JIRA_CUSTOM_HEADERS=X-Custom = value1
```

**Note:** Header values containing sensitive information are automatically masked in logs.

## Getting Help

- Check [GitHub Issues](https://github.com/sooperset/mcp-atlassian/issues) for known problems
- Review [SECURITY.md](../SECURITY.md) for security-related concerns
- Open a new issue with debug logs if the problem persists
