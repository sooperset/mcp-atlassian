"""Tests for the FastMCP registration helpers."""

import logging
from typing import Any

import pytest
from fastmcp import Client

from mcp_atlassian.servers.error_handling import ErrorPreservingFastMCP
from mcp_atlassian.servers.main import AtlassianMCP
from mcp_atlassian.utils.decorators import deprecated_tool


@pytest.mark.anyio
@pytest.mark.parametrize("decorator_order", ["inner", "outer"])
async def test_deprecated_tool_is_preserved_in_registered_mcp_tool(
    decorator_order: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Expose deprecation metadata and warnings through either decorator order."""
    server = ErrorPreservingFastMCP(f"deprecated-tool-{decorator_order}")
    tool_name = f"legacy_{decorator_order}"
    replacement = f"new_{decorator_order}"

    if decorator_order == "inner":

        @server.tool(
            tags={"jira", "read", "toolset:jira_fields"},
            annotations={"title": "Legacy tool"},
        )
        @deprecated_tool(replacement)
        async def legacy_inner() -> str:
            return "inner result"

    else:

        @deprecated_tool(replacement)
        @server.tool(
            tags={"confluence", "read", "toolset:confluence_pages"},
            annotations={"title": "Legacy tool"},
        )
        async def legacy_outer() -> str:
            return "outer result"

    registered = await server.get_tool(tool_name)
    assert registered is not None
    assert registered.description == f"DEPRECATED: use {replacement}."
    assert registered.tags == {
        "read",
        "jira" if decorator_order == "inner" else "confluence",
        "toolset:legacy",
    }

    listed = {tool.name: tool for tool in await server.list_tools()}
    assert listed[tool_name].description == registered.description
    assert listed[tool_name].tags == registered.tags

    with caplog.at_level(logging.WARNING, logger="mcp_atlassian.utils.decorators"):
        async with Client(server) as client:
            first_result = await client.call_tool_mcp(tool_name, {})
            second_result = await client.call_tool_mcp(tool_name, {})

    assert first_result.content[0].text == f"{decorator_order} result"
    assert second_result.content[0].text == f"{decorator_order} result"
    warnings = [
        record
        for record in caplog.records
        if "is deprecated; use" in record.getMessage()
    ]
    assert len(warnings) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("server_class", [ErrorPreservingFastMCP, AtlassianMCP])
async def test_tool_error_details_reach_client_when_masking(
    server_class: type[ErrorPreservingFastMCP[Any]],
) -> None:
    """Tool failures keep their message on the wire even with masking enabled."""
    server = server_class("error-details", mask_error_details=True)

    @server.tool(name="failing_tool", tags={"read"})
    async def failing_tool() -> str:
        raise ValueError("Jira rejected field 'customfield_10001'")

    async with Client(server) as client:
        result = await client.call_tool_mcp("failing_tool", {})

    assert result.is_error
    assert result.content[0].text == (
        "Error calling tool 'failing_tool': Jira rejected field 'customfield_10001'"
    )
