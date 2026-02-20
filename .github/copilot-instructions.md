# MCP Atlassian - Development Guide

Model Context Protocol (MCP) server for Atlassian products (Jira & Confluence). Python ≥3.10, <3.14.

## Build, Test, and Lint

**Dependencies**:
```bash
uv sync --frozen --all-extras --dev  # Install all dependencies
```

**Code Quality** (required before commit):
```bash
pre-commit run --all-files           # Run all checks: ruff, prettier, mypy
```

**Testing**:
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=mcp_atlassian

# Run single test file
uv run pytest tests/unit/test_preprocessing.py

# Run single test function
uv run pytest tests/unit/test_preprocessing.py::test_specific_function
```

**Running the Server**:
```bash
uv run mcp-atlassian                 # Start MCP server
uv run mcp-atlassian --oauth-setup   # OAuth configuration wizard
uv run mcp-atlassian -v              # Verbose logging mode
```

## Architecture

### Mixin-Based Composition
Functionality is organized into **focused mixins** that compose together:
- **Jira**: `JiraFetcher` inherits from 13 feature mixins (ProjectsMixin, IssuesMixin, WorklogMixin, etc.)
- **Confluence**: `ConfluenceFetcher` inherits from 7 feature mixins (SearchMixin, PagesMixin, SpacesMixin, etc.)

Each mixin lives in its own module under `src/mcp_atlassian/jira/` or `src/mcp_atlassian/confluence/`.

### Client + Fetcher Pattern
- **Client classes** (`JiraClient`, `ConfluenceClient`): Authentication, configuration, and API session management
- **Fetcher classes** (`JiraFetcher`, `ConfluenceFetcher`): Business operations by composing mixins; inherit from Client

### Protocol-Based Dependencies
Mixins declare dependencies via Protocol interfaces instead of direct imports:
```python
class IssuesMixin(AttachmentsOperationsProto, FieldsOperationsProto):
    # Mixin knows it needs attachment and field operations
    # Protocols define the contract without circular imports
```

The final Fetcher class satisfies all protocols through multiple inheritance.

### Data Models
- All models extend `ApiModel` base class with `from_api_response()` for deserialization
- Use `TimestampMixin` for timestamp handling across Jira/Confluence models
- Models support `to_simplified_dict()` for MCP tool responses
- Located in `src/mcp_atlassian/models/`

### MCP Server Layer
Servers (`src/mcp_atlassian/servers/`) use FastMCP framework:
- Instantiate Fetchers via dependency injection (`get_jira_fetcher()`, `get_confluence_fetcher()`)
- Wrap fetcher methods as MCP tools using `@mcp.tool()` decorator
- Handle error conversion and response serialization
- Support read-only and write modes

## Key Conventions

### Package Management
**Always use `uv`, never `pip`**. This is a hard requirement for dependency management.

### Branching Strategy
**Never work on `main`**. Always create feature branches:
```bash
git checkout -b feature/your-feature-name   # For new features
git checkout -b fix/issue-description       # For bug fixes
```

### Tool Naming
MCP tools follow the pattern: `{service}_{action}`
- Examples: `jira_create_issue`, `confluence_get_page`, `jira_search`

### Type Safety
- All functions require type hints
- Use modern union syntax: `str | None` (not `Optional[str]`)
- Use `type[T]` for class types
- Collections: `list[str]`, `dict[str, Any]`

### Code Style
- **Line length**: 88 characters maximum (enforced by ruff)
- **Imports**: Absolute imports, sorted by ruff
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes
- **Docstrings**: Google-style format for all public APIs
- **Error handling**: Use specific exceptions, avoid bare `except:`

### Testing
- New features require tests
- Bug fixes require regression tests
- Test files mirror source structure: `tests/unit/` and `tests/integration/`
- Use fixtures from `tests/fixtures/` for test data

### Commit Messages
Use git trailers for attribution:
```bash
git commit --trailer "Reported-by:<name>"          # For bug reports
git commit --trailer "Github-Issue:#<number>"      # For issue references
```

**Never mention tools or AI assistants in commit messages**.

## Authentication Support
The codebase supports multiple authentication methods:
- **API Tokens**: Cloud deployments (username + token)
- **Personal Access Tokens (PAT)**: Server/Data Center deployments
- **OAuth 2.0**: Interactive user authentication with consent flow

Auth configuration lives in `src/mcp_atlassian/utils/auth.py`.

## Pre-commit Hooks
Pre-commit runs:
- **ruff-format**: Auto-format Python code
- **ruff**: Lint with auto-fix (select rules in pyproject.toml)
- **mypy**: Type checking (currently lenient, see TODO comments in .pre-commit-config.yaml)
- **prettier**: Format YAML/JSON
- **Standard checks**: trailing whitespace, file endings, YAML/TOML validity

Tests are **not** run by pre-commit hooks—run them manually with `uv run pytest`.
