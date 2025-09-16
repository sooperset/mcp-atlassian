#!/usr/bin/env python3
"""Check what tools are available in the Jira MCP server."""

import asyncio
import json
from src.mcp_atlassian.servers.jira import jira_mcp


async def check_tools():
    """List all available tools in the Jira MCP server."""
    print("Checking available Jira MCP tools...")

    # Get the tools list
    tools_list = await jira_mcp.list_tools()

    # Extract just the tool names
    tool_names = [tool.name for tool in tools_list.tools]

    # Print all tools
    print(f"\nTotal tools available: {len(tool_names)}")
    print("\nAvailable tools:")
    for name in sorted(tool_names):
        print(f"  - {name}")

    # Check for forms-related tools
    forms_tools = [name for name in tool_names if 'form' in name.lower()]
    print(f"\nForms-related tools: {len(forms_tools)}")
    for name in sorted(forms_tools):
        print(f"  - {name}")

    return tool_names


if __name__ == "__main__":
    asyncio.run(check_tools())