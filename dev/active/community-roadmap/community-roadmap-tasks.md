# Community Roadmap - Task Checklist

**Last Updated**: 2026-02-20 (session 5 update)
**Branch**: `main` (roadmap is cross-branch; individual phases create feature branches)
**PR**: N/A (roadmap-level tracking)

---

## Phase -1: Alignment Sprint
- [x] **-1.1** Write Auth ADR — **DONE**: `dev/docs/auth-adr.md`
  - Covers Cloud/Server/DC auth matrix, token semantics, PR disposition (#856 accept, #835/#562 close, #699/#892 defer)
- [x] **-1.2** Multi-instance: PR #535 assessment — **DONE**: `dev/docs/pr-535-assessment.md`
  - NOT READY: stale, zero approvals, conflicts with Phase 0 PRs. Adopt in Phase 6.
- [x] **-1.3** Attachment contract — **DONE**: `dev/docs/attachment-contract.md`
  - Embedded-first: MCP tools return EmbeddedResource (base64), mixin keeps filesystem. 50MB limit.
- [x] **-1.4** Contributor communication templates — **DONE**: `dev/docs/contributor-templates.md`
  - 4 templates: merge-accepted, maintainer-rebase, superseded-close, stale-revive
- [x] ~~**-1.5** Post GitHub Discussion announcing roadmap~~ — **CANCELLED by maintainer**
- [x] **-1.6** Close superseded duplicate PRs — **DONE**
  - #815 closed (→ #849), #577 closed (→ #910), #705 closed (→ #905)

## Phase 0: Merge Ready PRs

### Cluster A — jira/issues.py
- [x] **0.1** Merge PR #874 (Remote Links API version) — **MERGED**
- [x] **0.2** Merge PR #876 (Auto-Include Comment Field) — **MERGED** (rebased, conflict resolved)
- [x] **0.3** Merge PR #887 (Field Update Structure) — **MERGED**
- [x] **0.4** Merge PR #901 (Components Field Updates) — **MERGED** (rebased, test assertions fixed)
- [x] **0.A** Tests pass (1174 passed, 5 skipped)

### Cluster B — preprocessing/jira.py
- [x] **0.5** Merge PR #914 (Code Block Languages) — **MERGED** (rebased, 2 conflicts resolved)
- [x] **0.6** Merge PR #894 (Preserve # in Code Blocks) — **MERGED**
- [x] **0.B** Tests pass

### Cluster C — servers/jira.py + independent
- [x] **0.7** Merge PR #902 (ASCII Transliteration) — **MERGED** (rebased, type annotation fixed)
- [x] **0.8** Merge PR #900 (Pattern Validation) — **MERGED**
- [x] **0.9** Merge PR #919 (Embedded Resources) — **MERGED** (rebased, conflict resolved)
- [x] **0.10** Merge PR #915 (Wiki Markup to Markdown) — **MERGED**
- [x] **0.C** Tests pass

### Cluster D — Standalone
- [x] **0.11** Merge PR #903 (ORDER BY Fix) — **MERGED**
- [x] **0.12** Merge PR #910 (Dev Info API) — **MERGED** (rebased, README conflict resolved)
- [x] **0.13** Merge PR #905 (Historical Versions) — **MERGED**
- [x] **0.14** Merge PR #849 (ProForma Forms) — **MERGED** (rebased, README + servers/jira.py conflicts resolved)
- [x] **0.15** Merge PR #898 (Confluence Attachments) — **MERGED** (rebased, pyproject.toml + uv.lock conflicts resolved, squash-merged via origin)
- [x] **0.D** Tests pass (1293 passed, 5 skipped)

### Triage
- [x] **0.16** Evaluate badge PRs (#911, #913, #879) — **SKIPPED** per maintainer (unnecessary)
- [x] **0.17** Check #878 (pip security pin) — **CLOSED** (project uses uv, not pip)
 - [x] **0.18** Cut patch release v0.13.1 — **RELEASED 2026-02-18**

### Lint Fixes (pushed directly to main)
- [x] Fix trailing newline in AGENTS.md
- [x] Fix unused `import unicodedata` + import ordering in users.py
- [x] Fix extra blank line in test_preprocessing.py

## Phase 1: Stability & Docker ✅ COMPLETE
- [x] **1.1** Fix orphaned process management (#909) — PR #931 merged `f73d8d4`
- [x] **1.2** Improve error messages (#702) — PR #702 closed (superseded); actionable errors implemented in PR #932 merged `c47502d`
- [x] **1.3** Docker documentation — CANCELLED (README covers Docker; #909 fix would make new doc stale)
- [x] **1.4** Streamable-HTTP transport fix (#507) — PR #933 merged `fb3c79e`
- [x] **1.5** Cut minor release v0.14.0 — **RELEASED 2026-02-18**

### Additional Bug Fixes Merged into v0.14.0
- [x] PR #927: Normalize MCP tool registration names + FastMCP settings deprecation `772d26c`
- [x] PR #926: Revert incorrect `fields=` kwarg in `update_issue` (critical regression) `25dbcc2`
- [x] PR #925: Assign issue post-creation for Server/DC `e5bcdb6`
- [x] PR #929: Confluence `EmbeddedResource` for attachment downloads `00142d0` (**follow-up from PR #898**)
- [x] PR #928: Dev info API 404/403 handling `22540aa` (**follow-up from PR #910**)
- [x] PR #886: Vertex AI schema fix `9fc0af8` (**Phase 4a.1 completed early**)
- [x] PR #694: Strip trailing slash in Confluence URL (#691) `b120857`
- [x] PR #685: Sprint issues `fields` parameter fix `f95f57c`
- [x] PR #659: Transitions endpoint fix `a3c6742`
- [x] PR #633: Epic/subtask creation with issue type ID `3893ac6`

### Post-v0.14.0 Hotfixes
- [x] **v0.14.1** — PR #934: SLA tool double-prefix (`jira_jira_get_issue_sla` → `jira_get_issue_sla`) + sprint date comparison crash `ba4ed4d`
- [x] **v0.14.2** — PR #936: stdio regression (stdin read blocking from #931) + Python 3.14 support `a794804`

## Phase 1+: Post-v0.14.2 Hotfixes (from 2026-02-20 notification triage)
- [x] **1+.0** Enable private security reporting (#908) — **DONE**: PVR enabled, SECURITY.md rewritten `e0b0f30`
- [x] **1+.1** Merge PR #890 — US Gov Cloud URL detection — **MERGED** `ffa6b39`
- [x] **1+.2** Fix project key regex >10 chars (#937) — **FIXED**: regex relaxed to `+` `142d5d9`
- [x] **1+.3** Investigate stdio hang in Homebrew packaging (#939) — **FIXED**: threading.Event stop signal `74b32ec`
- [x] **1+.4** Verify and close #916 — **CLOSED**: already fixed in v0.14.2, boundary tests added `d437876`
- [ ] **1+.5** Cut patch release v0.14.3

## Phase 2: Custom Field Handling
- [ ] **2a.1** Audit custom field handling
- [ ] **2a.2** Merge PR #690
- [ ] **2a.3** Components field support
- [ ] **2a.4** ADF support for Jira Cloud (#864) — 3 thumbsup, contributor willing to PR
- [ ] **2b.1** DateTime timezone fix (#863)
- [ ] **2c.1** Custom field options (#686)
- [ ] **2c.2** Checklist fields (#722)
- [ ] **2c.3** Cascading select support
- [ ] **2c.4** Expose Jira comment ID in `jira_get_issue` output (#923)
- [ ] **2c.5** ProForma Forms API integration for submitted forms (#866) — extends PR #849
- [ ] **2c.6** Cut minor release v0.15.0

## Phase 3: Auth & OAuth
- [ ] **3.1** Choose OAuth DC implementation
- [ ] **3.2** Multi-user OAuth flow (#610)
- [ ] **3.3** Bearer token for Server/DC (#892)
- [ ] **3.4** BYOT OAuth (#699)
- [ ] **3.5** Close duplicate auth PRs
- [ ] **3.6** Configurable HTTP timeout (#891, PR #895) — Server/DC needs longer timeouts
- [ ] **3.7** Cut minor release v0.16.0

## Phase 4: AI Platform Compatibility
- [x] **4a.1** Merge PR #886 (Vertex AI) — **DONE** (merged in v0.14.0, `9fc0af8`)
- [ ] **4a.2** Audit tool metadata
- [ ] **4a.3** Compatibility test harness
- [ ] **4a.4** Compatibility matrix docs
- [ ] **4a.5** Merge PR #938 — compatibility arg for `jira_get_link_types` (LiteLLM/OpenAI gateway workaround)
- [ ] **4b.1** Track ChatGPT compat (#484)
- [ ] **4b.2** Investigate Copilot (#541)
- [ ] **4b.3** Test Google ADK (#640)
- [ ] **4a.6** Cut patch release

## Phase 5: Confluence Attachments & Images
- [ ] **5.1** Image download from pages (#152)
- [ ] **5.2** Attachment content parsing (#667)
- [ ] **5.3** Cross-service parity check
- [ ] **5.4** Add `confluence_create_attachment` tool (#922)
- [ ] **5.5** Cut minor release

## Phase 6: Multi-Instance & Advanced
- [ ] **6.1** Merge PR #535 (multi-instance)
- [ ] **6.2** Evaluate Helm chart (#737)
- [ ] **6.3** Bitbucket feasibility (#289)
- [ ] **6.4** JSM internal comments (#867)
- [ ] **6.5** Zephyr Squad integration (PR #917) — 7 methods, 6 tools, tests included
- [ ] **6.6** Cut major release

### Follow-up Task Resolution
- [x] `tasks/followup-pr898-embedded-alignment.md` — **RESOLVED** by PR #929 (Confluence EmbeddedResource)
- [x] `tasks/followup-pr910-error-handling.md` — **PARTIALLY RESOLVED** by PR #928 (404/403 handling; caching/batch still open)

---

## Session Log

### Session 1: 2026-02-17 (Full session — analysis + planning)
- **Started**: Fresh analysis of all open issues and PRs
- **Actions**:
  - Launched 3 parallel Explore agents to catalog issues, PRs, and community stats
  - Explored all 126 open issues: categorized 66 bugs, 48 features, 7 stale, 5 unlabeled
  - Explored all 57 open PRs: 51 awaiting review, 6 draft, 5 changes requested
  - Launched 2 parallel Explore agents for emoji reaction + comment deep dive
  - Ranked all issues/PRs by thumbsup, heart, comments — identified top 20 in each category
  - Identified demand tiers: Auth (#1), Custom Fields (#2), AI Compat (#3)
  - Found 5 duplicate/conflicting PR sets
  - Created initial 8-phase roadmap plan
  - Entered plan mode, wrote plan file
  - Ran `/gpt-plan-review` via Codex (gpt-5.3-codex, read-only sandbox)
  - Codex returned 13 findings (7 must-address, 4 should-address, 2 non-blocking)
  - Validated each finding: verified PR states via `gh pr view`, checked file overlaps via `gh pr view --json files`
  - Caught 2 Codex hallucinations (false claims about merged PRs)
  - Accepted 9 findings, rejected 2, deferred 2
  - Revised plan: added Phase -1 alignment sprint, cluster-based merge ordering, release strategy, continuous cleanup lane, contributor communication
  - User confirmed all 15 Phase 0 PRs still OPEN (double-checked)
  - Created dev-docs directory and all 3 files
  - Updated dev-docs for session end
- **Files created**:
  - `dev/active/community-roadmap/community-roadmap-plan.md` (created)
  - `dev/active/community-roadmap/community-roadmap-context.md` (created)
  - `dev/active/community-roadmap/community-roadmap-tasks.md` (created)
  - `dev/docs/community-roadmap-review-prompt.md` (created)
  - `dev/docs/community-roadmap-gpt-review.md` (created by Codex)
  - `dev/docs/community-roadmap-codex-summary.md` (created by Codex -o flag)
  - `.claude/plans/encapsulated-doodling-fern.md` (created, then revised)
- **Blockers**: None
- **Total tool calls**: ~80+ (across main context + 5 subagents)

### Session 2: 2026-02-17 (Decision session — Phase -1 decisions + tooling)
- **Started**: Phase -1 decision-making
- **Actions**:
  - Made all 4 Phase -1 strategic decisions with maintainer
  - Enabled Claude Code Agent Teams in `~/.claude/settings.json`
  - Set `teammateMode: "tmux"` for split-pane display
  - Cancelled Phase -1.5 (GitHub Discussion) per maintainer request
- **Files modified**:
  - `~/.claude/settings.json`, dev-docs (context, tasks, plan)
- **Blockers**: Need to restart Claude Code for agent teams to activate

### Session 3: 2026-02-17 (Execution session — Phase -1 + Phase 0 complete)
- **Started**: Phase -1 execution, then Phase 0 merges
- **Actions**:
  - **Phase -1 execution**:
    - Created 4 docs in `dev/docs/`: auth-adr.md, attachment-contract.md, pr-535-assessment.md, contributor-templates.md
    - Closed 3 superseded PRs: #815 (→#849), #577 (→#910), #705 (→#905)
  - **Phase 0 PR reviews** (4 Explore subagents in parallel):
    - Cluster A: 4 ACCEPT (#874, #876, #887, #901)
    - Cluster B: 2 ACCEPT (#894, #914)
    - Cluster C: 4 ACCEPT (#900, #902 w/followup, #915, #919)
    - Cluster D: 5 ACCEPT (#903 w/lint fix, #905, #910 w/followup, #849, #898)
  - **Phase 0 merges** (all 15 PRs merged to main):
    - Cluster A: #887 → #874 → #876 (rebased) → #901 (rebased, test fixes)
    - Cluster B: #894 → #914 (rebased, 2 conflicts)
    - Cluster C: #900 → #915 → #902 (rebased, type fix) → #919 (rebased)
    - Cluster D: #905 → #910 (rebased) → #849 (rebased) → #903 → #898 (manual squash)
    - 8 merge conflicts resolved across all clusters
  - **Lint fixes** (3, pushed directly to main):
    - AGENTS.md trailing newline
    - users.py: removed unused `import unicodedata`, fixed import ordering
    - test_preprocessing.py: removed extra blank line
  - **Triage**:
    - #911/#913 (badges): SKIPPED per maintainer
    - #879 (DeepWiki): DEFERRED (build failed)
    - #878 (pip pin): CLOSED (project uses uv)
  - **Contributor comms**:
    - Thank-you comments posted on all 14 merged PRs
    - Apology posted on PR #898 (lost author attribution in manual squash merge)
  - **Follow-up tasks created**:
    - `tasks/followup-pr898-embedded-alignment.md` (Phase 5)
    - `tasks/followup-pr910-error-handling.md` (Phase 1)
- **Files created**:
  - `dev/docs/auth-adr.md`
  - `dev/docs/attachment-contract.md`
  - `dev/docs/pr-535-assessment.md`
  - `dev/docs/contributor-templates.md`
  - `dev/active/community-roadmap/tasks/followup-pr898-embedded-alignment.md`
  - `dev/active/community-roadmap/tasks/followup-pr910-error-handling.md`
- **Files modified on main** (via PR merges):
  - `src/mcp_atlassian/jira/` — issues.py, search.py, users.py, links.py, development.py (new), forms.py (new), forms_api.py (new), forms_common.py (new), __init__.py, protocols.py
  - `src/mcp_atlassian/confluence/` — attachments.py (new), protocols.py (new), pages.py, v2_adapter.py, __init__.py
  - `src/mcp_atlassian/servers/` — jira.py, confluence.py
  - `src/mcp_atlassian/preprocessing/jira.py`
  - `src/mcp_atlassian/models/` — base.py, jira/__init__.py, jira/forms.py (new), confluence/common.py, confluence/page.py
  - `src/mcp_atlassian/utils/lifecycle.py`
  - `tests/` — 8 new test files, 6 modified test files
  - `pyproject.toml`, `uv.lock`, `README.md`, `AGENTS.md`, `docs/tools-reference.mdx`
- **Blockers**: None
- **Test results**: 1293 passed, 5 skipped (up from 1174)

---

## 5-Question Reboot Check

| Question | Answer |
|----------|--------|
| Where am I? | Phase 0 COMPLETE. Phase 1 COMPLETE. v0.14.2 is latest release. Next: Phase 2 (Custom Fields). |
| Where am I going? | Phase 2 (Custom Field Handling) → Phase 3 (Auth & OAuth) |
| What's the goal? | Systematically address 118 issues + 34 PRs backlog via phased roadmap (down from 126/57) |
| What have I learned? | stdio EOF guard via `sys.stdin.read()` blocks FastMCP's own stdin reader — use `os.getppid()` polling instead (#936). Double-prefix bugs hit multiple tools (confluence_get_page_views, jira_get_issue_sla) — tool registration naming needs systematic audit. Rapid hotfix releases (v0.14.0→v0.14.1→v0.14.2 same day) happen when stability fixes introduce regressions. |
| What have I done? | Sessions 1-3: Analysis, decisions, Phase -1 + Phase 0 (15 PRs). Session 4: Phase 1 (stability) + 10 additional bug fixes + v0.13.1/v0.14.0/v0.14.1/v0.14.2 releases. Tests: 1174→1318. Issues: 126→118. PRs: 57→34. |

### Session 4: 2026-02-18 (Execution session — Phase 1 complete + v0.14.0-v0.14.2 releases)
- **Started**: v0.13.1 pre-release bug fixes (PRD created), then Phase 1 execution
- **Actions**:
  - **Pre-release fixes** (PRD `PRD-v0.13.1-prerelease-fixes.md`):
    - PR #927: Fixed double-prefix `confluence_confluence_get_page_views` + FastMCP `.settings` deprecation
  - **v0.13.1 released** (2026-02-18T00:57:33Z)
  - **Phase 1 execution**:
    - PR #931: stdio server EOF termination (#909)
    - PR #932: Actionable error messages (#702 closed as superseded)
    - PR #933: Streamable-HTTP transport fix (#507)
  - **Additional bug fixes merged into v0.14.0** (10 PRs):
    - #926 (critical regression: fields= kwarg), #925 (assignee drop), #929 (Confluence EmbeddedResource)
    - #928 (dev info 404/403), #886 (Vertex AI), #694 (trailing slash), #685 (sprint fields)
    - #659 (transitions endpoint), #633 (epic/subtask creation)
  - **v0.14.0 released** (2026-02-18T07:39:04Z) — 12 bug fixes + 2 community PRs
  - **Post-v0.14.0 hotfixes**:
    - v0.14.1 (PR #934): SLA tool double-prefix + sprint date comparison crash
    - v0.14.2 (PR #936): stdio regression (stdin read blocking) + Python 3.14 support
  - **Follow-up tasks resolved**: PR #929 resolved `followup-pr898-embedded-alignment`, PR #928 partially resolved `followup-pr910-error-handling`
- **Files modified**: `src/mcp_atlassian/` (multiple), `tests/` (multiple), `pyproject.toml`
- **Blockers**: None
- **Test results**: 1318 passed, 5 skipped (up from 1293)
- **Issues closed**: 118 open (down from 126). PRs: 34 open (down from 57).

---

## 3-Strike Error Protocol
ATTEMPT 1: Diagnose & Fix -> identify root cause, targeted fix
ATTEMPT 2: Alternative Approach -> different method/tool
ATTEMPT 3: Broader Rethink -> question assumptions, search solutions
AFTER 3 FAILURES: Escalate to User -> explain attempts, ask for guidance
