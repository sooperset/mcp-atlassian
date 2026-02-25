"""E2E tests for DC user email→username resolution (PR #999).

Tests _determine_user_api_params and _resolve_server_dc_user_params
via Fetcher direct calls, plus MCP tool assignment by email.
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
from mcp.types import CallToolResult

from mcp_atlassian.jira import JiraFetcher
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
    }


@pytest.fixture
async def mcp_client(dc_env: dict[str, str]) -> Any:
    """MCP client connected to the server configured for DC."""
    with patch.dict(os.environ, dc_env, clear=False):
        transport = FastMCPTransport(main_mcp)
        client = Client(transport=transport)
        async with client as connected_client:
            yield connected_client


class TestUserResolution:
    """Fetcher-level tests for DC user identifier resolution."""

    def test_resolve_email_to_username(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        """Admin email resolves to {"username": "admin"} via search."""
        if not dc_instance.admin_email:
            pytest.skip("Admin email not available")

        params = jira_fetcher._determine_user_api_params(dc_instance.admin_email)
        assert "username" in params or "key" in params
        # The resolved username should be the admin username
        resolved = params.get("username") or params.get("key", "")
        assert resolved == dc_instance.admin_username

    def test_resolve_username_directly(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        """Plain username goes straight to {"username": "admin"}."""
        params = jira_fetcher._determine_user_api_params(dc_instance.admin_username)
        assert params == {"username": dc_instance.admin_username}

    def test_get_user_profile_by_email(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        """Email-based profile lookup returns a valid user."""
        if not dc_instance.admin_email:
            pytest.skip("Admin email not available")

        user = jira_fetcher.get_user_profile_by_identifier(dc_instance.admin_email)
        assert user.display_name

    def test_invalid_email_fallback(
        self,
        jira_fetcher: JiraFetcher,
    ) -> None:
        """Non-existent email returns None from resolve."""
        result = jira_fetcher._resolve_server_dc_user_params(
            "nonexistent_e2e_user@invalid-domain-e2e-test.com"
        )
        assert result is None

    def test_unresolved_email_falls_back_to_username(
        self,
        jira_fetcher: JiraFetcher,
    ) -> None:
        """Unresolvable email falls back to {"username": email}."""
        fake_email = "nonexistent_e2e_user@invalid-domain-e2e-test.com"
        params = jira_fetcher._determine_user_api_params(fake_email)
        assert params == {"username": fake_email}


class TestAssignByEmail:
    """MCP tool-level test: assign issue by email on DC."""

    async def test_assign_by_email_via_mcp(
        self,
        mcp_client: Client,
        dc_instance: DCInstanceInfo,
    ) -> None:
        """Assigning by email resolves to correct user on DC."""
        if not dc_instance.admin_email:
            pytest.skip("Admin email not available")

        # Create a test issue
        uid = uuid.uuid4().hex[:8]
        create_result = await call_tool(
            mcp_client,
            "jira_create_issue",
            {
                "project_key": dc_instance.project_key,
                "summary": f"User Lookup Test {uid}",
                "description": "E2E test for email-based assignment.",
                "issue_type": "Task",
            },
        )
        assert not create_result.is_error
        data = json.loads(create_result.content[0].text)
        issue_key = data["issue"]["key"]

        try:
            # Assign by email
            update_result = await call_tool(
                mcp_client,
                "jira_update_issue",
                {
                    "issue_key": issue_key,
                    "fields": json.dumps({"assignee": dc_instance.admin_email}),
                },
            )
            assert not update_result.is_error

            # Verify assignment
            get_result = await call_tool(
                mcp_client,
                "jira_get_issue",
                {"issue_key": issue_key},
            )
            assert not get_result.is_error
            issue_data = json.loads(get_result.content[0].text)
            assignee = issue_data.get("assignee", "")
            assert assignee, "Issue should have an assignee after update"
        finally:
            await call_tool(
                mcp_client,
                "jira_delete_issue",
                {"issue_key": issue_key},
            )
