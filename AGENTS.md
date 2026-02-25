# MCP Atlassian

> **Audience**: LLM-driven engineering agents

---

## Repository map

| Path | Purpose |
| --- | --- |
| `src/mcp_atlassian/` | Library source (Python ≥ 3.10) |
| `  ├─ jira/` | Jira client + 16 mixins (issues, search, SLA, metrics, …) |
| `  ├─ confluence/` | Confluence client + 7 mixins (pages, search, analytics, …) |
| `  ├─ models/` | Pydantic v2 data models (`ApiModel` base) |
| `  ├─ servers/` | FastMCP server instances (`jira_mcp`, `confluence_mcp`) |
| `  ├─ preprocessing/` | Content conversion (ADF/Storage → Markdown) |
| `  └─ utils/` | Shared utilities (auth, logging, SSL, decorators) |
| `tests/` | Pytest suite — unit, integration, real-API validation |
| `scripts/` | OAuth setup and testing scripts |

---

## Architecture

- **Mixin composition**: `JiraFetcher` composes 16 mixins, `ConfluenceFetcher` composes 7. Client inheritance is transitive through mixins.
- **FastMCP servers**: `servers/main.py` → lifespan → dependency injection via `get_jira_fetcher(ctx)` / `get_confluence_fetcher(ctx)`.
- **Tool naming**: `{service}_{action}_{target}` (e.g., `jira_create_issue`, `confluence_get_page`).
- **Config**: Environment-based `from_env()` factory on `JiraConfig` / `ConfluenceConfig` dataclasses.
- **Auth**: Basic (Cloud + Server/DC), PAT (Server/DC), OAuth 2.0 (Cloud + Server/DC) — with multi-tenant header support.
- **Models**: All extend `ApiModel` → `from_api_response()` + `to_simplified_dict()`.

---

## Dev workflow

```bash
uv sync --frozen --all-extras --dev  # install dependencies
pre-commit install                    # setup hooks
pre-commit run --all-files           # Ruff + mypy
uv run pytest -xvs                   # full test suite
uv run pytest tests/unit/ -xvs       # unit tests only
uv run pytest tests/integration/     # integration tests
uv run pytest --cov=src/mcp_atlassian --cov-report=term-missing  # coverage
```

*Tests must pass* and *lint/typing must be clean* before committing.

---

## Rules

1. **Package management**: ONLY use `uv`, NEVER `pip`
2. **Branching**: NEVER work on `main`, always create feature branches
3. **Type safety**: All functions require type hints
4. **Testing**: New features need tests, bug fixes need regression tests
5. **Commits**: Use trailers for attribution, never mention tools/AI
6. **Commit types**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci` — scopes: `jira`, `confluence`, `server`, `auth`, `docker`, `docs`
7. **File hygiene**: Prefer editing existing files over creating new ones

---

## Code conventions

- **Language**: Python ≥ 3.10
- **Line length**: 88 characters maximum
- **Imports**: Absolute imports, sorted by Ruff
- **Naming**: `snake_case` functions, `PascalCase` classes
- **Docstrings**: Google-style for all public APIs
- **Error handling**: Specific exceptions only

---

## Gotchas

- **Cloud vs Server/DC**: API endpoints, field names, and auth methods differ. Always check `is_cloud` before assuming behavior.
- **OAuth 2.0**: Supported on both Cloud and Server/Data Center. PAT is also available for Server/DC. Basic auth (user + API token) works on both Cloud and Server/DC.
- **Read-only mode**: `READ_ONLY_MODE=true` blocks all write tools at server level.
- **Type checking**: pre-commit runs **mypy** (strict mode).
- **Environment**: See `.env.example` for all configuration options (auth, proxy, SLA, filtering).

---

## Quick reference

```bash
# Running the server
uv run mcp-atlassian                 # Start server
uv run mcp-atlassian --oauth-setup   # OAuth wizard
uv run mcp-atlassian -v              # Verbose mode

# Git workflow
git checkout -b feature/description   # New feature
git checkout -b fix/issue-description # Bug fix
git commit --trailer "Reported-by:<name>"      # Attribution
git commit --trailer "Github-Issue:#<number>"  # Issue reference
```
