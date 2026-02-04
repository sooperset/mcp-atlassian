# MCP-Atlassian Server

FastMCP server providing multi-instance Jira and Confluence integration.

## Tech Stack

- **Language**: Python 3.12+
- **Framework**: FastMCP (Model Context Protocol)
- **Dependencies**:
  - atlassian-python-api (Jira/Confluence client)
  - mcp (Model Context Protocol)
  - pydantic (configuration)
  - pytest (testing)

## Architecture

### Multi-Instance Support

This server supports multiple Jira and Confluence instances simultaneously:

**Configuration Pattern:**
- Primary instance: `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN`
- Secondary instances: `JIRA_2_URL`, `JIRA_2_USERNAME`, `JIRA_2_API_TOKEN`, `JIRA_2_INSTANCE_NAME`
- Additional instances: `JIRA_3_*`, `JIRA_4_*`, etc.

**Tool Registration:**
- Primary instance tools: `jira_get_issue`, `jira_search`, etc.
- Secondary instance tools: `jira_{instance_name}_get_issue`, `jira_{instance_name}_search`, etc.

### Directory Structure

```
src/mcp_atlassian/
├── jira/
│   ├── config.py          # Multi-instance configuration
│   ├── fetcher.py         # Jira API client wrapper
│   └── mcp.py             # Primary instance tools
├── confluence/
│   ├── config.py          # Multi-instance configuration
│   ├── fetcher.py         # Confluence API client wrapper
│   └── mcp.py             # Primary instance tools
├── servers/
│   ├── main.py            # Server initialization & lifespan
│   ├── tool_factory.py    # Dynamic tool registration
│   └── tool_router.py     # Smart routing tools (auto-detect instance)
└── utils/
    └── dependencies.py    # Dependency injection providers
```

## Jira Instances

### Primary Instance: Justworks Main
- **URL**: https://justworks.atlassian.net
- **Tools**: `jira_get_issue`, `jira_search`, `jira_create_issue`, etc.
- **Use for**: Main Justworks Jira, customer-facing projects
- **Common Projects**: [Add your main project keys here]

### Tech Instance: Justworks Tech
- **URL**: https://justworks-tech.atlassian.net
- **Instance Name**: `tech`
- **Tools**: `jira_tech_get_issue`, `jira_tech_search`, `jira_tech_create_issue`, etc.
- **Use for**: Infrastructure, operations, internal tech projects
- **Common Projects**: INFRAOPS, [Add other tech project keys]

## Tool Selection Rules

When working with Jira issues, the LLM should automatically select the correct instance:

### Automatic Routing (Recommended)
Use the smart router tools that auto-detect the instance:
- `get_jira_issue_auto` - Works with any Jira URL or issue key
- `search_jira_auto` - Searches across all instances or specific instance by URL
- `create_jira_issue_auto` - Creates issues with automatic instance detection

### Manual Tool Selection
If you need explicit control:

1. **By URL pattern**:
   - `https://justworks.atlassian.net/*` → use `jira_*` tools
   - `https://justworks-tech.atlassian.net/*` → use `jira_tech_*` tools

2. **By issue key prefix** (if known):
   - `INFRAOPS-*` → use `jira_tech_*` tools
   - Other keys → check URL or use auto-routing

3. **By explicit user request**:
   - "From the tech instance..." → use `jira_tech_*` tools
   - "In the main Jira..." → use `jira_*` tools

## Confluence Instances

### Primary Instance: Justworks Wiki
- **URL**: https://justworks.atlassian.net/wiki
- **Tools**: `confluence_search`, `confluence_get_page`, `confluence_create_page`, etc.
- **Use for**: Main Justworks Confluence space

## Development Workflow

### Running Tests
```bash
pytest tests/
```

### Running the Server Locally
```bash
# With environment variables
export JIRA_URL="https://justworks.atlassian.net"
export JIRA_USERNAME="your-email@justworks.com"
export JIRA_API_TOKEN="your-token"
export JIRA_2_URL="https://justworks-tech.atlassian.net"
export JIRA_2_USERNAME="your-email@justworks.com"
export JIRA_2_API_TOKEN="your-token"
export JIRA_2_INSTANCE_NAME="tech"

uv run mcp-atlassian
```

### Testing Multi-Instance Setup
```bash
# Verify which instances will be loaded
uv run python verify_tools.py

# Test server startup and tool registration
/tmp/test_startup.sh

# Test programmatic tool registration
uv run python /tmp/test_user_config.py
```

### Debugging
```bash
# Enable verbose logging (use in tests only, not in Cursor MCP config)
export MCP_VERBOSE="true"

# Run diagnostic script
/tmp/diagnose_cursor.sh
```

## Coding Conventions

### Testing
- Use TDD: Write tests first, then implementation
- Test file naming: `test_{module_name}.py`
- Use pytest fixtures for common setup
- Mock external API calls in unit tests

### Configuration
- Use Pydantic models for configuration
- Support environment variables with prefixes
- Validate configuration at load time
- Provide clear error messages for missing config

### Tool Development
- Use type hints for all function parameters
- Provide comprehensive docstrings
- Include examples in docstrings
- Tag tools appropriately (e.g., "jira", "read", "write")
- Mark read-only tools with `readOnlyHint: True`

### Error Handling
- Return structured error messages
- Include actionable guidance in errors
- Log errors appropriately
- Don't expose sensitive data in error messages

## Common Commands

### Install Dependencies
```bash
uv sync
```

### Run Tests
```bash
uv run pytest
```

### Run Single Test
```bash
uv run pytest tests/test_jira_config.py::test_from_env_multi
```

### Format Code
```bash
uv run ruff format src/ tests/
```

### Lint Code
```bash
uv run ruff check src/ tests/
```

### Type Check
```bash
uv run mypy src/
```

## Configuration Files

### For Local Development
Create `.env` file (not committed):
```bash
JIRA_URL=https://justworks.atlassian.net
JIRA_USERNAME=your-email@justworks.com
JIRA_API_TOKEN=your-token
JIRA_2_URL=https://justworks-tech.atlassian.net
JIRA_2_USERNAME=your-email@justworks.com
JIRA_2_API_TOKEN=your-token
JIRA_2_INSTANCE_NAME=tech
CONFLUENCE_URL=https://justworks.atlassian.net/wiki
CONFLUENCE_USERNAME=your-email@justworks.com
CONFLUENCE_API_TOKEN=your-token
```

### For Cursor/Claude Integration
Edit `~/.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "atlassian": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp-atlassian", "run", "mcp-atlassian"],
      "env": {
        "JIRA_URL": "https://justworks.atlassian.net",
        "JIRA_USERNAME": "your-email@justworks.com",
        "JIRA_API_TOKEN": "your-token",
        "JIRA_2_URL": "https://justworks-tech.atlassian.net",
        "JIRA_2_USERNAME": "your-email@justworks.com",
        "JIRA_2_API_TOKEN": "your-token",
        "JIRA_2_INSTANCE_NAME": "tech",
        "CONFLUENCE_URL": "https://justworks.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your-email@justworks.com",
        "CONFLUENCE_API_TOKEN": "your-token"
      }
    }
  }
}
```

**Important**: Do NOT add `MCP_LOGGING_STDOUT` to Cursor config - it breaks the JSON-RPC protocol.

## Troubleshooting

### Tools Not Appearing in Cursor
1. Verify config: `/tmp/diagnose_cursor.sh`
2. Check branch: Should be on feature branch for multi-instance
3. Restart Cursor completely: `killall Cursor && sleep 3 && open -a Cursor`
4. Check Developer Tools console for errors

### Wrong Jira Instance
- Use smart router tools (`get_jira_issue_auto`) for automatic routing
- Or be explicit: "Use jira_tech_get_issue for INFRAOPS-15157"
- Check URL pattern matches the instance

### Permission Errors
- Verify API tokens are correct for each instance
- Check user has access to the project/issue in that Jira instance
- Some operations require specific Jira permissions

## Project-Specific Notes

This is the multi-instance connection feature implementation. Key features:
- Load multiple Jira/Confluence instances from numbered environment variables
- Register instance-specific tools with prefixed names
- Maintain backward compatibility (primary instance uses unprefixed names)
- Smart routing tools for automatic instance detection

See `context/plans/2026-02-04-multi-instance-connection.md` for implementation details.
