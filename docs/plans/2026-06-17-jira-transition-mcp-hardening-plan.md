# Jira Transition MCP Hardening Plan

## Goal

Tighten the first Jira transition planning implementation so it better follows MCP
best practices while keeping the second round deliberately small. This round is
about context control, actionable recovery, and safer workflow guidance. It does
not redesign the transition planner or add a full structured-output contract.

## Scope

Implement the minimal hardening set selected for round two:

- Make `jira_get_transitions` compact by default so large `allowedValues` lists do
  not flood MCP responses.
- Add clearer failure statuses and `next_actions` for transition workflow tools.
- Run freshness validation during preview, not only during apply.
- Limit `include_ids` so selected version echoing cannot bypass pagination.
- Mark `jira_transition_issue` as the low-level direct write path and steer
  complex transitions toward the plan/preview/apply workflow.
- Add focused regression tests for these behavior changes.

## Non-Goals

- Do not add MCP `outputSchema` or structured content in this round.
- Do not implement generic lookup for every Jira option field yet.
- Do not replace the existing direct `jira_transition_issue` tool.
- Do not change persistence beyond the existing in-memory plan store.
- Do not solve Jira-side server pagination for versions unless the existing API
  surface already exposes it cheaply.

## Task 1: Compact `jira_get_transitions`

Change the transition listing so the default response is safe for high-cardinality
fields. The compact response should keep enough information for an agent to choose
the next workflow step without embedding hundreds of options.

Default response shape per transition:

- `id`
- `name`
- `to`
- `has_screen`
- `fields` summary only when transition fields are requested
- `required_fields`

For fields with `allowedValues`, return metadata instead of the full list:

- `allowed_values_sample`: first small sample, for example 10 items
- `allowed_values_count`
- `allowed_values_truncated`
- `lookup_tool` when the field can be resolved through
  `jira_search_transition_field_options`

Compatibility option:

- Add a parameter such as `response_mode: "compact" | "full" = "compact"` or
  `include_fields: bool = false`.
- Prefer `response_mode` if it fits existing server style; it makes the behavior
  explicit and future-friendly.

Tests:

- Existing tests for transition fields should expect truncated metadata by
  default.
- Add a regression with a version field containing hundreds of allowed values.
- Add a compatibility test for full mode if full mode is retained.

## Task 2: Actionable Workflow Errors

Update transition workflow server responses so common failure states tell the
agent what to do next. Keep the existing JSON response envelope:

- `success`
- `status`
- `warnings`
- `next_actions`
- `error`

Minimum status mapping:

- `not_found` -> `["jira_prepare_transition"]`
- `field_not_found` -> `["inspect_plan_fields", "jira_update_transition_plan"]`
- `unsupported_field_type` -> `["provide_field_value_directly"]`
- `confirmation_required` -> `["jira_preview_transition_plan", "jira_apply_transition_plan"]`
- `payload_hash_mismatch` -> `["jira_preview_transition_plan", "jira_apply_transition_plan"]`
- `missing_fields` -> `["jira_update_transition_plan", "jira_preview_transition_plan"]`
- `reconfirmation_required` -> `["review_new_context", "jira_preview_transition_plan"]`
- `stale` -> `["jira_prepare_transition"]`
- generic `failed` -> include the most conservative recovery action for that
  tool, usually `["jira_prepare_transition"]` or `["retry_after_review"]`

Tests:

- Add focused server tests for `not_found`, hash mismatch, missing fields, and
  stale responses.
- Keep failures as tool-result JSON rather than protocol-level exceptions.

## Task 3: Preview Freshness Gate

Preview should not become the user's confirmation surface if the plan is already
stale. Reuse the existing `validate_transition_plan_freshness()` logic before
building the preview payload.

Behavior:

- If freshness returns `hard_stale`, mark the plan stale and return a response
  that asks for a new prepare step.
- If freshness returns `requires_reconfirmation`, include freshness information
  in the preview response and require the agent/user to review the new context
  before apply.
- If fresh, include a lightweight `freshness` object in the preview response.

Tests:

- Preview rejects changed issue status/schema/updated timestamp.
- Preview surfaces edited or new high-value assignee comments.
- Apply behavior remains unchanged and still performs its own freshness check.

## Task 4: Bound `include_ids`

`include_ids` exists so already selected versions stay visible even when they are
outside the current page. It should not become a second unbounded result channel.

Behavior:

- Limit `include_ids` to at most 20 ids.
- If more are provided, keep the first 20 and return metadata:
  `include_ids_truncated`, `requested_include_ids_count`,
  `included_selected_count`.
- Keep the normal `limit` behavior unchanged for the search page itself.

Tests:

- Version search includes selected ids outside the current page.
- More than 20 selected ids are truncated.
- Response metadata reports truncation clearly.

## Task 5: Clarify Direct Transition Tool

Keep `jira_transition_issue`, but make its contract explicit:

- It is the low-level direct write path.
- It is suitable for simple transitions when the caller already knows the
  transition id and required payload.
- For transitions with screens, required fields, high-cardinality pickers, or
  user-facing confirmation, agents should prefer:
  `jira_prepare_transition` -> `jira_update_transition_plan` /
  `jira_search_transition_field_options` -> `jira_preview_transition_plan` ->
  `jira_apply_transition_plan`.

Also ensure annotations are explicit:

- `readOnlyHint: false`
- `destructiveHint: true`
- `idempotentHint: false`
- `openWorldHint: true`

Tests:

- Assert annotations for `jira_transition_issue`.
- Assert its description mentions the planning workflow.

## Verification

Run focused tests first:

```bash
uv run pytest tests/unit/jira/test_transitions.py tests/unit/jira/test_projects.py tests/unit/jira/test_transition_planning.py tests/unit/servers/test_jira_server.py -q
```

Run type and lint checks for touched implementation files:

```bash
uv run mypy src/mcp_atlassian/jira/transitions.py src/mcp_atlassian/jira/projects.py src/mcp_atlassian/jira/transition_planning.py
uv run ruff check src/mcp_atlassian/jira/transitions.py src/mcp_atlassian/jira/projects.py src/mcp_atlassian/jira/transition_planning.py tests/unit/jira/test_transitions.py tests/unit/jira/test_projects.py tests/unit/jira/test_transition_planning.py
```

Because `src/mcp_atlassian/servers/jira.py` has existing lint debt, run targeted
tests and report any pre-existing whole-file lint failures separately.

## Acceptance Criteria

- Default transition listing no longer returns hundreds of version options.
- Transition workflow errors give concrete next actions.
- Preview detects stale plans before presenting a payload for confirmation.
- Version option lookup cannot inflate responses through unbounded `include_ids`.
- The direct transition tool clearly signals that the planning workflow is safer
  for complex transitions.
- Focused unit tests pass.
