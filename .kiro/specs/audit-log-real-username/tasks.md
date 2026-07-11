# Implementation Plan

## Overview

Fix the audit log username resolution timing bug in `ToolCallLoggingMiddleware`. The middleware currently extracts the username BEFORE `call_next(context)`, but for PAT/OAuth users the real email is only available AFTER dependency injection runs inside `call_next`. The fix moves username extraction to after `call_next` completes.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - PAT/OAuth Username Resolution Timing Bug
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to PAT and OAuth auth types where DI backfills email during `call_next`
  - Create test file `tests/unit/test_audit_bug_condition.py`
  - Mock `get_http_request()` to return a request with `state.user_atlassian_auth_type = "pat"` (or `"oauth"`) and `state.user_atlassian_email = None`
  - Mock `call_next` to simulate DI backfill: set `request.state.user_atlassian_email = "user@company.com"` during execution, then return a mock ToolResult
  - Use Hypothesis to generate random email addresses and auth types from `["pat", "oauth"]`
  - Assert that the audit log entry contains the resolved real email (e.g., `user@company.com`), NOT `pat-user` or `oauth-user`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (audit log contains `pat-user`/`oauth-user` instead of real email — this confirms the bug exists)
  - Document counterexamples found (e.g., "PAT user with email user@company.com logs as pat-user")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Basic Auth and Anonymous Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Create test file `tests/unit/test_audit_preservation.py`
  - Observe: Basic auth user with `Authorization: Basic base64(user@example.com:token)` logs `user@example.com` on unfixed code
  - Observe: Unauthenticated request (no auth state) logs `anonymous` on unfixed code
  - Observe: Sensitive fields like `{"token": "secret123"}` are masked to `{"token": "***"}` on unfixed code
  - Observe: Bodies exceeding `max_body_length` are truncated with `...truncated` on unfixed code
  - Use Hypothesis to generate:
    - Random valid email addresses for Basic auth (property: result always contains the email from the Authorization header)
    - Random tool names and argument dictionaries for anonymous requests (property: result always contains `anonymous`)
    - Random argument dictionaries with sensitive field names matching DEFAULT_SENSITIVE_PATTERNS (property: sensitive values are always masked)
    - Random argument dictionaries with varying lengths around the truncation threshold (property: bodies exceeding max_body_length are truncated)
  - Write property-based tests asserting these observed behaviors hold for all generated inputs
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Fix for audit log username resolution timing

  - [x] 3.1 Implement the fix in `src/mcp_atlassian/servers/audit.py`
    - Restructure `on_call_tool` to extract source IP, tool name, and masked arguments BEFORE `call_next` (they don't depend on DI)
    - Call `result = await call_next(context)` to execute the tool (triggers DI / email backfill)
    - Extract username AFTER `call_next` completes (email is now available via `request.state.user_atlassian_email`)
    - Emit the audit log entry after username extraction
    - Wrap in try/except: if `call_next` raises an exception, still emit the audit log (with whatever username is available at that point) before re-raising
    - If audit logging itself fails after `call_next`, emit a warning and return the tool result without blocking
    - Maintain fallback to `pat-user`/`oauth-user` when DI fails to resolve email (email still `None` after `call_next`)
    - _Bug_Condition: isBugCondition(input) where input.request.state.user_atlassian_auth_type IN ['pat', 'oauth'] AND username_extracted_before_call_next IS True_
    - _Expected_Behavior: audit_log_entry.username == resolved_email after call_next completes_
    - _Preservation: Basic auth email from Authorization header, anonymous fallback, error isolation, argument masking, body truncation, enable/disable gating_
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - PAT/OAuth Username Resolution Timing Bug
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (audit log contains real email)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — real email now appears in audit log)
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Basic Auth and Anonymous Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm Basic auth still logs email from Authorization header
    - Confirm anonymous still logs `anonymous`
    - Confirm sensitive field masking is unchanged
    - Confirm body truncation is unchanged
    - Confirm audit logging errors don't block tool execution

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `uv run pytest tests/unit/test_audit_bug_condition.py tests/unit/test_audit_preservation.py -xvs`
  - Verify no regressions in existing audit tests (if any): `uv run pytest tests/ -k audit -xvs`
  - Run linting and type checking: `pre-commit run --all-files`
  - Ensure all tests pass, ask the user if questions arise.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2"] },
    { "id": 1, "tasks": ["3.1"] },
    { "id": 2, "tasks": ["3.2", "3.3"] },
    { "id": 3, "tasks": ["4"] }
  ]
}
```

## Notes

- Tasks 1 and 2 are independent and can be worked on in parallel
- Task 1 (exploration test) MUST fail on unfixed code — this confirms the bug exists
- Task 2 (preservation tests) MUST pass on unfixed code — this captures baseline behavior
- Task 3.1 (implementation) should only begin after tasks 1 and 2 are complete
- Tasks 3.2 and 3.3 re-run existing tests from tasks 1 and 2 — no new tests are written
- The fix uses a try/finally pattern to ensure audit logging even when `call_next` raises
- Hypothesis is used for property-based testing to generate diverse inputs across auth types, emails, and argument shapes
