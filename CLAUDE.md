# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Environment Setup

This project uses **UV** as the package manager. All commands should be run with UV.

### Package Management
```bash
# Install dependencies
uv sync --all-extras --dev

# Run any command with uv
uv run <command>
```

### Testing
```bash
# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src/mcp_atlassian --cov-report=term-missing

# Run specific test file
uv run pytest tests/unit/jira/test_client.py

# Run tests matching a pattern
uv run pytest -k "test_jira_search"

# Skip real API validation tests (requires credentials)
uv run pytest -k "not test_real_api_validation"
```

### Code Quality
```bash
# Run all linting and formatting
uv run pre-commit run --all-files

# Run individual tools
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

## Architecture Overview

This is a **Model Context Protocol (MCP)** server for Atlassian products with the following structure:

### Core Components

1. **Entry Point**: `src/mcp_atlassian/__init__.py` - Main CLI with comprehensive options for transports (stdio, sse, streamable-http) and authentication methods

2. **Servers** (`src/mcp_atlassian/servers/`):
   - `main.py` - MCP server setup and dependency injection
   - `jira.py` - Jira MCP server implementation
   - `confluence.py` - Confluence MCP server implementation
   - `dependencies.py` - FastAPI dependency management
   - `context.py` - Server context management

3. **Clients** (`src/mcp_atlassian/jira/` & `src/mcp_atlassian/confluence/`):
   - Modular client implementations for each service
   - Handle authentication, API calls, and error handling
   - Support multiple auth methods: API tokens, PATs, OAuth 2.0

4. **Models** (`src/mcp_atlassian/models/`):
   - Pydantic models for data validation
   - Separate modules for Jira and Confluence entities
   - Base models with common functionality

5. **Utils** (`src/mcp_atlassian/utils/`):
   - `logging.py` - Configurable logging setup
   - `oauth.py` - OAuth 2.0 utilities and setup wizard
   - `ssl.py` - SSL verification configuration
   - `lifecycle.py` - Graceful shutdown handling
   - `env.py` - Environment variable management

### Authentication Support

The project supports three authentication methods:
- **API Token** (Cloud recommended)
- **Personal Access Token** (Server/Data Center)
- **OAuth 2.0** (Cloud only, with setup wizard)

### Transport Options

- **stdio** - Default, for IDE integration
- **sse** - Server-Sent Events HTTP transport
- **streamable-http** - HTTP transport with multi-user support

## Key Development Patterns

### Code Style
- **Line length**: 88 characters
- **Formatter**: Ruff (replaces black, isort, flake8)
- **Type hints**: Required with MyPy validation
- **Imports**: Use absolute imports from `src.mcp_atlassian`

### Testing Patterns
- Tests use `pytest` with `pytest-asyncio` for async support
- Mock Atlassian APIs in `tests/fixtures/`
- Integration tests separate from unit tests
- Coverage reporting with `pytest-cov`

### Error Handling
- Custom exceptions in `src/mcp_atlassian/exceptions.py`
- Graceful degradation for partial service configurations
- Comprehensive logging with configurable levels

### Configuration
- Environment variables with CLI fallbacks
- `.env` file support for development
- Service-specific configurations (JIRA_*, CONFLUENCE_*)
- Tool filtering via `ENABLED_TOOLS` environment variable

## Common Development Tasks

### Adding New Tools
1. Add tool function in appropriate server (`jira.py` or `confluence.py`)
2. Add corresponding client method in service client
3. Create/update Pydantic models in `models/`
4. Write tests in `tests/unit/`
5. Update documentation in README.md

### Authentication Testing
```bash
# Test OAuth setup wizard
uv run mcp-atlassian --oauth-setup -v

# Test with local .env file
uv run mcp-atlassian --transport stdio -vv
```

### Multi-user Development
For HTTP transport development, use:
```bash
# Start HTTP server for testing
uv run mcp-atlassian --transport streamable-http --port 9000 -vv

# Test with different auth methods
curl -H "Authorization: Bearer <token>" http://localhost:9000/mcp
```

## Project Configuration Notes

### Dependencies
- **Core**: `mcp>=1.8.0`, `fastmcp>=2.3.4`, `atlassian-python-api>=4.0.0`
- **HTTP**: `httpx>=0.28.0`, `uvicorn>=0.27.1`
- **Data**: `pydantic>=2.10.6`, `markdown-to-confluence>=0.3.0`

### Pre-commit Hooks
- Trailing whitespace cleanup
- YAML/TOML validation
- Ruff formatting and linting
- MyPy type checking (with some disabled error codes for existing issues)

### CI/CD
- Tests run on Python 3.10, 3.11, 3.12
- Coverage reporting required
- Pre-commit hooks enforced on PRs

### Known Type Issues
The codebase has some existing MyPy issues that are being tracked:
- Union-attr errors in server.py
- Index errors in test fixtures
- Assignment type errors in jira.py
- Unreachable statements in preprocessing.py and jira.py

These are temporarily disabled in pre-commit but should be fixed in future PRs.