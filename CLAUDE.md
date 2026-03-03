# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core Development Commands

### Environment Setup
```bash
# Install dependencies
uv sync
uv sync --frozen --all-extras --dev

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate.ps1  # Windows

# Install pre-commit hooks
pre-commit install

# Setup environment variables
cp .env.example .env
```

### Testing Commands
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=mcp_atlassian

# Run integration tests only
uv run pytest tests/integration/ --integration

# Run specific test file
uv run pytest tests/unit/servers/test_jira_server.py -v

# Run tests with real API (requires setup)
uv run pytest tests/integration/test_real_api.py --integration --use-real-data
```

### Code Quality
```bash
# Run all pre-commit checks
pre-commit run --all-files

# Run formatting and linting
ruff check src/ tests/
ruff format src/ tests/

# Type checking
mypy src/
```

### Build and Package
```bash
# Build package
uv build

# Run the MCP server locally
python -m mcp_atlassian
```

## Architecture Overview

MCP Atlassian is a Model Context Protocol (MCP) server that provides AI assistants with tools to interact with Atlassian Jira and Confluence. The architecture follows a layered approach:

### Core Structure

**`src/mcp_atlassian/servers/`** - FastMCP server implementations
- `main.py` - Main server application with lifespan management and health checks
- `jira.py` - Jira tool definitions and MCP endpoints
- `confluence.py` - Confluence tool definitions and MCP endpoints
- `context.py` - Shared application context
- `dependencies.py` - Dependency injection for clients

**`src/mcp_atlassian/{jira,confluence}/`** - Service-specific modules
- `client.py` - Base API client with authentication handling
- `config.py` - Configuration management from environment variables
- Individual modules for domain operations (`issues.py`, `pages.py`, `search.py`, etc.)

**`src/mcp_atlassian/models/`** - Pydantic data models
- `base.py` - Base model classes with common functionality
- `{jira,confluence}/` - Service-specific models matching API responses

**`src/mcp_atlassian/utils/`** - Shared utilities
- `oauth.py` - OAuth 2.0 authentication flow
- `ssl.py` - SSL verification configuration
- `environment.py` - Service availability detection
- `decorators.py` - Common decorators like `@check_write_access`

### Authentication Architecture

The system supports three authentication methods with automatic detection:

1. **OAuth 2.0** - Preferred for Cloud instances, with token refresh handling
2. **API Tokens** - For Cloud instances, passed via Basic Auth
3. **Personal Access Tokens** - For Server/Data Center instances

Authentication is configured per-service (Jira/Confluence can use different methods) and handled at the client level with session management.

### Tool Registration Pattern

Tools are registered using FastMCP decorators:
```python
@jira_mcp.tool(tags={"jira", "write"})
@check_write_access
async def create_issue(ctx: Context, project_key: str, ...) -> str:
    jira = await get_jira_fetcher(ctx)
    # Implementation
```

The `@check_write_access` decorator enforces read-only mode when configured.

### Custom Fields Architecture

Custom fields handling is a critical component, particularly for `additional_fields` parameters:

- **JSON String Parsing**: Supports both dict and JSON string formats to handle XML-to-JSON conversion from AI clients
- **Field Format Analysis**: Basic pattern matching for common field types (boolean, select, user fields)
- **Error Handling**: Structured JSON responses with field-specific diagnostics and suggestions
- **Fallback Logic**: Individual field updates when batch operations fail

## Key Development Patterns

### Error Handling Strategy
- Use structured JSON error responses instead of exceptions for MCP tools
- Include field-specific analysis and troubleshooting suggestions
- Implement fallback mechanisms for batch operations
- Preserve detailed JIRA/Confluence API error information

### Environment Configuration
- Configuration classes (`JiraConfig`, `ConfluenceConfig`) load from environment variables
- Support for multiple authentication types with automatic detection
- SSL verification and proxy configuration per service
- Read-only mode enforcement via `MCP_READ_ONLY_MODE`

### Testing Architecture
The test suite uses a sophisticated fixture system:

- **Session-scoped fixtures** for expensive operations (field definitions, projects)
- **Factory-based fixtures** for customizable test data (`make_jira_issue`, `make_confluence_page`)
- **Environment fixtures** for testing different auth scenarios
- **Integration tests** with real API support using `--use-real-data` flag

### Content Processing
- HTML ↔ Markdown conversion for rich content
- Confluence-specific macro handling
- Content preprocessing for search and display

## Important Implementation Notes

### Custom Field Handling
When working with `additional_fields` in Jira operations, the code must handle:
- Dict objects (native Python)
- JSON strings (from XML-to-JSON converters in AI tools)
- Validation errors with specific field format suggestions
- Individual field fallback when batch updates fail

### Authentication Flow
OAuth 2.0 setup requires an interactive wizard:
```bash
docker run --rm -i -p 8080:8080 -v "${HOME}/.mcp-atlassian:/home/app/.mcp-atlassian" \
  ghcr.io/sooperset/mcp-atlassian:latest --oauth-setup -v
```

### Service Detection
The system automatically detects available services (Jira/Confluence) based on environment variables and loads only the necessary components.

### Docker Usage
The application is primarily distributed as a Docker container with support for:
- SSE transport for web interfaces
- stdio transport for Claude Desktop
- Environment variable configuration
- Volume mounting for persistent OAuth tokens

## Code Style Requirements

- Python 3.10+ with modern type annotations (`str | None`, not `Optional[str]`)
- 88 character line limit (Ruff formatting)
- Google-style docstrings for all public functions
- Comprehensive type hints using `Annotated` for FastMCP tools
- Pre-commit hooks enforce formatting, linting, and type checking
