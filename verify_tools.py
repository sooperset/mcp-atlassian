#!/usr/bin/env python3
"""Verify what tools will be available with current configuration.

Run this script to verify multi-instance tool registration before starting your MCP client.
"""
import asyncio
import json
import os
import sys


async def verify_tools():
    """Verify tools that will be registered."""
    # Import here to get environment from shell
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

    from mcp_atlassian.jira.config import JiraConfig
    from mcp_atlassian.confluence.config import ConfluenceConfig

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
                "confluence_"
                if instance_name == ""
                else f"confluence_{instance_name}_"
            )
            print(f"  • {instance_label:15} {config.url}")
            print(f"    Tool prefix: {prefix}")
            if instance_name != "":
                print(f"    Example: {prefix}search, {prefix}get_page")
    except Exception as e:
        print(f"\n❌ Error loading Confluence configs: {e}")
        confluence_configs = {}

    # Show expected tools
    if any(name != "" for name in jira_configs.keys()):
        print("\n" + "=" * 70)
        print("Expected Secondary Instance Tools:")
        print("=" * 70)
        for instance_name in jira_configs.keys():
            if instance_name != "":
                prefix = f"jira_{instance_name}_"
                print(f"\nJira '{instance_name}' instance tools:")
                for tool in [
                    "get_user_profile",
                    "get_issue",
                    "search",
                    "create_issue",
                ]:
                    print(f"  ✓ {prefix}{tool}")

    if any(name != "" for name in confluence_configs.keys()):
        for instance_name in confluence_configs.keys():
            if instance_name != "":
                prefix = f"confluence_{instance_name}_"
                print(f"\nConfluence '{instance_name}' instance tools:")
                for tool in ["search", "get_page", "create_page"]:
                    print(f"  ✓ {prefix}{tool}")

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
