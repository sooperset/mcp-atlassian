# Pull Request Guide for Issue #850

**Issue:** https://github.com/sooperset/mcp-atlassian/issues/850
**Feature:** Per-Request Configuration Headers for Multi-User HTTP Deployments

---

## Step 1: Fork & Clone

```bash
# Fork via GitHub UI first, then:
git clone https://github.com/YOUR-USERNAME/mcp-atlassian.git
cd mcp-atlassian
git remote add upstream https://github.com/sooperset/mcp-atlassian.git
```

## Step 2: Setup Development Environment

```bash
# Requires Python 3.10+ and uv (https://docs.astral.sh/uv/getting-started/installation/)
uv sync
uv sync --frozen --all-extras --dev
source .venv/bin/activate  # macOS/Linux
pre-commit install
cp .env.example .env
# Edit .env with your Jira/Confluence credentials for testing
```

## Step 3: Create Feature Branch

```bash
git checkout -b feature/per-request-config-headers
```

## Step 4: Implementation Tasks

### 4.1 Modify `src/mcp_atlassian/servers/main.py`

**File:** `UserTokenMiddleware` class

**Changes:**
- Extend `_process_authentication_headers()` to extract configuration headers
- NOTE: PR #683 already added authentication headers (`X-Atlassian-Jira-Personal-Token`, etc.)
- Extract config headers following the same `X-Atlassian-*` naming convention

```python
# Add these extractions after existing service header handling:
# NOTE: Authentication headers (X-Atlassian-Jira-Personal-Token, X-Atlassian-Confluence-Personal-Token)
# are already handled by PR #683. We're adding configuration override headers:

read_only_header = headers.get(b"x-atlassian-read-only-mode")
jira_filter_header = headers.get(b"x-atlassian-jira-projects-filter")
confluence_filter_header = headers.get(b"x-atlassian-confluence-spaces-filter")
enabled_tools_header = headers.get(b"x-atlassian-enabled-tools")

# Convert to strings and store in scope state
if read_only_header:
    scope["state"]["read_only_mode"] = read_only_header.decode("latin-1")
if jira_filter_header:
    scope["state"]["jira_projects_filter"] = jira_filter_header.decode("latin-1")
if confluence_filter_header:
    scope["state"]["confluence_spaces_filter"] = confluence_filter_header.decode("latin-1")
if enabled_tools_header:
    scope["state"]["enabled_tools"] = enabled_tools_header.decode("latin-1")
```

### 4.2 Modify `src/mcp_atlassian/utils/io.py`

**Function:** `is_read_only_mode()`

**Change:** Accept optional request context parameter, check header first

```python
def is_read_only_mode(request_context: dict | None = None) -> bool:
    """Check if read-only mode is enabled.

    Args:
        request_context: Optional request state dict from middleware

    Returns:
        True if read-only mode is enabled
    """
    # Check request-level override first
    if request_context:
        header_value = request_context.get("read_only_mode")
        if header_value is not None:
            return header_value.lower() == "true"
    # Fall back to environment variable
    return os.environ.get("READ_ONLY_MODE", "false").lower() == "true"
```

### 4.3 Modify `src/mcp_atlassian/utils/decorators.py`

**Decorator:** `check_write_access`

**Change:** Pass request context to `is_read_only_mode()`

### 4.4 Update Filter Consumers

Find where `JIRA_PROJECTS_FILTER` and `CONFLUENCE_SPACES_FILTER` are read from env vars and modify to check request state first.

### 4.5 Update Enabled Tools Logic

Find where `ENABLED_TOOLS` filtering happens and modify to check request state first.

### 4.6 (Optional) Add `ALLOW_HEADER_OVERRIDES` env var

Allow admins to disable per-request config entirely:

```python
def _should_allow_header_overrides() -> bool:
    return os.environ.get("ALLOW_HEADER_OVERRIDES", "true").lower() == "true"
```

---

## Step 5: Add Tests

Create test file: `tests/servers/test_per_request_config.py`

Test cases:
- [ ] Authentication headers from PR #683 work (`X-Atlassian-Jira-Personal-Token`, etc.)
- [ ] `X-Atlassian-Read-Only-Mode: true` blocks write operations
- [ ] `X-Atlassian-Read-Only-Mode: false` allows writes (when env allows)
- [ ] `X-Atlassian-Jira-Projects-Filter` overrides env var
- [ ] `X-Atlassian-Confluence-Spaces-Filter` overrides env var
- [ ] `X-Atlassian-Enabled-Tools` overrides env var
- [ ] Missing headers fall back to env vars
- [ ] `ALLOW_HEADER_OVERRIDES=false` ignores all config headers

---

## Step 6: Run Tests & Checks

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=mcp_atlassian

# Run code quality checks
pre-commit run --all-files
```

---

## Step 7: Commit & Push

```bash
git add .
git commit -m "feat: Add per-request configuration headers for multi-user deployments

Implements #850 - Extends HTTP transport to support per-request config via headers:
- X-Jira-Token / X-Confluence-Token for dual authentication
- X-Read-Only-Mode for per-user read-only enforcement
- X-Jira-Projects-Filter / X-Confluence-Spaces-Filter for per-user filtering
- X-Enabled-Tools for per-user tool restrictions

Headers take precedence over env vars, with env vars as fallbacks.
Fully backward compatible - existing deployments work unchanged."

git push origin feature/per-request-config-headers
```

---

## Step 8: Create Pull Request

1. Go to https://github.com/sooperset/mcp-atlassian/compare
2. Select your fork and branch
3. Fill out PR template:

**Title:** `feat: Add per-request configuration headers for multi-user HTTP deployments`

**Description:**
```markdown
## Summary
Implements #850 - Enables true multi-user HTTP deployments by supporting per-request configuration via headers.

## Changes
- Extended `UserTokenMiddleware` to extract configuration headers (following `X-Atlassian-*` convention from PR #683)
- Added per-request config headers:
  - `X-Atlassian-Read-Only-Mode` - Per-user read-only enforcement
  - `X-Atlassian-Jira-Projects-Filter` - Per-user Jira project filtering
  - `X-Atlassian-Confluence-Spaces-Filter` - Per-user Confluence space filtering
  - `X-Atlassian-Enabled-Tools` - Per-user tool restrictions
- Modified config consumers to check request state before env vars
- Added `ALLOW_HEADER_OVERRIDES` env var for admin control
- Works alongside PR #683's authentication headers (`X-Atlassian-Jira-Personal-Token`, `X-Atlassian-Confluence-Personal-Token`)

## Backward Compatibility
- All new headers are optional
- Existing env-based configuration works unchanged
- No breaking changes

## Testing
- Added unit tests for header extraction
- Added integration tests for config precedence
- Tested with VS Code MCP client

Closes #850

---

## Header Naming Convention

This PR follows the `X-Atlassian-*` naming convention established by PR #683:

**Authentication (from PR #683):**
- `X-Atlassian-Jira-Personal-Token`
- `X-Atlassian-Confluence-Personal-Token`
- `X-Atlassian-Jira-Url`
- `X-Atlassian-Confluence-Url`
- `X-Atlassian-Cloud-Id`

**Configuration (this PR):**
- `X-Atlassian-Read-Only-Mode`
- `X-Atlassian-Jira-Projects-Filter`
- `X-Atlassian-Confluence-Spaces-Filter`
- `X-Atlassian-Enabled-Tools`
```

4. Submit and request review

---

## Key Files Reference

| File | What to Change |
|------|----------------|
| `src/mcp_atlassian/servers/main.py` | `UserTokenMiddleware._process_authentication_headers()` |
| `src/mcp_atlassian/utils/io.py` | `is_read_only_mode()` |
| `src/mcp_atlassian/utils/decorators.py` | `check_write_access` decorator |
| `src/mcp_atlassian/config.py` | Filter/enabled tools config readers |
| `tests/servers/test_per_request_config.py` | New test file |

---

## Tips

- Run `git fetch upstream && git rebase upstream/main` before submitting to ensure your branch is up-to-date
- Use `pre-commit run --all-files` frequently to catch issues early
- Reference issue numbers in commits: `Implements #850`, `Closes #850`
- The maintainer (sooperset) is active - expect feedback within a few days

## After Step 9: After merge

# 1. Sync your fork's main with upstream
```
git checkout main
git fetch upstream
git merge upstream/main
git push origin main
```

# 2. Delete the feature branch (optional cleanup)
`git branch -d feature/per-request-config-headers`
`git push origin --delete feature/per-request-config-headers`
