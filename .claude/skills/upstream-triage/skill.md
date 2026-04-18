---
name: upstream-triage
description: Use when triaging upstream sooperset/mcp-atlassian issues. Provides the workflow for writing tests and creating branches for all open issues (bugs and features).
---

# Upstream Issue Triage

## Quick Start

1. Read the tracking log: `docs/upstream-triage-log.md`
2. Find the next issues without a `Fix Branch` entry (oldest first)
3. Process in batches — dispatch parallel background agents for independent branches
4. Follow the per-issue workflow below
5. Update the tracking log and commit to `eruditis/main`

## Scope

**In scope (write a test for everything testable):**
- Bugs and feature requests, any service (Confluence, Jira, JSM)
- Cloud and Server/DC (unit tests work for both; E2E tests target Cloud)

**OUT_OF_SCOPE (no test possible — log only):**
- Pure infrastructure: Docker config, SIGTERM handling, HTTP transport, port mapping
- Third-party plugins: Xray, Zephyr, ProForma (separate product licenses)
- Documentation requests, README changes, GitHub metadata
- Client-side compatibility (ChatGPT, GPT Agent client support)
- Complex auth infrastructure: OAuth flows, token forwarding, multi-tenant server

## Red/Green TDD

Every issue gets a test. The test result determines status:
- Test **passes** (GREEN) → RESOLVED — feature works, submit upstream PR immediately
- Test **fails** (RED) → CONFIRMED — feature missing or bug present, branch sits until fixed

CONFIRMED branch tests must genuinely fail, not just skip. If you can't write a failing test, classify as CANNOT_REPRODUCE.

## Two-Phase Strategy

**Phase 1 (Triage):** One branch per issue. Write test. Classify. For RESOLVED, open upstream PR and comment. For CONFIRMED, branch sits with failing test.

**Phase 2 (Fix):** Sweep CONFIRMED items by difficulty. Implement fixes on existing branches. When test goes GREEN, open upstream PR.

## Where Tests Live

Tests belong in the natural location — not in any special triage directory.

| Content | Location |
|---------|----------|
| Unit test (mockable, any service) | `tests/unit/{confluence,jira}/` |
| Confluence Cloud E2E | `tests/e2e/cloud/test_confluence_cloud_operations.py` |
| Jira Cloud E2E | `tests/e2e/cloud/test_jira_cloud_operations.py` |

## Branch Naming

```
triage/upstream-NNN-short-description   ← all new triage branches
fix/upstream-NNN-short-description      ← only for previously confirmed bugs (pre-existing convention)
```

All branches cut from `main` (the clean upstream mirror).

## Environment Setup

`.env` in project root (gitignored). The `CLOUD_E2E_*` vars are aliases required by the E2E test framework:

```
# Confluence Cloud
CONFLUENCE_URL=https://eruditis.atlassian.net/wiki
CONFLUENCE_USERNAME=eric@eruditis.com
CONFLUENCE_API_TOKEN=<token>
CONFLUENCE_TEST_PAGE_ID=2570944513   # page in MCPTEST space
TRIAGE_SPACE_KEY=MCPTEST

# Jira Cloud
JIRA_URL=https://eruditis.atlassian.net
JIRA_USERNAME=eric@eruditis.com
JIRA_API_TOKEN=<same token>
JIRA_TEST_PROJECT_KEY=JTEST

# Cloud E2E aliases (required by tests/e2e/cloud/conftest.py)
CLOUD_E2E_CONFLUENCE_URL=<same as CONFLUENCE_URL>
CLOUD_E2E_JIRA_URL=<same as JIRA_URL>
CLOUD_E2E_USERNAME=<same as CONFLUENCE_USERNAME>
CLOUD_E2E_API_TOKEN=<same as CONFLUENCE_API_TOKEN>
CLOUD_E2E_SPACE_KEY=MCPTEST
CLOUD_E2E_PROJECT_KEY=JTEST
```

Run E2E tests:
```bash
set -a && source .env && set +a && uv run pytest tests/e2e/cloud/ --cloud-e2e -xvs
```

Run unit tests:
```bash
uv run pytest tests/unit/ -xvs
```

## Per-Issue Workflow

### 1. READ
```bash
gh issue view <NUMBER> --repo sooperset/mcp-atlassian \
  --json title,body,labels,comments,createdAt \
  --jq '{title:.title,labels:[.labels[].name],body:.body}'
```

### 2. ASSESS
- Is it testable in code? If pure infra/docs/client-side → OUT_OF_SCOPE
- Does it have >5 comments with failed fix attempts? → COMPLEX_DEFER
- Is there an active PR addressing it? → note in log, skip
- Does the feature/fix already exist in the codebase? → RESOLVED
- Can we write a meaningful failing test? → CONFIRMED or CANNOT_REPRODUCE

Cross-reference against the MCP tool list before writing tests:
```bash
grep "^async def\|^def " src/mcp_atlassian/servers/{jira,confluence}.py | sed 's/async def //' | sed 's/(.*//'
```

### 3. WRITE TEST

**Unit test (mockable):**
```python
# tests/unit/{confluence,jira}/test_<module>.py
class Test<Feature>:
    """<What the issue requests. Link: https://github.com/sooperset/mcp-atlassian/issues/NNN>"""

    def test_<behavior>(self, <mixin_fixture>):
        # For RESOLVED: assert the feature works as expected
        # For CONFIRMED: assert the expected behavior — will fail until fixed
        ...
```

**E2E test (needs live API):**
```python
# tests/e2e/cloud/test_{confluence,jira}_cloud_operations.py
class Test<Feature>:
    """<What the issue requests. Link: https://github.com/sooperset/mcp-atlassian/issues/NNN>"""

    def test_<behavior>(
        self,
        {confluence,jira}_fetcher: {Confluence,Jira}Fetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        # Setup, action, assert
        # Always use resource_tracker.add_{jira_issue,confluence_page}() for cleanup
```

### 4. RUN
```bash
# Unit:
uv run pytest tests/unit/.../test_file.py::TestClass::test_name -xvs

# E2E:
set -a && source .env && set +a && \
  uv run pytest tests/e2e/cloud/test_<file>.py::TestClass --cloud-e2e -xvs
```

### 5. CLASSIFY
- GREEN (passes) → **RESOLVED**
- RED (fails) → **CONFIRMED**
- Can't write meaningful test → **CANNOT_REPRODUCE**
- Too complex/architectural → **COMPLEX_DEFER**

### 6. RATE DIFFICULTY (CONFIRMED only)

| Rating | Meaning |
|--------|---------|
| Easy | 1-2 files, <20 lines — expose existing method, fix param, adjust filter |
| Medium | 3-5 files, <100 lines — new tool, error handling, model field |
| Hard | Architectural, >100 lines — new pipeline, multi-instance, auth overhaul |

### 7. COMMIT & PUSH

After test runs (pass or fail is expected — that's the point):

```bash
# Fix any ruff errors in files you touched (tech debt reduction)
uv run ruff format <file>
uv run ruff check --fix <file>

git add <test_file>
git commit -m "test: add {regression,triage} test for <feature> (upstream #NNN)

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>"

git push origin triage/upstream-NNN-short-description
```

### 8. RECORD

Update `docs/upstream-triage-log.md` on `eruditis/main`:
- Status, Difficulty, Date, Notes, Fix Branch column

### 9. ACT

**RESOLVED:** Open upstream PR immediately after pushing.

```bash
gh pr create \
  --repo sooperset/mcp-atlassian \
  --base main \
  --head Troubladore:triage/upstream-NNN-short-description \
  --title "test: add regression test for <title> (closes #NNN)" \
  --body "$(cat <<'EOF'
Adds a regression test proving that #NNN is resolved.

## What This Does
<one sentence>

## Test Evidence
<paste test output showing PASSED>

Closes #NNN
EOF
)"

# Then comment on the upstream issue
gh issue comment NNN --repo sooperset/mcp-atlassian --body "$(cat <<'EOF'
Verified on Confluence/Jira Cloud (commit `<SHA>`).

**Test:** <link to test in PR>
**Result:** Passes — the expected behavior works correctly.

PR #<PR_NUMBER> adds a regression test if you'd like the coverage.

<details>
<summary>Test output</summary>

\`\`\`
<paste output>
\`\`\`

</details>
EOF
)"
```

**CONFIRMED:** Branch sits with failing test. No upstream comment yet.
Branch name and failing test are recorded in the log. Phase 2 will implement the fix.

**CANNOT_REPRODUCE / COMPLEX_DEFER / OUT_OF_SCOPE:** Log only. No branch needed.

## Code Quality Rule

**When touching any file, fix pre-existing ruff errors in that file.**
This reduces tech debt incrementally without needing dedicated cleanup PRs.

```bash
uv run ruff format <path/to/file>
uv run ruff check --fix <path/to/file>
```

Never suppress warnings. Never add `# noqa` unless the rule is genuinely inapplicable.

## Parallel Processing

For batches of independent branches, dispatch background agents:

```
Agent A: triage/upstream-NNN-a, triage/upstream-NNN-b, triage/upstream-NNN-c
Agent B: triage/upstream-NNN-d, triage/upstream-NNN-e, triage/upstream-NNN-f
```

Each agent works on separate branches — no git conflicts. Report results back,
then update the triage log in one commit on `eruditis/main`.

## Comment Etiquette

- Only comment upstream when you have a PR to attach (RESOLVED)
- Never say "I can fix this if you want" — just do the work
- Polite, factual, includes test output and commit SHA
- Each issue gets its own PR — never bundle multiple issues into one PR
- Never mark review conversations as resolved
- Comment language should work for both bugs ("no longer reproduces") and features ("already implemented")
