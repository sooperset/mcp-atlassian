# Authentication Fix for Atlassian Server/Data Center PATs

## Problem
The original implementation incorrectly used Basic Authentication for Personal Access Tokens (PATs) on Atlassian Server/Data Center instances. Server/DC PATs require Bearer authentication, not Basic authentication.

## Solution
This fix introduces proper Bearer authentication support for Server/DC PATs while maintaining compatibility with Cloud instances.

### Changes Made

1. **New authentication utility** (`src/mcp_atlassian/utils/auth.py`):
   - Added `configure_server_pat_auth()` function to configure Bearer authentication

2. **Updated Jira client** (`src/mcp_atlassian/jira/client.py`):
   - Detects Server/DC instances when using PAT authentication
   - Creates a session with Bearer authentication for Server/DC
   - Maintains existing behavior for Cloud instances

3. **Updated Confluence client** (`src/mcp_atlassian/confluence/client.py`):
   - Same improvements as Jira client

4. **Updated tests**:
   - Modified PAT authentication tests to verify Bearer headers
   - Added unit tests for the new authentication utility

## Authentication Matrix

| Instance Type | Auth Method | Implementation |
|--------------|-------------|----------------|
| Cloud | API Token | Basic Auth (username + token) |
| Cloud | OAuth | Bearer Auth (via OAuth flow) |
| Cloud | PAT | Token parameter (rare) |
| Server/DC | Username/Password | Basic Auth |
| Server/DC | PAT | **Bearer Auth** (fixed) |
| Server/DC | OAuth | Not supported |

## Testing

To test the fix:

1. **Server/DC with PAT**:
   ```bash
   export JIRA_URL="https://jira.yourcompany.com"
   export JIRA_PERSONAL_TOKEN="your-pat-token"
   ```

2. **Cloud with API Token** (unchanged):
   ```bash
   export JIRA_URL="https://yourinstance.atlassian.net"
   export JIRA_USERNAME="your-email@example.com"
   export JIRA_API_TOKEN="your-api-token"
   ```

## Verification

You can verify the authentication is working correctly by checking the debug logs:

```bash
export MCP_ATLASSIAN_LOG_LEVEL=DEBUG
# Run your MCP server
```

For Server/DC with PAT, you should see:
```
Jira Server/DC client initialized with Bearer auth. Session headers (Authorization masked): {'Authorization': 'Bearer ***'}
```

## Compatibility

This fix is backward compatible:
- Cloud instances continue to work as before
- Server/DC instances with username/password still work
- Server/DC instances with PAT now work correctly with Bearer authentication
