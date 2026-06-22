"""Tests for privacy.tool_map."""

from __future__ import annotations

from mcp_atlassian.privacy.tool_map import (
    JIRA_ISSUE,
    TOOL_RESOURCE_TYPES,
    resource_type_for_tool,
)


class TestResourceTypeForTool:
    def test_known_tool_returns_resource_type(self) -> None:
        assert resource_type_for_tool(tool_name="jira_get_issue") == JIRA_ISSUE

    def test_unknown_tool_returns_none(self) -> None:
        assert resource_type_for_tool(tool_name="totally_unknown") is None

    def test_table_keys_are_distinct(self) -> None:
        assert len(TOOL_RESOURCE_TYPES) == len(set(TOOL_RESOURCE_TYPES))
