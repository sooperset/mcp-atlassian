# Jira Server/DC Development Information Issue

## Issue Summary
The `jira_get_development_information` tool was not returning development data for Jira Server/DC instances due to two issues:

1. **API Parameter Issue**: The Server/DC API endpoint requires numeric issue IDs, not issue keys
2. **API Limitation**: Some Jira Server/DC configurations don't expose detailed development information via REST API

## Fix Applied
The following changes were made to `/src/mcp_atlassian/jira/development.py`:

1. **Issue Key to ID Conversion**: For Server/DC instances, the code now converts issue keys (e.g., LQC-25567) to numeric IDs (e.g., 2688920) before calling the API

2. **Summary Fallback**: When the detail endpoint returns empty data, the code now also checks the summary endpoint to confirm if development data exists

3. **Error Reporting**: The tool now properly reports when development data exists but details are not accessible

## Current Limitations
Even with the fix, the Jira Server/DC API at jira.openbet.com only provides summary-level information:
- Number of pull requests and their states (open/merged/declined)
- Number of commits
- No detailed information (PR titles, commit messages, authors, etc.)

This appears to be a configuration limitation where the Bitbucket Server integration doesn't fully expose data through the REST API.

## Rebuilding the Docker Image
Run the provided script to rebuild the Docker image with the fix:
```bash
chmod +x /Users/shaun.prince/repos/mcp-atlassian/rebuild_docker.sh
/Users/shaun.prince/repos/mcp-atlassian/rebuild_docker.sh
```

Then restart Claude Desktop to apply the changes.

## Alternative Solutions

### 1. Direct Bitbucket API Access
Since you have Bitbucket configured in your MCP setup, you could query Bitbucket directly for development information:
- Use the Bitbucket MCP tool to search for pull requests by issue key
- This would give you full PR details that the Jira API cannot provide

### 2. Use Jira Web UI
The Development panel in the Jira web interface shows all the information correctly. This suggests the data exists but isn't exposed via the REST API.

### 3. Check Jira Configuration
Contact your Jira administrator to check if:
- The Bitbucket integration plugin is fully configured
- REST API access to development information is enabled
- There are any permission restrictions on the API endpoints

## Testing the Fix
To test if the fix is working:
```bash
cd /Users/shaun.prince/repos/mcp-atlassian
source .venv/bin/activate
export JIRA_URL=https://jira.openbet.com
export JIRA_PERSONAL_TOKEN=YOUR_TOKEN_HERE
python test_dev_info.py LQC-25567
```

You should see:
- A warning that development data exists but details are not accessible
- Summary showing: PRs: 3 (Merged: 3, Open: 0), Commits: 6
