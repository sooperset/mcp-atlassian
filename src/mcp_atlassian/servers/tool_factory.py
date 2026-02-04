"""Dynamic tool registration for multi-instance support.

This module provides factory functions to dynamically register tools for
multiple Jira and Confluence instances.
"""

import logging
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from mcp_atlassian.jira.constants import DEFAULT_READ_JIRA_FIELDS
from mcp_atlassian.servers.dependencies import get_confluence_fetcher, get_jira_fetcher
from mcp_atlassian.utils.decorators import check_write_access

logger = logging.getLogger(__name__)


def create_jira_instance_tools(
    mcp: FastMCP, instance_name: str, instance_label: str
) -> None:
    """Register Jira tools for a specific instance.

    Args:
        mcp: The FastMCP server to register tools on
        instance_name: Internal instance name (e.g., "" for primary, "tech" for secondary)
        instance_label: Display label (e.g., "primary", "tech")
    """
    # Tool name prefix: "jira_" for primary, "jira_{instance}_" for secondary
    prefix = "jira_" if instance_name == "" else f"jira_{instance_name}_"

    logger.info(
        f"Registering Jira tools for instance '{instance_label}' with prefix '{prefix}'"
    )

    # Create tool functions with instance_name captured in closure

    @mcp.tool(
        name=f"{prefix}get_user_profile",
        tags={"jira", "read"},
        annotations={
            "title": f"Get Jira User Profile ({instance_label})",
            "readOnlyHint": True,
        },
    )
    async def get_user_profile(
        ctx: Context,
        user_identifier: Annotated[
            str,
            Field(
                description="Identifier for the user (e.g., email address 'user@example.com', username 'johndoe', account ID 'accountid:...', or key for Server/DC)."
            ),
        ],
    ) -> str:
        """Retrieve profile information for a specific Jira user."""
        from requests.exceptions import HTTPError

        from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
        from mcp_atlassian.models.jira.common import JiraUser

        jira = await get_jira_fetcher(ctx, instance_name=instance_name)
        try:
            user: JiraUser = jira.get_user_profile_by_identifier(user_identifier)
            result = user.to_simplified_dict()
            response_data = {"success": True, "user": result}
        except Exception as e:
            error_message = ""
            log_level = logging.ERROR
            if isinstance(e, ValueError) and "not found" in str(e).lower():
                log_level = logging.WARNING
                error_message = str(e)
            elif isinstance(e, MCPAtlassianAuthenticationError):
                error_message = f"Authentication/Permission Error: {str(e)}"
            elif isinstance(e, OSError | HTTPError):
                error_message = f"Network or API Error: {str(e)}"
            else:
                error_message = (
                    "An unexpected error occurred while fetching the user profile."
                )
                logger.exception(
                    f"Unexpected error in get_user_profile for '{user_identifier}':"
                )
            error_result = {
                "success": False,
                "error": str(e),
                "message": error_message,
            }
            logger.log(log_level, error_message)
            response_data = error_result
        return f"```json\n{str(response_data)}\n```"

    @mcp.tool(
        name=f"{prefix}get_issue",
        tags={"jira", "read"},
        annotations={
            "title": f"Get Jira Issue ({instance_label})",
            "readOnlyHint": True,
        },
    )
    async def get_issue(
        ctx: Context,
        issue_key: Annotated[
            str, Field(description="Jira issue key (e.g., 'PROJ-123')")
        ],
        fields: Annotated[
            str,
            Field(
                description="(Optional) Comma-separated list of fields to return (e.g., 'summary,status,customfield_10010'). You may also provide a single field as a string (e.g., 'duedate'). Use '*all' for all fields (including custom fields), or omit for essential fields only."
            ),
        ] = DEFAULT_READ_JIRA_FIELDS,
        expand: Annotated[
            str | None,
            Field(
                description="(Optional) Fields to expand. Examples: 'renderedFields' (for rendered content), 'transitions' (for available status transitions), 'changelog' (for history)"
            ),
        ] = None,
        comment_limit: Annotated[
            int,
            Field(
                description="Maximum number of comments to include (0 or null for no comments)",
                ge=0,
                le=100,
            ),
        ] = 10,
        properties: Annotated[
            str | None,
            Field(
                description="(Optional) A comma-separated list of issue properties to return"
            ),
        ] = None,
        update_history: Annotated[
            bool,
            Field(
                description="Whether to update the issue view history for the requesting user"
            ),
        ] = True,
    ) -> str:
        """Get details of a specific Jira issue including its Epic links and relationship information."""
        import json

        jira = await get_jira_fetcher(ctx, instance_name=instance_name)
        issue = jira.get_issue(
            issue_key,
            fields=fields,
            expand=expand,
            comment_limit=comment_limit,
            properties=properties,
            update_history=update_history,
        )
        return json.dumps(issue.to_simplified_dict(), indent=2)

    @mcp.tool(
        name=f"{prefix}search",
        tags={"jira", "read"},
        annotations={
            "title": f"Search Jira Issues ({instance_label})",
            "readOnlyHint": True,
        },
    )
    async def search(
        ctx: Context,
        jql: Annotated[
            str,
            Field(
                description='JQL query string (Jira Query Language). Examples:\n- Find Epics: "issuetype = Epic AND project = PROJ"\n- Find issues in Epic: "parent = PROJ-123"\n- Find by status: "status = \'In Progress\' AND project = PROJ"\n- Find by assignee: "assignee = currentUser()"\n- Find recently updated: "updated >= -7d AND project = PROJ"\n- Find by label: "labels = frontend AND project = PROJ"\n- Find by priority: "priority = High AND project = PROJ"'
            ),
        ],
        fields: Annotated[
            str,
            Field(
                description="(Optional) Comma-separated fields to return in the results. Use '*all' for all fields, or specify individual fields like 'summary,status,assignee,priority'"
            ),
        ] = DEFAULT_READ_JIRA_FIELDS,
        limit: Annotated[
            int, Field(description="Maximum number of results (1-50)", ge=1, le=50)
        ] = 10,
        start_at: Annotated[
            int,
            Field(description="Starting index for pagination (0-based)", ge=0),
        ] = 0,
        projects_filter: Annotated[
            str | None,
            Field(
                description="(Optional) Comma-separated list of project keys to filter results by. Overrides the environment variable JIRA_PROJECTS_FILTER if provided."
            ),
        ] = None,
        expand: Annotated[
            str | None,
            Field(
                description="(Optional) fields to expand. Examples: 'renderedFields', 'transitions', 'changelog'"
            ),
        ] = None,
    ) -> str:
        """Search Jira issues using JQL (Jira Query Language)."""
        import json

        jira = await get_jira_fetcher(ctx, instance_name=instance_name)
        results = jira.search_issues(
            jql=jql,
            fields=fields,
            max_results=limit,
            start_at=start_at,
            projects_filter=projects_filter,
            expand=expand,
        )
        return json.dumps(results, indent=2)

    @mcp.tool(
        name=f"{prefix}create_issue",
        tags={"jira", "write"},
        annotations={"title": f"Create Jira Issue ({instance_label})"},
    )
    @check_write_access
    async def create_issue(
        ctx: Context,
        project_key: Annotated[
            str,
            Field(
                description="The JIRA project key (e.g. 'PROJ', 'DEV', 'SUPPORT'). This is the prefix of issue keys in your project. Never assume what it might be, always ask the user."
            ),
        ],
        summary: Annotated[str, Field(description="Summary/title of the issue")],
        issue_type: Annotated[
            str,
            Field(
                description="Issue type (e.g. 'Task', 'Bug', 'Story', 'Epic', 'Subtask'). The available types depend on your project configuration. For subtasks, use 'Subtask' (not 'Sub-task') and include parent in additional_fields."
            ),
        ],
        assignee: Annotated[
            str | None,
            Field(
                description="(Optional) Assignee's user identifier (string): Email, display name, or account ID (e.g., 'user@example.com', 'John Doe', 'accountid:...')"
            ),
        ] = None,
        description: Annotated[
            str | None, Field(description="Issue description")
        ] = None,
        components: Annotated[
            str | None,
            Field(
                description="(Optional) Comma-separated list of component names to assign (e.g., 'Frontend,API')"
            ),
        ] = None,
        additional_fields: Annotated[
            dict[str, Any] | None,
            Field(
                description="(Optional) Dictionary of additional fields to set. Examples:\n- Set priority: {'priority': {'name': 'High'}}\n- Add labels: {'labels': ['frontend', 'urgent']}\n- Link to parent (for any issue type): {'parent': 'PROJ-123'}\n- Set Fix Version/s: {'fixVersions': [{'id': '10020'}]}\n- Custom fields: {'customfield_10010': 'value'}"
            ),
        ] = None,
    ) -> str:
        """Create a new Jira issue with optional Epic link or parent for subtasks."""
        import json

        jira = await get_jira_fetcher(ctx, instance_name=instance_name)
        result = jira.create_issue(
            project_key=project_key,
            summary=summary,
            issue_type=issue_type,
            assignee=assignee,
            description=description,
            components=components,
            additional_fields=additional_fields,
        )
        return json.dumps(result, indent=2)

    logger.info(
        f"Successfully registered {5} tools for Jira instance '{instance_label}'"
    )


def create_confluence_instance_tools(
    mcp: FastMCP, instance_name: str, instance_label: str
) -> None:
    """Register Confluence tools for a specific instance.

    Args:
        mcp: The FastMCP server to register tools on
        instance_name: Internal instance name (e.g., "" for primary, "community" for secondary)
        instance_label: Display label (e.g., "primary", "community")
    """
    # Tool name prefix: "confluence_" for primary, "confluence_{instance}_" for secondary
    prefix = "confluence_" if instance_name == "" else f"confluence_{instance_name}_"

    logger.info(
        f"Registering Confluence tools for instance '{instance_label}' with prefix '{prefix}'"
    )

    @mcp.tool(
        name=f"{prefix}search",
        tags={"confluence", "read"},
        annotations={
            "title": f"Search Confluence ({instance_label})",
            "readOnlyHint": True,
        },
    )
    async def search(
        ctx: Context,
        query: Annotated[
            str,
            Field(
                description="Search query - can be either a simple text (e.g. 'project documentation') or a CQL query string. Simple queries use 'siteSearch' by default, to mimic the WebUI search, with an automatic fallback to 'text' search if not supported. Examples of CQL:\n- Basic search: 'type=page AND space=DEV'\n- Personal space search: 'space=\"~username\"' (note: personal space keys starting with ~ must be quoted)\n- Search by title: 'title~\"Meeting Notes\"'\n- Use siteSearch: 'siteSearch ~ \"important concept\"'\n- Use text search: 'text ~ \"important concept\"'\n- Recent content: 'created >= \"2023-01-01\"'\n- Content with specific label: 'label=documentation'\n- Recently modified content: 'lastModified > startOfMonth(\"-1M\")'\n- Content modified this year: 'creator = currentUser() AND lastModified > startOfYear()'\n- Content you contributed to recently: 'contributor = currentUser() AND lastModified > startOfWeek()'\n- Content watched by user: 'watcher = \"user@domain.com\" AND type = page'\n- Exact phrase in content: 'text ~ \"\\\"Urgent Review Required\\\"\" AND label = \"pending-approval\"'\n- Title wildcards: 'title ~ \"Minutes*\" AND (space = \"HR\" OR space = \"Marketing\")'\nNote: Special identifiers need proper quoting in CQL: personal space keys (e.g., \"~username\"), reserved words, numeric IDs, and identifiers with special characters."
            ),
        ],
        limit: Annotated[
            int,
            Field(description="Maximum number of results (1-50)", ge=1, le=50),
        ] = 10,
        spaces_filter: Annotated[
            str | None,
            Field(
                description="(Optional) Comma-separated list of space keys to filter results by. Overrides the environment variable CONFLUENCE_SPACES_FILTER if provided. Use empty string to disable filtering."
            ),
        ] = None,
    ) -> str:
        """Search Confluence content using simple terms or CQL."""
        import json

        confluence = await get_confluence_fetcher(ctx, instance_name=instance_name)
        results = confluence.search(
            query=query, limit=limit, spaces_filter=spaces_filter
        )
        return json.dumps(results, indent=2)

    @mcp.tool(
        name=f"{prefix}get_page",
        tags={"confluence", "read"},
        annotations={
            "title": f"Get Confluence Page ({instance_label})",
            "readOnlyHint": True,
        },
    )
    async def get_page(
        ctx: Context,
        page_id: Annotated[
            str | int | None,
            Field(
                description="Confluence page ID (numeric ID, can be found in the page URL). For example, in the URL 'https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/Page+Title', the page ID is '123456789'. Provide this OR both 'title' and 'space_key'. If page_id is provided, title and space_key will be ignored."
            ),
        ] = None,
        title: Annotated[
            str | None,
            Field(
                description="The exact title of the Confluence page. Use this with 'space_key' if 'page_id' is not known."
            ),
        ] = None,
        space_key: Annotated[
            str | None,
            Field(
                description="The key of the Confluence space where the page resides (e.g., 'DEV', 'TEAM'). Required if using 'title'."
            ),
        ] = None,
        include_metadata: Annotated[
            bool,
            Field(
                description="Whether to include page metadata such as creation date, last update, version, and labels."
            ),
        ] = True,
        convert_to_markdown: Annotated[
            bool,
            Field(
                description="Whether to convert page to markdown (true) or keep it in raw HTML format (false). Raw HTML can reveal macros (like dates) not visible in markdown, but CAUTION: using HTML significantly increases token usage in AI responses."
            ),
        ] = True,
    ) -> str:
        """Get content of a specific Confluence page by its ID, or by its title and space key."""
        import json

        confluence = await get_confluence_fetcher(ctx, instance_name=instance_name)
        result = confluence.get_page(
            page_id=page_id,
            title=title,
            space_key=space_key,
            include_metadata=include_metadata,
            convert_to_markdown=convert_to_markdown,
        )
        return json.dumps(result, indent=2)

    @mcp.tool(
        name=f"{prefix}create_page",
        tags={"confluence", "write"},
        annotations={"title": f"Create Confluence Page ({instance_label})"},
    )
    @check_write_access
    async def create_page(
        ctx: Context,
        space_key: Annotated[
            str,
            Field(
                description="The key of the space to create the page in (usually a short uppercase code like 'DEV', 'TEAM', or 'DOC')"
            ),
        ],
        title: Annotated[str, Field(description="The title of the page")],
        content: Annotated[
            str,
            Field(
                description="The content of the page. Format depends on content_format parameter. Can be Markdown (default), wiki markup, or storage format"
            ),
        ],
        parent_id: Annotated[
            str | None,
            Field(
                description="(Optional) parent page ID. If provided, this page will be created as a child of the specified page"
            ),
        ] = None,
        content_format: Annotated[
            str,
            Field(
                description="(Optional) The format of the content parameter. Options: 'markdown' (default), 'wiki', or 'storage'. Wiki format uses Confluence wiki markup syntax"
            ),
        ] = "markdown",
        enable_heading_anchors: Annotated[
            bool,
            Field(
                description="(Optional) Whether to enable automatic heading anchor generation. Only applies when content_format is 'markdown'"
            ),
        ] = False,
        emoji: Annotated[
            str | None,
            Field(
                description="(Optional) Page title emoji (icon shown in navigation). Can be any emoji character like '📝', '🚀', '📚'. Set to null/None to remove."
            ),
        ] = None,
    ) -> str:
        """Create a new Confluence page."""
        import json

        confluence = await get_confluence_fetcher(ctx, instance_name=instance_name)
        result = confluence.create_page(
            space_key=space_key,
            title=title,
            content=content,
            parent_id=parent_id,
            content_format=content_format,
            enable_heading_anchors=enable_heading_anchors,
            emoji=emoji,
        )
        return json.dumps(result, indent=2)

    logger.info(
        f"Successfully registered {4} tools for Confluence instance '{instance_label}'"
    )
