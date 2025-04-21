"""Backup of original metadata from server.py for preservation during refactoring.

This file preserves the original tool and resource descriptions and schemas from
the monolithic server.py implementation. It's used as a reference during refactoring
to ensure we maintain the same API and documentation for LLMs interacting with the service.
"""

# Resource URIs and descriptions
ORIGINAL_RESOURCES = {
    "confluence": {
        "uri_template": "confluence://{space_key}",
        "description": (
            "A Confluence space containing documentation and knowledge base articles. "
            "Space Key: {space_key}. "
            "{description} "
            "Access content using: confluence://{space_key}/pages/PAGE_TITLE"
        ),
    },
    "confluence_page": {
        "uri_template": "confluence://{space_key}/pages/{title}",
        "description": "A specific Confluence page",
    },
    "jira": {
        "uri_template": "jira://{project_key}",
        "description": (
            "A Jira project tracking issues and tasks. Project Key: {project_key}. "
        ),
    },
    "jira_issue": {
        "uri_template": "jira://{project_key}/{issue_key}",
        "description": "A specific Jira issue",
    },
}

# Tool descriptions and input schemas
ORIGINAL_METADATA = {
    "tools": {
        # --- Confluence Tools ---
        "confluence_search": {
            "name": "confluence_search",
            "description": "Search Confluence content using simple terms or CQL",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query - can be either a simple text (e.g. 'project documentation') or a CQL query string. Simple queries use 'siteSearch' by default, to mimic the WebUI search, with an automatic fallback to 'text' search if not supported. Examples of CQL:\n"
                        "- Basic search: 'type=page AND space=DEV'\n"
                        "- Personal space search: 'space=\"~username\"' (note: personal space keys starting with ~ must be quoted)\n"
                        "- Search by title: 'title~\"Meeting Notes\"'\n"
                        "- Use siteSearch: 'siteSearch ~ \"important concept\"'\n"
                        "- Use text search: 'text ~ \"important concept\"'\n"
                        "- Recent content: 'created >= \"2023-01-01\"'\n"
                        "- Content with specific label: 'label=documentation'\n"
                        "- Recently modified content: 'lastModified > startOfMonth(\"-1M\")'\n"
                        "- Content modified this year: 'creator = currentUser() AND lastModified > startOfYear()'\n"
                        "- Content you contributed to recently: 'contributor = currentUser() AND lastModified > startOfWeek()'\n"
                        "- Content watched by user: 'watcher = \"user@domain.com\" AND type = page'\n"
                        '- Exact phrase in content: \'text ~ "\\"Urgent Review Required\\"" AND label = "pending-approval"\'\n'
                        '- Title wildcards: \'title ~ "Minutes*" AND (space = "HR" OR space = "Marketing")\'\n'
                        'Note: Special identifiers need proper quoting in CQL: personal space keys (e.g., "~username"), reserved words, numeric IDs, and identifiers with special characters.',
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (1-50)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "spaces_filter": {
                        "type": "string",
                        "description": "Comma-separated list of space keys to filter results by. Overrides the environment variable CONFLUENCE_SPACES_FILTER if provided.",
                    },
                },
                "required": ["query"],
            },
        },
        "confluence_get_page": {
            "name": "confluence_get_page",
            "description": "Get content of a specific Confluence page by ID",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Confluence page ID (numeric ID, can be found in the page URL). "
                        "For example, in the URL 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title', "
                        "the page ID is '123456789'",
                    },
                    "include_metadata": {
                        "type": "boolean",
                        "description": "Whether to include page metadata such as creation date, last update, version, and labels",
                        "default": True,
                    },
                    "convert_to_markdown": {
                        "type": "boolean",
                        "description": "Whether to convert page to markdown (true) or keep it in raw HTML format (false). Raw HTML can reveal macros (like dates) not visible in markdown, but CAUTION: using HTML significantly increases token usage in AI responses.",
                        "default": True,
                    },
                },
                "required": ["page_id"],
            },
        },
        "confluence_get_page_children": {
            "name": "confluence_get_page_children",
            "description": "Get child pages of a specific Confluence page",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "parent_id": {
                        "type": "string",
                        "description": "The ID of the parent page whose children you want to retrieve",
                    },
                    "expand": {
                        "type": "string",
                        "description": "Fields to expand in the response (e.g., 'version', 'body.storage')",
                        "default": "version",
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of child pages to return (1-50)",
                        "default": 25,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "Whether to include the page content in the response",
                        "default": False,
                    },
                },
                "required": ["parent_id"],
            },
        },
        "confluence_get_page_ancestors": {
            "name": "confluence_get_page_ancestors",
            "description": "Get ancestor (parent) pages of a specific Confluence page",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "The ID of the page whose ancestors you want to retrieve",
                    },
                },
                "required": ["page_id"],
            },
        },
        "confluence_get_comments": {
            "name": "confluence_get_comments",
            "description": "Get comments for a specific Confluence page",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Confluence page ID (numeric ID, can be parsed from URL, "
                        "e.g. from 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title' "
                        "-> '123456789')",
                    }
                },
                "required": ["page_id"],
            },
        },
        "confluence_create_page": {
            "name": "confluence_create_page",
            "description": "Create a new Confluence page",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "space_key": {
                        "type": "string",
                        "description": "The key of the space to create the page in "
                        "(usually a short uppercase code like 'DEV', 'TEAM', or 'DOC')",
                    },
                    "title": {
                        "type": "string",
                        "description": "The title of the page",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content of the page in Markdown format. "
                        "Supports headings, lists, tables, code blocks, and other "
                        "Markdown syntax",
                    },
                    "parent_id": {
                        "type": "string",
                        "description": "Optional parent page ID. If provided, this page "
                        "will be created as a child of the specified page",
                    },
                },
                "required": ["space_key", "title", "content"],
            },
        },
        "confluence_update_page": {
            "name": "confluence_update_page",
            "description": "Update an existing Confluence page",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "The ID of the page to update",
                    },
                    "title": {
                        "type": "string",
                        "description": "The new title of the page",
                    },
                    "content": {
                        "type": "string",
                        "description": "The new content of the page in Markdown format",
                    },
                    "is_minor_edit": {
                        "type": "boolean",
                        "description": "Whether this is a minor edit",
                        "default": False,
                    },
                    "version_comment": {
                        "type": "string",
                        "description": "Optional comment for this version",
                        "default": "",
                    },
                    "parent_id": {
                        "type": "string",
                        "description": "Optional the new parent page ID",
                    },
                },
                "required": ["page_id", "title", "content"],
            },
        },
        "confluence_delete_page": {
            "name": "confluence_delete_page",
            "description": "Delete an existing Confluence page",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "The ID of the page to delete",
                    },
                },
                "required": ["page_id"],
            },
        },
        # --- Jira Tools (Existing from original metadata.py) ---
        "jira_get_issue": {
            "name": "jira_get_issue",
            "description": "Get details of a specific Jira issue including its Epic links and relationship information",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Jira issue key (e.g., 'PROJ-123')",
                    },
                    "fields": {
                        "type": "string",
                        "description": "Fields to return. Can be a comma-separated list (e.g., 'summary,status,customfield_10010'), '*all' for all fields (including custom fields), or omitted for essential fields only",
                        "default": "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
                    },
                    "expand": {
                        "type": "string",
                        "description": (
                            "Optional fields to expand. Examples: 'renderedFields' "
                            "(for rendered content), 'transitions' (for available "
                            "status transitions), 'changelog' (for history)"
                        ),
                        "default": None,
                    },
                    "comment_limit": {
                        "type": "integer",
                        "description": (
                            "Maximum number of comments to include "
                            "(0 or null for no comments)"
                        ),
                        "minimum": 0,
                        "maximum": 100,
                        "default": 10,
                    },
                    "properties": {
                        "type": "string",
                        "description": "A comma-separated list of issue properties to return",
                        "default": None,
                    },
                    "update_history": {
                        "type": "boolean",
                        "description": "Whether to update the issue view history for the requesting user",
                        "default": True,
                    },
                },
                "required": ["issue_key"],
            },
        },
        "jira_search": {
            "name": "jira_search",
            "description": "Search Jira issues using JQL (Jira Query Language)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "jql": {
                        "type": "string",
                        "description": "JQL query string (Jira Query Language). Examples:\n"
                        '- Find Epics: "issuetype = Epic AND project = PROJ"\n'
                        '- Find issues in Epic: "parent = PROJ-123"\n'
                        "- Find by status: \"status = 'In Progress' AND project = PROJ\"\n"
                        '- Find by assignee: "assignee = currentUser()"\n'
                        '- Find recently updated: "updated >= -7d AND project = PROJ"\n'
                        '- Find by label: "labels = frontend AND project = PROJ"\n'
                        '- Find by priority: "priority = High AND project = PROJ"',
                    },
                    "fields": {
                        "type": "string",
                        "description": (
                            "Comma-separated fields to return in the results. "
                            "Use '*all' for all fields, or specify individual "
                            "fields like 'summary,status,assignee,priority'"
                        ),
                        "default": "summary,description,status,assignee,reporter,labels,priority,created,updated,issuetype",
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (1-50)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "startAt": {
                        "type": "number",
                        "description": "Starting index for pagination (0-based)",
                        "default": 0,
                        "minimum": 0,
                    },
                    "projects_filter": {
                        "type": "string",
                        "description": "Comma-separated list of project keys to filter results by. Overrides the environment variable JIRA_PROJECTS_FILTER if provided.",
                    },
                },
                "required": ["jql"],
            },
        },
        "jira_get_project_issues": {
            "name": "jira_get_project_issues",
            "description": "Get all issues for a specific Jira project",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_key": {
                        "type": "string",
                        "description": "The project key",
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (1-50)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "startAt": {
                        "type": "number",
                        "description": "Starting index for pagination (0-based)",
                        "default": 0,
                        "minimum": 0,
                    },
                },
                "required": ["project_key"],
            },
        },
        "jira_get_epic_issues": {
            "name": "jira_get_epic_issues",
            "description": "Get all issues linked to a specific epic",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "epic_key": {
                        "type": "string",
                        "description": "The key of the epic (e.g., 'PROJ-123')",
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of issues to return (1-50)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "startAt": {
                        "type": "number",
                        "description": "Starting index for pagination (0-based)",
                        "default": 0,
                        "minimum": 0,
                    },
                },
                "required": ["epic_key"],
            },
        },
        "jira_get_transitions": {
            "name": "jira_get_transitions",
            "description": "Get available status transitions for a Jira issue",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Jira issue key (e.g., 'PROJ-123')",
                    },
                },
                "required": ["issue_key"],
            },
        },
        "jira_get_worklog": {
            "name": "jira_get_worklog",
            "description": "Get worklog entries for a Jira issue",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Jira issue key (e.g., 'PROJ-123')",
                    },
                },
                "required": ["issue_key"],
            },
        },
        "jira_download_attachments": {
            "name": "jira_download_attachments",
            "description": "Download attachments from a Jira issue",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Jira issue key (e.g., 'PROJ-123')",
                    },
                    "target_dir": {
                        "type": "string",
                        "description": "Directory where attachments should be saved",
                    },
                },
                "required": ["issue_key", "target_dir"],
            },
        },
        "jira_get_agile_boards": {
            "name": "jira_get_agile_boards",
            "description": "Get jira agile boards by name, project key, or type",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "board_name": {
                        "type": "string",
                        "description": "The name of board, support fuzzy search",
                    },
                    "project_key": {
                        "type": "string",
                        "description": "Jira project key (e.g., 'PROJ-123')",
                    },
                    "board_type": {
                        "type": "string",
                        "description": "The type of jira board (e.g., 'scrum', 'kanban')",
                    },
                    "startAt": {
                        "type": "number",
                        "description": "Starting index for pagination (0-based)",
                        "default": 0,
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (1-50)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
            },
        },
        "jira_get_board_issues": {
            "name": "jira_get_board_issues",
            "description": "Get all issues linked to a specific board",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "board_id": {
                        "type": "string",
                        "description": "The id of the board (e.g., '1001')",
                    },
                    "jql": {
                        "type": "string",
                        "description": "JQL query string (Jira Query Language). Examples:\n"
                        '- Find Epics: "issuetype = Epic AND project = PROJ"\n'
                        '- Find issues in Epic: "parent = PROJ-123"\n'
                        "- Find by status: \"status = 'In Progress' AND project = PROJ\"\n"
                        '- Find by assignee: "assignee = currentUser()"\n'
                        '- Find recently updated: "updated >= -7d AND project = PROJ"\n'
                        '- Find by label: "labels = frontend AND project = PROJ"\n'
                        '- Find by priority: "priority = High AND project = PROJ"',
                    },
                    "fields": {
                        "type": "string",
                        "description": (
                            "Comma-separated fields to return in the results. "
                            "Use '*all' for all fields, or specify individual "
                            "fields like 'summary,status,assignee,priority'"
                        ),
                        "default": "*all",
                    },
                    "startAt": {
                        "type": "number",
                        "description": "Starting index for pagination (0-based)",
                        "default": 0,
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (1-50)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "expand": {
                        "type": "string",
                        "description": "Fields to expand in the response (e.g., 'version', 'body.storage')",
                        "default": "version",
                    },
                },
                "required": ["board_id", "jql"],
            },
        },
        "jira_get_sprints_from_board": {
            "name": "jira_get_sprints_from_board",
            "description": "Get jira sprints from board by state",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "board_id": {
                        "type": "string",
                        "description": "The id of board (e.g., '1000')",
                    },
                    "state": {
                        "type": "string",
                        "description": "Sprint state (e.g., 'active', 'future', 'closed')",
                    },
                    "startAt": {
                        "type": "number",
                        "description": "Starting index for pagination (0-based)",
                        "default": 0,
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (1-50)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
            },
        },
        "jira_get_sprint_issues": {
            "name": "jira_get_sprint_issues",
            "description": "Get jira issues from sprint",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "sprint_id": {
                        "type": "string",
                        "description": "The id of sprint (e.g., '10001')",
                    },
                    "fields": {
                        "type": "string",
                        "description": (
                            "Comma-separated fields to return in the results. "
                            "Use '*all' for all fields, or specify individual "
                            "fields like 'summary,status,assignee,priority'"
                        ),
                        "default": "*all",
                    },
                    "startAt": {
                        "type": "number",
                        "description": "Starting index for pagination (0-based)",
                        "default": 0,
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (1-50)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["sprint_id"],
            },
        },
        "jira_update_sprint": {
            "name": "jira_update_sprint",
            "description": "Update jira sprint",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "sprint_id": {
                        "type": "string",
                        "description": "The id of sprint (e.g., '10001')",
                    },
                    "sprint_name": {
                        "type": "string",
                        "description": "Optional: New name for the sprint",
                    },
                    "state": {
                        "type": "string",
                        "description": "Optional: New state for the sprint (future|active|closed)",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Optional: New start date for the sprint",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Optional: New end date for the sprint",
                    },
                    "goal": {
                        "type": "string",
                        "description": "Optional: New goal for the sprint",
                    },
                },
                "required": ["sprint_id"],
            },
        },
        "jira_create_issue": {
            "name": "jira_create_issue",
            "description": "Create a new Jira issue with optional Epic link or parent for subtasks",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_key": {
                        "type": "string",
                        "description": (
                            "The JIRA project key (e.g. 'PROJ', 'DEV', 'SUPPORT'). "
                            "This is the prefix of issue keys in your project. "
                            "Never assume what it might be, always ask the user."
                        ),
                    },
                    "summary": {
                        "type": "string",
                        "description": "Summary/title of the issue",
                    },
                    "issue_type": {
                        "type": "string",
                        "description": (
                            "Issue type (e.g. 'Task', 'Bug', 'Story', 'Epic', 'Subtask'). "
                            "The available types depend on your project configuration. "
                            "For subtasks, use 'Subtask' (not 'Sub-task') and include parent in additional_fields."
                        ),
                    },
                    "assignee": {
                        "type": "string",
                        "description": "Assignee of the ticket (accountID, full name or e-mail)",
                        "default": None,
                    },
                    "description": {
                        "type": "string",
                        "description": "Issue description",
                        "default": "",
                    },
                    "components": {
                        "type": "string",
                        "description": "Comma-separated list of component names to assign (e.g., 'Frontend,API')",
                        "default": "",
                    },
                    "additional_fields": {
                        "type": "string",
                        "description": (
                            "Optional JSON string of additional fields to set. "
                            "Examples:\n"
                            '- Set priority: {"priority": {"name": "High"}}\n'
                            '- Add labels: {"labels": ["frontend", "urgent"]}\n'
                            '- Link to parent (for any issue type): {"parent": "PROJ-123"}\n'
                            '- Set Fix Version/s: {"fixVersions": [{"id": "10020"}]}\n'
                            '- Custom fields: {"customfield_10010": "value"}'
                        ),
                        "default": "{}",
                    },
                },
                "required": ["project_key", "summary", "issue_type"],
            },
        },
        "jira_batch_create_issues": {
            "name": "jira_batch_create_issues",
            "description": "Create multiple Jira issues in a batch",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issues": {
                        "type": "string",
                        "description": (
                            "JSON array of issue objects. Each object should contain:\n"
                            "- project_key (required): The project key (e.g., 'PROJ')\n"
                            "- summary (required): Issue summary/title\n"
                            "- issue_type (required): Type of issue (e.g., 'Task', 'Bug')\n"
                            "- description (optional): Issue description\n"
                            "- assignee (optional): Assignee username or email\n"
                            "- components (optional): Array of component names\n"
                            "Example: [\n"
                            '  {"project_key": "PROJ", "summary": "Issue 1", "issue_type": "Task"},\n'
                            '  {"project_key": "PROJ", "summary": "Issue 2", "issue_type": "Bug", "components": ["Frontend"]}\n'
                            "]"
                        ),
                    },
                    "validate_only": {
                        "type": "boolean",
                        "description": "If true, only validates the issues without creating them",
                        "default": False,
                    },
                },
                "required": ["issues"],
            },
        },
        "jira_update_issue": {
            "name": "jira_update_issue",
            "description": "Update an existing Jira issue including changing status, adding Epic links, updating fields, etc.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Jira issue key (e.g., 'PROJ-123')",
                    },
                    "fields": {
                        "type": "string",
                        "description": (
                            "A valid JSON object of fields to update as a string. "
                            'Example: \'{"summary": "New title", "description": "Updated description", '
                            '"priority": {"name": "High"}, "assignee": {"name": "john.doe"}}\''
                        ),
                    },
                    "additional_fields": {
                        "type": "string",
                        "description": "Optional JSON string of additional fields to update. Use this for custom fields or more complex updates.",
                        "default": "{}",
                    },
                    "attachments": {
                        "type": "string",
                        "description": "Optional JSON string or comma-separated list of file paths to attach to the issue. "
                        'Example: "/path/to/file1.txt,/path/to/file2.txt" or "["/path/to/file1.txt","/path/to/file2.txt"]"',
                    },
                },
                "required": ["issue_key", "fields"],
            },
        },
        "jira_delete_issue": {
            "name": "jira_delete_issue",
            "description": "Delete an existing Jira issue",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Jira issue key (e.g. PROJ-123)",
                    },
                },
                "required": ["issue_key"],
            },
        },
        "jira_add_comment": {
            "name": "jira_add_comment",
            "description": "Add a comment to a Jira issue",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Jira issue key (e.g., 'PROJ-123')",
                    },
                    "comment": {
                        "type": "string",
                        "description": "Comment text in Markdown format",
                    },
                },
                "required": ["issue_key", "comment"],
            },
        },
        "jira_add_worklog": {
            "name": "jira_add_worklog",
            "description": "Add a worklog entry to a Jira issue",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Jira issue key (e.g., 'PROJ-123')",
                    },
                    "time_spent": {
                        "type": "string",
                        "description": (
                            "Time spent in Jira format. Examples: "
                            "'1h 30m' (1 hour and 30 minutes), "
                            "'1d' (1 day), '30m' (30 minutes), "
                            "'4h' (4 hours)"
                        ),
                    },
                    "comment": {
                        "type": "string",
                        "description": "Optional comment for the worklog in Markdown format",
                    },
                    "started": {
                        "type": "string",
                        "description": (
                            "Optional start time in ISO format. "
                            "If not provided, the current time will be used. "
                            "Example: '2023-08-01T12:00:00.000+0000'"
                        ),
                    },
                },
                "required": ["issue_key", "time_spent"],
            },
        },
        "jira_link_to_epic": {
            "name": "jira_link_to_epic",
            "description": "Link an existing issue to an epic",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "The key of the issue to link (e.g., 'PROJ-123')",
                    },
                    "epic_key": {
                        "type": "string",
                        "description": "The key of the epic to link to (e.g., 'PROJ-456')",
                    },
                },
                "required": ["issue_key", "epic_key"],
            },
        },
        "jira_create_issue_link": {
            "name": "jira_create_issue_link",
            "description": "Create a link between two Jira issues",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "link_type": {
                        "type": "string",
                        "description": "The type of link to create (e.g., 'Duplicate', 'Blocks', 'Relates to')",
                    },
                    "inward_issue_key": {
                        "type": "string",
                        "description": "The key of the inward issue (e.g., 'PROJ-123')",
                    },
                    "outward_issue_key": {
                        "type": "string",
                        "description": "The key of the outward issue (e.g., 'PROJ-456')",
                    },
                    "comment": {
                        "type": "string",
                        "description": "Optional comment to add to the link",
                    },
                    "comment_visibility": {
                        "type": "object",
                        "description": "Optional visibility settings for the comment",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "Type of visibility restriction (e.g., 'group')",
                            },
                            "value": {
                                "type": "string",
                                "description": "Value for the visibility restriction (e.g., 'jira-software-users')",
                            },
                        },
                    },
                },
                "required": [
                    "link_type",
                    "inward_issue_key",
                    "outward_issue_key",
                ],
            },
        },
        "jira_remove_issue_link": {
            "name": "jira_remove_issue_link",
            "description": "Remove a link between two Jira issues",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "link_id": {
                        "type": "string",
                        "description": "The ID of the link to remove",
                    },
                },
                "required": ["link_id"],
            },
        },
        "jira_transition_issue": {
            "name": "jira_transition_issue",
            "description": "Transition a Jira issue to a new status",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_key": {
                        "type": "string",
                        "description": "Jira issue key (e.g., 'PROJ-123')",
                    },
                    "transition_id": {
                        "type": "string",
                        "description": (
                            "ID of the transition to perform. Use the jira_get_transitions tool first "
                            "to get the available transition IDs for the issue. "
                            "Example values: '11', '21', '31'"
                        ),
                    },
                    "fields": {
                        "type": "string",
                        "description": (
                            "JSON string of fields to update during the transition. "
                            "Some transitions require specific fields to be set. "
                            'Example: \'{"resolution": {"name": "Fixed"}}\''
                        ),
                        "default": "{}",
                    },
                    "comment": {
                        "type": "string",
                        "description": (
                            "Comment to add during the transition (optional). "
                            "This will be visible in the issue history."
                        ),
                    },
                },
                "required": ["issue_key", "transition_id"],
            },
        },
    },
    "resources": {
        # Intentionally left as stubs - the resources are defined dynamically in list_resources()
    },
}
