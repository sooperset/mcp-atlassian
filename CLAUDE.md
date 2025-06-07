# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Guidelines

This document contains critical information about working with this codebase. Follow these guidelines precisely.

## Core Development Rules

1. Package Management
   - ONLY use uv, NEVER pip
   - Installation: `uv add package`
   - Running tools: `uv run tool`
   - Upgrading: `uv add --dev package --upgrade-package package`
   - FORBIDDEN: `uv pip install`, `@latest` syntax

2. Code Quality
   - Type hints required for all code
   - Public APIs must have docstrings
   - Functions must be focused and small
   - Follow existing patterns exactly
   - Line length: 88 chars maximum

3. Testing Requirements
   - Framework: `uv run pytest`
   - Async testing: use anyio, not asyncio
   - Coverage: test edge cases and errors
   - New features require tests
   - Bug fixes require regression tests

- For commits fixing bugs or adding features based on user reports add:
  ```bash
  git commit --trailer "Reported-by:<name>"
  ```
  Where `<name>` is the name of the user.

- For commits related to a Github issue, add
  ```bash
  git commit --trailer "Github-Issue:#<number>"
  ```
- NEVER ever mention a `co-authored-by` or similar aspects. In particular, never
  mention the tool used to create the commit message or PR.

## Pull Requests

- Create a detailed message of what changed. Focus on the high level description of
  the problem it tries to solve, and how it is solved. Don't go into the specifics of the
  code unless it adds clarity.

- NEVER ever mention a `co-authored-by` or similar aspects. In particular, never
  mention the tool used to create the commit message or PR.

## Python Tools

## Code Formatting

1. Pre-commit
   - Run all checks: `pre-commit run --all-files`
   - Handles: Ruff (Python), Prettier (YAML/JSON)
   - Critical issues:
     - Line length (88 chars)
     - Import sorting (I001)
     - Unused imports
   - Line wrapping:
     - Strings: use parentheses
     - Function calls: multi-line with proper indent
     - Imports: split into multiple lines

2. Type Checking
   - Tool: `uv run pyright`
   - Requirements:
     - Explicit None checks for Optional
     - Type narrowing for strings
     - Version warnings can be ignored if checks pass

3. Pre-commit
   - Config: `.pre-commit-config.yaml`
   - Runs: on git commit
   - Tools: Prettier (YAML/JSON), Ruff (Python)
   - Ruff updates:
     - Check PyPI versions
     - Update config rev
     - Commit config first

## Error Resolution

1. CI Failures
   - Fix order:
     1. Formatting
     2. Type errors
     3. Linting
   - Type errors:
     - Get full line context
     - Check Optional types
     - Add type narrowing
     - Verify function signatures

2. Common Issues
   - Line length:
     - Break strings with parentheses
     - Multi-line function calls
     - Split imports
   - Types:
     - Add None checks
     - Narrow string types
     - Match existing patterns

3. Best Practices
   - Check git status before commits
   - Run `pre-commit run --all-files` before commits
   - Keep changes minimal
   - Follow existing patterns
   - Document public APIs
   - Test thoroughly

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

## Essential Development Commands

1. **Setup**
   ```bash
   uv sync --frozen --all-extras --dev  # Install all dependencies
   pre-commit install                    # Setup pre-commit hooks
   ```

2. **Testing**
   ```bash
   uv run pytest                       # Run all tests
   uv run pytest --cov=mcp_atlassian   # Run tests with coverage
   uv run pytest tests/unit/           # Run unit tests only
   ```

3. **Code Quality**
   ```bash
   pre-commit run --all-files           # Run all pre-commit checks
   ```

4. **Running the Server**
   ```bash
   uv run mcp-atlassian                 # Start MCP server
   uv run mcp-atlassian --oauth-setup   # Run OAuth setup wizard
   uv run mcp-atlassian -v              # Verbose logging
   ```

## Architecture Overview

This is a **Model Context Protocol (MCP) server** that enables AI assistants to interact with Atlassian products (Jira and Confluence). Key architectural patterns:

### Directory Structure
- `src/mcp_atlassian/`: Main application code
  - `jira/`: Jira-specific modules (clients, models, operations)
  - `confluence/`: Confluence-specific modules
  - `models/`: Pydantic data models for API responses
  - `preprocessing/`: Data transformation logic
  - `servers/`: FastMCP server implementations
  - `utils/`: Shared utilities (auth, logging, etc.)

### Key Patterns

1. **Mixin Architecture**: Functionality is split into focused mixins (e.g., `IssuesMixin`, `CommentsMixin`) that extend base clients. Follow this pattern when adding new features.

2. **Pydantic Models**: All data structures use Pydantic for validation. Extend `ApiModel` base class (`models/base.py`) for API response handling.

3. **Configuration**: Environment-based configuration using `Config` classes in each service module.

4. **Authentication**: Supports API tokens, PAT tokens, and OAuth 2.0 with automatic credential management.

### MCP Implementation
- Server entry point: `servers/main.py`
- Tool definitions: Each service defines MCP tools following the pattern `{service}_{action}`
- FastMCP framework handles MCP protocol details

### Testing Strategy
- Unit tests mirror source structure (`tests/unit/`)
- Integration tests for real API validation
- Fixtures for consistent mock data
- Async testing with anyio

## Project-Specific Conventions

1. **Environment Variables**: Prefix with service names (`JIRA_URL`, `CONFLUENCE_URL`)
2. **Tool Naming**: `{service}_{action}` pattern (e.g., `jira_create_issue`)
3. **Error Handling**: Use custom exceptions from `exceptions.py`
4. **Logging**: Sensitive data masking, controlled by `-v` flags
5. **Constants**: Import from `models/constants.py` instead of hardcoding
6. **Docstrings**: Google-style format for all public APIs

## Code Style Requirements

- **Line length**: 88 characters maximum
- **Type hints**: Required for all function signatures
- **Imports**: Use absolute imports, sorted by ruff
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes
- **String quotes**: Double quotes (enforced by ruff)
- **Error handling**: Specific exception types, avoid broad `except Exception`

When modifying code, always check existing patterns in similar modules and follow the established conventions.
