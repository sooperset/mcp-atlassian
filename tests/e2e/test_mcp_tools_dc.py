"""MCP tool-level tests against DC instances."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastmcp import Client
from fastmcp.client import FastMCPTransport
from mcp.types import CallToolResult, TextContent

from mcp_atlassian.servers import main_mcp

from .conftest import DCInstanceInfo

pytestmark = [pytest.mark.dc_e2e, pytest.mark.anyio]


async def call_tool(
    client: Client, tool_name: str, arguments: dict[str, Any]
) -> CallToolResult:
    """Helper to call tools via the MCP client."""
    return await client.call_tool(tool_name, arguments)


@pytest.fixture
def dc_env(dc_instance: DCInstanceInfo) -> dict[str, str]:
    """Environment variables for configuring MCP server against DC."""
    return {
        "JIRA_URL": dc_instance.jira_url,
        "JIRA_USERNAME": dc_instance.admin_username,
        "JIRA_API_TOKEN": dc_instance.admin_password,
        "CONFLUENCE_URL": dc_instance.confluence_url,
        "CONFLUENCE_USERNAME": dc_instance.admin_username,
        "CONFLUENCE_API_TOKEN": dc_instance.admin_password,
        "READ_ONLY_MODE": "false",
        "TOOLSETS": "all",
    }


@pytest.fixture
async def mcp_client(dc_env: dict[str, str]) -> Any:
    """MCP client connected to the server configured for DC."""
    with patch.dict(os.environ, dc_env, clear=False):
        transport = FastMCPTransport(main_mcp)
        client = Client(transport=transport)
        async with client as connected_client:
            yield connected_client


class TestMCPJiraTools:
    """MCP Jira tool tests against DC."""

    @pytest.mark.anyio
    async def test_jira_get_issue(
        self,
        mcp_client: Client,
        dc_instance: DCInstanceInfo,
    ) -> None:
        result = await call_tool(
            mcp_client,
            "jira_get_issue",
            {"issue_key": dc_instance.test_issue_key},
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        assert data["key"] == dc_instance.test_issue_key

    @pytest.mark.anyio
    async def test_jira_get_issue_include_remote_links(
        self,
        mcp_client: Client,
        dc_instance: DCInstanceInfo,
    ) -> None:
        result = await call_tool(
            mcp_client,
            "jira_get_issue",
            {
                "issue_key": dc_instance.test_issue_key,
                "fields": "summary,status",
                "include": "remote_links",
            },
        )

        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        assert data["key"] == dc_instance.test_issue_key
        assert isinstance(data["remote_links"], list)

    @pytest.mark.anyio
    async def test_jira_search(
        self,
        mcp_client: Client,
        dc_instance: DCInstanceInfo,
    ) -> None:
        result = await call_tool(
            mcp_client,
            "jira_search",
            {
                "jql": f"project={dc_instance.project_key}",
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
        dc_instance: DCInstanceInfo,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        result = await call_tool(
            mcp_client,
            "jira_create_issue",
            {
                "project_key": dc_instance.project_key,
                "summary": f"MCP Tool Test {uid}",
                "description": "Created via MCP tool test.",
                "issue_type": "Task",
            },
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        issue_key = data["issue"]["key"]
        assert issue_key.startswith(dc_instance.project_key)

        # Cleanup
        await call_tool(
            mcp_client,
            "jira_delete_issue",
            {"issue_key": issue_key},
        )

    @pytest.mark.anyio
    async def test_jira_assign_issue(
        self,
        mcp_client: Client,
        dc_instance: DCInstanceInfo,
    ) -> None:
        assign_result = await call_tool(
            mcp_client,
            "jira_assign_issue",
            {
                "issue_key": dc_instance.test_issue_key,
                "assignee": dc_instance.admin_username,
            },
        )
        assert not assign_result.is_error
        assert assign_result.content
        assign_data = json.loads(assign_result.content[0].text)
        assignee = assign_data["issue"].get("assignee")
        assert isinstance(assignee, dict)
        assert assignee.get("name") or assignee.get("display_name")


class TestMCPConfluenceTools:
    """MCP Confluence tool tests against DC."""

    @pytest.mark.anyio
    async def test_confluence_get_page(
        self,
        mcp_client: Client,
        dc_instance: DCInstanceInfo,
    ) -> None:
        result = await call_tool(
            mcp_client,
            "confluence_get_page",
            {"page_id": dc_instance.test_page_id},
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)

    @pytest.mark.anyio
    async def test_confluence_search(
        self,
        mcp_client: Client,
        dc_instance: DCInstanceInfo,
    ) -> None:
        result = await call_tool(
            mcp_client,
            "confluence_search",
            {"query": "E2E", "limit": 5},
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)

    @pytest.mark.anyio
    async def test_confluence_create_and_delete_page(
        self,
        mcp_client: Client,
        dc_instance: DCInstanceInfo,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        result = await call_tool(
            mcp_client,
            "confluence_create_page",
            {
                "space_key": dc_instance.space_key,
                "title": f"MCP Tool Test {uid}",
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

    @pytest.mark.anyio
    async def test_confluence_create_update_xhtml_page(
        self,
        mcp_client: Client,
        dc_instance: DCInstanceInfo,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page_id = None
        create_result = await call_tool(
            mcp_client,
            "confluence_create_page",
            {
                "space_key": dc_instance.space_key,
                "title": f"MCP XHTML Tool Test {uid}",
                "content": "<p>Created via MCP XHTML tool test.</p>",
                "content_format": "xhtml",
            },
        )
        assert not create_result.is_error
        assert create_result.content and isinstance(
            create_result.content[0], TextContent
        )
        page_id = json.loads(create_result.content[0].text)["page"]["id"]
        assert page_id is not None

        try:
            update_result = await call_tool(
                mcp_client,
                "confluence_update_page",
                {
                    "page_id": page_id,
                    "title": f"MCP XHTML Tool Test {uid}",
                    "content": "<p>Updated via MCP XHTML tool test.</p>",
                    "content_format": "xhtml",
                },
            )
            assert not update_result.is_error
        finally:
            if page_id:
                await call_tool(
                    mcp_client,
                    "confluence_delete_page",
                    {"page_id": page_id},
                )

    @pytest.mark.anyio
    async def test_confluence_create_update_page_with_content_file(
        self,
        mcp_client: Client,
        dc_instance: DCInstanceInfo,
        tmp_path: Path,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page_id = None
        create_file = tmp_path / "dc-create.md"
        update_file = tmp_path / "dc-update.md"
        create_file.write_text("# Created from file\n\nDC body.", encoding="utf-8")
        update_file.write_text("# Updated from file\n\nDC body.", encoding="utf-8")

        create_result = await call_tool(
            mcp_client,
            "confluence_create_page",
            {
                "space_key": dc_instance.space_key,
                "title": f"MCP File Tool Test {uid}",
                "content_file": str(create_file),
            },
        )
        assert not create_result.is_error
        assert create_result.content and isinstance(
            create_result.content[0], TextContent
        )
        page_id = json.loads(create_result.content[0].text)["page"]["id"]
        assert page_id is not None

        try:
            update_result = await call_tool(
                mcp_client,
                "confluence_update_page",
                {
                    "page_id": page_id,
                    "title": f"MCP File Tool Test {uid}",
                    "content_file": str(update_file),
                },
            )
            assert not update_result.is_error
        finally:
            if page_id:
                await call_tool(
                    mcp_client,
                    "confluence_delete_page",
                    {"page_id": page_id},
                )

    @pytest.mark.anyio
    async def test_confluence_update_page_section(
        self,
        mcp_client: Client,
        dc_instance: DCInstanceInfo,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page_id = None
        create_result = await call_tool(
            mcp_client,
            "confluence_create_page",
            {
                "space_key": dc_instance.space_key,
                "title": f"MCP Section Update Test {uid}",
                "content": (
                    "# Summary\n\nKeep summary.\n\n"
                    "## Target Section\n\nOld target body.\n\n"
                    "## Next Section\n\nKeep next."
                ),
            },
        )
        assert not create_result.is_error
        assert create_result.content and isinstance(
            create_result.content[0], TextContent
        )
        page_id = json.loads(create_result.content[0].text)["page"]["id"]

        try:
            update_result = await call_tool(
                mcp_client,
                "confluence_update_page_section",
                {
                    "page_id": page_id,
                    "heading_text": "Target Section",
                    "new_content": "New target body.",
                    "is_minor_edit": True,
                    "version_comment": "DC MCP e2e section update",
                },
            )
            assert not update_result.is_error

            get_result = await call_tool(
                mcp_client,
                "confluence_get_page",
                {"page_id": page_id, "include_metadata": False},
            )
            assert not get_result.is_error
            assert get_result.content and isinstance(get_result.content[0], TextContent)
            content = json.loads(get_result.content[0].text)["content"]["value"]
            assert "New target body" in content
            assert "Old target body" not in content
            assert "Keep summary" in content
            assert "Keep next" in content
        finally:
            if page_id:
                await call_tool(
                    mcp_client,
                    "confluence_delete_page",
                    {"page_id": page_id},
                )
