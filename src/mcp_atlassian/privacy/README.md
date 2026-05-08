# `mcp_atlassian.privacy`

Opt-in privacy filter for MCP Atlassian tool responses. Strips PII /
drops or masks fields / removes denied resources from every tool response
before it reaches the LLM.

> User-facing reference and worked examples live in `.env.example`. This
> document is for contributors extending the module.

---

## Architecture

The filter is a **FastMCP middleware** registered on `AtlassianMCP` from
inside `servers/main.py`. Choosing the FastMCP middleware boundary as the
hook (over per-mixin code or `to_simplified_dict()` overrides) is
intentional:

- It is the smallest, most stable surface — `Middleware.on_call_tool` is
  part of FastMCP's documented API and survives any upstream
  Jira/Confluence model or mixin refactor.
- It operates on already-serialized JSON, so the filter has zero coupling
  to upstream model classes (no imports from `mcp_atlassian.{jira,
  confluence,models}`; verifiable by `grep -r 'from mcp_atlassian' src/
  mcp_atlassian/privacy/`).
- New upstream tools automatically benefit from PII redaction without
  any change to this module — only field rules need a `tool_map.py`
  entry, and even then the default is to gracefully skip rules.

```text
                 ┌────────────────────────────────────────────┐
   tool call ──▶ │  AtlassianMCP (FastMCP)                    │
                 │   ├─ UserTokenMiddleware (auth)            │
                 │   └─ PrivacyFilterMiddleware  ◀─── this    │
                 │        │                                    │
                 │        ▼                                    │
                 │   call_next  ─▶ tool fn  ─▶ ToolResult     │
                 │        │                                    │
                 │        ▼                                    │
                 │   PrivacyPipeline.apply_with_stats          │
                 │        │                                    │
                 │        ▼                                    │
                 │   filtered ToolResult ─────────────────────▶
                 └────────────────────────────────────────────┘
```

## Pipeline order

`PrivacyPipeline.apply_with_stats(tool_name, value)` runs three stages in
this order:

1. **`ResourceFilter`** — drops items by `labels` / `space.key` /
   `project.key`. Operates at top level (single-resource responses) AND
   on every list item (search/list responses).
2. **`FieldFilter`** — drops or masks specific paths per resource type
   (or globally via the `"*"` resource key). Glob path syntax: `*` for
   one segment, `**` for zero-or-more segments, `user_*` for partial
   wildcards within a segment.
3. **PII redactor** — regex sweep + optional Presidio NER over every
   string in what survives. Activated by `PRIVACY_PII_PATTERNS` /
   `PRIVACY_PII_CUSTOM_REGEX` and (optionally) `PRIVACY_USE_PRESIDIO=true`.

Order matters: cheap drops first, then per-field rules, then a costly
recursive string sweep over a smaller payload.

## File map

| File | Responsibility |
| --- | --- |
| `__init__.py` | Public API (`install_privacy_filter`, `PrivacyConfig`, `FilterStats`) |
| `config.py` | `@dataclass PrivacyConfig` + `from_env()` parser |
| `patterns.py` | Built-in regex set: email, phone, IPv4, IBAN, credit_card |
| `pii_redactor.py` | `Redactor` Protocol; `RegexRedactor`, `PresidioRedactor` (soft-import), `CompositeRedactor`; `build_redactor()` selector |
| `field_filter.py` | `FieldFilter` + `_GlobMatcher` (glob path matching) |
| `resource_filter.py` | `ResourceFilter` (top-level + list-item denylist) |
| `tool_map.py` | Tool-name → resource-type map (the only file coupled to upstream tool names) |
| `pipeline.py` | `PrivacyPipeline` orchestrator (compose 3 stages) |
| `middleware.py` | `PrivacyFilterMiddleware` — wraps `ToolResult` and emits telemetry |
| `stats.py` | `FilterStats` dataclass — counters threaded through the pipeline |

## How to extend

### Add a new built-in PII pattern

1. Add the regex to `patterns.py`:

   ```python
   SLACK_TOKEN: re.Pattern[str] = re.compile(r"\bxox[bpoa]-...\b")
   BUILTIN_PATTERNS["slack_token"] = SLACK_TOKEN
   ```

2. Document the new name in `.env.example` (built-in patterns table).
3. Add a parametrized test case to `test_patterns.py` covering happy +
   negative samples.
4. Add an entry to `test_documented_examples.py::TestBuiltinPatternsAreDocumented`
   so future doc drift is caught.

### Add a new tool → resource-type mapping

When upstream adds a new tool returning an existing resource shape:

1. Pick (or add) a resource-type constant in `tool_map.py`.
2. Add the `"new_tool_name": EXISTING_TYPE` entry to
   `TOOL_RESOURCE_TYPES`.
3. Add the tool name to the resource-type listing in `.env.example`
   (sections 4 & 5).
4. Verify with `test_tool_map.py` — the test asserting wildcard rules
   apply for every mapped tool will catch you forgetting one.

Unknown tools are not an error: PII redaction and resource filtering
still run; field rules safely skip.

### Add a new filter stage

If you need a fourth stage (e.g. content-classifier-based redaction):

1. Build it as a class with `apply(value, *, stats)` matching the
   existing pattern.
2. Wire it into `PrivacyPipeline.__init__` and `apply_with_stats`.
3. Add a counter field to `FilterStats` if it makes a distinct kind of
   change, and update `summary()` accordingly.
4. Tests: at minimum a per-stage unit test, an `apply_with_stats`
   aggregation test, and a `test_documented_examples` end-to-end test.

## Telemetry

The middleware emits one `DEBUG` log line per tool call when the
pipeline modified the response:

```
DEBUG mcp_atlassian.privacy.middleware: privacy filter applied:
  tool=jira_search resources_dropped=2 fields_dropped=4 fields_masked=1 pii_redactions=7
```

Calls where the pipeline made no changes are silent. The log is
structured so it can be parsed by ops tooling without regex acrobatics.
For cumulative metrics (e.g. Prometheus counters), wrap
`PrivacyFilterMiddleware` and aggregate `FilterStats` across calls — out
of scope for this module.

## Activation contract

`install_privacy_filter(server, config=None)` returns:

- `True` — middleware was registered. The pipeline has at least one
  active rule.
- `False` — nothing registered. Either the master toggle is off, or all
  rule lists are empty (a "no-op pipeline").

Both Presidio activation conditions must hold:

1. `PRIVACY_USE_PRESIDIO=true` is set, AND
2. `presidio-analyzer` is importable.

If only (1) holds, `build_redactor` raises a `RuntimeError` at startup
with an "install `mcp-atlassian[privacy-nlp]`" message — failing fast
beats silent degradation.

## What this module deliberately does **not** do

- It does **not** filter inputs. Tool arguments going to Atlassian are
  unchanged; only responses to the LLM are filtered.
- It does **not** import upstream models. Field rules are dot-path
  matches against the serialized JSON, not attribute lookups on
  Pydantic objects.
- It does **not** filter binary content blocks (images, audio,
  resources). PII regex applies to text only.
- It does **not** maintain cumulative metrics. Per-call `FilterStats`
  are emitted via debug log; cumulative aggregation is the caller's
  responsibility.
- It does **not** filter wrapper-shaped resources at the top level
  (e.g. `confluence_get_page`'s `{"metadata": ..., "content": ...}`
  envelope). Use field rules with paths like `metadata.space.key` for
  those — this is documented in `.env.example`.
