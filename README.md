# MCP Atlassian

![PyPI Version](https://img.shields.io/pypi/v/mcp-atlassian)
![PyPI - Downloads](https://img.shields.io/pypi/dm/mcp-atlassian)
![PePy - Total Downloads](https://static.pepy.tech/personalized-badge/mcp-atlassian?period=total&units=international_system&left_color=grey&right_color=blue&left_text=Total%20Downloads)
[![Run Tests](https://github.com/sooperset/mcp-atlassian/actions/workflows/tests.yml/badge.svg)](https://github.com/sooperset/mcp-atlassian/actions/workflows/tests.yml)
![License](https://img.shields.io/github/license/sooperset/mcp-atlassian)
[![Docs](https://img.shields.io/badge/docs-mintlify-blue)](https://personal-1d37018d.mintlify.app)

Model Context Protocol (MCP) server for Atlassian products (Jira, Confluence, Zephyr Scale, and Zephyr Squad). Supports both Cloud and Server/Data Center deployments.

https://github.com/user-attachments/assets/35303504-14c6-4ae4-913b-7c25ea511c3e

<details>
<summary>Confluence Demo</summary>

https://github.com/user-attachments/assets/7fe9c488-ad0c-4876-9b54-120b666bb785

</details>

## Quick Start

### 1. Get Your API Token

Go to https://id.atlassian.com/manage-profile/security/api-tokens and create a token.

> For Server/Data Center, use a Personal Access Token instead. See [Authentication](https://personal-1d37018d.mintlify.app/docs/authentication).

### 2. Configure Your IDE

Add to your Claude Desktop or Cursor MCP configuration:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your.email@company.com",
        "JIRA_API_TOKEN": "your_api_token",
        "CONFLUENCE_URL": "https://your-company.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@company.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "ZEPHYR_URL": "https://api.zephyrscale.smartbear.com/v2",
        "ZEPHYR_API_TOKEN": "your_zephyr_api_token"
      }
    }
  }
}
```

> **Server/Data Center users**: Use `JIRA_PERSONAL_TOKEN` / `CONFLUENCE_PERSONAL_TOKEN` / `ZEPHYR_PERSONAL_TOKEN` instead of username + token combinations. See [Authentication](https://personal-1d37018d.mintlify.app/docs/authentication) for details.

### 3. Start Using

Ask your AI assistant to:
- **"Find issues assigned to me in PROJ project"**
- **"Search Confluence for onboarding docs"**
- **"Create a bug ticket for the login issue"**
- **"Update the status of PROJ-123 to Done"**
- **"Search for test cases in Zephyr for the login feature"** (Zephyr Scale)
- **"Get Zephyr Squad test cycles for project 10000"** (Zephyr Squad plugin)

> **Note on Zephyr versions:**
> - **Zephyr Scale** is a standalone test management service with its own API (Cloud: `api.zephyrscale.smartbear.com`)
> - **Zephyr Squad** is a Jira plugin accessed through Jira's REST API (`/rest/zapi/latest/`)
> - Tools are prefixed accordingly: `zephyr_*` for Scale, `zephyr_squad_*` for Squad

## Documentation

Full documentation is available at **[personal-1d37018d.mintlify.app](https://personal-1d37018d.mintlify.app)**.

Documentation is also available in [llms.txt format](https://llmstxt.org/), which LLMs can consume easily:
- [`llms.txt`](https://personal-1d37018d.mintlify.app/llms.txt) — documentation sitemap
- [`llms-full.txt`](https://personal-1d37018d.mintlify.app/llms-full.txt) — complete documentation

| Topic | Description |
|-------|-------------|
| [Installation](https://personal-1d37018d.mintlify.app/docs/installation) | uvx, Docker, pip, from source |
| [Authentication](https://personal-1d37018d.mintlify.app/docs/authentication) | API tokens, PAT, OAuth 2.0 |
| [Configuration](https://personal-1d37018d.mintlify.app/docs/configuration) | IDE setup, environment variables |
| [HTTP Transport](https://personal-1d37018d.mintlify.app/docs/http-transport) | SSE, streamable-http, multi-user |
| [Tools Reference](https://personal-1d37018d.mintlify.app/docs/tools-reference) | All Jira & Confluence tools |
| [Troubleshooting](https://personal-1d37018d.mintlify.app/docs/troubleshooting) | Common issues & debugging |

## Compatibility

| Product | Deployment | Support |
|---------|------------|---------|
| Jira | Cloud | Fully supported |
| Jira | Server/Data Center | Supported (v8.14+) |
| Confluence | Cloud | Fully supported |
| Confluence | Server/Data Center | Supported (v6.0+) |
| Zephyr Scale | Cloud | Fully supported |
| Zephyr Scale | Server/Data Center | Supported (v6.0+) |
| Zephyr Squad | Jira Plugin | Fully supported |

## Key Tools

| Jira | Confluence | Zephyr                                                          |
|------|------------|-----------------------------------------------------------------|
| `jira_search` - Search with JQL | `confluence_search` - Search with CQL | **Scale**: `zephyr_search_test_cases` - Search test cases       |
| `jira_get_issue` - Get issue details | `confluence_get_page` - Get page content | **Scale**: `zephyr_create_test_case` - Create test cases        |
| `jira_create_issue` - Create issues | `confluence_create_page` - Create pages | **Scale**: `zephyr_create_test_execution` - Create test executions |
| `jira_update_issue` - Update issues | `confluence_update_page` - Update pages | **Squad**: `zephyr_squad_get_cycles` - Get test cycles          |
| `jira_transition_issue` - Change status | `confluence_add_comment` - Add comments | **Squad**: `zephyr_squad_create_execution` - Create test execution |
| `jira_get_queue_issues` - Read JSM queue items | | |
| `jira_get_issue_sla` - Calculate SLA metrics | `confluence_get_page_history` - Get historical page versions | **Squad**: `zephyr_squad_execute_test` - Execute test           |
| `jira_get_issue_development_info` - Get linked PRs, branches, commits | `confluence_get_page_views` - Get page view stats (Cloud only) | |
| `jira_get_issue_proforma_forms` - Get ProForma forms | | |
| `jira_get_proforma_form_details` - Get form details | | |
| `jira_update_proforma_form_answers` - Update form answers | | |

See [Tools Reference](https://personal-1d37018d.mintlify.app/docs/tools-reference) for the complete list.

## Security

Never share API tokens. Keep `.env` files secure. See [SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

## License

MIT - See [LICENSE](LICENSE). Not an official Atlassian product.
