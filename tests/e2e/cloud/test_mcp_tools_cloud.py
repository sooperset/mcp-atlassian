"""MCP tool-level tests against Cloud instances."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any
from unittest.mock import patch

import pytest
from fastmcp import Client
from fastmcp.client import FastMCPTransport
from mcp.types import CallToolResult, TextContent

from mcp_atlassian.servers import main_mcp

from .conftest import CloudInstanceInfo

pytestmark = [pytest.mark.cloud_e2e, pytest.mark.anyio]


async def call_tool(
    client: Client, tool_name: str, arguments: dict[str, Any]
) -> CallToolResult:
    """Helper to call tools via the MCP client."""
    return await client.call_tool(tool_name, arguments)


@pytest.fixture
def cloud_env(cloud_instance: CloudInstanceInfo) -> dict[str, str]:
    """Environment variables for configuring MCP server against Cloud."""
    return {
        "JIRA_URL": cloud_instance.jira_url,
        "JIRA_USERNAME": cloud_instance.username,
        "JIRA_API_TOKEN": cloud_instance.api_token,
        "CONFLUENCE_URL": cloud_instance.confluence_url,
        "CONFLUENCE_USERNAME": cloud_instance.username,
        "CONFLUENCE_API_TOKEN": cloud_instance.api_token,
        "READ_ONLY_MODE": "false",
        "TOOLSETS": "all",
    }


@pytest.fixture
async def mcp_client(cloud_env: dict[str, str]) -> Any:
    """MCP client connected to the server configured for Cloud."""
    with patch.dict(os.environ, cloud_env, clear=False):
        transport = FastMCPTransport(main_mcp)
        client = Client(transport=transport)
        async with client as connected_client:
            yield connected_client


class TestMCPJiraTools:
    """MCP Jira tool tests against Cloud."""

    @pytest.mark.anyio
    async def test_jira_get_issue(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        result = await call_tool(
            mcp_client,
            "jira_get_issue",
            {"issue_key": cloud_instance.test_issue_key},
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        assert data["key"] == cloud_instance.test_issue_key

    @pytest.mark.anyio
    async def test_jira_search(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        result = await call_tool(
            mcp_client,
            "jira_search",
            {
                "jql": f"project={cloud_instance.project_key}",
                "limit": 5,
            },
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        assert "issues" in data
        assert len(data["issues"]) > 0

    @pytest.mark.anyio
    async def test_jira_create_and_delete_issue(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        result = await call_tool(
            mcp_client,
            "jira_create_issue",
            {
                "project_key": cloud_instance.project_key,
                "summary": f"Cloud MCP Tool Test {uid}",
                "description": "Created via MCP tool test.",
                "issue_type": "Task",
            },
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        issue_key = data["issue"]["key"]
        assert issue_key.startswith(cloud_instance.project_key)

        # Cleanup
        await call_tool(
            mcp_client,
            "jira_delete_issue",
            {"issue_key": issue_key},
        )


class TestMCPConfluenceTools:
    """MCP Confluence tool tests against Cloud."""

    @pytest.mark.anyio
    async def test_confluence_get_page(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        result = await call_tool(
            mcp_client,
            "confluence_get_page",
            {"page_id": cloud_instance.test_page_id},
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)

    @pytest.mark.anyio
    async def test_confluence_search(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        result = await call_tool(
            mcp_client,
            "confluence_search",
            {"query": "Cloud E2E", "limit": 5},
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)

    @pytest.mark.anyio
    async def test_confluence_create_and_delete_page(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        result = await call_tool(
            mcp_client,
            "confluence_create_page",
            {
                "space_key": cloud_instance.space_key,
                "title": f"Cloud MCP Tool Test {uid}",
                "content": "<p>Created via MCP tool test.</p>",
            },
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        page_id = data["page"]["id"]
        assert page_id is not None

        # Cleanup
        await call_tool(
            mcp_client,
            "confluence_delete_page",
            {"page_id": page_id},
        )
