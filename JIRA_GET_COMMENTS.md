# New Feature: jira_get_comments

## Overview
Added a dedicated `jira_get_comments` tool to retrieve comments from Jira issues. This complements the existing `jira_add_comment` functionality and provides a focused way to fetch issue comments.

## Tool Details

### Name
`jira_get_comments`

### Purpose
Retrieve all comments from a specific Jira issue with configurable limits.

### Parameters
- **issue_key** (required): Jira issue key (e.g., 'PROJ-123')
- **limit** (optional): Maximum number of comments to retrieve (1-1000, default: 50)

### Returns
JSON object containing:
```json
{
  "issue_key": "PROJ-123",
  "total_comments": 5,
  "comments": [
    {
      "id": "10001",
      "body": "Comment text content (cleaned and converted to markdown)",
      "created": "2025-08-20 10:30:00",
      "updated": "2025-08-20 10:35:00", 
      "author": "John Doe"
    },
    // ... more comments
  ]
}
```

## Features
- **Markdown Conversion**: Comment body text is automatically cleaned and converted from Jira markup to Markdown
- **User Mention Processing**: Jira user mentions are properly processed and formatted
- **Date Formatting**: Creation and update dates are formatted consistently
- **Configurable Limit**: Retrieve anywhere from 1 to 1000 comments per request
- **Error Handling**: Graceful error handling with detailed logging

## Implementation Details

### Files Modified
1. **`src/mcp_atlassian/servers/jira.py`**:
   - Added `get_comments` tool function
   - Integrated with existing `CommentsMixin.get_issue_comments` method
   - Properly tagged with `{"jira", "read"}` for tool filtering

### Files Already Present
1. **`src/mcp_atlassian/jira/comments.py`**:
   - Contains the `CommentsMixin` class with `get_issue_comments` method
   - Handles comment retrieval from Jira API
   - Processes comment text through the preprocessor

## Usage Examples

### Via MCP Tool in Claude
```
Use the jira_get_comments tool to get comments from issue PROJ-123 with a limit of 20 comments.
```

### Via Python Client
```python
from mcp_atlassian.jira.comments import CommentsMixin
from mcp_atlassian.jira.config import JiraConfig

# Create client
config = JiraConfig.from_env()
client = CommentsMixin(config)

# Get comments
comments = client.get_issue_comments(
    issue_key="PROJ-123",
    limit=20
)

# Process results
for comment in comments:
    print(f"Author: {comment['author']}")
    print(f"Date: {comment['created']}")
    print(f"Text: {comment['body']}")
```

## Testing

A test script is provided at `test_jira_comments.py`:

```bash
# Test with a specific issue
python test_jira_comments.py PROJ-123
```

The test script:
1. Tests direct client method (`get_issue_comments`)
2. Tests server endpoint (`jira_get_comments`)
3. Optionally tests adding a comment (if not in read-only mode)
4. Validates comment structure and content

## Compatibility
- Works with both Cloud and Server/DC instances
- Supports all authentication methods (OAuth, PAT, Basic Auth)
- Respects read-only mode (tool is read-only, tagged with "read")

## Related Tools
- **jira_get_issue**: Can also retrieve comments as part of issue details (with `comment_limit` parameter)
- **jira_add_comment**: Add new comments to issues
- **jira_search**: Search for issues (comments not included in search results)

## Notes
- Comments are returned in chronological order (oldest first)
- The comment body is automatically processed to convert Jira markup to Markdown
- User mentions in comments are properly formatted
- HTML content in comments is converted to readable text
