"""confluence_get_page include param: inline comments, labels, views.

Regression for https://github.com/sooperset/mcp-atlassian/issues/1103.
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

from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.servers import main_mcp

from .conftest import CloudInstanceInfo, CloudResourceTracker

pytestmark = [pytest.mark.cloud_e2e, pytest.mark.anyio]


async def call_tool(
    client: Client, tool_name: str, arguments: dict[str, Any]
) -> CallToolResult:
    """Call a tool through the MCP client."""
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


class TestGetPageIncludeEnrichments:
    """confluence_get_page include param inlines comments, labels, views.

    Regression for https://github.com/sooperset/mcp-atlassian/issues/1103.
    """

    async def test_include_comments_labels_and_views(
        self,
        mcp_client: Client,
        confluence_fetcher: ConfluenceFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        comment_body = f"Test comment for include {uid}"
        label_name = f"e2e-include-{uid}"
        page = confluence_fetcher.create_page(
            space_key=cloud_instance.space_key,
            title=f"Include enrichments test {uid}",
            body="<p>Testing include param.</p>",
            is_markdown=False,
        )
        resource_tracker.add_confluence_page(page.id)

        confluence_fetcher.add_comment(page.id, comment_body)
        confluence_fetcher.add_page_label(page_id=page.id, name=label_name)

        result = await call_tool(
            mcp_client,
            "confluence_get_page",
            {"page_id": page.id, "include": "comments, labels, views"},
        )

        assert not result.is_error
        assert isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)

        assert data["metadata"]["id"] == page.id
        assert any(comment_body in comment["body"] for comment in data["comments"])
        assert any(label["name"] == label_name for label in data["labels"])
        assert data["views"]["page_id"] == page.id
        assert isinstance(data["views"]["total_views"], int)
