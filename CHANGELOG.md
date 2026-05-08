# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Privacy filter** (`src/mcp_atlassian/privacy/`) — opt-in, environment-configured
  output filter that runs on every tool response via FastMCP middleware. Off by
  default; enabled with `PRIVACY_FILTER_ENABLED=true`.

  Capabilities:

  - **PII redaction** in any string within tool output. Built-in regex patterns
    for `email`, `phone`, `ipv4`, `iban`, `credit_card`. Custom regexes via
    `PRIVACY_PII_CUSTOM_REGEX`.
  - **Optional Microsoft Presidio engine** (`PRIVACY_USE_PRESIDIO=true`) for
    NER-based detection of names, locations, etc. Soft-imported — installing the
    package alone is a no-op; the env var without the package surfaces a clear
    install hint. Available as the `privacy-nlp` extra.
  - **Field rules** with glob wildcards (`*`, `**`, partial). Drop fields with
    `PRIVACY_DROP_FIELDS`, mask with `PRIVACY_MASK_FIELDS` (token configurable
    via `PRIVACY_MASK_TOKEN`, default `[REDACTED]`). Per-resource scoping
    (`jira_issue_list:issues.*.assignee`) or wildcard (`*:**.email`).
  - **Resource denylists** drop entire issues/pages/comments by label, space
    key, or project key (`PRIVACY_DENY_LABELS`, `PRIVACY_DENY_SPACE_KEYS`,
    `PRIVACY_DENY_PROJECT_KEYS`).
  - **Telemetry**: one structured DEBUG log per changed call, summarising
    counters (`resources_dropped`, `fields_dropped`, `fields_masked`,
    `pii_redactions`). Calls with no changes are silent.

  Design properties:

  - **Upstream-resilient.** Operates on serialized tool responses (after
    FastMCP serialization), not on internal model classes. Survives upstream
    mixin/model refactors.
  - **Stateless per call.** Pipeline, redactors, and compiled regexes are
    immutable after construction; per-call state lives on a fresh
    `FilterStats`. Verified by 5 concurrency tests asserting no cross-talk
    between 100 parallel calls.
  - **Single-pass filtering.** When FastMCP duplicates a tool return into
    both `structured_content` and a serialized text block, the middleware
    extracts the canonical input value (parsing JSON-string wraps so field
    rules reach the actual structure), runs the pipeline once, and projects
    the filtered result back into both outputs.
  - **Performance.** Full pipeline at ~92 µs per Jira issue on a 1000-issue
    payload (developer laptop). Performance tests fail loudly on regressions
    via documented thresholds; opt-in via `pytest -m performance`.
  - **Comprehensive `.env.example`** with real-world recipes for Jira and
    Confluence, both regex and Presidio. Examples are validated by tests.

  Tests: 272 unit tests covering config parsing, pattern matching, glob
  semantics, pipeline ordering, FastMCP integration, upstream tool shapes,
  documented `.env.example` examples, telemetry, performance thresholds,
  and concurrency.

### Changed

- `src/mcp_atlassian/servers/main.py`: registers the privacy middleware on
  `main_mcp` at startup. Two-line change; no-op when the filter is disabled.
- `.env.example`: added a fully documented `PRIVACY_*` section with worked
  examples for both regex and Presidio engines.
- `pyproject.toml`: added `privacy-nlp` optional dependency
  (`presidio-analyzer`) and a `performance` pytest marker.
