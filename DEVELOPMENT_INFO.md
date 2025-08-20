# Jira Development Information Integration

This feature adds support for retrieving development information (pull requests, branches, commits, builds) linked to Jira issues through integrations like Bitbucket for Jira, GitHub for Jira, or GitLab for Jira.

## Features

### New MCP Tool
- `get_development_information` - Retrieves all linked development data for a Jira issue

### Data Retrieved
- **Pull Requests**: Title, status, author, source/destination branches, URLs
- **Branches**: Name, repository, last commit, URLs  
- **Commits**: ID, message, author, timestamp, files changed
- **Builds**: Name, status, duration, URLs
- **Repositories**: Name, URL, description

## Implementation Details

### Files Added
1. `src/mcp_atlassian/jira/development.py` - Core development information retrieval logic
2. `src/mcp_atlassian/models/jira/development.py` - Data models for development information
3. `test_dev_info.py` - Test script to verify functionality

### Files Modified
1. `src/mcp_atlassian/jira/client.py` - Added DevelopmentMixin to JiraClient
2. `src/mcp_atlassian/servers/jira.py` - Added MCP tool endpoint
3. `src/mcp_atlassian/models/__init__.py` - Exported development models

## API Endpoints Used

### Server/Data Center
- `/rest/dev-status/latest/issue/detail` - Legacy endpoint for development status

### Cloud
- `/rest/api/3/issue/{issueIdOrKey}/development` - Cloud API endpoint
- Falls back to legacy endpoint if needed

## Usage

### Via MCP Tool in Claude
```python
# Get all development information
await get_development_information(
    issue_key="PROJ-123"
)

# Filter by application type
await get_development_information(
    issue_key="PROJ-123",
    application_type="bitbucket"  # or "github", "gitlab", "stash"
)
```

### Direct Python Usage
```python
from mcp_atlassian.jira.client import JiraClient
from mcp_atlassian.jira.config import JiraConfig

# Initialize client
config = JiraConfig.from_env()
client = JiraClient(config)

# Get development information
dev_info = client.get_development_information("PROJ-123")

# Access specific data
print(f"Open PRs: {len(dev_info.open_pull_requests)}")
print(f"Total commits: {dev_info.total_commits}")
print(f"Summary: {dev_info.summary}")

# Get just pull requests
prs = client.get_linked_pull_requests("PROJ-123")
```

## Testing

Test the feature using the provided script:

```bash
# Test with a specific issue
python test_dev_info.py PROJ-123
```

This will:
1. Fetch development information for the issue
2. Display a summary in the console
3. Export full details to a JSON file

## Data Models

### DevelopmentInformation
Main container with:
- `pull_requests`: List of PullRequest objects
- `branches`: List of Branch objects
- `commits`: List of Commit objects
- `builds`: List of Build objects
- `repositories`: List of Repository objects
- `has_development_info`: Boolean indicator
- `summary`: Text summary of all development data

### PullRequest
- `id`, `title`, `url`
- `status` (OPEN, MERGED, DECLINED)
- `author`, `source_branch`, `destination_branch`
- `last_update`, `commentCount`
- Helper properties: `is_open`, `is_merged`

### Branch
- `id`, `name`, `url`
- `last_commit`, `repository`
- Helper properties: `is_feature_branch`, `is_bugfix_branch`

### Commit
- `id`, `message`, `url`
- `author`, `author_timestamp`
- `files_changed`, `lines_added`, `lines_removed`
- Helper properties: `short_id`, `first_line_message`

### Build
- `id`, `name`, `url`
- `status` (SUCCESS, FAILED, IN_PROGRESS)
- `started_time`, `finished_time`, `duration_seconds`
- Helper properties: `is_successful`, `is_failed`

## Error Handling

The implementation handles:
- Missing development panel/plugin
- Permission issues accessing development data
- Different response formats between Cloud and Server/DC
- Empty or malformed responses

If development information cannot be retrieved, an empty DevelopmentInformation object is returned with error details.

## Compatibility

- ✅ Jira Server/Data Center (with Bitbucket Server integration)
- ✅ Jira Cloud (with Bitbucket Cloud, GitHub, GitLab integrations)
- ✅ Handles both PAT and Basic authentication
- ✅ Works with the authentication fix for Server/DC Bearer tokens

## Limitations

1. Requires the appropriate integration plugin installed in Jira
2. User must have permission to view development information
3. Some fields may not be available depending on the integration type
4. Build information requires additional CI/CD integration

## Contributing

When adding support for new development tool integrations:
1. Add parsing logic in `_parse_<provider>_instance()` method
2. Update the `application_type` parameter documentation
3. Add test cases for the new provider format
