"""Smart routing tools for automatic instance detection.

These tools automatically detect which Jira/Confluence instance to use based on:
- URL patterns (e.g., justworks-tech.atlassian.net → tech instance)
- Issue key prefixes (e.g., INFRAOPS-* → tech instance if configured)
- Project keys (if known mapping exists)
"""

import re

from mcp.server.fastmcp import Context, FastMCP

from mcp_atlassian.jira.config import JiraConfig
from mcp_atlassian.servers.dependencies import get_jira_fetcher


def extract_issue_key(text: str) -> str:
    """Extract Jira issue key from URL or text.

    Args:
        text: URL like "https://site.atlassian.net/browse/PROJ-123" or just "PROJ-123"

    Returns:
        Issue key like "PROJ-123"

    Examples:
        >>> extract_issue_key("https://justworks.atlassian.net/browse/PROJ-123")
        'PROJ-123'
        >>> extract_issue_key("PROJ-123")
        'PROJ-123'
    """
    # Try to extract from URL first
    url_match = re.search(r"/browse/([A-Z]+-\d+)", text)
    if url_match:
        return url_match.group(1)

    # Try to match standalone issue key
    key_match = re.search(r"\b([A-Z]+-\d+)\b", text)
    if key_match:
        return key_match.group(1)

    # Return as-is if no pattern matched (might be just the key)
    return text


def detect_jira_instance(text: str, configs: dict[str, JiraConfig]) -> str:
    """Detect which Jira instance to use based on URL or issue key.

    Args:
        text: URL, issue key, or project key
        configs: Loaded Jira instance configurations

    Returns:
        Instance name ("" for primary, "tech" for secondary, etc.)

    Examples:
        >>> detect_jira_instance("https://justworks-tech.atlassian.net/browse/INFRAOPS-123", configs)
        'tech'
        >>> detect_jira_instance("PROJ-123", configs)
        ''
    """
    # Check URL patterns
    for instance_name, config in configs.items():
        # Extract domain from config URL
        domain_match = re.search(r"https?://([^/]+)", config.url)
        if domain_match:
            domain = domain_match.group(1)
            if domain in text:
                return instance_name

    # Check project key patterns (can be extended with known mappings)
    # For now, check if issue key matches known patterns
    issue_key = extract_issue_key(text)

    # Example: INFRAOPS-* goes to tech instance
    if issue_key.startswith("INFRAOPS-"):
        # Find tech instance
        for instance_name, config in configs.items():
            if "justworks-tech" in config.url:
                return instance_name

    # Default to primary instance
    return ""


def create_router_tools(
    mcp: FastMCP,
    jira_configs: dict[str, JiraConfig],
) -> None:
    """Register smart routing tools that auto-detect instances.

    Args:
        mcp: FastMCP server instance
        jira_configs: Loaded Jira instance configurations
    """

    @mcp.tool(
        name="get_jira_issue_auto",
        tags={"jira", "read", "router"},
        annotations={
            "title": "Get Jira Issue (Auto-Route)",
            "readOnlyHint": True,
        },
    )
    async def get_jira_issue_auto(
        ctx: Context,
        issue_url_or_key: str,
        fields: str = "status,updated,priority,assignee,issuetype,created,summary,description,labels,reporter",
        expand: str | None = None,
    ) -> str:
        """Get Jira issue from ANY configured instance with automatic routing.

        This tool automatically detects which Jira instance to use based on:
        - Full URL: https://justworks-tech.atlassian.net/browse/INFRAOPS-15157
        - Issue key patterns: INFRAOPS-* automatically routes to tech instance
        - Project key patterns: [can be extended with known mappings]

        Args:
            issue_url_or_key: Full Jira URL or issue key (e.g., "PROJ-123" or "https://...")
            fields: Comma-separated fields to return (default: essential fields)
            expand: Optional fields to expand (e.g., "changelog", "transitions")

        Returns:
            JSON string with issue details

        Examples:
            >>> get_jira_issue_auto("https://justworks-tech.atlassian.net/browse/INFRAOPS-15157")
            # Automatically uses tech instance

            >>> get_jira_issue_auto("INFRAOPS-15157")
            # Detects INFRAOPS prefix, uses tech instance

            >>> get_jira_issue_auto("PROJ-123")
            # No specific pattern, uses primary instance
        """
        # Detect which instance to use
        instance_name = detect_jira_instance(issue_url_or_key, jira_configs)

        # Extract issue key
        issue_key = extract_issue_key(issue_url_or_key)

        # Get the appropriate fetcher
        jira = await get_jira_fetcher(ctx, instance_name=instance_name)

        # Get issue details
        issue = await jira.get_issue(
            issue_key=issue_key,
            fields=fields,
            expand=expand,
        )

        # Add routing metadata to response
        instance_label = "primary" if instance_name == "" else instance_name
        instance_url = jira_configs[instance_name].url

        return f"""{{
  "_routing_info": {{
    "instance": "{instance_label}",
    "instance_url": "{instance_url}",
    "detected_from": "{issue_url_or_key}"
  }},
  "issue": {issue}
}}"""

    @mcp.tool(
        name="search_jira_auto",
        tags={"jira", "read", "router"},
        annotations={
            "title": "Search Jira Issues (Auto-Route)",
            "readOnlyHint": True,
        },
    )
    async def search_jira_auto(
        ctx: Context,
        jql: str,
        instance_hint: str | None = None,
        fields: str = "status,updated,priority,assignee,issuetype,created,summary,description,labels,reporter",
        limit: int = 10,
    ) -> str:
        """Search Jira issues with automatic instance detection.

        Args:
            jql: JQL query string
            instance_hint: Optional hint for instance selection:
                          - URL like "https://justworks-tech.atlassian.net"
                          - Instance name like "tech"
                          - If not provided, uses primary instance
            fields: Comma-separated fields to return
            limit: Maximum number of results (1-50)

        Returns:
            JSON string with search results

        Examples:
            >>> search_jira_auto("project = INFRAOPS AND status = 'In Progress'", instance_hint="tech")
            # Explicitly uses tech instance

            >>> search_jira_auto("status = Open", instance_hint="https://justworks-tech.atlassian.net")
            # Detects tech instance from URL

            >>> search_jira_auto("project = PROJ")
            # No hint, uses primary instance
        """
        # Detect instance from hint or use primary
        instance_name = ""
        if instance_hint:
            instance_name = detect_jira_instance(instance_hint, jira_configs)

        # Get the appropriate fetcher
        jira = await get_jira_fetcher(ctx, instance_name=instance_name)

        # Search issues
        results = await jira.search(
            jql=jql,
            fields=fields,
            limit=limit,
        )

        # Add routing metadata
        instance_label = "primary" if instance_name == "" else instance_name
        instance_url = jira_configs[instance_name].url

        return f"""{{
  "_routing_info": {{
    "instance": "{instance_label}",
    "instance_url": "{instance_url}",
    "instance_hint": {f'"{instance_hint}"' if instance_hint else "null"}
  }},
  "results": {results}
}}"""

    @mcp.tool(
        name="create_jira_issue_auto",
        tags={"jira", "write", "router"},
        annotations={
            "title": "Create Jira Issue (Auto-Route)",
        },
    )
    async def create_jira_issue_auto(
        ctx: Context,
        project_key: str,
        summary: str,
        issue_type: str,
        instance_hint: str | None = None,
        description: str | None = None,
        assignee: str | None = None,
    ) -> str:
        """Create a Jira issue with automatic instance detection.

        Args:
            project_key: Project key (e.g., "INFRAOPS", "PROJ")
            summary: Issue summary/title
            issue_type: Issue type (e.g., "Task", "Bug", "Story")
            instance_hint: Optional hint for instance selection:
                          - URL like "https://justworks-tech.atlassian.net"
                          - Instance name like "tech"
                          - Project key like "INFRAOPS" (will try to match)
                          - If not provided, uses primary instance
            description: Issue description (optional)
            assignee: Assignee username or email (optional)

        Returns:
            JSON string with created issue details

        Examples:
            >>> create_jira_issue_auto("INFRAOPS", "Fix server", "Task", instance_hint="tech")
            # Creates in tech instance

            >>> create_jira_issue_auto("INFRAOPS", "Fix server", "Task", instance_hint="INFRAOPS-123")
            # Detects tech instance from INFRAOPS issue key pattern
        """
        # Detect instance
        instance_name = ""
        if instance_hint:
            instance_name = detect_jira_instance(instance_hint, jira_configs)
        elif project_key.startswith("INFRAOPS"):
            # Known project mapping
            instance_name = detect_jira_instance("INFRAOPS-", jira_configs)

        # Get the appropriate fetcher
        jira = await get_jira_fetcher(ctx, instance_name=instance_name)

        # Create issue
        result = await jira.create_issue(
            project_key=project_key,
            summary=summary,
            issue_type=issue_type,
            description=description,
            assignee=assignee,
        )

        # Add routing metadata
        instance_label = "primary" if instance_name == "" else instance_name
        instance_url = jira_configs[instance_name].url

        return f"""{{
  "_routing_info": {{
    "instance": "{instance_label}",
    "instance_url": "{instance_url}",
    "instance_hint": {f'"{instance_hint}"' if instance_hint else "null"}
  }},
  "created_issue": {result}
}}"""
