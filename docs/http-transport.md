# HTTP Transport

Instead of using `stdio`, you can run the server as a persistent HTTP service. This enables multi-user scenarios and remote deployment.

## Transport Types

| Transport | Endpoint | Use Case |
|-----------|----------|----------|
| `sse` | `/sse` | Server-Sent Events, good for streaming |
| `streamable-http` | `/mcp` | HTTP-based, good for multi-user |

## Basic Setup

### SSE Transport

```bash
# Using uvx
uvx mcp-atlassian --transport sse --port 9000 -vv

# Or using Docker
docker run --rm -p 9000:9000 \
  --env-file /path/to/your/.env \
  ghcr.io/sooperset/mcp-atlassian:latest \
  --transport sse --port 9000 -vv
```

**IDE Configuration:**
```json
{
  "mcpServers": {
    "mcp-atlassian-http": {
      "url": "http://localhost:9000/sse"
    }
  }
}
```

### Streamable-HTTP Transport

```bash
# Using uvx
uvx mcp-atlassian --transport streamable-http --port 9000 -vv

# Or using Docker
docker run --rm -p 9000:9000 \
  --env-file /path/to/your/.env \
  ghcr.io/sooperset/mcp-atlassian:latest \
  --transport streamable-http --port 9000 -vv
```

**IDE Configuration:**
```json
{
  "mcpServers": {
    "mcp-atlassian-service": {
      "url": "http://localhost:9000/mcp"
    }
  }
}
```

## Multi-User Authentication

Both transport types support per-request authentication where each user provides their own credentials.

### Authentication Methods

**Cloud (OAuth 2.0):**
```json
{
  "mcpServers": {
    "mcp-atlassian-service": {
      "url": "http://localhost:9000/mcp",
      "headers": {
        "Authorization": "Bearer <USER_OAUTH_ACCESS_TOKEN>"
      }
    }
  }
}
```

**Server/Data Center (PAT):**
```json
{
  "mcpServers": {
    "mcp-atlassian-service": {
      "url": "http://localhost:9000/mcp",
      "headers": {
        "Authorization": "Token <USER_PERSONAL_ACCESS_TOKEN>"
      }
    }
  }
}
```

### Server Setup for Multi-User

1. Run the OAuth setup wizard first (if using OAuth):
   ```bash
   # Using uvx
   uvx mcp-atlassian --oauth-setup -v

   # Or using Docker
   docker run --rm -i \
     -p 8080:8080 \
     -v "${HOME}/.mcp-atlassian:/home/app/.mcp-atlassian" \
     ghcr.io/sooperset/mcp-atlassian:latest --oauth-setup -v
   ```

2. Start the server with HTTP transport:
   ```bash
   # Using uvx (with env vars set)
   uvx mcp-atlassian --transport streamable-http --port 9000 -vv

   # Or using Docker
   docker run --rm -p 9000:9000 \
     --env-file /path/to/your/.env \
     ghcr.io/sooperset/mcp-atlassian:latest \
     --transport streamable-http --port 9000 -vv
   ```

3. Required environment variables:
   ```bash
   JIRA_URL=https://your-company.atlassian.net
   CONFLUENCE_URL=https://your-company.atlassian.net/wiki
   ATLASSIAN_OAUTH_CLIENT_ID=your_oauth_app_client_id
   ATLASSIAN_OAUTH_CLIENT_SECRET=your_oauth_app_client_secret
   ATLASSIAN_OAUTH_REDIRECT_URI=http://localhost:8080/callback
   ATLASSIAN_OAUTH_SCOPE=read:jira-work write:jira-work read:confluence-content.all write:confluence-content offline_access
   ATLASSIAN_OAUTH_CLOUD_ID=your_cloud_id_from_setup_wizard
   ```

### Multi-Cloud Support

For multi-tenant applications where each user connects to their own Atlassian cloud instance:

1. Enable minimal OAuth mode:
   ```bash
   # Using uvx
   ATLASSIAN_OAUTH_ENABLE=true uvx mcp-atlassian --transport streamable-http --port 9000

   # Or using Docker
   docker run -e ATLASSIAN_OAUTH_ENABLE=true -p 9000:9000 \
     ghcr.io/sooperset/mcp-atlassian:latest \
     --transport streamable-http --port 9000
   ```

2. Users provide authentication via HTTP headers:
   - `Authorization: Bearer <user_oauth_token>`
   - `X-Atlassian-Cloud-Id: <user_cloud_id>`

**Example (Python):**
```python
import asyncio
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

user_token = "user-specific-oauth-token"
user_cloud_id = "user-specific-cloud-id"

async def main():
    async with streamablehttp_client(
        "http://localhost:9000/mcp",
        headers={
            "Authorization": f"Bearer {user_token}",
            "X-Atlassian-Cloud-Id": user_cloud_id
        }
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "jira_get_issue",
                {"issue_key": "PROJ-123"}
            )
            print(result)

asyncio.run(main())
```

### Notes

- The server should have fallback authentication configured via environment variables
- User tokens are isolated per request - no cross-tenant data leakage
- Falls back to global `ATLASSIAN_OAUTH_CLOUD_ID` if header not provided
- User tokens should have appropriate scopes for their needed operations
