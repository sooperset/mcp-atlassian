"""get_issue include param: inline enrichments in one call.

Regression for https://github.com/sooperset/mcp-atlassian/issues/857
and https://github.com/sooperset/mcp-atlassian/issues/1101
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

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.servers import main_mcp

from .conftest import CloudInstanceInfo, CloudResourceTracker

pytestmark = pytest.mark.cloud_e2e


async def call_tool(
    client: Client, tool_name: str, arguments: dict[str, Any]
) -> CallToolResult:
    """Call an MCP tool."""
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


class TestGetIssueIncludeEnrichments:
    """get_issue include param inlines enrichments in one call.

    Regression for github.com/sooperset/mcp-atlassian/issues/857
    and github.com/sooperset/mcp-atlassian/issues/1101
    """

    def test_get_remote_issue_links(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Include test {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue.key)

        jira_fetcher.create_remote_issue_link(
            issue.key,
            {
                "object": {
                    "url": f"https://example.com/{uid}",
                    "title": "Test Link",
                }
            },
        )

        links = jira_fetcher.get_remote_issue_links(issue.key)
        assert isinstance(links, list)
        assert len(links) >= 1

    def test_get_transitions(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Transitions test {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue.key)

        transitions = jira_fetcher.get_transitions(issue.key)
        assert isinstance(transitions, list)
        assert len(transitions) > 0

    def test_get_watchers(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Watchers test {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue.key)

        watchers = jira_fetcher.get_issue_watchers(issue.key)
        assert isinstance(watchers, dict)

    @pytest.mark.anyio
    async def test_get_issue_include_all_tool(
        self,
        mcp_client: Client,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Include all tool test {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue.key)
        jira_fetcher.add_comment(issue.key, f"Include comment {uid}")
        jira_fetcher.create_remote_issue_link(
            issue.key,
            {
                "object": {
                    "url": f"https://example.com/{uid}",
                    "title": "Include Tool Test Link",
                }
            },
        )

        result = await call_tool(
            mcp_client,
            "jira_get_issue",
            {
                "issue_key": issue.key,
                "fields": "summary,status",
                "include": "all",
            },
        )

        assert not result.is_error
        assert result.content and isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        assert data["key"] == issue.key
        assert any(
            comment["body"] == f"Include comment {uid}" for comment in data["comments"]
        )
        assert any(
            link.get("object", {}).get("url") == f"https://example.com/{uid}"
            for link in data["remote_links"]
        )
        assert isinstance(data["transitions"], list)
        assert data["transitions"]
        assert isinstance(data["watchers"], dict)
        assert isinstance(data["worklogs"], list)
