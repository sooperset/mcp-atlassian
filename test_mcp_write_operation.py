#!/usr/bin/env python3
"""
Test script to call MCP server write operations and trigger debug logging.
This will help us see what happens in the @check_write_access decorator.
"""

import json
import sys
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_write_operation():
    print("=== MCP WRITE OPERATION TEST ===")
    print("Testing confluence_create_page through MCP server...")
    
    # Create MCP client connection to the server
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "mcp-atlassian", "-vv"],
        env=None
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the session
                await session.initialize()
                
                print("Connected to MCP server successfully")
                
                # Try to call confluence_create_page
                print("Calling confluence_create_page...")
                
                result = await session.call_tool(
                    "confluence_create_page",
                    arguments={
                        "space_key": "TEST",
                        "title": "Debug Test Page",
                        "content": "This is a debug test page to trigger the decorator logging.",
                        "content_format": "markdown"
                    }
                )
                
                print(f"Result: {result}")
                
    except Exception as e:
        print(f"Error: {e}")
        print(f"Error type: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_write_operation())