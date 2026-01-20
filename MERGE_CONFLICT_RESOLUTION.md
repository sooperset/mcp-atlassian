# Merge Conflict Resolution Guide

## Overview

PR #683 was merged before your PR #851, introducing header-based authentication. Your PR needs to be rebased and updated to follow the established naming convention.

## Header Naming Convention (Established by PR #683)

All headers use the `X-Atlassian-*` prefix for consistency:

### Authentication Headers (Already Implemented in PR #683)
- `X-Atlassian-Jira-Personal-Token` - Jira PAT authentication
- `X-Atlassian-Confluence-Personal-Token` - Confluence PAT authentication
- `X-Atlassian-Jira-Url` - Override Jira URL
- `X-Atlassian-Confluence-Url` - Override Confluence URL
- `X-Atlassian-Cloud-Id` - Cloud ID for OAuth

### Configuration Headers (Your PR #851 - To Be Added)
- `X-Atlassian-Read-Only-Mode` - Per-request read-only enforcement
- `X-Atlassian-Jira-Projects-Filter` - Per-request Jira project filtering
- `X-Atlassian-Confluence-Spaces-Filter` - Per-request Confluence space filtering
- `X-Atlassian-Enabled-Tools` - Per-request tool restrictions

## What Changed from Your Original Design

**Original (your PR):**
```
X-Jira-Token
X-Confluence-Token
X-Read-Only-Mode
X-Jira-Projects-Filter
X-Confluence-Spaces-Filter
X-Enabled-Tools
```

**Updated (to match PR #683):**
```
X-Atlassian-Jira-Personal-Token (already exists from PR #683)
X-Atlassian-Confluence-Personal-Token (already exists from PR #683)
X-Atlassian-Read-Only-Mode (yours - renamed)
X-Atlassian-Jira-Projects-Filter (yours - renamed)
X-Atlassian-Confluence-Spaces-Filter (yours - renamed)
X-Atlassian-Enabled-Tools (yours - renamed)
```

## Key Points

1. **Dual authentication is already handled** by PR #683 via `X-Atlassian-Jira-Personal-Token` and `X-Atlassian-Confluence-Personal-Token`
2. **Your PR should NOT re-implement authentication** - it's already there
3. **Your PR should focus on configuration overrides** - the read-only mode, filters, and enabled tools
4. **Follow the `X-Atlassian-*` naming pattern** for consistency

## Files with Merge Conflicts

1. `src/mcp_atlassian/servers/main.py`
   - PR #683 added authentication header extraction in `_process_authentication_headers()`
   - Your PR tried to add similar logic - need to merge them properly
   - Your PR should ADD configuration headers AFTER the auth headers

2. `src/mcp_atlassian/servers/dependencies.py`
   - PR #683 added logic to use service-specific tokens
   - Your PR needs to add config override logic that works with this

3. `tests/unit/servers/test_dependencies.py`
   - Test conflicts need resolution

## Resolution Steps

### Step 1: Rebase on Latest Main

```bash
cd /Users/sean4003/_projects/public/mcp-atlassian
git fetch upstream
git rebase upstream/main
```

This will trigger the conflicts again.

### Step 2: Resolve `src/mcp_atlassian/servers/main.py`

In `_process_authentication_headers()`:
- **Keep** all the authentication header extraction from PR #683
- **Add** your configuration header extraction AFTER the auth headers
- Use the new header names with `X-Atlassian-*` prefix

```python
# At the end of _process_authentication_headers(), after the service headers section:

# Extract per-request configuration overrides (Issue #850)
read_only_header = headers.get(b"x-atlassian-read-only-mode")
jira_filter_header = headers.get(b"x-atlassian-jira-projects-filter")
confluence_filter_header = headers.get(b"x-atlassian-confluence-spaces-filter")
enabled_tools_header = headers.get(b"x-atlassian-enabled-tools")

# Store in scope state (convert bytes to strings)
if read_only_header:
    scope["state"]["read_only_mode"] = read_only_header.decode("latin-1")
if jira_filter_header:
    scope["state"]["jira_projects_filter"] = jira_filter_header.decode("latin-1")
if confluence_filter_header:
    scope["state"]["confluence_spaces_filter"] = confluence_filter_header.decode("latin-1")
if enabled_tools_header:
    scope["state"]["enabled_tools"] = enabled_tools_header.decode("latin-1")

logger.debug(
    f"UserTokenMiddleware: Extracted config headers - "
    f"read_only: {bool(read_only_header)}, "
    f"jira_filter: {bool(jira_filter_header)}, "
    f"confluence_filter: {bool(confluence_filter_header)}, "
    f"enabled_tools: {bool(enabled_tools_header)}"
)
```

Also in the `__call__` method, where scope state is initialized:
- **Keep** the auth-related initializations from PR #683
- **Add** your config-related initializations

```python
# Initialize per-request configuration overrides (for multi-user HTTP deployments)
scope_copy["state"]["read_only_mode"] = None
scope_copy["state"]["jira_projects_filter"] = None
scope_copy["state"]["confluence_spaces_filter"] = None
scope_copy["state"]["enabled_tools"] = None
```

### Step 3: Resolve `src/mcp_atlassian/servers/dependencies.py`

This file has changes from PR #683 that handle service-specific tokens. Your changes should work alongside this, not replace it.

- **Keep** all the token handling logic from PR #683
- **Add** your filter override logic where filters are used

### Step 4: Resolve `tests/unit/servers/test_dependencies.py`

Update tests to use the new header names with `X-Atlassian-*` prefix.

### Step 5: Mark Conflicts as Resolved

After manually editing the files:

```bash
git add src/mcp_atlassian/servers/main.py
git add src/mcp_atlassian/servers/dependencies.py
git add tests/unit/servers/test_dependencies.py
git rebase --continue
```

### Step 6: Update Your PR Description

Make sure your PR description mentions:
- Builds on PR #683's authentication headers
- Follows the `X-Atlassian-*` naming convention
- Focuses on configuration overrides, not authentication

## Testing After Resolution

```bash
# Run tests
uv run pytest

# Run linting
pre-commit run --all-files

# Push updated branch
git push -f origin feature/per-request-config-headers
```

## Communication with Maintainer

When you push the resolved changes, add a comment to the PR:

```
Rebased on latest main and resolved conflicts with PR #683.

Changes made:
- Updated all header names to follow the X-Atlassian-* convention from PR #683
- Authentication is now handled by PR #683's headers (X-Atlassian-Jira-Personal-Token, etc.)
- This PR focuses on configuration overrides only:
  - X-Atlassian-Read-Only-Mode
  - X-Atlassian-Jira-Projects-Filter
  - X-Atlassian-Confluence-Spaces-Filter
  - X-Atlassian-Enabled-Tools

These work alongside the authentication headers and provide per-request configuration
overrides while maintaining backward compatibility with env vars.

Ready for review!
```
