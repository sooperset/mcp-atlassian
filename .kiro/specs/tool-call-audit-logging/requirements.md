# Requirements Document

## Introduction

This feature adds structured per-tool-call audit logging to the MCP Atlassian server. A custom `ToolCallLoggingMiddleware` subclass of `fastmcp.server.middleware.Middleware` intercepts all `tools/call` requests via the `on_call_tool` hook. The middleware extracts contextual information (source IP, username), masks sensitive fields in the request body, and emits a structured log entry before delegating to the actual tool execution.

The log format is: `<source_ip> <tool_name> <bitbucket_username> <request_body>`

## Glossary

- **Audit_Logger**: The dedicated Python logger instance (`mcp-atlassian.audit`) that emits structured tool-call audit log entries
- **ToolCallLoggingMiddleware**: A subclass of `fastmcp.server.middleware.Middleware` that intercepts tool calls via the `on_call_tool` hook to produce audit log entries
- **Source_IP**: The IP address of the client making the MCP request, extracted from the connection scope or forwarded headers
- **Tool_Name**: The string identifier of the MCP tool being invoked (e.g., `jira_get_issue`, `confluence_search`)
- **Bitbucket_Username**: The authenticated username associated with the request, extracted from the authentication context (Basic auth email, OAuth identity, or PAT-based identifier)
- **Request_Body**: The JSON-serialized arguments passed to the tool call, with sensitive fields masked
- **Sensitive_Field**: A tool argument whose value contains credentials, tokens, API keys, or other secret data that must not appear in logs in cleartext
- **FastMCP_Middleware**: The base class `fastmcp.server.middleware.Middleware` that provides lifecycle hooks including `on_call_tool` for intercepting tool invocations

## Requirements

### Requirement 1: Middleware Registration

**User Story:** As a server operator, I want the audit logging middleware to be automatically registered with the FastMCP server, so that all tool calls are logged without manual configuration.

#### Acceptance Criteria

1. WHEN the MCP server starts, THE ToolCallLoggingMiddleware SHALL be registered as a middleware on the AtlassianMCP server instance before any tool call is processed
2. THE ToolCallLoggingMiddleware SHALL subclass `fastmcp.server.middleware.Middleware`
3. THE ToolCallLoggingMiddleware SHALL intercept tool calls exclusively via the `on_call_tool` hook and SHALL NOT override any other middleware lifecycle hooks or use alternative logging mechanisms such as database triggers or separate event listeners
4. IF the `MCP_AUDIT_LOG_ENABLED` environment variable is unset or set to a truthy value (case-insensitive `true`, `1`, or `yes`), THEN THE ToolCallLoggingMiddleware SHALL be registered on the server

### Requirement 2: Source IP Extraction

**User Story:** As a security auditor, I want each audit log entry to include the client's source IP address, so that I can trace requests back to their origin.

#### Acceptance Criteria

1. WHEN a tool call is intercepted, THE ToolCallLoggingMiddleware SHALL extract the source IP from the MCP request context's ASGI connection scope `client` tuple (first element); the requirement SHALL be considered satisfied only if the correct IP value is successfully extracted
2. WHEN an `X-Forwarded-For` header is present in the request scope headers, THE ToolCallLoggingMiddleware SHALL use the first IP address in the comma-separated `X-Forwarded-For` value as the source IP, taking precedence over the connection scope `client` IP
3. WHEN neither an `X-Forwarded-For` header nor a connection scope `client` IP can be determined, THE ToolCallLoggingMiddleware SHALL use the string `unknown` as the source IP value
4. THE ToolCallLoggingMiddleware SHALL strip leading and trailing whitespace from the extracted IP address value

### Requirement 3: Username Extraction

**User Story:** As a security auditor, I want each audit log entry to include the authenticated username, so that I can attribute tool calls to specific users.

#### Acceptance Criteria

1. WHEN the request uses Basic authentication and an `Authorization` header is present, THE ToolCallLoggingMiddleware SHALL extract the email address from the decoded credentials (the portion before the first `:` in the Base64-decoded `Authorization` header value) as the username; WHEN Basic authentication is expected but no `Authorization` header is present, THE ToolCallLoggingMiddleware SHALL use the string `anonymous` as the username
2. WHEN the request uses a Personal Access Token and the `user_atlassian_email` field in the request state contains a non-empty value, THE ToolCallLoggingMiddleware SHALL use that value as the username
3. IF the request uses a Personal Access Token and no non-empty `user_atlassian_email` is available in the request state, THEN THE ToolCallLoggingMiddleware SHALL use the string `pat-user` as the username
4. WHEN the request uses OAuth authentication, THE ToolCallLoggingMiddleware SHALL extract the username from the request state field `user_atlassian_email`, falling back to the string `oauth-user` if the field is absent or empty
5. WHEN no `user_atlassian_auth_type` is set in the request state, THE ToolCallLoggingMiddleware SHALL use the string `anonymous` as the username
6. THE ToolCallLoggingMiddleware SHALL not perform additional network calls to resolve usernames

### Requirement 4: Sensitive Field Masking

**User Story:** As a security engineer, I want sensitive fields in tool call arguments to be masked before logging, so that credentials and secrets are not exposed in log files.

#### Acceptance Criteria

1. WHEN a tool call argument name matches a configured sensitive field pattern (case-insensitive substring match), THE ToolCallLoggingMiddleware SHALL replace the argument value with the output of the `mask_sensitive` utility function applied to the string representation of that value
2. THE ToolCallLoggingMiddleware SHALL mask fields whose names contain `token`, `password`, `secret`, `key`, `credential`, or `auth` (case-insensitive substring matching)
3. THE ToolCallLoggingMiddleware SHALL use the existing `mask_sensitive` utility function from `mcp_atlassian.utils.logging` for masking values, converting non-string values to their string representation before masking
4. WHEN additional sensitive field patterns are specified via the `MCP_AUDIT_SENSITIVE_FIELDS` environment variable, THE ToolCallLoggingMiddleware SHALL parse them as a comma-separated list and apply the same case-insensitive substring matching used for the default patterns; IF the environment variable contains malformed data that cannot be parsed as a comma-separated list, THEN THE ToolCallLoggingMiddleware SHALL skip pattern matching for the additional patterns and use only the default sensitive field patterns
5. THE ToolCallLoggingMiddleware SHALL mask sensitive values in nested dictionaries within the request body up to one level of depth, leaving values at deeper nesting levels unmasked
6. IF a tool call argument value is a dictionary and the argument name does not match a sensitive field pattern, THEN THE ToolCallLoggingMiddleware SHALL inspect the keys of that dictionary and mask any values whose keys match a sensitive field pattern

### Requirement 5: Structured Log Emission

**User Story:** As a server operator, I want audit log entries to follow a consistent structured format, so that I can parse and analyze them with log aggregation tools.

#### Acceptance Criteria

1. WHEN a tool call is intercepted, THE Audit_Logger SHALL emit a log entry in the format: `<source_ip> <tool_name> <bitbucket_username> <request_body>` where each field is separated by a single space character and the request_body occupies the remainder of the line
2. THE Audit_Logger SHALL emit audit log entries at the `INFO` log level
3. THE Audit_Logger SHALL use a dedicated logger named `mcp-atlassian.audit` to separate audit logs from application logs
4. THE Audit_Logger SHALL serialize the request body as a single-line JSON string with no embedded newlines or control characters
5. WHEN the original request body content length (before JSON serialization) exceeds 2048 characters, THE Audit_Logger SHALL truncate the body to 2048 characters and append the literal string `...truncated` as a suffix outside the character limit
6. IF the tool call has no arguments, THEN THE Audit_Logger SHALL use an empty JSON object `{}` as the request_body field value

### Requirement 6: Tool Execution Delegation

**User Story:** As a developer, I want the audit middleware to delegate to the actual tool execution after logging, so that tool functionality is not disrupted.

#### Acceptance Criteria

1. WHEN the audit log entry has been emitted, THE ToolCallLoggingMiddleware SHALL delegate to the next middleware or tool handler by calling the appropriate continuation method
2. THE ToolCallLoggingMiddleware SHALL not modify the tool call arguments passed to the downstream handler
3. THE ToolCallLoggingMiddleware SHALL not catch or suppress exceptions raised by the downstream tool execution
4. IF the audit logging itself raises an exception, THEN THE ToolCallLoggingMiddleware SHALL log the logging failure at the `WARNING` level to the application logger and SHALL ensure the warning is successfully written before delegating to the downstream handler; THE ToolCallLoggingMiddleware SHALL only emit warnings when audit logging actually fails with an exception and SHALL NOT log warnings during normal successful operation

### Requirement 7: Configuration

**User Story:** As a server operator, I want to configure audit logging behavior via environment variables, so that I can enable or disable it and tune its behavior without code changes.

#### Acceptance Criteria

1. WHEN `MCP_AUDIT_LOG_ENABLED` is set to a falsy value (`false`, `0`, or `no`, case-insensitive), THE ToolCallLoggingMiddleware SHALL not be registered on the server; other enablement mechanisms MAY override the environment variable setting
2. WHEN `MCP_AUDIT_SENSITIVE_FIELDS` is set, THE ToolCallLoggingMiddleware SHALL parse it as a comma-separated list of additional field name substrings to use as case-insensitive masking patterns, trimming whitespace around each entry and ignoring empty entries
3. WHEN `MCP_AUDIT_MAX_BODY_LENGTH` is set to an integer greater than or equal to 64, THE ToolCallLoggingMiddleware SHALL use that value as the truncation threshold instead of the default 2048 characters
4. IF `MCP_AUDIT_MAX_BODY_LENGTH` is set to a non-integer value or an integer less than 64, THEN THE ToolCallLoggingMiddleware SHALL ignore the invalid value and fall back to exactly 2048 characters as the default threshold

### Requirement 8: Documentation

**User Story:** As a server operator, I want the audit logging feature to be documented, so that I can understand how to configure and use it without reading the source code.

#### Acceptance Criteria

1. THE project documentation SHALL include a section describing the audit logging feature, its purpose, and the log entry format (`<source_ip> <tool_name> <username> <request_body>`)
2. THE documentation SHALL list all audit-related environment variables (`MCP_AUDIT_LOG_ENABLED`, `MCP_AUDIT_SENSITIVE_FIELDS`, `MCP_AUDIT_MAX_BODY_LENGTH`) with their types, default values, and descriptions
3. THE `.env.example` file SHALL include the audit logging environment variables with commented-out example values and brief descriptions
4. THE documentation SHALL describe the default sensitive field patterns that are masked and how to add custom patterns via `MCP_AUDIT_SENSITIVE_FIELDS`
5. THE documentation SHALL explain how the username is resolved for each authentication method (Basic, PAT, OAuth) and the fallback values used when credentials are unavailable
