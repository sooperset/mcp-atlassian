"""E2E tests for image retrieval tools against Cloud instances.

Tests jira_get_issue_images and confluence_get_page_images
via MCP tool calls with real Jira Cloud/Confluence Cloud instances.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import patch

import pytest
from fastmcp import Client
from fastmcp.client import FastMCPTransport
from mcp.types import CallToolResult, ImageContent, TextContent

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


class TestJiraGetIssueImages:
    """Tests for jira_get_issue_images tool against Cloud."""

    async def test_jira_get_issue_images(
        self,
        mcp_client: Client,
        cloud_image_issue: str,
    ) -> None:
        """Image issue returns ImageContent with valid PNG."""
        result = await call_tool(
            mcp_client,
            "jira_get_issue_images",
            {"issue_key": cloud_image_issue},
        )
        assert not result.is_error
        assert len(result.content) >= 2

        # First: JSON summary
        assert isinstance(result.content[0], TextContent)
        summary = json.loads(result.content[0].text)
        assert summary["success"] is True
        assert summary["downloaded"] >= 1

        # Second: image data
        assert isinstance(result.content[1], ImageContent)
        assert result.content[1].mimeType.startswith("image/")
        assert len(result.content[1].data) > 0

    async def test_jira_get_issue_images_no_images(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Issue without images returns informational message."""
        result = await call_tool(
            mcp_client,
            "jira_get_issue_images",
            {"issue_key": cloud_instance.test_issue_key},
        )
        assert not result.is_error
        assert len(result.content) >= 1
        assert isinstance(result.content[0], TextContent)
        text = result.content[0].text
        if text.startswith("{"):
            data = json.loads(text)
            assert data["downloaded"] == 0
        else:
            assert "no image" in text.lower() or "No image" in text


class TestConfluenceGetPageImages:
    """Tests for confluence_get_page_images tool against Cloud."""

    async def test_confluence_get_page_images(
        self,
        mcp_client: Client,
        cloud_image_page: str,
    ) -> None:
        """Image page returns ImageContent with valid PNG."""
        result = await call_tool(
            mcp_client,
            "confluence_get_page_images",
            {"content_id": cloud_image_page},
        )
        assert not result.is_error
        assert len(result.content) >= 2

        # First: JSON summary
        assert isinstance(result.content[0], TextContent)
        summary = json.loads(result.content[0].text)
        assert summary["success"] is True
        assert summary["downloaded"] >= 1

        # Second: image data
        assert isinstance(result.content[1], ImageContent)
        assert result.content[1].mimeType.startswith("image/")
        assert len(result.content[1].data) > 0

    async def test_confluence_get_page_images_no_images(
        self,
        mcp_client: Client,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Page without images returns informational message."""
        result = await call_tool(
            mcp_client,
            "confluence_get_page_images",
            {"content_id": cloud_instance.test_page_id},
        )
        assert not result.is_error
        assert len(result.content) >= 1
        assert isinstance(result.content[0], TextContent)
        text = result.content[0].text
        if text.startswith("{"):
            data = json.loads(text)
            assert data["downloaded"] == 0
        else:
            assert "no image" in text.lower() or "No image" in text


class TestAcImageConversion:
    """Verify ac:image macro is converted to markdown in page body."""

    async def test_ac_image_converted_to_markdown(
        self,
        mcp_client: Client,
        cloud_image_page: str,
    ) -> None:
        """Page with ac:image macro shows markdown image reference."""
        result = await call_tool(
            mcp_client,
            "confluence_get_page",
            {"page_id": cloud_image_page},
        )
        assert not result.is_error
        assert isinstance(result.content[0], TextContent)
        page_text = result.content[0].text
        assert "![test.png]" in page_text or "![](http" in page_text, (
            f"Expected markdown image in page body, got: {page_text[:500]}"
        )
