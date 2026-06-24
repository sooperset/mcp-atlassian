# Jira Transition Planning Design

## Goal

Turn Jira transition support from a direct API wrapper into a guided workflow
that can help finish issue status handling after work is complete.

The first implementation should use generic Jira transition schema parsing, then
apply optional workflow profiles for business-specific fields. The first
validated profile is `gyenno_defect_analysis`, using the real transitions
`更新信息` and `完成分析`.

## Non-Goals

- Do not build a visual MCP App in the first version.
- Do not make the open-source MCP server depend on local git workspaces.
- Do not automatically choose high-risk values such as release versions.
- Do not persist transition plans across server restarts in the first version.
- Do not support multi-process or multi-worker transition plan sharing in the
  first version. The first version is scoped to one local MCP server process.
- Do not implement complex `add` or `remove` update operations unless the user
  explicitly requests them.

## Existing Inputs

The current repository already has these building blocks:

- `jira_get_transitions`: returns transitions from
  `transitions?expand=transitions.fields`.
- `jira_transition_issue`: executes a transition with `fields`, `comment`, and
  `update_data`.
- `jira_get_project_versions`: returns project versions.
- `ProjectsMixin.get_project_versions`: can be wrapped with a short-lived
  in-process full-list cache so transition option lookup does not repeatedly
  fetch all project versions from Jira.
- `jira_get_field_options`: returns selectable custom field options.
- `jira.issue_get_comments(issue_key)`: returns raw comments through the
  Atlassian Python API.

The browser extension `AutoFill Jira Remark` provides the desired behavior
pattern:

- Render fields based on Jira schema.
- Collect payload values based on Jira schema.
- Load version options separately.
- Reuse current issue field values when previewing and submitting.
- Validate visible transition screen fields before submit.

## Proposed Tools

Add five tools around the existing direct execution tool.

### `jira_prepare_transition`

Builds a transition plan.

Inputs:

```json
{
  "issue_key": "RY-8714",
  "target_transition_name": "完成分析",
  "profile": "gyenno_defect_analysis",
  "work_context": {
    "change_summary": "...",
    "changed_files": ["..."],
    "verification": ["..."],
    "risk_notes": ["..."]
  }
}
```

Responsibilities:

- Read issue details.
- Read available transitions with `expand=transitions.fields`.
- Resolve the target transition by id, name, or target status.
- Parse transition fields into interaction metadata.
- Read comments using `jira.issue_get_comments(issue_key)`.
- Classify comments into evidence categories.
- Generate field drafts where evidence is strong enough.
- Store a short-lived plan and return `plan_id`.
- `plan_id` must be an unguessable random token, scoped to the current
  authenticated user or tenant when identity is available.

### `jira_search_transition_field_options`

Resolves large or dynamic option sets for a field in a plan.

Supported first-version field types:

- Project versions for `array + items=version`.
- Static `allowedValues` for option and multi-option fields.
- Jira users for user fields, if needed.

Version fields must not dump hundreds of `allowedValues` into the main plan.
They return a lookup hint and are queried on demand. Project version lookup uses
the cached full version list for the project, then filters and paginates in
memory. The cache should have a short TTL and a force-refresh path so repeated
lookups do not call Jira for every request.

### `jira_update_transition_plan`

Applies user choices or edited text to a plan.

It must distinguish between:

- User explicitly set a value.
- User explicitly cleared a value.
- User left the current issue value unchanged.

### `jira_preview_transition_plan`

Composes the final Jira transition payload without writing to Jira.

It must show:

- The exact payload.
- Field sources.
- Changed fields.
- Reused unchanged fields.
- Destructive changes.
- Missing required or effectively required fields.

### `jira_apply_transition_plan`

Revalidates the plan and executes the transition.

It must call the existing transition execution path only after stale checks and
field validation pass. The caller must provide the last preview `payload_hash`
or `preview_id`, and apply must refuse to submit if the current preview differs
from what the user confirmed.

## MCP Tool Contract

The repository currently returns JSON strings from FastMCP tools. The first
version can keep that style for consistency, but each response must have a
stable machine-readable shape. Every successful or failed planning response
should include:

- `success`: boolean.
- `status`: current plan or operation status.
- `next_actions`: concrete suggested follow-up tool calls or user choices.
- `warnings`: non-fatal concerns.
- `error`: structured error object when `success=false`.

Tool annotations:

| Tool | Read-only mode | MCP annotations |
| --- | --- | --- |
| `jira_prepare_transition` | Allowed. Writes only local process memory. | `readOnlyHint=false`, `destructiveHint=false`, `idempotentHint=false`, `openWorldHint=true` |
| `jira_search_transition_field_options` | Allowed. | `readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=false`, `openWorldHint=true` |
| `jira_update_transition_plan` | Allowed unless product policy decides local planning state also counts as a write. Does not write Jira. | `readOnlyHint=false`, `destructiveHint=false`, `idempotentHint=false`, `openWorldHint=false` |
| `jira_preview_transition_plan` | Allowed. Does not write Jira. | `readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=false`, `openWorldHint=false` |
| `jira_apply_transition_plan` | Blocked by `READ_ONLY_MODE=true`; must use `@check_write_access`. | `readOnlyHint=false`, `destructiveHint=true`, `idempotentHint=false`, `openWorldHint=true` |

`openWorldHint=true` is used whenever the tool reads Jira or exposes Jira-origin
content. Jira issue fields and comments are external, untrusted content.

## Field Schema Parsing

Use the same generic ordering as the browser extension.

| Jira schema | Interaction type | Payload format |
| --- | --- | --- |
| `type=user` | `user_auto_or_picker` | `{name}` or `{accountId}` |
| `type=array`, `items=version` | `version_picker` | `[{id}]` |
| `type=array`, `allowedValues` | `multi_option_picker` | `[{id}]` |
| `type=option` or `option-with-child` | `single_option_picker` | `{id}` |
| `type=string`, textarea or textfield custom type | `textarea` | string |
| `type=number` | `number_input` | number |
| unknown | `text_input` | fallback value |

The schema parser returns metadata, not UI HTML:

```json
{
  "field_key": "customfield_11405",
  "name": "引入版本",
  "schema": {
    "type": "array",
    "items": "version"
  },
  "interaction_type": "version_picker",
  "value_format": "array_of_id_objects",
  "required": false,
  "operations": ["set", "add", "remove"],
  "lookup_tool": "jira_search_transition_field_options"
}
```

## Profile Overrides

Generic parsing stays open-source friendly. Business semantics live in profiles.

First profile:

```yaml
gyenno_defect_analysis:
  transitions:
    complete_analysis: "完成分析"
    update_info: "更新信息"
  fields:
    customfield_11405:
      name: "引入版本"
      semantic: introduced_versions
      resolver: project_versions
    customfield_11407:
      name: "历史数据处理"
      semantic: historical_data_handling
      resolver: option_with_guidance
    customfield_10718:
      name: "缺陷产生原因"
      semantic: defect_causes
      resolver: cause_classifier
    customfield_10705:
      name: "根因描述"
      semantic: root_cause
      resolver: evidence_text
    customfield_11001:
      name: "短期应对措施"
      semantic: workaround
      resolver: evidence_text
    customfield_10706:
      name: "解决方案"
      semantic: solution
      resolver: work_summary
    assignee:
      name: "经办人"
      semantic: assignee
      resolver: current_or_existing_user
```

Profiles may add guidance, preferred defaults, or resolver choices. They must not
override Jira's live schema or allowed operations.

## Comment Evidence

`jira_prepare_transition` reads comments through:

```python
jira.issue_get_comments(issue_key)
```

The plan does not include all raw comments. It includes classified evidence.
Comment text is treated as untrusted external context. It may provide facts, but
instructions embedded in comments must not change tool behavior, override Jira
schema, bypass confirmation, or select destructive values.

Comment categories:

- `commit_reference`: GitLab or other VCS auto-linked commit comments.
- `assignee_analysis`: human comment authored by the current assignee.
- `human_analysis`: human comment from a non-assignee.
- `impact_scope`: comment describing affected modules, data, patients, scales,
  fields, versions, or test scope.
- `noise_or_system`: low-value system comments or duplicates.

Priority:

1. User explicit input.
2. Jira current issue fields and transition schema.
3. Current assignee human comments.
4. Caller-provided `work_context`.
5. Auto-linked commit comments.
6. Other human comments.
7. LLM inference.

Commit references are code evidence, not business analysis. For example, a
GitLab auto-linked comment by `admin` should produce a commit evidence object,
while an assignee comment listing affected scales should become high-weight
impact evidence.

Evidence item example:

```json
{
  "comment_id": "77717",
  "category": ["assignee_analysis", "impact_scope"],
  "weight": 11,
  "author": "jianghaitao",
  "reason": [
    "author is current assignee",
    "human-authored comment",
    "mentions affected scales and question ranges"
  ],
  "extracted_facts": [
    "副作用监测量表，第 61、68 题",
    "冲动控制障碍评分（AUIP-RS），第 1~4 题"
  ]
}
```

## Preview Payload Composition

Preview must follow the browser extension behavior: reuse issue fields that are
already filled.

For every field on the selected transition screen:

```text
final value =
  user explicit value
  else automatic draft with enough confidence
  else current issue value if present and schema-compatible
  else empty
```

Source priority:

1. User explicit input.
2. Automatic draft.
3. Current issue field value.
4. Empty.

Only fields on the selected transition screen are considered. Current issue
values outside the screen must not be blindly submitted.

Empty value rules:

- Current issue has value and user did not change it: reuse the current value.
- Current issue has value and user explicitly clears it: mark as destructive and
  require confirmation.
- Current issue is empty and field is required or effectively required: mark as
  `needs_user_input`.
- Current issue is empty and field is optional: omit it.

Preview output example:

```json
{
  "payload": {
    "transition": {"id": "771"},
    "fields": {
      "customfield_10705": "已有根因描述",
      "customfield_10706": "自动草拟解决方案",
      "customfield_11405": [{"id": "12345"}]
    }
  },
  "field_sources": {
    "customfield_10705": "current_issue",
    "customfield_10706": "auto_draft",
    "customfield_11405": "user_selection"
  },
  "unchanged_reused_fields": ["customfield_10705"],
  "changed_fields": ["customfield_10706", "customfield_11405"],
  "destructive_changes": [],
  "preview_id": "pv_...",
  "payload_hash": "sha256:..."
}
```

## Effective Required Fields

Hard required:

- Jira marks `required=true`.

Soft required:

- The field appears on the transition screen.
- The active profile enables screen-field validation.
- The field is not a user field that can be preserved or auto-filled.

The plan should distinguish hard and soft requirements so generic users are not
forced into GYENNO-specific strictness.

## Stale Checks

`jira_apply_transition_plan` must re-read Jira before submit.

Hard stale:

- Issue status changed.
- Target transition is no longer available.
- Transition field schema hash changed.

Reconfirmation required:

- A new high-weight assignee comment appeared after plan creation.
- A user field or version field changed since plan creation.

Warning only:

- New commit-reference system comment appeared.
- Non-screen issue fields changed.

The plan records:

```json
{
  "issue_updated": "...",
  "status_id": "3",
  "transition_id": "771",
  "schema_hash": "...",
  "latest_comment_id": "77717",
  "latest_comment_updated": "..."
}
```

## Plan Lifecycle

```text
created
needs_user_input
ready
previewed
applied
stale
failed
```

First version can use an in-memory TTL plan store. A 30 minute TTL is enough for
interactive use. The store key should include authenticated user identity where
available, so users cannot accidentally apply each other's plans.

This is intentionally a local, single-process design:

- Plans are invalid after server restart.
- Plans are not shared across multiple worker processes.
- `plan_id` values are random and unguessable, not derived only from issue key
  or transition id.
- Store entries are scoped by user or tenant when identity is available.
- A lightweight lock should protect store mutation because multiple MCP calls may
  arrive concurrently in the same process.

## Error Handling

- Invalid transition target: return available transitions.
- Missing required field: return field metadata and lookup hints.
- Invalid option or version id: return resolver hint and nearest candidates.
- Stale plan: return stale reason and suggest rerunning prepare.
- Preview mismatch: return the current `payload_hash` and require the user to
  preview and confirm again.
- Jira API rejection: return Jira error plus the previewed payload summary.
- Unsupported schema: mark field as `manual_text_input` or `cannot_submit`,
  depending on whether safe formatting is possible.

## First-Version Acceptance Criteria

Use the GYENNO defect analysis transition sample as the real validation path.

Acceptance criteria:

1. `jira_prepare_transition` can identify `更新信息` and `完成分析`.
2. It parses these fields:
   - `customfield_11405` (`引入版本`)
   - `customfield_11407` (`历史数据处理`)
   - `customfield_10718` (`缺陷产生原因`)
   - `customfield_10705` (`根因描述`)
   - `customfield_11001` (`短期应对措施`)
   - `customfield_10706` (`解决方案`)
   - `assignee` (`经办人`)
3. Version fields are not expanded into hundreds of values in the main plan.
4. Version candidates are resolved through a lookup tool with limit and query.
5. Project versions are fetched through a short-lived full-list cache and then
   filtered/paginated locally for transition lookup.
6. Current issue field values are reused in preview when the user did not change
   them.
7. Current assignee comments have higher analysis weight than auto-linked commit
   comments.
8. Preview shows payload, field sources, changed fields, reused fields,
   destructive changes, `preview_id`, and `payload_hash`.
9. Apply performs stale checks and verifies the confirmed preview hash before
   calling the Jira transition API.
10. MCP tool responses use stable JSON fields and correct annotations.
11. The existing `jira_transition_issue` tool remains available as a direct
   low-level escape hatch.

## Suggested Implementation Sequence

1. Add a transition field schema parser and formatter.
2. Add transition plan models and local single-process in-memory TTL store.
3. Add comment evidence extraction and commit-reference parsing.
4. Add `jira_prepare_transition`.
5. Add project version full-list cache and paginated version search.
6. Add `jira_search_transition_field_options`.
7. Add `jira_update_transition_plan`.
8. Add `jira_preview_transition_plan` with preview hashes.
9. Add `jira_apply_transition_plan`.
10. Add MCP tool contract tests and annotations.
11. Add the `gyenno_defect_analysis` profile.
12. Validate against the real GYENNO transition sample.
