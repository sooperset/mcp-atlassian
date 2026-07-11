# Implementation Plan: Tool Call Audit Logging

## Overview

Implement a `ToolCallLoggingMiddleware` that subclasses `fastmcp.server.middleware.Middleware` and intercepts tool calls via the `on_call_tool` hook to emit structured audit log entries. The middleware extracts source IP, username, and masks sensitive fields before logging. Registration is gated by the `MCP_AUDIT_LOG_ENABLED` environment variable.

## Tasks

- [x] 1. Create audit middleware module with core class and helpers
  - [x] 1.1 Create `src/mcp_atlassian/servers/audit.py` with `ToolCallLoggingMiddleware` class
    - Subclass `fastmcp.server.middleware.Middleware`
    - Define `__init__` accepting `sensitive_patterns: list[str] | None` and `max_body_length: int = 2048`
    - Store default sensitive patterns: `["token", "password", "secret", "key", "credential", "auth"]`
    - Merge additional patterns from constructor parameter
    - Create dedicated logger `logging.getLogger("mcp-atlassian.audit")`
    - Implement `on_call_tool(self, context: MiddlewareContext, call_next)` as the only overridden hook
    - _Requirements: 1.2, 1.3, 5.3_

  - [x] 1.2 Implement `_extract_source_ip` helper method
    - Access ASGI scope from `context.request` to get connection scope headers
    - Check for `X-Forwarded-For` header, use first comma-separated IP if present
    - Fall back to scope `client` tuple first element
    - Fall back to `"unknown"` if neither available
    - Strip leading/trailing whitespace from result
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 1.3 Implement `_extract_username` helper method
    - Read `user_atlassian_auth_type` from request state
    - For `"basic"`: extract email from decoded Authorization header (portion before first `:`), fall back to `"anonymous"`
    - For `"pat"`: use `user_atlassian_email` from state, fall back to `"pat-user"`
    - For `"oauth"`: use `user_atlassian_email` from state, fall back to `"oauth-user"`
    - When no auth type is set: return `"anonymous"`
    - No network calls allowed
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 1.4 Implement `_mask_arguments` helper method
    - Accept tool arguments dictionary
    - For each top-level key, check case-insensitive substring match against sensitive patterns
    - If match: apply `mask_sensitive(str(value))` from `mcp_atlassian.utils.logging`
    - If no match and value is a dict: inspect nested keys for sensitive patterns (1 level deep only)
    - Convert non-string values to string before masking
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

  - [x] 1.5 Implement `_serialize_body` helper method
    - JSON-serialize masked arguments as single-line string (no newlines/control chars)
    - Measure original content length before JSON serialization
    - If exceeds `max_body_length`, truncate serialized output to threshold and append `...truncated`
    - Use `default=repr` for non-serializable values
    - Return `{}` for empty/None arguments
    - _Requirements: 5.4, 5.5, 5.6_

  - [x] 1.6 Wire `on_call_tool` to emit structured log and delegate
    - Extract source IP, tool name, username, and masked/serialized body
    - Emit log at INFO level in format: `<source_ip> <tool_name> <username> <request_body>`
    - Wrap logging in try/except: on failure, log WARNING to application logger and ensure it's written before proceeding
    - Call `call_next(context)` to delegate to downstream handler
    - Do not modify arguments passed downstream
    - Do not catch/suppress exceptions from downstream
    - Only emit warnings when audit logging actually fails, not during normal operation
    - _Requirements: 5.1, 5.2, 6.1, 6.2, 6.3, 6.4_

- [x] 2. Implement factory function and server registration
  - [x] 2.1 Add `create_audit_middleware()` factory function in `src/mcp_atlassian/servers/audit.py`
    - Read `MCP_AUDIT_LOG_ENABLED` env var; return `None` if falsy (`false`, `0`, `no`, case-insensitive)
    - Return middleware instance if unset or truthy (`true`, `1`, `yes`, case-insensitive)
    - Parse `MCP_AUDIT_SENSITIVE_FIELDS` as comma-separated list, trim whitespace, discard empty entries
    - If malformed, skip additional patterns and use only defaults
    - Parse `MCP_AUDIT_MAX_BODY_LENGTH`; use value if integer ≥ 64, otherwise default to 2048
    - _Requirements: 1.4, 7.1, 7.2, 7.3, 7.4, 4.4_

  - [x] 2.2 Register middleware in `src/mcp_atlassian/servers/main.py`
    - Import `create_audit_middleware` from `.audit`
    - Call factory and register via `mcp.add_middleware()` during server construction
    - Ensure registration happens before any tool call is processed
    - _Requirements: 1.1, 1.4_

- [x] 3. Checkpoint - Verify core implementation
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add property-based tests with Hypothesis
  - [x] 4.1 Add `hypothesis` to dev dependencies in `pyproject.toml`
    - Add `"hypothesis>=6.0.0"` to the dev dependency group
    - _Requirements: Testing infrastructure_

  - [x] 4.2 Write property test for configuration gating (Property 1)
    - **Property 1: Configuration gating**
    - **Validates: Requirements 1.4, 7.1**
    - Test that factory returns middleware for truthy/unset values and `None` for falsy values
    - Use Hypothesis strategies for generating truthy/falsy string variants

  - [x] 4.3 Write property test for source IP extraction (Property 2)
    - **Property 2: Source IP extraction**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    - Generate ASGI scopes with/without client tuples and X-Forwarded-For headers
    - Verify precedence: X-Forwarded-For > scope client > "unknown"
    - Verify whitespace stripping

  - [x] 4.4 Write property test for username extraction (Property 3)
    - **Property 3: Username extraction**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    - Generate request states with various auth types and email values
    - Verify correct fallback behavior for each auth type

  - [x] 4.5 Write property test for sensitive field masking (Property 4)
    - **Property 4: Sensitive field masking**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    - Generate argument dictionaries with mixed sensitive/non-sensitive field names
    - Verify sensitive fields are masked and non-sensitive fields are unchanged

  - [x] 4.6 Write property test for depth-limited nested masking (Property 5)
    - **Property 5: Depth-limited nested masking**
    - **Validates: Requirements 4.5, 4.6**
    - Generate nested dictionaries with sensitive keys at various depths
    - Verify masking applies only to 1 level of nesting

  - [x] 4.7 Write property test for log format (Property 6)
    - **Property 6: Log format and single-line serialization**
    - **Validates: Requirements 5.1, 5.4**
    - Generate valid IPs, tool names, usernames, and arguments
    - Verify output matches `<ip> <tool_name> <username> <json_body>` with no embedded newlines

  - [x] 4.8 Write property test for body truncation (Property 7)
    - **Property 7: Body truncation**
    - **Validates: Requirements 5.5, 7.3, 7.4**
    - Generate arguments of varying sizes and threshold values
    - Verify truncation behavior and `...truncated` suffix

  - [x] 4.9 Write property test for transparent delegation (Property 8)
    - **Property 8: Transparent delegation**
    - **Validates: Requirements 6.1, 6.2, 6.3**
    - Verify downstream handler receives unmodified arguments
    - Verify exceptions propagate unchanged

  - [x] 4.10 Write property test for graceful degradation (Property 9)
    - **Property 9: Graceful degradation on logging failure**
    - **Validates: Requirements 6.4**
    - Simulate logging failures and verify WARNING is emitted before delegation
    - Verify no warnings during normal successful operation

  - [x] 4.11 Write property test for sensitive fields env var parsing (Property 10)
    - **Property 10: Sensitive fields environment variable parsing**
    - **Validates: Requirements 4.4, 7.2**
    - Generate comma-separated strings with whitespace, empty entries, and malformed data
    - Verify correct parsing and fallback behavior

- [x] 5. Add unit tests for specific behaviors
  - [x] 5.1 Write unit tests in `tests/unit/servers/test_audit.py`
    - Test middleware subclasses `fastmcp.server.middleware.Middleware`
    - Test only `on_call_tool` is overridden (no other hooks)
    - Test log level is INFO
    - Test logger name is `mcp-atlassian.audit`
    - Test empty arguments produce `{}`
    - Test no network calls (no httpx/requests imports in module)
    - Test middleware enabled by default when env var unset
    - Test warning only emitted on actual failure, not on success
    - Test malformed `MCP_AUDIT_SENSITIVE_FIELDS` falls back to defaults only
    - _Requirements: 1.2, 1.3, 5.2, 5.3, 5.6, 3.6, 1.4, 6.4, 4.4_

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Update documentation
  - [x] 7.1 Add audit logging section to `README.md`
    - Add "Audit Logging" section describing the feature and log entry format
    - Include environment variables table with types, defaults, and descriptions
    - Document default sensitive field patterns and customization via `MCP_AUDIT_SENSITIVE_FIELDS`
    - Explain username resolution for each auth method (Basic, PAT, OAuth) with fallback values
    - _Requirements: 8.1, 8.2, 8.4, 8.5_

  - [x] 7.2 Update `.env.example` with audit logging variables
    - Add commented-out `MCP_AUDIT_LOG_ENABLED=true` with description
    - Add commented-out `MCP_AUDIT_SENSITIVE_FIELDS=` with description
    - Add commented-out `MCP_AUDIT_MAX_BODY_LENGTH=2048` with description
    - _Requirements: 8.3_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The middleware operates at the FastMCP middleware layer (not ASGI), relying on `UserTokenMiddleware` for auth state
- Uses existing `mask_sensitive` utility from `mcp_atlassian.utils.logging`
- Python ≥ 3.10 with type hints required per project conventions

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "4.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5"] },
    { "id": 2, "tasks": ["1.6"] },
    { "id": 3, "tasks": ["2.1"] },
    { "id": 4, "tasks": ["2.2"] },
    { "id": 5, "tasks": ["4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9", "4.10", "4.11", "5.1"] },
    { "id": 6, "tasks": ["7.1", "7.2"] }
  ]
}
```
