# MCP Atlassian

[![smithery badge](https://smithery.ai/badge/mcp-atlassian)](https://smithery.ai/server/mcp-atlassian)

Model Context Protocol (MCP) server for Atlassian products (Confluence and Jira). This integration supports both Atlassian Cloud and Jira Server/Data Center deployments.

<a href="https://glama.ai/mcp/servers/kc33m1kh5m"><img width="380" height="200" src="https://glama.ai/mcp/servers/kc33m1kh5m/badge" alt="Atlassian MCP server" /></a>

### Feature Demo
![Demo](https://github.com/user-attachments/assets/995d96a8-4cf3-4a03-abe1-a9f6aea27ac0)

### Server/Data Center Compatibility

This MCP server supports:

- **Atlassian Cloud**: Fully supported for both Confluence and Jira
- **Jira Server/Data Center**: Supported for on-premise Jira installations (version 8.14+)
- **Confluence Server/Data Center**: Not yet supported

> **Note for On-Premise Users:** When using with Jira Server/Data Center, you'll need to generate a Personal Access Token instead of using username/API token authentication. See the [Authentication](#authentication) section for details.

### Resources

> **Note:** The MCP server filters resources to only show Confluence spaces and Jira projects that the user is actively interacting with, based on their contributions and assignments. This makes the integration more efficient and focused on relevant content.

- `confluence://{space_key}`: Access Confluence spaces
- `jira://{project_key}`: Access Jira projects

### Tools

#### Confluence Tools

1. `confluence_search`
   - Search Confluence content using CQL
   - Inputs:
     - `query` (string): CQL query string
     - `limit` (number, optional): Results limit (1-50, default: 10)
   - Returns: Array of search results with page_id, title, space, url, last_modified, type, and excerpt

2. `confluence_get_page`
   - Get content of a specific Confluence page
   - Inputs:
     - `page_id` (string): Confluence page ID
     - `include_metadata` (boolean, optional): Include page metadata (default: true)
   - Returns: Page content and optional metadata

3. `confluence_get_comments`
   - Get comments for a specific Confluence page
   - Input:
     - `page_id` (string): Confluence page ID
   - Returns: Array of comments with author, creation date, and content

4. `confluence_create_page`
   - Create a new Confluence page
   - Inputs:
     - `space_key` (string): The key of the space to create the page in
     - `title` (string): The title of the page
     - `content` (string): The content of the page in Markdown format
     - `parent_id` (string, optional): Optional parent page ID
   - Returns: Created page details with metadata
   - Note: Uses markdown-to-confluence library for proper Confluence storage format conversion

5. `confluence_update_page`
   - Update an existing Confluence page
   - Inputs:
     - `page_id` (string): The ID of the page to update
     - `title` (string): The new title of the page
     - `content` (string): The new content of the page in Markdown format
     - `minor_edit` (boolean, optional): Whether this is a minor edit (default: false)
     - `version_comment` (string, optional): Optional comment for this version (default: "")
   - Returns: Updated page details with metadata
   - Note: Uses markdown-to-confluence library for proper Confluence storage format conversion

#### Jira Tools

1. `jira_get_issue`
   - Get details of a specific Jira issue
   - Inputs:
     - `issue_key` (string): Jira issue key (e.g., 'PROJ-123')
     - `expand` (string, optional): Fields to expand
     - `comment_limit` (integer, optional): Maximum number of comments to include (0 or null for no comments)
   - Returns: Issue details including content and metadata

2. `jira_search`
   - Search Jira issues using JQL
   - Inputs:
     - `jql` (string): JQL query string
     - `fields` (string, optional): Comma-separated fields (default: "*all")
     - `limit` (number, optional): Results limit (1-50, default: 10)
   - Returns: Array of matching issues with metadata

3. `jira_get_project_issues`
   - Get all issues for a specific Jira project
   - Inputs:
     - `project_key` (string): Project key
     - `limit` (number, optional): Results limit (1-50, default: 10)
   - Returns: Array of project issues with metadata

4. `jira_create_issue`
   - Create a new issue in Jira
   - Inputs:
     - `project_key` (string): The JIRA project key (e.g. 'PROJ')
     - `summary` (string): Summary/title of the issue
     - `issue_type` (string): Issue type (e.g. 'Task', 'Bug', 'Story')
     - `description` (string, optional): Issue description
     - `additional_fields` (string, optional): JSON string of additional fields
   - Returns: Created issue details with metadata

5. `jira_update_issue`
   - Update an existing Jira issue
   - Inputs:
     - `issue_key` (string): Jira issue key
     - `fields` (string): JSON object of fields to update
     - `additional_fields` (string, optional): JSON string of additional fields
   - Returns: Updated issue details with metadata

6. `jira_delete_issue`
   - Delete an existing Jira issue
   - Inputs:
     - `issue_key` (string): Jira issue key (e.g. PROJ-123)
   - Returns: Success confirmation message

7. `jira_get_transitions`
   - Get available status transitions for a Jira issue
   - Inputs:
     - `issue_key` (string): Jira issue key (e.g. 'PROJ-123')
   - Returns: Array of available transitions with ID, name, and target status information

8. `jira_transition_issue`
   - Transition a Jira issue to a new status
   - Inputs:
     - `issue_key` (string): Jira issue key (e.g. 'PROJ-123')
     - `transition_id` (string): ID of the transition to perform (get this from jira_get_transitions)
     - `fields` (string, optional): JSON string of fields to update during the transition
     - `comment` (string, optional): Comment to add during the transition
   - Returns: Updated issue details including the new status

9. `jira_link_to_epic`
   - Link an issue to an Epic
   - Inputs:
     - `issue_key` (string): Jira issue key to link (e.g. 'PROJ-123')
     - `epic_key` (string): Epic issue key to link to (e.g. 'PROJ-456')
   - Returns: Linked issue details with confirmation message

10. `jira_get_epic_issues`
    - Get all issues linked to a specific Epic
    - Inputs:
      - `epic_key` (string): Epic issue key (e.g. 'PROJ-456')
      - `limit` (number, optional): Results limit (1-50, default: 10)
    - Returns: Array of issues linked to the Epic with metadata

## Installation

### Using uv (recommended)

On macOS:
```bash
brew install uv
```

When using [`uv`](https://docs.astral.sh/uv/), no specific installation is needed. We will use [`uvx`](https://docs.astral.sh/uv/guides/tools/) to directly run *mcp-atlassian*.

```bash
uvx mcp-atlassian
```

### Using PIP

Alternatively you can install mcp-atlassian via pip:

```bash
pip install mcp-atlassian
```

### Installing via Smithery

To install Atlassian Integration for Claude Desktop automatically via [Smithery](https://smithery.ai/server/mcp-atlassian):

```bash
npx -y @smithery/cli install mcp-atlassian --client claude
```

## Configuration

The MCP Atlassian integration supports using either Confluence, Jira, or both services. You only need to provide the environment variables for the service(s) you want to use.

### Authentication

#### For Atlassian Cloud

1. Get API tokens from: https://id.atlassian.com/manage-profile/security/api-tokens

#### For Jira Server/Data Center

1. Generate a Personal Access Token in your Jira Server/Data Center (version 8.14 or later):
   - Navigate to your profile by clicking on your avatar in the top right corner
   - Select **Profile** → **Personal Access Tokens**
     *(Alternative path in some versions: Account Settings → Security → Personal Access Tokens)*
   - Click **Create token**
   - Give your token a meaningful name (e.g., "MCP Integration")
   - Set an expiry date (or choose "Never" if permitted by your organization)
   - Copy the generated token immediately (you won't be able to see it again)

   > **Important Notes:**
   > - PATs inherit your existing Jira permissions - no separate permission configuration is needed during creation
   > - Ensure your account has the necessary project access before creating the token
   > - In Data Center, administrators can view/revoke all PATs via **System → Administering personal access tokens**
   > - By default, users are limited to 10 active tokens
   > - The implementation uses Bearer token authentication (`Authorization: Bearer <token>`)
   > - Personal Access Tokens were introduced in Jira Server/Data Center 8.14

### Usage with Claude Desktop

> **Note:** For all configuration methods, include only the environment variables needed for your services:
> - For Confluence only (Cloud): Include `CONFLUENCE_URL`, `CONFLUENCE_USERNAME`, and `CONFLUENCE_API_TOKEN`
> - For Jira Cloud: Include `JIRA_URL`, `JIRA_USERNAME`, and `JIRA_API_TOKEN`
> - For Jira Server/Data Center: Include `JIRA_URL` and `JIRA_PERSONAL_TOKEN`
> - For multiple services: Include the variables for each service you want to use

<details>
<summary>Using uvx</summary>

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@domain.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "JIRA_URL": "https://your-domain.atlassian.net",
        "JIRA_USERNAME": "your.email@domain.com",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

For Jira Server/Data Center:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@domain.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "JIRA_URL": "https://jira.your-company.com",
        "JIRA_PERSONAL_TOKEN": "your_personal_access_token"
      }
    }
  }
}
```

</details>

<details>
<summary>Using pip</summary>

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "python",
      "args": ["-m", "mcp-atlassian"],
      "env": {
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@domain.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "JIRA_URL": "https://your-domain.atlassian.net",
        "JIRA_USERNAME": "your.email@domain.com",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

</details>

<details>
<summary>Using docker</summary>

There are two ways to configure the Docker environment:

1. Using environment variables directly in the config:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "mcp/atlassian"],
      "env": {
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "your.email@domain.com",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "JIRA_URL": "https://your-domain.atlassian.net",
        "JIRA_USERNAME": "your.email@domain.com",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

2. Using an environment file:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "/path/to/your/.env",
        "mcp/atlassian"
      ]
    }
  }
}
```

The .env file should contain:
```env
CONFLUENCE_URL=https://your-domain.atlassian.net/wiki
CONFLUENCE_USERNAME=your.email@domain.com
CONFLUENCE_API_TOKEN=your_api_token
JIRA_URL=https://your-domain.atlassian.net
JIRA_USERNAME=your.email@domain.com
JIRA_API_TOKEN=your_api_token
```

</details>

### Cursor IDE Configuration

To integrate the MCP server with Cursor IDE:

![image](https://github.com/user-attachments/assets/dee83445-c694-4b2e-8e47-7c280f806964)

Configure the server:
- Open Cursor Settings
- Navigate to `Features` > `MCP Servers`
- Click `Add new MCP server`
- Enter this configuration:
  ```yaml
  name: mcp-atlassian
  type: command
  command: uvx mcp-atlassian --confluence-url=https://your-domain.atlassian.net/wiki --confluence-username=your.email@domain.com --confluence-token=your_api_token --jira-url=https://your-domain.atlassian.net --jira-username=your.email@domain.com --jira-token=your_api_token
  ```

### Using a Local Development Version

If you've cloned the repository and want to run a local version of `mcp-atlassian`:

Configure in Claude Desktop:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/your/mcp-atlassian",
        "run", "mcp-atlassian",
        "--confluence-url=https://your-domain.atlassian.net",
        "--confluence-username=your.email@domain.com",
        "--confluence-token=your_api_token",
        "--jira-url=https://your-domain.atlassian.net",
        "--jira-username=your.email@domain.com",
        "--jira-token=your_api_token"
      ]
    }
  }
}
```

## Debugging

You can use the MCP inspector to debug the server:

```bash
npx @modelcontextprotocol/inspector uvx mcp-atlassian
```

For development installations:
```bash
cd path/to/mcp-atlassian
npx @modelcontextprotocol/inspector uv run mcp-atlassian
```

View logs with:
```bash
tail -n 20 -f ~/Library/Logs/Claude/mcp*.log
```

## Development

For local development testing:

1. Use the MCP inspector (see [Debugging](#debugging))
2. Test with Claude Desktop or Cursor IDE using the configuration above

## Build

Docker build:
```bash
docker build -t mcp/atlassian .
```

## Security

- Never share API tokens
- Keep .env files secure and private
- See [SECURITY.md](SECURITY.md) for best practices

## License

Licensed under MIT - see [LICENSE](LICENSE) file. This is not an official Atlassian product.
