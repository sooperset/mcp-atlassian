# HTEC MCP Atlassian

HTEC Group's internal MCP server for Atlassian products (Confluence and Jira). Supports both Cloud and Server/Data Center deployments.

> **Fork of [sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian)** — maintained by HTEC Platform Engineering with enterprise configuration and internal distribution.

## Installation

### Option A: Install from GitHub (recommended)

```bash
# Using uvx (one-shot execution, no install needed)
uvx --from git+https://github.com/htecgroup/mcp-atlassian.git mcp-atlassian

# Or install persistently
uv pip install git+https://github.com/htecgroup/mcp-atlassian.git
```

### Option B: Install from GitHub Releases

```bash
# Download the wheel from the latest release
uv pip install htec_mcp_atlassian-1.0.0-py3-none-any.whl
```

### Option C: Docker

```bash
docker pull ghcr.io/htecgroup/mcp-atlassian:latest
docker run -e JIRA_URL=... -e JIRA_API_TOKEN=... ghcr.io/htecgroup/mcp-atlassian:latest
```

## Configure Your IDE

Add to your Claude Desktop, Cursor, or Kiro MCP configuration:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/htecgroup/mcp-atlassian.git", "mcp-atlassian"],
      "env": {
        "JIRA_URL": "https://htecgroup.atlassian.net",
        "JIRA_USERNAME": "your.email@htecgroup.com",
        "JIRA_API_TOKEN": "your_api_token",
        "CONFLUENCE_URL": "https://htecgroup.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@htecgroup.com",
        "CONFLUENCE_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

> **Get your API token:** https://id.atlassian.com/manage-profile/security/api-tokens

## Key Tools

| Jira | Confluence |
|------|------------|
| `jira_search` — Search with JQL | `confluence_search` — Search with CQL |
| `jira_get_issue` — Get issue details | `confluence_get_page` — Get page content |
| `jira_create_issue` — Create issues | `confluence_create_page` — Create pages |
| `jira_update_issue` — Update issues | `confluence_update_page` — Update pages |
| `jira_transition_issue` — Change status | `confluence_add_comment` — Add comments |

**93+ tools total** — See [upstream docs](https://mcp-atlassian.soomiles.com/docs/tools-reference) for the complete list.

## Compatibility

| Product | Deployment | Support |
|---------|------------|---------|
| Confluence | Cloud | Fully supported |
| Confluence | Server/Data Center | Supported (v6.0+) |
| Jira | Cloud | Fully supported |
| Jira | Server/Data Center | Supported (v8.14+) |

## Versioning

This package uses its own version scheme independent of upstream:

| HTEC Version | Based on Upstream | Notes |
|--------------|-------------------|-------|
| `1.0.0` | `v0.22.0+44` | Initial HTEC release |

- **HTEC tags:** `htec-v1.0.0`, `htec-v1.1.0`, etc.
- **Upstream sync:** Periodic merges from `sooperset/mcp-atlassian` main branch
- **Version bumps:** Minor for upstream syncs, patch for HTEC-specific fixes

## Development

```bash
# Clone and set up
git clone git@github.com:htecgroup/mcp-atlassian.git
cd mcp-atlassian
uv sync --frozen --all-extras --dev

# Run tests
uv run pytest -xvs

# Lint
pre-commit run --all-files
```

### Upstream Sync

```bash
git remote add upstream https://github.com/sooperset/mcp-atlassian.git
git fetch upstream main
git merge upstream/main  # resolve conflicts if any
```

## Security

Never share API tokens. Keep `.env` files secure. See [SECURITY.md](SECURITY.md).

## License

MIT — See [LICENSE](LICENSE). Originally created by [sooperset](https://github.com/sooperset/mcp-atlassian).
