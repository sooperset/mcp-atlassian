# Authentication

MCP Atlassian supports three authentication methods depending on your Atlassian deployment type.

## API Token (Cloud) - Recommended

The simplest method for Atlassian Cloud users.

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **Create API token**, name it
3. Copy the token immediately

**Environment variables:**
```bash
JIRA_URL=https://your-company.atlassian.net
JIRA_USERNAME=your.email@company.com
JIRA_API_TOKEN=your_api_token

CONFLUENCE_URL=https://your-company.atlassian.net/wiki
CONFLUENCE_USERNAME=your.email@company.com
CONFLUENCE_API_TOKEN=your_api_token
```

## Personal Access Token (Server/Data Center)

For Server or Data Center deployments.

1. Go to your profile (avatar) → **Profile** → **Personal Access Tokens**
2. Click **Create token**, name it, set expiry
3. Copy the token immediately

**Environment variables:**
```bash
JIRA_URL=https://jira.your-company.com
JIRA_PERSONAL_TOKEN=your_personal_access_token

CONFLUENCE_URL=https://confluence.your-company.com
CONFLUENCE_PERSONAL_TOKEN=your_personal_access_token
```

> **Note**: For self-signed certificates, set `JIRA_SSL_VERIFY=false` and/or `CONFLUENCE_SSL_VERIFY=false`.

## OAuth 2.0 (Cloud) - Advanced

OAuth 2.0 provides enhanced security features but requires more setup. For most users, API Token authentication is simpler and sufficient.

### Setup Steps

1. Go to [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/)
2. Create an "OAuth 2.0 (3LO) integration" app
3. Configure **Permissions** (scopes) for Jira/Confluence
4. Set **Callback URL** (e.g., `http://localhost:8080/callback`)
5. Run setup wizard:
   ```bash
   # Using uvx
   uvx mcp-atlassian --oauth-setup -v

   # Or using Docker
   docker run --rm -i \
     -p 8080:8080 \
     -v "${HOME}/.mcp-atlassian:/home/app/.mcp-atlassian" \
     ghcr.io/sooperset/mcp-atlassian:latest --oauth-setup -v
   ```
6. Follow prompts for `Client ID`, `Secret`, `URI`, and `Scope`
7. Complete browser authorization
8. Use the obtained credentials in your configuration

**Environment variables (after setup):**
```bash
JIRA_URL=https://your-company.atlassian.net
CONFLUENCE_URL=https://your-company.atlassian.net/wiki
ATLASSIAN_OAUTH_CLOUD_ID=your_cloud_id_from_wizard
ATLASSIAN_OAUTH_CLIENT_ID=your_oauth_client_id
ATLASSIAN_OAUTH_CLIENT_SECRET=your_oauth_client_secret
ATLASSIAN_OAUTH_REDIRECT_URI=http://localhost:8080/callback
ATLASSIAN_OAUTH_SCOPE=read:jira-work write:jira-work read:confluence-content.all write:confluence-content offline_access
```

> **Important**: Include `offline_access` in your scope to allow automatic token refresh.

### Bring Your Own Token (BYOT)

If you manage OAuth tokens externally (e.g., through a central identity provider), you can provide an access token directly:

**Environment variables:**
```bash
ATLASSIAN_OAUTH_CLOUD_ID=your_cloud_id
ATLASSIAN_OAUTH_ACCESS_TOKEN=your_pre_existing_access_token
```

**Important considerations:**
- Token refresh is your responsibility - the server does not handle it
- Standard OAuth client variables are not used and can be omitted
- The `--oauth-setup` wizard is not applicable
- No token cache volume mount is needed

### Multi-Cloud OAuth

For multi-tenant applications where users provide their own OAuth tokens:

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

See [HTTP Transport](http-transport.md) for more details on multi-user authentication.
