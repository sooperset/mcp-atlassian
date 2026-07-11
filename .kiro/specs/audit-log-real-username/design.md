# Audit Log Real Username Bugfix Design

## Overview

The `ToolCallLoggingMiddleware` in `src/mcp_atlassian/servers/audit.py` emits audit log entries with a generic fallback username (`pat-user` or `oauth-user`) instead of the real user email. The root cause is a timing issue: the middleware extracts the username BEFORE calling `call_next(context)`, but the real email is only resolved during dependency injection inside `call_next` when `_create_and_validate()` backfills `request.state.user_atlassian_email`.

The fix moves the audit log emission to AFTER `call_next(context)` completes, so the email has been backfilled by dependency injection. The username is extracted after the tool runs, then the log entry is emitted.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — when a PAT or OAuth authenticated user invokes a tool and the middleware extracts the username before dependency injection has resolved the real email
- **Property (P)**: The desired behavior — audit log entries contain the real user email resolved during token validation
- **Preservation**: Existing behaviors that must remain unchanged — Basic auth logging, anonymous logging, error handling, argument masking, truncation, and enable/disable gating
- **ToolCallLoggingMiddleware**: The middleware class in `src/mcp_atlassian/servers/audit.py` that emits structured audit log entries for each tool call
- **UserTokenMiddleware**: The ASGI middleware in `src/mcp_atlassian/servers/main.py` that parses auth headers and sets initial `request.state` values (email is `None` for PAT/OAuth at this stage)
- **_create_and_validate()**: The function in `src/mcp_atlassian/servers/dependencies.py` that validates tokens and backfills `request.state.user_atlassian_email` with the real email
- **call_next(context)**: The FastMCP middleware chain delegation that triggers dependency injection and tool execution

## Bug Details

### Bug Condition

The bug manifests when a PAT or OAuth authenticated user invokes any MCP tool. The `ToolCallLoggingMiddleware.on_call_tool` method extracts the username from `request.state.user_atlassian_email` BEFORE calling `call_next(context)`. At that point, `UserTokenMiddleware` has only set `user_atlassian_auth_type` to `"pat"` or `"oauth"` and left `user_atlassian_email` as `None`. The real email is only populated later during dependency injection inside `call_next`.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ToolCallRequest with associated RequestState
  OUTPUT: boolean

  RETURN input.request.state.user_atlassian_auth_type IN ['pat', 'oauth']
         AND input.request.state.user_atlassian_email IS None
         AND username_extracted_before_call_next IS True
END FUNCTION
```

### Examples

- PAT user calls `jira_get_issue`: audit logs `192.168.1.1 jira_get_issue pat-user {...}` instead of `192.168.1.1 jira_get_issue user@company.com {...}`
- OAuth user calls `confluence_search`: audit logs `10.0.0.5 confluence_search oauth-user {...}` instead of `10.0.0.5 confluence_search admin@org.com {...}`
- PAT user with header-based auth calls `jira_search`: logs `pat-user` even though the Confluence `_on_validated` callback would have backfilled the email during `call_next`
- Basic auth user calls `jira_create_issue`: correctly logs `user@example.com` (NOT affected by this bug — email is available from the Authorization header before `call_next`)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Basic auth users must continue to have their email extracted from the Authorization header and logged correctly
- Unauthenticated requests must continue to log `anonymous` as the username
- Audit logging errors must continue to emit a warning and proceed without blocking the tool call
- Sensitive fields in tool arguments must continue to be masked before logging
- Serialized request bodies exceeding `max_body_length` must continue to be truncated with `...truncated`
- The `MCP_AUDIT_LOG_ENABLED` environment variable must continue to gate audit logging on/off
- Source IP extraction (X-Forwarded-For fallback to ASGI client) must remain unchanged
- Tool call results must be returned unchanged regardless of audit logging behavior

**Scope:**
All inputs that do NOT involve PAT or OAuth authentication (where email is initially `None`) should be completely unaffected by this fix. This includes:
- Basic auth requests (email already in Authorization header)
- Unauthenticated requests (no auth state)
- Requests where `user_atlassian_email` is already populated before `call_next`

## Hypothesized Root Cause

Based on the code analysis, the root cause is confirmed:

1. **Timing of username extraction**: In `on_call_tool`, the middleware calls `self._extract_username(context)` BEFORE `await call_next(context)`. At this point, `request.state.user_atlassian_email` is `None` for PAT/OAuth users because `UserTokenMiddleware._parse_auth_header` only sets `user_atlassian_auth_type` and `user_atlassian_token`, not the email.

2. **Email backfill happens inside call_next**: The `_create_and_validate()` function in `dependencies.py` calls `spec.validate_fn(fetcher)` which makes an API call to resolve the user identity. The `on_validated` callback (e.g., `_confluence_on_validated`) then sets `request.state.user_atlassian_email = validation_data["email"]`. This all happens INSIDE `call_next(context)`.

3. **Fallback logic masks the real issue**: The `_extract_username` method returns `"pat-user"` or `"oauth-user"` when `email` is `None`, which is always the case before dependency injection runs.

4. **No race condition**: This is purely a sequencing issue — the middleware logs too early in the request lifecycle.

## Correctness Properties

Property 1: Bug Condition - Real Email in Audit Log

_For any_ tool call where the authentication type is `pat` or `oauth` and dependency injection successfully resolves the user email during `call_next`, the fixed `on_call_tool` method SHALL log the resolved real email address as the username in the audit entry.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Non-PAT/OAuth Behavior Unchanged

_For any_ tool call where the authentication type is `basic` or absent (anonymous), the fixed `on_call_tool` method SHALL produce exactly the same audit log output as the original method, preserving Basic auth email extraction from the Authorization header and anonymous fallback behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/mcp_atlassian/servers/audit.py`

**Function**: `ToolCallLoggingMiddleware.on_call_tool`

**Specific Changes**:

1. **Move audit emission to after call_next**: Restructure `on_call_tool` so that `await call_next(context)` executes first, then extract the username and emit the audit log entry. This ensures dependency injection has backfilled `request.state.user_atlassian_email`.

2. **Extract pre-call data before call_next**: Source IP, tool name, and masked arguments can still be extracted before `call_next` since they don't depend on dependency injection. Only username extraction needs to move after.

3. **Preserve error handling semantics**: If `call_next` raises an exception, the audit log should still be emitted (with whatever username is available at that point) before re-raising. Use a try/finally pattern.

4. **Maintain fallback behavior**: After `call_next`, if `user_atlassian_email` is still `None` (e.g., validation failed or the service didn't backfill), continue to fall back to `pat-user` or `oauth-user`.

5. **Keep audit logging failure isolation**: If the audit logging itself fails (after `call_next`), emit a warning and return the tool result without blocking.

**Pseudocode for fixed `on_call_tool`:**
```
async def on_call_tool(self, context, call_next):
    # Extract data that doesn't depend on DI
    source_ip = self._extract_source_ip(context)
    tool_name = context.message.name
    arguments = context.message.arguments or {}
    masked_arguments = self._mask_arguments(arguments)
    body = self._serialize_body(masked_arguments)

    # Execute the tool (triggers dependency injection / email backfill)
    result = await call_next(context)

    # NOW extract username (email is available after DI)
    try:
        username = self._extract_username(context)
        audit_logger.info(f"{source_ip} {tool_name} {username} {body}")
    except Exception:
        app_logger.warning("Audit logging failed for tool call", exc_info=True)

    return result
```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that simulate PAT/OAuth authenticated tool calls through the middleware, mock dependency injection to backfill the email during `call_next`, and assert the logged username. Run these tests on the UNFIXED code to observe that `pat-user`/`oauth-user` is logged instead of the real email.

**Test Cases**:
1. **PAT Auth Test**: Simulate a PAT-authenticated tool call where DI backfills email during `call_next` (will log `pat-user` on unfixed code)
2. **OAuth Auth Test**: Simulate an OAuth-authenticated tool call where DI backfills email during `call_next` (will log `oauth-user` on unfixed code)
3. **Header PAT Test**: Simulate a header-based PAT call where `_confluence_on_validated` backfills email (will log `pat-user` on unfixed code)
4. **DI Failure Test**: Simulate a call where DI fails to resolve email (should log `pat-user`/`oauth-user` on both unfixed and fixed code)

**Expected Counterexamples**:
- Audit log entries contain `pat-user` or `oauth-user` even when the email is successfully resolved during `call_next`
- Confirmed cause: `_extract_username` is called before `call_next` where `user_atlassian_email` is still `None`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := on_call_tool_fixed(input)
  ASSERT audit_log_entry.username == resolved_email
  ASSERT result == expected_tool_result
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT on_call_tool_original(input).audit_entry == on_call_tool_fixed(input).audit_entry
  ASSERT on_call_tool_original(input).tool_result == on_call_tool_fixed(input).tool_result
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (various auth types, tool names, argument shapes)
- It catches edge cases that manual unit tests might miss (empty arguments, special characters in emails, long bodies)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for Basic auth and anonymous requests, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Basic Auth Preservation**: Verify Basic auth email extraction continues to work identically before and after fix
2. **Anonymous Preservation**: Verify unauthenticated requests continue to log `anonymous`
3. **Argument Masking Preservation**: Verify sensitive field masking is unchanged
4. **Body Truncation Preservation**: Verify body serialization and truncation behavior is unchanged
5. **Error Isolation Preservation**: Verify audit logging failures don't block tool execution

### Unit Tests

- Test that PAT-authenticated calls log the real email after fix
- Test that OAuth-authenticated calls log the real email after fix
- Test that Basic auth calls continue to log email from Authorization header
- Test that anonymous calls continue to log `anonymous`
- Test fallback to `pat-user`/`oauth-user` when DI fails to resolve email
- Test that tool results are returned unchanged regardless of audit log timing
- Test that exceptions during `call_next` still produce an audit entry

### Property-Based Tests

- Generate random auth states (basic/pat/oauth/none) with random emails and verify correct username resolution after `call_next`
- Generate random tool arguments with varying sensitive field patterns and verify masking is unchanged
- Generate random body lengths around the truncation threshold and verify truncation behavior is preserved
- Test across many combinations of source IPs, tool names, and auth types to verify log format consistency

### Integration Tests

- Test full middleware chain with mocked dependency injection that backfills email
- Test middleware behavior when `call_next` raises an exception (audit should still emit)
- Test middleware with `MCP_AUDIT_LOG_ENABLED=false` to verify gating is preserved
- Test concurrent tool calls to verify no state leakage between requests
