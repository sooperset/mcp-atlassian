#!/usr/bin/env python3
"""Verify what tools will be available with current configuration.

Run this script to verify multi-instance tool registration before starting your MCP client.
"""

import asyncio
import os
import sys

# Canonical list of all tools (must match server registration).
# Primary Jira: jira_<name> (from servers/jira.py, mounted with prefix "jira").
# Primary Confluence: confluence_<name> (from servers/confluence.py, mounted with "confluence").
# Router: registered on main_mcp when len(jira_configs) > 1.
# Instance: jira_{instance}_<name> / confluence_{instance}_<name> from tool_factory.

PRIMARY_JIRA_TOOLS = [
    "get_user_profile",
    "get_issue",
    "search",
    "search_fields",
    "get_project_issues",
    "get_transitions",
    "get_worklog",
    "download_attachments",
    "get_agile_boards",
    "get_board_issues",
    "get_sprints_from_board",
    "get_sprint_issues",
    "get_link_types",
    "create_issue",
    "batch_create_issues",
    "batch_get_changelogs",
    "update_issue",
    "delete_issue",
    "add_comment",
    "edit_comment",
    "add_worklog",
    "link_to_epic",
    "create_issue_link",
    "create_remote_issue_link",
    "remove_issue_link",
    "transition_issue",
    "create_sprint",
    "update_sprint",
    "get_project_versions",
    "get_all_projects",
    "create_version",
    "batch_create_versions",
    "jira_get_issue_dates",
    "jira_get_issue_sla",
]

PRIMARY_CONFLUENCE_TOOLS = [
    "search",
    "get_page",
    "get_page_children",
    "get_comments",
    "get_labels",
    "add_label",
    "create_page",
    "update_page",
    "delete_page",
    "add_comment",
    "search_user",
    "confluence_get_page_views",
]

ROUTER_TOOLS = [
    "get_jira_issue_auto",
    "search_jira_auto",
    "create_jira_issue_auto",
    "jira_update_issue_auto",
]

# Subset of primary tools registered per secondary Jira instance (tool_factory).
JIRA_INSTANCE_TOOLS = ["get_user_profile", "get_issue", "search", "create_issue"]

# Subset of primary tools registered per secondary Confluence instance (tool_factory).
CONFLUENCE_INSTANCE_TOOLS = ["search", "get_page", "create_page"]


async def verify_tools() -> None:
    """Verify tools that will be registered."""
    # Import here to get environment from shell
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

    from mcp_atlassian.confluence.config import ConfluenceConfig
    from mcp_atlassian.jira.config import JiraConfig

    print("=" * 70)
    print("MCP-Atlassian Multi-Instance Tool Verification")
    print("=" * 70)

    # Load Jira configs
    try:
        jira_configs = JiraConfig.from_env_multi()
        print(f"\n📊 Jira Instances: {len(jira_configs)}")
        for instance_name, config in jira_configs.items():
            instance_label = "primary" if instance_name == "" else instance_name
            prefix = "jira_" if instance_name == "" else f"jira_{instance_name}_"
            print(f"  • {instance_label:15} {config.url}")
            print(f"    Tool prefix: {prefix}")
            if instance_name != "":
                print(f"    Example: {prefix}get_issue, {prefix}search")
    except Exception as e:
        print(f"\n❌ Error loading Jira configs: {e}")
        jira_configs = {}

    # Load Confluence configs
    try:
        confluence_configs = ConfluenceConfig.from_env_multi()
        print(f"\n📚 Confluence Instances: {len(confluence_configs)}")
        for instance_name, config in confluence_configs.items():
            instance_label = "primary" if instance_name == "" else instance_name
            prefix = (
                "confluence_" if instance_name == "" else f"confluence_{instance_name}_"
            )
            print(f"  • {instance_label:15} {config.url}")
            print(f"    Tool prefix: {prefix}")
            if instance_name != "":
                print(f"    Example: {prefix}search, {prefix}get_page")
    except Exception as e:
        print(f"\n❌ Error loading Confluence configs: {e}")
        confluence_configs = {}

    # Show expected secondary instance tools
    if any(name != "" for name in jira_configs.keys()):
        print("\n" + "=" * 70)
        print("Expected Secondary Instance Tools:")
        print("=" * 70)
        for instance_name in jira_configs.keys():
            if instance_name != "":
                prefix = f"jira_{instance_name}_"
                print(f"\nJira '{instance_name}' instance tools:")
                for tool in JIRA_INSTANCE_TOOLS:
                    print(f"  ✓ {prefix}{tool}")

    if any(name != "" for name in confluence_configs.keys()):
        for instance_name in confluence_configs.keys():
            if instance_name != "":
                prefix = f"confluence_{instance_name}_"
                print(f"\nConfluence '{instance_name}' instance tools:")
                for tool in CONFLUENCE_INSTANCE_TOOLS:
                    print(f"  ✓ {prefix}{tool}")

    # Full checklist: all tools that will be registered (or would be with config)
    print("\n" + "=" * 70)
    print("All Tools (checklist)")
    print("=" * 70)
    total = 0
    if jira_configs:
        print("\n📊 Primary Jira:")
        for tool in PRIMARY_JIRA_TOOLS:
            print(f"  • jira_{tool}")
            total += 1
    else:
        print("\n📊 Primary Jira: (none — set JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN)")
    if confluence_configs:
        print("\n📚 Primary Confluence:")
        for tool in PRIMARY_CONFLUENCE_TOOLS:
            print(f"  • confluence_{tool}")
            total += 1
    else:
        print("\n📚 Primary Confluence: (none — set CONFLUENCE_* env)")
    if len(jira_configs) > 1:
        print("\n🔀 Router (auto-detect instance):")
        for tool in ROUTER_TOOLS:
            print(f"  • {tool}")
            total += 1
    else:
        print("\n🔀 Router: (only when 2+ Jira instances)")
    for instance_name in jira_configs.keys():
        if instance_name != "":
            prefix = f"jira_{instance_name}_"
            print(f"\n📊 Jira '{instance_name}' instance:")
            for tool in JIRA_INSTANCE_TOOLS:
                print(f"  • {prefix}{tool}")
                total += 1
    for instance_name in confluence_configs.keys():
        if instance_name != "":
            prefix = f"confluence_{instance_name}_"
            print(f"\n📚 Confluence '{instance_name}' instance:")
            for tool in CONFLUENCE_INSTANCE_TOOLS:
                print(f"  • {prefix}{tool}")
                total += 1
    if total > 0:
        print(f"\nTotal tools: {total}")

    print("\n" + "=" * 70)
    print("Next Steps:")
    print("=" * 70)
    print("1. Restart Cursor completely (Cmd+Q, then reopen)")
    print("2. Tools will be registered during MCP server startup")
    print("3. Look for log messages like:")
    print("   '🔧 Registering tools for Jira instance...'")
    print("4. Try using the tools in Cursor")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(verify_tools())
