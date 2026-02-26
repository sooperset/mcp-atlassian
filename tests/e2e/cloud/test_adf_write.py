"""E2E tests for ADF write support (Markdown → ADF) on Jira Cloud.

Tests that Markdown formatting in issue descriptions and comments
is correctly converted to ADF on Cloud and survives a round-trip read.
"""

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
    }


@pytest.fixture
async def mcp_client(cloud_env: dict[str, str]) -> Any:
    """MCP client connected to the server configured for Cloud."""
    with patch.dict(os.environ, cloud_env, clear=False):
        transport = FastMCPTransport(main_mcp)
        client = Client(transport=transport)
        async with client as connected_client:
            yield connected_client


async def _create_issue_with_description(
    mcp_client: Client,
    project_key: str,
    description: str,
) -> str:
    """Create an issue and return the issue key."""
    uid = uuid.uuid4().hex[:8]
    result = await call_tool(
        mcp_client,
        "jira_create_issue",
        {
            "project_key": project_key,
            "summary": f"ADF Test {uid}",
            "description": description,
            "issue_type": "Task",
        },
    )
    assert not result.is_error
    data = json.loads(result.content[0].text)
    return data["issue"]["key"]


async def _read_issue_description(mcp_client: Client, issue_key: str) -> str:
    """Read an issue and return the description text."""
    result = await call_tool(
        mcp_client,
        "jira_get_issue",
        {"issue_key": issue_key},
    )
    assert not result.is_error
    data = json.loads(result.content[0].text)
    return data.get("description", "")


async def _delete_issue(mcp_client: Client, issue_key: str) -> None:
    """Delete an issue (best-effort cleanup)."""
    await call_tool(
        mcp_client,
        "jira_delete_issue",
        {"issue_key": issue_key},
    )


class TestADFCreateIssue:
    """Test Markdown → ADF conversion on issue creation."""

    async def test_create_issue_bold_italic(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Bold and italic markdown survives ADF round-trip."""
        key = await _create_issue_with_description(
            mcp_client,
            cloud_instance.project_key,
            "**bold** and *italic*",
        )
        try:
            desc = await _read_issue_description(mcp_client, key)
            assert "bold" in desc
            assert "italic" in desc
        finally:
            await _delete_issue(mcp_client, key)

    async def test_create_issue_lists(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Bullet and numbered lists survive ADF round-trip."""
        key = await _create_issue_with_description(
            mcp_client,
            cloud_instance.project_key,
            "- bullet a\n- bullet b\n1. num c\n2. num d",
        )
        try:
            desc = await _read_issue_description(mcp_client, key)
            assert "bullet a" in desc
            assert "num c" in desc
        finally:
            await _delete_issue(mcp_client, key)

    async def test_create_issue_code_block(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Code block markdown survives ADF round-trip."""
        key = await _create_issue_with_description(
            mcp_client,
            cloud_instance.project_key,
            "```python\nprint('hello')\n```",
        )
        try:
            desc = await _read_issue_description(mcp_client, key)
            assert "print" in desc
        finally:
            await _delete_issue(mcp_client, key)

    async def test_create_issue_heading_link(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Heading and link markdown survive ADF round-trip."""
        key = await _create_issue_with_description(
            mcp_client,
            cloud_instance.project_key,
            "# My Title\n[example](https://example.com)",
        )
        try:
            desc = await _read_issue_description(mcp_client, key)
            assert "My Title" in desc
            assert "example" in desc
        finally:
            await _delete_issue(mcp_client, key)

    async def test_create_issue_blockquote(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Blockquote markdown survives ADF round-trip."""
        key = await _create_issue_with_description(
            mcp_client,
            cloud_instance.project_key,
            "> quoted text here",
        )
        try:
            desc = await _read_issue_description(mcp_client, key)
            assert "quoted text here" in desc
        finally:
            await _delete_issue(mcp_client, key)

    async def test_create_issue_mixed(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Mixed markdown elements don't cause errors."""
        mixed = (
            "# Heading\n\n"
            "**bold** and *italic*\n\n"
            "- list item\n\n"
            "> quote\n\n"
            "```\ncode\n```\n\n"
            "[link](https://example.com)"
        )
        key = await _create_issue_with_description(
            mcp_client,
            cloud_instance.project_key,
            mixed,
        )
        try:
            desc = await _read_issue_description(mcp_client, key)
            assert "Heading" in desc
            assert "bold" in desc
        finally:
            await _delete_issue(mcp_client, key)


class TestADFUpdateAndComment:
    """Test ADF conversion on issue update and comment."""

    async def test_update_issue_description(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Updating description with markdown works via ADF."""
        # Create a plain issue first
        key = await _create_issue_with_description(
            mcp_client,
            cloud_instance.project_key,
            "original text",
        )
        try:
            # Update with markdown
            update_result = await call_tool(
                mcp_client,
                "jira_update_issue",
                {
                    "issue_key": key,
                    "fields": json.dumps(
                        {"description": "**updated bold** description"}
                    ),
                },
            )
            assert not update_result.is_error

            desc = await _read_issue_description(mcp_client, key)
            assert "updated bold" in desc
        finally:
            await _delete_issue(mcp_client, key)

    async def test_add_comment_markdown(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Adding a markdown comment works via ADF."""
        key = await _create_issue_with_description(
            mcp_client,
            cloud_instance.project_key,
            "issue for comment test",
        )
        try:
            comment_result = await call_tool(
                mcp_client,
                "jira_add_comment",
                {
                    "issue_key": key,
                    "body": "**bold comment** with `code`",
                },
            )
            assert not comment_result.is_error
            assert isinstance(comment_result.content[0], TextContent)
            comment_data = json.loads(comment_result.content[0].text)
            # Verify comment was created (has an id or body)
            assert comment_data.get("id") or comment_data.get("body")
        finally:
            await _delete_issue(mcp_client, key)
