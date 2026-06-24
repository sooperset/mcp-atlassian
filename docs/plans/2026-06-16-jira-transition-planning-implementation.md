# Jira Transition Planning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a guided Jira transition planning workflow that prepares, previews, validates, and applies issue transitions using Jira schema, comments, current issue values, and optional workflow profiles.

**Architecture:** Add a planning layer around the existing transition execution path. Keep `jira_transition_issue` as the low-level executor, and add plan models, schema parsing, evidence extraction, a local single-process in-memory plan store, a cached project-version lookup path, and MCP tools for prepare, option lookup, update, preview, and apply.

**Tech Stack:** Python 3.10+, Pydantic v2, FastMCP, Atlassian Python API, pytest, Ruff, mypy, uv.

---

## Preconditions

- Work from the existing branch `fix/transition-required-fields` or a new feature branch.
- Preserve existing changes in:
  - `src/mcp_atlassian/jira/transitions.py`
  - `tests/unit/jira/test_transitions.py`
- Use `uv`, never `pip`.
- Keep writes scoped to transition planning files and tests.
- First version supports one local MCP server process only. Do not design plan
  storage for multi-worker sharing yet.

## Task 1: Add Transition Planning Models

**Files:**
- Create: `src/mcp_atlassian/models/jira/transition_plan.py`
- Modify: `src/mcp_atlassian/models/jira/__init__.py`
- Test: `tests/unit/models/test_jira_transition_plan.py`

**Step 1: Write failing model tests**

Create tests for:

- `TransitionPlan` stores issue identity, target transition, fields, stale checks.
- `TransitionFieldPlan` records interaction type, value format, required level.
- `TransitionFieldValue` distinguishes `current_issue`, `auto_draft`, and `user_selection`.
- `TransitionPlanStatus` supports `created`, `needs_user_input`, `ready`, `previewed`, `applied`, `stale`, `failed`.
- `TransitionPlan` records the last preview id/hash after preview composition.

Example test shape:

```python
from mcp_atlassian.models.jira.transition_plan import (
    TransitionFieldPlan,
    TransitionPlan,
    TransitionPlanStatus,
)


def test_transition_plan_defaults_to_created() -> None:
    plan = TransitionPlan(
        plan_id="RY-8714:771:test",
        issue_key="RY-8714",
        transition_id="771",
        transition_name="完成分析",
        to_status="已分析",
        schema_hash="abc",
        issue_updated="2026-06-16T10:00:00.000+0800",
    )

    assert plan.status == TransitionPlanStatus.CREATED
    assert plan.fields == []
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/models/test_jira_transition_plan.py -q
```

Expected: import failure because the model file does not exist.

**Step 3: Implement minimal models**

Create Pydantic models:

```python
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TransitionPlanStatus(StrEnum):
    CREATED = "created"
    NEEDS_USER_INPUT = "needs_user_input"
    READY = "ready"
    PREVIEWED = "previewed"
    APPLIED = "applied"
    STALE = "stale"
    FAILED = "failed"


class TransitionFieldSource(StrEnum):
    CURRENT_ISSUE = "current_issue"
    AUTO_DRAFT = "auto_draft"
    USER_SELECTION = "user_selection"
    EMPTY = "empty"


class TransitionFieldValue(BaseModel):
    value: Any = None
    source: TransitionFieldSource
    changed: bool = False
    destructive: bool = False
    confidence: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class TransitionFieldPlan(BaseModel):
    field_key: str
    name: str
    schema: dict[str, Any] = Field(default_factory=dict)
    required: bool = False
    required_level: str = "optional"
    operations: list[str] = Field(default_factory=list)
    interaction_type: str = "text_input"
    value_format: str = "raw"
    lookup_tool: str | None = None
    needs_user_input: bool = False
    current_value: Any = None
    auto_draft: TransitionFieldValue | None = None
    user_value: TransitionFieldValue | None = None
    final_value: TransitionFieldValue | None = None


class TransitionStaleChecks(BaseModel):
    issue_updated: str
    status_id: str | None = None
    transition_id: str
    schema_hash: str
    latest_comment_id: str | None = None
    latest_comment_updated: str | None = None


class TransitionPlan(BaseModel):
    plan_id: str
    issue_key: str
    transition_id: str
    transition_name: str
    to_status: str | None = None
    schema_hash: str
    issue_updated: str
    status: TransitionPlanStatus = TransitionPlanStatus.CREATED
    profile: str | None = None
    fields: list[TransitionFieldPlan] = Field(default_factory=list)
    comment_context: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    stale_checks: TransitionStaleChecks | None = None
    last_preview_id: str | None = None
    last_payload_hash: str | None = None
```

Export these classes from `src/mcp_atlassian/models/jira/__init__.py`.

**Step 4: Run tests**

Run:

```bash
uv run pytest tests/unit/models/test_jira_transition_plan.py -q
```

Expected: PASS.

**Step 5: Commit**

Only commit this task's files if committing is requested:

```bash
git add src/mcp_atlassian/models/jira/transition_plan.py src/mcp_atlassian/models/jira/__init__.py tests/unit/models/test_jira_transition_plan.py
git commit -m "feat(jira): add transition plan models"
```

## Task 2: Add Generic Transition Field Schema Parser

**Files:**
- Create: `src/mcp_atlassian/jira/transition_schema.py`
- Test: `tests/unit/jira/test_transition_schema.py`

**Step 1: Write failing parser tests**

Cover schema mappings from the browser extension:

- `type=user` -> `user_auto_or_picker`
- `array + items=version` -> `version_picker`
- `array + allowedValues` -> `multi_option_picker`
- `option` -> `single_option_picker`
- `option-with-child` -> `single_option_picker`
- `string + textarea/textfield custom` -> `textarea`
- `number` -> `number_input`
- unknown -> `text_input`

Add a test for `allowedValues` truncation metadata on version fields.

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/jira/test_transition_schema.py -q
```

Expected: import failure.

**Step 3: Implement parser**

Implement:

```python
def parse_transition_field(
    field_key: str,
    field_meta: dict[str, Any],
    current_value: Any = None,
    effective_required: bool = False,
) -> TransitionFieldPlan:
    ...
```

Rules:

- Use `field_meta["schema"]`.
- Preserve `required`, `operations`, `name`, `schema`.
- Set `required_level` to `hard`, `soft`, or `optional`.
- For version fields, set:
  - `interaction_type="version_picker"`
  - `value_format="array_of_id_objects"`
  - `lookup_tool="jira_search_transition_field_options"`
- Do not attach all version `allowedValues` to the plan.
- For option fields, allowed values can remain in metadata only if reasonably small.

Also implement:

```python
def schema_hash_for_transition(transition: dict[str, Any]) -> str:
    ...
```

Hash only stable schema-relevant parts:

- transition id
- transition name
- field keys
- field schema
- field operations
- required flags

**Step 4: Run tests**

```bash
uv run pytest tests/unit/jira/test_transition_schema.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/mcp_atlassian/jira/transition_schema.py tests/unit/jira/test_transition_schema.py
git commit -m "feat(jira): parse transition field schema"
```

## Task 3: Add Transition Value Formatter

**Files:**
- Modify: `src/mcp_atlassian/jira/transition_schema.py`
- Test: `tests/unit/jira/test_transition_schema.py`

**Step 1: Write failing formatter tests**

Cover:

- version scalar id -> `[{id: "123"}]`
- version object list remains list of id objects
- multi option ids -> `[{id: "..."}]`
- single option id -> `{id: "..."}`
- string -> string
- number -> int or float
- empty values recognized consistently

**Step 2: Run tests to verify failure**

```bash
uv run pytest tests/unit/jira/test_transition_schema.py -q
```

Expected: formatter not found.

**Step 3: Implement formatter**

Add:

```python
def format_transition_field_value(field_plan: TransitionFieldPlan, value: Any) -> Any:
    ...


def is_empty_transition_value(value: Any) -> bool:
    ...
```

Keep this function pure and independent from Jira network calls.

**Step 4: Run tests**

```bash
uv run pytest tests/unit/jira/test_transition_schema.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/mcp_atlassian/jira/transition_schema.py tests/unit/jira/test_transition_schema.py
git commit -m "feat(jira): format transition field values"
```

## Task 4: Add Comment Evidence Extractor

**Files:**
- Create: `src/mcp_atlassian/jira/transition_comments.py`
- Test: `tests/unit/jira/test_transition_comments.py`

**Step 1: Write failing tests with sample comments**

Use small fixtures based on the provided sample:

- GitLab auto-linked commit comment authored by `admin`.
- Human assignee comment authored by `jianghaitao` listing affected scales.
- Duplicate commit references.

Expected behavior:

- Commit comments become `commit_reference`.
- Assignee comments become `assignee_analysis`.
- Impact scope facts are extracted.
- Duplicate commit sha or duplicate commit body is not weighted twice.

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/jira/test_transition_comments.py -q
```

Expected: import failure.

**Step 3: Implement extractor**

Add:

```python
def extract_comment_evidence(
    comments_response: dict[str, Any],
    assignee_name: str | None,
    assignee_key: str | None = None,
) -> dict[str, Any]:
    ...
```

Return shape:

```json
{
  "total": 14,
  "used": 6,
  "high_value_comments": [],
  "commit_references": [],
  "impact_scope": [],
  "ignored": []
}
```

Commit parsing should extract:

- repo
- branch if present
- commit URL
- short sha
- quoted commit message
- mentioned author display text

Keep extraction heuristic simple and testable.

**Step 4: Run tests**

```bash
uv run pytest tests/unit/jira/test_transition_comments.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/mcp_atlassian/jira/transition_comments.py tests/unit/jira/test_transition_comments.py
git commit -m "feat(jira): extract transition comment evidence"
```

## Task 5: Add In-Memory Transition Plan Store

**Files:**
- Create: `src/mcp_atlassian/jira/transition_plan_store.py`
- Test: `tests/unit/jira/test_transition_plan_store.py`

**Step 1: Write failing tests**

Cover:

- Store and retrieve plan.
- Missing plan returns `None`.
- Expired plan is removed.
- User scope prevents cross-user retrieval when user identity is provided.
- Tenant scope prevents cross-tenant retrieval when tenant identity is provided.
- Concurrent put/get/delete operations remain internally consistent in a single
  process.

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/jira/test_transition_plan_store.py -q
```

Expected: import failure.

**Step 3: Implement store**

Add:

```python
class TransitionPlanStore:
    def __init__(self, ttl_seconds: int = 1800) -> None: ...
    def put(
        self,
        plan: TransitionPlan,
        user_key: str | None = None,
        tenant_key: str | None = None,
    ) -> None: ...
    def get(
        self,
        plan_id: str,
        user_key: str | None = None,
        tenant_key: str | None = None,
    ) -> TransitionPlan | None: ...
    def delete(
        self,
        plan_id: str,
        user_key: str | None = None,
        tenant_key: str | None = None,
    ) -> None: ...
```

Use process memory only. Protect the store with a lightweight lock because
multiple MCP calls can arrive concurrently in the same local process. This
store is intentionally not shared across restarts, multiple processes, or remote
workers.

**Step 4: Run tests**

```bash
uv run pytest tests/unit/jira/test_transition_plan_store.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/mcp_atlassian/jira/transition_plan_store.py tests/unit/jira/test_transition_plan_store.py
git commit -m "feat(jira): add transition plan store"
```

## Task 6: Add Transition Planning Mixin

**Files:**
- Create: `src/mcp_atlassian/jira/transition_planning.py`
- Modify: `src/mcp_atlassian/jira/__init__.py`
- Test: `tests/unit/jira/test_transition_planning.py`

**Step 1: Write failing prepare tests**

Mock:

- `get_issue`
- `get_available_transitions`
- `jira.issue_get_comments`

Test:

- It resolves target transition by name.
- It parses screen fields.
- It includes comment evidence.
- It reuses current issue values in field plans.
- It marks version fields as needing lookup.
- It generates an unguessable random `plan_id`, not a predictable id derived
  only from issue key and transition id.

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/jira/test_transition_planning.py -q
```

Expected: import failure.

**Step 3: Implement minimal planning mixin**

Add class:

```python
class TransitionPlanningMixin(JiraClient):
    def prepare_transition_plan(
        self,
        issue_key: str,
        target_transition_id: str | None = None,
        target_transition_name: str | None = None,
        target_status: str | None = None,
        profile: str | None = None,
        work_context: dict[str, Any] | None = None,
    ) -> TransitionPlan:
        ...
```

Implementation notes:

- Use `get_issue(issue_key, fields=None, expand=None, comment_limit=0)` or an
  existing method that returns enough fields.
- Use `get_available_transitions(issue_key)`.
- Resolve selected transition.
- Build current issue field map.
- Call `parse_transition_field` for each transition screen field.
- Call `jira.issue_get_comments(issue_key)` directly for raw comments.
- Call `extract_comment_evidence`.
- Generate `plan_id` with `secrets.token_urlsafe` or equivalent randomness, then
  store issue key, transition id, schema hash, and timestamps as plan fields.
- Treat Jira issue fields and comments as untrusted external content. Comment
  text can become evidence facts, but comment instructions must never override
  Jira schema, profile rules, or user confirmation.

Modify `JiraFetcher` inheritance in `src/mcp_atlassian/jira/__init__.py` to
include `TransitionPlanningMixin`.

**Step 4: Run tests**

```bash
uv run pytest tests/unit/jira/test_transition_planning.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/mcp_atlassian/jira/transition_planning.py src/mcp_atlassian/jira/__init__.py tests/unit/jira/test_transition_planning.py
git commit -m "feat(jira): prepare transition plans"
```

## Task 7: Add Payload Composition and Preview

**Files:**
- Modify: `src/mcp_atlassian/jira/transition_planning.py`
- Test: `tests/unit/jira/test_transition_planning.py`

**Step 1: Write failing preview tests**

Cover:

- User value wins over auto draft.
- Auto draft wins over current issue value.
- Current issue value is reused when no user or auto value exists.
- Empty optional fields are omitted.
- Empty required fields are returned as missing.
- Explicit clear is destructive.
- Preview returns a stable `payload_hash` and stores it on the plan.

**Step 2: Run test to verify failure**

```bash
uv run pytest tests/unit/jira/test_transition_planning.py -q
```

Expected: preview method missing.

**Step 3: Implement preview methods**

Add:

```python
def update_transition_plan(
    self,
    plan: TransitionPlan,
    field_values: dict[str, Any],
    cleared_fields: list[str] | None = None,
) -> TransitionPlan:
    ...


def preview_transition_plan(self, plan: TransitionPlan) -> dict[str, Any]:
    ...
```

Preview output must include:

- `payload`
- `field_sources`
- `changed_fields`
- `unchanged_reused_fields`
- `destructive_changes`
- `missing_fields`
- `preview_id`
- `payload_hash`

Compute `payload_hash` from a canonical JSON serialization of the exact payload
that would be submitted. Store `last_preview_id` and `last_payload_hash` on the
plan when preview succeeds.

**Step 4: Run tests**

```bash
uv run pytest tests/unit/jira/test_transition_planning.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/mcp_atlassian/jira/transition_planning.py tests/unit/jira/test_transition_planning.py
git commit -m "feat(jira): preview transition plans"
```

## Task 8: Add Stale Checks and Apply

**Files:**
- Modify: `src/mcp_atlassian/jira/transition_planning.py`
- Test: `tests/unit/jira/test_transition_planning.py`

**Step 1: Write failing apply tests**

Cover:

- Status changed -> hard stale.
- Transition unavailable -> hard stale.
- Schema hash changed -> hard stale.
- New high-weight assignee comment -> reconfirm required.
- Confirmed `payload_hash` missing or different from the latest preview -> apply
  refused.
- Valid plan calls `transition_issue`.

**Step 2: Run test to verify failure**

```bash
uv run pytest tests/unit/jira/test_transition_planning.py -q
```

Expected: apply method missing.

**Step 3: Implement stale check and apply**

Add:

```python
def validate_transition_plan_freshness(self, plan: TransitionPlan) -> dict[str, Any]:
    ...


def apply_transition_plan(
    self,
    plan: TransitionPlan,
    confirmed: bool = False,
    payload_hash: str | None = None,
) -> dict[str, Any]:
    ...
```

`apply_transition_plan` must:

- Call freshness validation.
- Call preview composition.
- Require `confirmed=True`.
- Require the caller-provided `payload_hash` to match the latest preview hash.
- Refuse missing fields or destructive changes without confirmation.
- Call existing `transition_issue`.

**Step 4: Run tests**

```bash
uv run pytest tests/unit/jira/test_transition_planning.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/mcp_atlassian/jira/transition_planning.py tests/unit/jira/test_transition_planning.py
git commit -m "feat(jira): apply transition plans safely"
```

## Task 9: Add MCP Server Tools

**Files:**
- Modify: `src/mcp_atlassian/servers/jira.py`
- Test: `tests/unit/servers/test_jira_server.py`

**Step 1: Write failing server tests**

Add tests for:

- `jira_prepare_transition`
- `jira_search_transition_field_options`
- `jira_update_transition_plan`
- `jira_preview_transition_plan`
- `jira_apply_transition_plan`

Use `mock_jira_fetcher` methods from prior tasks.

Also assert each tool has the intended annotations and stable JSON response
shape:

| Tool | `READ_ONLY_MODE` behavior | Required annotations |
| --- | --- | --- |
| `jira_prepare_transition` | Allowed; writes only local process memory. | `readOnlyHint=false`, `destructiveHint=false`, `idempotentHint=false`, `openWorldHint=true` |
| `jira_search_transition_field_options` | Allowed. | `readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=false`, `openWorldHint=true` |
| `jira_update_transition_plan` | Allowed unless local plan mutation is later classified as a server write. Does not write Jira. | `readOnlyHint=false`, `destructiveHint=false`, `idempotentHint=false`, `openWorldHint=false` |
| `jira_preview_transition_plan` | Allowed. | `readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=false`, `openWorldHint=false` |
| `jira_apply_transition_plan` | Blocked by `READ_ONLY_MODE=true`; must use `@check_write_access`. | `readOnlyHint=false`, `destructiveHint=true`, `idempotentHint=false`, `openWorldHint=true` |

**Step 2: Run test to verify failure**

```bash
uv run pytest tests/unit/servers/test_jira_server.py -q
```

Expected: tool not found.

**Step 3: Implement tools**

Add planning tools with names exposed as:

- `jira_prepare_transition`
- `jira_search_transition_field_options`
- `jira_update_transition_plan`
- `jira_preview_transition_plan`
- `jira_apply_transition_plan`

Only `jira_apply_transition_plan` writes to Jira and must use
`@check_write_access`. `jira_prepare_transition` and
`jira_update_transition_plan` mutate local process memory only.

Parameter style:

- JSON strings for nested objects, matching existing server patterns.
- Parse with existing `_parse_additional_fields`.
- Return JSON strings with `ensure_ascii=False`.
- Every response includes `success`, `status`, `warnings`, `next_actions`, and
  either operation data or a structured `error`.
- `jira_apply_transition_plan` requires `confirmed=True` and `payload_hash`
  matching the last preview.

**Step 4: Register tools in server tests**

Update test MCP setup to add the new tools.

**Step 5: Run server tests**

```bash
uv run pytest tests/unit/servers/test_jira_server.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/mcp_atlassian/servers/jira.py tests/unit/servers/test_jira_server.py
git commit -m "feat(jira): expose transition planning tools"
```

## Task 10: Add Cached Project Version Search Support

**Files:**
- Modify: `src/mcp_atlassian/jira/projects.py`
- Modify: `src/mcp_atlassian/servers/jira.py`
- Test: `tests/unit/jira/test_projects.py` or existing project tests
- Test: `tests/unit/servers/test_jira_server.py`

**Step 1: Write failing tests**

Test:

- `get_project_versions` uses a short-lived full-list cache per project.
- Repeated `get_project_versions(project_key)` calls within the TTL do not call
  Jira again.
- `force_refresh=True` bypasses and refreshes the cache.
- Limit defaults to 20.
- Query filters by version name.
- Released and archived filters work.
- Current selected version ids can be included even if not in first page.
- Search output includes `items`, `count`, `limit`, `has_more`, and
  `next_offset`.

**Step 2: Run tests**

```bash
uv run pytest tests/unit/servers/test_jira_server.py -q
```

Expected: failure until implemented.

**Step 3: Implement full-list cache and search**

Add cache support to project version retrieval:

```python
def get_project_versions(
    self,
    project_key: str,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    ...
```

Implementation notes:

- Cache the complete simplified version list in process memory by project key.
- Use a short TTL, for example 5 minutes.
- Return a copy of cached data so callers cannot mutate the cache.
- Keep the cache local to the current process. It is not shared across workers
  or restarts.
- Add a private helper if needed, for example `_get_cached_project_versions`.

Add paginated search:

Add:

```python
def search_project_versions(
    self,
    project_key: str,
    query: str | None = None,
    limit: int = 20,
    offset: int = 0,
    released: bool | None = None,
    archived: bool | None = None,
    include_ids: list[str] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    ...
```

Search uses `get_project_versions(project_key, force_refresh=force_refresh)`,
then filters and paginates locally. Return:

```json
{
  "items": [],
  "count": 0,
  "limit": 20,
  "offset": 0,
  "has_more": false,
  "next_offset": null
}
```

If later performance requires REST paging, replace internals without changing
the server tool contract.

**Step 4: Wire to option resolver**

`jira_search_transition_field_options` should call version search for
`version_picker` fields. It should expose `query`, `limit`, `offset`,
`include_ids`, and `force_refresh` parameters for version fields.

**Step 5: Run tests**

```bash
uv run pytest tests/unit/servers/test_jira_server.py tests/unit/jira -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/mcp_atlassian/jira/projects.py src/mcp_atlassian/servers/jira.py tests/unit/servers/test_jira_server.py
git commit -m "feat(jira): search project versions for transitions"
```

## Task 11: Add GYENNO Defect Analysis Profile

**Files:**
- Create: `src/mcp_atlassian/jira/transition_profiles.py`
- Test: `tests/unit/jira/test_transition_profiles.py`

**Step 1: Write failing tests**

Test:

- Profile maps the seven known fields.
- Profile identifies `完成分析` and `更新信息`.
- Profile enables soft required screen validation.

**Step 2: Run tests**

```bash
uv run pytest tests/unit/jira/test_transition_profiles.py -q
```

Expected: import failure.

**Step 3: Implement profile registry**

Add:

```python
def get_transition_profile(name: str | None) -> dict[str, Any]:
    ...
```

Include `gyenno_defect_analysis`.

**Step 4: Integrate profile**

`prepare_transition_plan` should use profile field semantics and soft-required
behavior when profile is provided.

**Step 5: Run tests**

```bash
uv run pytest tests/unit/jira/test_transition_profiles.py tests/unit/jira/test_transition_planning.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/mcp_atlassian/jira/transition_profiles.py tests/unit/jira/test_transition_profiles.py src/mcp_atlassian/jira/transition_planning.py
git commit -m "feat(jira): add defect analysis transition profile"
```

## Task 12: End-to-End Unit Scenario

**Files:**
- Test: `tests/unit/jira/test_transition_planning_e2e.py`

**Step 1: Write E2E unit test**

Use the provided transition and comment samples in reduced fixture form.

Scenario:

1. Prepare `RY-8714` with target `完成分析`.
2. Confirm fields are parsed.
3. Confirm version field requires lookup.
4. Confirm assignee comment has higher evidence weight.
5. Update plan with selected version.
6. Preview payload reuses current issue fields and returns `payload_hash`.
7. Apply with a mismatched hash is refused.
8. Apply with the matching hash calls `transition_issue` with expected payload.

Add one malicious-comment fixture that attempts to instruct the agent to ignore
required fields or apply without confirmation. The extractor may include the
comment as evidence text, but planning logic must not follow those instructions.

**Step 2: Run test**

```bash
uv run pytest tests/unit/jira/test_transition_planning_e2e.py -q
```

Expected: PASS after previous tasks.

**Step 3: Run focused suite**

```bash
uv run pytest tests/unit/jira/test_transition_schema.py tests/unit/jira/test_transition_comments.py tests/unit/jira/test_transition_planning.py tests/unit/jira/test_transition_planning_e2e.py -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add tests/unit/jira/test_transition_planning_e2e.py
git commit -m "test(jira): cover transition planning workflow"
```

## Task 13: Final Verification

**Files:**
- No new files unless fixes are required.

**Step 1: Run focused tests**

```bash
uv run pytest tests/unit/jira/test_transitions.py tests/unit/jira/test_transition_schema.py tests/unit/jira/test_transition_comments.py tests/unit/jira/test_transition_planning.py tests/unit/jira/test_transition_planning_e2e.py tests/unit/servers/test_jira_server.py -q
```

Expected: PASS.

**Step 2: Run lint on changed files**

```bash
uv run ruff check src/mcp_atlassian/jira src/mcp_atlassian/servers/jira.py tests/unit/jira tests/unit/servers/test_jira_server.py
```

Expected: PASS.

**Step 3: Run mypy on changed implementation files**

```bash
uv run mypy src/mcp_atlassian/jira/transition_schema.py src/mcp_atlassian/jira/transition_comments.py src/mcp_atlassian/jira/transition_plan_store.py src/mcp_atlassian/jira/transition_planning.py src/mcp_atlassian/servers/jira.py
```

Expected: PASS or only pre-existing unrelated errors documented clearly.

**Step 4: Produce manual test notes**

Document a dry-run sequence:

```text
jira_prepare_transition(issue_key="RY-8714", target_transition_name="完成分析", profile="gyenno_defect_analysis")
jira_search_transition_field_options(plan_id, field_key="customfield_11405", query="V2.13", limit=20)
jira_update_transition_plan(plan_id, field_values={"customfield_11405": [{"id": "..."}]})
preview = jira_preview_transition_plan(plan_id)
jira_apply_transition_plan(plan_id, confirmed=true, payload_hash=preview.payload_hash)
```

**Step 5: Commit final fixes if requested**

```bash
git add <changed-files>
git commit -m "feat(jira): complete transition planning workflow"
```
