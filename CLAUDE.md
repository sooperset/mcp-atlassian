# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Install dependencies using uv (required)
uv sync
uv sync --frozen --all-extras --dev

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate.ps1  # Windows

# Setup pre-commit hooks
pre-commit install

# Copy environment template
cp .env.example .env
```

### Code Quality & Testing
```bash
# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=mcp_atlassian

# Run tests with real API data (requires env vars)
uv run pytest --use-real-data

# Run code quality checks (linting, formatting, type checking)
pre-commit run --all-files

# Individual quality checks
ruff format .          # Format code
ruff check --fix .     # Lint and auto-fix
mypy src/             # Type checking
```

### Running the Server
```bash
# Run with stdio transport (for MCP integration)
uv run mcp-atlassian

# Run with HTTP transport for testing
uv run mcp-atlassian --transport sse --port 9000 -vv
uv run mcp-atlassian --transport streamable-http --port 9000 -vv

# Run OAuth setup wizard
uv run mcp-atlassian --oauth-setup -v

# Run with environment file
uv run mcp-atlassian --env-file .env

# Run with specific tool filtering
uv run mcp-atlassian --enabled-tools "confluence_search,jira_get_issue"

# Run in read-only mode
uv run mcp-atlassian --read-only
```

### Development and Debugging
```bash
# Run with verbose logging
uv run mcp-atlassian -vv

# Test with MCP Inspector
npx @modelcontextprotocol/inspector uv run mcp-atlassian
```

## Architecture Overview

### High-Level Structure
This is a Model Context Protocol (MCP) server that provides AI assistants with access to Atlassian products (Jira and Confluence). The architecture follows a modular design with clear separation between:

- **Server layer**: FastMCP-based HTTP/stdio server with tool mounting and middleware
- **Service layer**: Separate Jira and Confluence modules with their own tools and configurations
- **Client layer**: Abstracted API clients for both Atlassian Cloud and Server/Data Center deployments
- **Model layer**: Pydantic models for type-safe data handling and API responses
- **Preprocessing layer**: Data transformation and formatting for AI consumption

### Key Components

#### Main Server (`src/mcp_atlassian/servers/main.py`)
- `AtlassianMCP`: Custom FastMCP server with tool filtering and authentication middleware
- `UserTokenMiddleware`: Handles OAuth/PAT token extraction from Authorization headers
- Supports stdio, SSE, and streamable-HTTP transports
- Tool filtering based on enabled tools, read-only mode, and service availability

#### Service Modules
- **Jira** (`src/mcp_atlassian/jira/`): Issue management, search, boards, sprints, worklogs
- **Confluence** (`src/mcp_atlassian/confluence/`): Page management, search, comments, labels, version history

#### Authentication Support
- **Cloud**: Username/API token, OAuth 2.0 (standard and BYOT)
- **Server/Data Center**: Personal Access Tokens (PAT)
- **Multi-tenant**: Per-request authentication via HTTP headers

#### Configuration System
- Environment-based configuration with validation
- Service-specific configs (`JiraConfig`, `ConfluenceConfig`) 
- Support for proxy settings and custom HTTP headers

## Code Conventions

### Python Style
- Use ruff for formatting and linting (88-character line limit)
- Type annotations required for all public functions
- Use modern Python syntax: `str | None` instead of `Union[str, None]`
- Pydantic models for data validation and serialization

### Module Organization
```
src/mcp_atlassian/
├── __init__.py              # Main entry point and CLI
├── servers/                 # FastMCP server implementations
├── jira/                    # Jira-specific tools and clients
├── confluence/              # Confluence-specific tools and clients
├── models/                  # Pydantic data models
├── preprocessing/           # Data transformation for AI
├── utils/                   # Shared utilities
└── exceptions.py            # Custom exceptions
```

### Tool Development
- All tools are implemented as FastMCP tools with tags for categorization
- Tools tagged with "write" are filtered out in read-only mode
- Tools require service-specific authentication configuration
- Use preprocessing layer to format data for optimal AI consumption

### Testing
- Comprehensive test suite with pytest and factory patterns
- Mock fixtures for API responses and authentication
- Real API integration tests (use `--use-real-data` flag)
- Environment-based configuration testing

### Environment Variables
Key environment variables for development:
- `MCP_VERBOSE=true`: Enable info-level logging
- `MCP_VERY_VERBOSE=true`: Enable debug-level logging  
- `MCP_LOGGING_STDOUT=true`: Log to stdout instead of stderr
- `READ_ONLY_MODE=true`: Disable write operations
- `ENABLED_TOOLS`: Comma-separated list of enabled tools
- Service-specific auth variables (see `.env.example`)

### Docker Integration
The application is primarily distributed as a Docker image:
- Multi-stage build with Python 3.10+
- uv-based dependency management
- Support for volume mounts for OAuth token persistence
- Environment variable and env-file configuration

## Important Implementation Notes

### Authentication Flow
1. Server loads global auth config during startup
2. UserTokenMiddleware extracts per-request auth headers
3. Service clients use request-specific auth when available, fallback to global
4. OAuth tokens are cached with TTL for performance

### Tool Filtering
Tools are filtered at runtime based on:
1. `ENABLED_TOOLS` environment variable
2. Read-only mode (excludes "write" tagged tools)
3. Service authentication availability
4. Per-request authorization scope

### Error Handling
- Custom exception hierarchy for different error types
- Graceful degradation when services are unavailable
- Detailed logging with sensitive data masking
- Health check endpoint for monitoring

### Performance Considerations
- TTL cache for token validation
- Efficient preprocessing for large API responses
- Support for batch operations where available
- Connection pooling and reuse in HTTP clients

## Development Workflow
1. Create feature branch from main
2. Implement changes following code conventions
3. Add/update tests for new functionality
4. Run quality checks: `pre-commit run --all-files`
5. Test with: `uv run pytest`
6. Update documentation if needed
7. Submit PR against main branch