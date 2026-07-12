"""MCP tool-level tests against Cloud instances."""

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

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.jira import JiraFetcher
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
    async def test_jira_get_issue_use_display_names(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        result = await call_tool(
            mcp_client,
            "jira_get_issue",
            {
                "issue_key": cloud_instance.test_issue_key,
                "fields": "*all",
                "use_display_names": True,
            },
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        assert data["key"] == cloud_instance.test_issue_key
        custom_fields = {
            key: value
            for key, value in data.items()
            if isinstance(value, dict) and "field_id" in value
        }
        assert custom_fields
        assert any(key != value["field_id"] for key, value in custom_fields.items())

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
    async def test_jira_search_use_display_names(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        result = await call_tool(
            mcp_client,
            "jira_search",
            {
                "jql": f"project={cloud_instance.project_key}",
                "fields": "*all",
                "limit": 1,
                "use_display_names": True,
            },
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        assert len(data["issues"]) == 1
        issue = data["issues"][0]
        assert issue["key"].startswith(f"{cloud_instance.project_key}-")
        custom_fields = {
            key: value
            for key, value in issue.items()
            if isinstance(value, dict) and "field_id" in value
        }
        assert custom_fields
        assert any(key != value["field_id"] for key, value in custom_fields.items())

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

    @pytest.mark.anyio
    async def test_jira_assign_issue(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
        jira_fetcher: JiraFetcher,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        result = await call_tool(
            mcp_client,
            "jira_create_issue",
            {
                "project_key": cloud_instance.project_key,
                "summary": f"Cloud MCP Assign Test {uid}",
                "description": "Created for MCP assign_issue test.",
                "issue_type": "Task",
            },
        )
        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        issue_key = data["issue"]["key"]

        try:
            account_id = jira_fetcher.get_current_user_account_id()
            assign_result = await call_tool(
                mcp_client,
                "jira_assign_issue",
                {"issue_key": issue_key, "assignee": account_id},
            )
            assert not assign_result.is_error
            assert assign_result.content
            assign_data = json.loads(assign_result.content[0].text)
            assignee = assign_data["issue"].get("assignee")
            assert isinstance(assignee, dict)
            assert assignee.get("account_id") == account_id
        finally:
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
    async def test_confluence_get_page_with_tiny_link(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
        confluence_fetcher: ConfluenceFetcher,
    ) -> None:
        raw_page = confluence_fetcher.confluence.get_page_by_id(
            cloud_instance.test_page_id
        )
        assert isinstance(raw_page, dict)
        links = raw_page["_links"]
        tiny_url = (
            f"{links.get('base', cloud_instance.confluence_url).rstrip('/')}"
            f"/{links['tinyui'].lstrip('/')}"
        )

        result = await call_tool(
            mcp_client,
            "confluence_get_page",
            {"page_id": tiny_url},
        )

        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        assert str(data["metadata"]["id"]) == cloud_instance.test_page_id

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

    @pytest.mark.anyio
    async def test_confluence_create_update_xhtml_page(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page_id = None
        create_result = await call_tool(
            mcp_client,
            "confluence_create_page",
            {
                "space_key": cloud_instance.space_key,
                "title": f"Cloud MCP XHTML Tool Test {uid}",
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
                    "title": f"Cloud MCP XHTML Tool Test {uid}",
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
        cloud_instance: CloudInstanceInfo,
        workspace_tmp_path: Path,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page_id = None
        create_file = workspace_tmp_path / "cloud-create.md"
        update_file = workspace_tmp_path / "cloud-update.md"
        create_file.write_text("# Created from file\n\nCloud body.", encoding="utf-8")
        update_file.write_text("# Updated from file\n\nCloud body.", encoding="utf-8")

        create_result = await call_tool(
            mcp_client,
            "confluence_create_page",
            {
                "space_key": cloud_instance.space_key,
                "title": f"Cloud MCP File Tool Test {uid}",
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
                    "title": f"Cloud MCP File Tool Test {uid}",
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
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        page_id = None
        create_result = await call_tool(
            mcp_client,
            "confluence_create_page",
            {
                "space_key": cloud_instance.space_key,
                "title": f"Cloud MCP Section Update Test {uid}",
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
                    "version_comment": "Cloud MCP e2e section update",
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
