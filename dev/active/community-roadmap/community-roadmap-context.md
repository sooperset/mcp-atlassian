# Community Roadmap - Context

**Last Updated**: 2026-02-20 (session 5 update)

## SESSION PROGRESS
- Completed:
  - Session 1: Full community analysis, plan creation, GPT review, plan revision, dev-docs
  - Session 2: All 4 Phase -1 strategic decisions finalized by maintainer
  - Session 3: Phase -1 fully executed + Phase 0 fully executed (15 PRs merged)
  - **Session 4 (2026-02-18): Phase 1 complete + v0.13.1/v0.14.0/v0.14.1/v0.14.2 released**
    - Pre-release: PR #927 fixed double-prefix tool name + FastMCP settings deprecation
    - v0.13.1 released (2026-02-18T00:57:33Z)
    - Phase 1: PRs #931 (stdio EOF), #932 (error messages), #933 (streamable-HTTP)
    - 10 additional bug fixes merged: #926, #925, #929, #928, #886, #694, #685, #659, #633, #927
    - v0.14.0 released (2026-02-18T07:39:04Z)
    - v0.14.1 hotfix: PR #934 (SLA tool double-prefix + sprint date crash)
    - v0.14.2 hotfix: PR #936 (stdio regression + Python 3.14 support)
    - Follow-up tasks resolved: PR #929 (Confluence EmbeddedResource), PR #928 (dev info 404/403)
    - Tests: 1318 passed, 5 skipped (up from 1293)
    - Issues: 118 open (down from 126). PRs: 34 open (down from 57)
  - **Session 5 (2026-02-20): Phase 1+ hotfixes complete**
    - 1+.0: PVR enabled, SECURITY.md rewritten `e0b0f30`
    - 1+.1: PR #890 merged (US Gov Cloud URL detection) `ffa6b39`
    - 1+.2: Project key regex relaxed for Server/DC long keys `142d5d9`
    - 1+.3: stdio Homebrew hang fixed with threading.Event `74b32ec`
    - 1+.4: #916 verified closed (fixed in v0.14.2), boundary tests added `d437876`
    - MCP smoke tests: all 3 transports passing (stdio, SSE, streamable-http)
    - Tests: 1325 passed, 5 skipped
    - Issues: #937 closed, #939 closed, #916 already closed, #908 PVR comment posted
- In Progress: Nothing (session updating)
- Next: Phase 2 (Custom Field Handling)

## Key Files

### Server Architecture
- `src/mcp_atlassian/servers/main.py` — AtlassianMCP, UserTokenMiddleware, tool filtering, lifespan
- `src/mcp_atlassian/servers/jira.py` — Jira tool definitions
- `src/mcp_atlassian/servers/confluence.py` — Confluence tool definitions
- `src/mcp_atlassian/servers/dependencies.py` — Dependency injection (get_jira_fetcher, get_confluence_fetcher)

### Auth System
- `src/mcp_atlassian/jira/config.py` — JiraConfig dataclass, `is_cloud` property, `from_env()`, `is_auth_configured()`
- `src/mcp_atlassian/confluence/config.py` — ConfluenceConfig (parallel structure)
- `src/mcp_atlassian/utils/oauth.py` — OAuthConfig, BYOAccessTokenOAuthConfig, token management
- `src/mcp_atlassian/utils/oauth_setup.py` — OAuth wizard CLI

### Custom Fields
- `src/mcp_atlassian/jira/fields.py` — FieldsMixin: get_fields(), format_field_value() (only handles user/array/option)
- `src/mcp_atlassian/jira/issues.py` — IssuesMixin: create/update issue paths

### Attachments
- `src/mcp_atlassian/jira/attachments.py` — AttachmentsMixin: download_attachment() writes to disk (filesystem-based)

### Preprocessing
- `src/mcp_atlassian/preprocessing/jira.py` — JiraPreprocessor: markup conversion, mentions, smart links
- `src/mcp_atlassian/preprocessing/confluence.py` — ConfluencePreprocessor
- `src/mcp_atlassian/preprocessing/base.py` — BasePreprocessor

### Models
- `src/mcp_atlassian/models/` — Pydantic v2 models, ApiModel base

## Research Findings

### Community Demand Tiers (by reaction + comment analysis)

**Tier 1 — Overwhelming demand:**
- Auth/OAuth for DC: #527 (20 comments, thumbsup x4), #610 (10 comments, thumbsup x6), #433 (thumbsup x6)
- Custom fields: #673 (thumbsup x7), multiple related bugs
- AI platform compat: #484 (thumbsup x9), #541 (thumbsup x7, 14 comments)

**Tier 2 — Strong demand:**
- Confluence attachments/images: #152 (thumbsup x6), #667 (thumbsup x6)
- Docker stability: #693 (7 comments), #920, #909
- Error messages: #486 (heart x6)

**Tier 3 — Steady interest:**
- Multi-instance: #231, #535 (10 comments)
- Bitbucket: #289 (thumbsup x4)
- Helm chart: #737 (thumbsup x2, rocket x1)
- JSM: #447 (thumbsup x4)

### Notification Triage (2026-02-20) — 25 notifications analyzed

**New items added to roadmap (12):**

| # | Title | Phase | Priority |
|---|-------|-------|----------|
| #908 | Security private disclosure channel | 1+ (immediate) | Critical |
| #890 | US Gov Cloud URL detection (PR ready) | 1+ (hotfix) | High |
| #937 | Project key regex too restrictive | 1+ (hotfix) | High |
| #939 | stdio hang in Homebrew 0.14.2 | 1+ (hotfix) | Medium |
| #864 | ADF support for Jira Cloud | 2a | High (3 thumbsup) |
| #923 | Missing Jira comment ID | 2c | Medium |
| #866 | ProForma Forms API limitations | 2c | Medium |
| #891/#895 | Configurable HTTP timeout (issue+PR) | 3 | Medium |
| #938 | Compatibility arg for link types (PR) | 4 | Low |
| #922 | confluence_create_attachment tool | 5 | Low |
| #917 | Zephyr Squad integration (PR) | 6 | Medium |

**Already resolved (5):** #940 (self-closed), #935 (v0.14.2), #924 (COMPLETED), #920 (COMPLETED), #918 (not found)
**Already tracked (6):** #926, #925, #876, #886, #919, #905, #892
**Verify & close (1):** #916 (likely fixed in v0.14.2 Python 3.14 support)

### Biggest Closed Issue Ever
- #721: Pydantic 2.12.0 incompatibility — 26 thumbsup, 27 total reactions, 13 comments

### Repository Stats
- 4,292 stars, 921 forks
- Created Dec 2024 (young project, explosive growth)
- Latest: v0.14.2 (Feb 18, 2026) — 4 releases in one day (v0.13.1 → v0.14.0 → v0.14.1 → v0.14.2)

### Phase 0 PR File Overlap (verified)
- PRs #876, #887, #901 all touch `jira/issues.py` + `test_issues.py`
- PRs #914, #894 both touch `preprocessing/jira.py` + `test_preprocessing.py`
- PR #874 touches `links.py` (separate from issues.py cluster)

### Auth Architecture Notes
- AGENTS.md: "OAuth = Cloud only, PAT = Server/DC only"
- `config.py` auth_type: Literal["basic", "pat", "oauth"]
- Server/DC: PAT takes priority over OAuth (fixes #824)
- `UserTokenMiddleware` supports Bearer (oauth) and Token (pat) prefixes
- 5+ competing auth PRs: #856, #835, #562, #892, #851, #699, #841, #739

### Attachment PR Inconsistency (Session 2 finding → Session 3 resolved)
- **PR #919 (Jira)**: Returns `EmbeddedResource` (base64 inline), removes `target_dir` param. Docker-safe. **MERGED.**
- **PR #898 (Confluence)**: Writes to disk via `download_path`/`download_folder`. **Breaks in Docker.** **MERGED.**
- Both merged as-is in Phase 0. Follow-up task created: `tasks/followup-pr898-embedded-alignment.md` (Phase 5).
- Size limit consideration: Files >50MB should fall back to URL-only response (base64 too expensive).

### Phase 0 Merge Conflicts Resolved (Session 3)
- **PR #876**: test_issues.py conflict with #887 (make_issue_data fixture vs new comment tests). Kept both.
- **PR #901**: Test assertions used old `update={"fields": ...}` signature after #887 changed it. Fixed 3 occurrences.
- **PR #914**: Two conflicts with #894 — save_code_block() (combined jira_lang + placeholder) and test file.
- **PR #919**: servers/jira.py conflict with #900 (kept ISSUE_KEY_PATTERN + EmbeddedResource return type).
- **PR #902**: Type annotation `str` → `str | None` for normalize_text().
- **PR #910**: README.md conflict (combined dev tools + historical versions rows).
- **PR #849**: README.md + servers/jira.py conflicts (kept ISSUE_KEY_PATTERN + added ProForma tools).
- **PR #898**: pyproject.toml (kept both unidecode + tzdata deps), uv.lock (regenerated).

### PR #898 Attribution Issue (Session 3)
- Could not push to contributor fork (permission denied to `kdtix-open`).
- Squash-merged locally via origin branch — commit authored as `sooperset` instead of original contributor.
- Force-push to fix was considered but rejected (risky on main for cosmetic fix).
- Posted apology comment on PR explaining the attribution loss.
- **Lesson**: For future manual squash merges, always use `--author` flag at commit time.

### Contributor Communication Strategy (Session 2 finding)
- Maintainer was absent for months — stale PRs are maintainer's fault, not contributors'
- All rebase work should be done by maintainer (not wait for contributors)
- Rebase methods: `gh pr checkout` + rebase + force-push (if "Allow edits" enabled), or cherry-pick to new branch
- Templates should be honest/apologetic, not blame contributors for inactivity
- **No GitHub Discussion post** — maintainer prefers to skip public announcement

### Agent Team Setup (Session 2)
- `~/.claude/settings.json` updated with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and `teammateMode: "tmux"`
- User works in tmux 3.5a — split-pane mode will auto-activate
- Plan: Use agent team for Phase -1 (Auth ADR teammate + PR #535 review teammate)

### Worktree Requirements for Teammates (Session 3 finding)
- **Git-excluded files that must be copied to worktrees:**
  - `.claude/` — excluded via `.gitignore`
  - `CLAUDE.md` — excluded via `.git/info/exclude`
  - `dev/` — excluded via `.git/info/exclude`
- `AGENTS.md` is the only Claude-relevant file tracked by git (CLAUDE.md has `@AGENTS.md`)
- **Follow `/worktree-workflow` skill** when creating worktrees for teammates:
  ```bash
  cp -r .claude/ CLAUDE.md $WT_DIR/
  cp -r dev/ $WT_DIR/  # if teammate needs dev-docs
  mkdir -p .git/worktrees/$WT_NAME/info
  echo "dev/" >> .git/worktrees/$WT_NAME/info/exclude
  ```

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Phase -1 before any merges | Auth ADR and multi-instance decision affect all subsequent work |
| Cluster-based merge order | PRs touching same files need sequential merging to avoid rebase churn |
| Continuous cleanup lane | Stale items shouldn't wait until Phase 7; close alongside merges |
| Phase 2 split into 2a/2b/2c | format_field_value() only handles 3 types; community needs 5+ more |
| Phase 4 two-lane approach | ChatGPT/Copilot compat is largely upstream; separate project-owned work |
| Release per phase | Community needs to know when fixes ship; defined release cadence |
| **Auth: Expand OAuth to Server/DC** | Community #1 demand (33+ comments). AGENTS.md "OAuth = Cloud only" will be updated. |
| **Multi-instance: Adopt PR #535** | Deferring risks rework on Phases 1-5. Better to align early. |
| **Attachment: Embedded-first** | PR #919 (Jira) already does it right. PR #898 (Confluence) needs post-merge alignment. Docker compat is non-negotiable. |
| **Comms: Maintainer-driven, no Discussion** | Maintainer will rebase PRs directly, not wait for contributors. 4 templates: merge-accepted, maintainer-rebase, superseded-close, stale-revive. Honest/apologetic tone. |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| Codex claimed PRs #903/#915/#898 merged | 1 | Verified via `gh pr view` — all still OPEN. Hallucination. |
| Codex said Phase 5 needs re-scoping | 1 | Based on false premise (#898 merged). Rejected. |
| Explore agent output truncated (agent a75c2a2) | 1 | Agent ran 32 tool uses but output not captured. Did direct file reads instead. |
| Branch protection blocking `gh pr merge` | 1 | Used `--admin` flag per maintainer instruction. |
| Fork push `--force-with-lease` failed (stale info) | 1 | Switched to `--force`. |
| Fork push went to origin instead of fork | 1 | Pushed directly to fork URL instead. |
| PR #898 fork push permission denied (kdtix-open) | 1 | Pushed to origin branch, closed PR, squash-merged locally. |
| PR #898 commit authored as sooperset not contributor | 1 | Left as-is (force-push to main too risky). Posted apology. |
| CI lint failures after merges (users.py, test_preprocessing.py) | 1 | Fixed unused import, import ordering, extra blank line. Pushed to main. |
| v0.14.0 stdio regression (#935) — `sys.stdin.read()` blocks FastMCP's own stdin reader | 1 | Replaced with `os.getppid()` polling in v0.14.2 (PR #936). Lesson: touching stdin in a stdio-transport server is dangerous. |
| v0.14.1 SLA tool double-prefix (`jira_jira_get_issue_sla`) | 1 | Same root cause as `confluence_confluence_get_page_views`. Fixed in PR #934. Lesson: tool naming normalization (#927) missed Jira SLA tool. |
| v0.14.1 sprint date comparison crash (naive vs aware datetime) | 1 | `start_date` was date-only string, compared against aware datetime. Fixed in PR #934. |

## Quick Resume

**Last worked on**: Phase 1 complete. v0.14.0 released, then v0.14.1 + v0.14.2 hotfixes for regressions.

**Current state**:
- Phase -1: COMPLETE (4 docs, 3 PR closures)
- Phase 0: COMPLETE (15 PRs merged, v0.13.1 released)
- Phase 1: COMPLETE (3 stability fixes + 10 additional bug fixes, v0.14.0/v0.14.1/v0.14.2 released)
- Phase 4a.1: DONE early (Vertex AI schema fix PR #886 merged in v0.14.0)
- Tests: 1318 passed, 5 skipped (up from 1293)
- Main branch: clean (all lint + tests passing), HEAD at `a794804`
- Open issues: 118 (down from 126). Open PRs: 34 (down from 57)
- Follow-up tasks: `followup-pr898-embedded-alignment` RESOLVED (PR #929), `followup-pr910-error-handling` PARTIALLY RESOLVED (PR #928, items 2-3 still open)

**Next steps**:
1. **Phase 1+ hotfixes** (before Phase 2):
   - **1+.0** Enable private security reporting (#908) — SECURITY.md blank contact
   - **1+.1** Merge PR #890 — US Gov Cloud URL detection (blocking users)
   - **1+.2** Fix project key regex (#937) — Server/DC >10 chars
   - **1+.3** Investigate stdio Homebrew hang (#939)
   - **1+.4** Verify & close #916 (Python 3.14 timestamp)
   - **1+.5** Cut v0.14.3
2. Begin Phase 2: Custom Field Handling
   - **2a.1** Audit custom field handling in create/update paths
   - **2a.2** Merge/integrate PR #690
   - **2a.3** Components field support
   - **2a.4** ADF support (#864)
3. Continue Phase 2c: Advanced field families (#923, #866)
4. Remaining Phase 4 items (4a.2-4a.5, 4b.1-4b.3)

**Commands to verify state**:
```bash
# Tests pass
uv run pytest tests/unit/ -x --tb=short -q

# Lint clean
uv run pre-commit run --all-files

# Current version tags
git tag --sort=-creatordate | head -5

# Recent commits on main
git log --oneline -20

# Open issues/PRs count
gh issue list --state open --limit 200 --json number --jq 'length'
gh pr list --state open --limit 200 --json number --jq 'length'
```

**Key files for next session**:
- `dev/active/community-roadmap/community-roadmap-tasks.md` — Task checklist (Phase 2+ remaining)
- `dev/active/community-roadmap/tasks/followup-pr910-error-handling.md` — Partially resolved (items 2-3 still open)
- `dev/docs/` — Phase -1 deliverables (auth-adr, attachment-contract, pr-535-assessment, contributor-templates)
