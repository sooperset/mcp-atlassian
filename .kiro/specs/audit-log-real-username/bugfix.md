# Bugfix Requirements Document

## Introduction

The `ToolCallLoggingMiddleware` in `audit.py` logs a generic fallback username (`pat-user` or `oauth-user`) instead of the real user email for PAT and OAuth authenticated requests. This happens because the middleware extracts the username in its `on_call_tool` hook BEFORE delegating to the tool handler via `call_next`. The real email is only resolved later during dependency injection (inside `call_next`) when `_create_and_validate()` backfills `request.state.user_atlassian_email`. This makes audit logs unreliable for identifying which user performed an action.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a PAT-authenticated user invokes a tool AND the email has not yet been backfilled by dependency injection THEN the system logs `pat-user` as the username in the audit entry

1.2 WHEN an OAuth-authenticated user invokes a tool AND the email has not yet been backfilled by dependency injection THEN the system logs `oauth-user` as the username in the audit entry

1.3 WHEN the audit log entry is emitted before `call_next(context)` completes THEN the system uses the stale `user_atlassian_email` value (which is `None` for PAT/OAuth at that point)

### Expected Behavior (Correct)

2.1 WHEN a PAT-authenticated user invokes a tool THEN the system SHALL log the real user email (resolved during token validation) as the username in the audit entry

2.2 WHEN an OAuth-authenticated user invokes a tool THEN the system SHALL log the real user email (resolved during token validation) as the username in the audit entry

2.3 WHEN the real email cannot be resolved after tool execution (e.g., validation failure) THEN the system SHALL fall back to `pat-user` or `oauth-user` respectively

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a Basic-auth user invokes a tool THEN the system SHALL CONTINUE TO extract the email from the Authorization header and log it correctly

3.2 WHEN an unauthenticated request invokes a tool THEN the system SHALL CONTINUE TO log `anonymous` as the username

3.3 WHEN audit logging encounters an internal error THEN the system SHALL CONTINUE TO emit a warning and proceed without blocking the tool call

3.4 WHEN tool call arguments contain sensitive fields THEN the system SHALL CONTINUE TO mask them before logging

3.5 WHEN the serialized request body exceeds the configured max length THEN the system SHALL CONTINUE TO truncate it with `...truncated`

3.6 WHEN the `MCP_AUDIT_LOG_ENABLED` environment variable is set to a falsy value THEN the system SHALL CONTINUE TO disable audit logging entirely
