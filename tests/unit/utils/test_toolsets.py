"""Tests for toolset utility functions."""

import pytest

from mcp_atlassian.utils.toolsets import (
    ALL_TOOLSETS,
    DEFAULT_TOOLSETS,
    TOOLSET_TAG_PREFIX,
    get_enabled_toolsets,
    get_toolset_tag,
    should_include_tool_by_toolset,
)


class TestGetEnabledToolsets:
    """Tests for get_enabled_toolsets() env var parsing."""

    @pytest.mark.parametrize(
        "env_value, expected",
        [
            pytest.param(None, set(ALL_TOOLSETS.keys()), id="unset_uses_all"),
            pytest.param("", set(ALL_TOOLSETS.keys()), id="empty_uses_all"),
            pytest.param(" , , ", set(ALL_TOOLSETS.keys()), id="whitespace_uses_all"),
            pytest.param("jira_agile", {"jira_agile"}, id="single_toolset"),
            pytest.param("typo_name", set(), id="unknown_name_fail_closed"),
        ],
    )
    def test_basic_parsing(self, env_value, expected, monkeypatch):
        """Test basic env var parsing cases."""
        monkeypatch.delenv("TOOLSETS", raising=False)
        if env_value is not None:
            monkeypatch.setenv("TOOLSETS", env_value)
        result = get_enabled_toolsets()
        assert result == expected

    def test_all_keyword(self, monkeypatch):
        """Test 'all' keyword returns all 21 toolset names."""
        monkeypatch.setenv("TOOLSETS", "all")
        result = get_enabled_toolsets()
        assert result is not None
        assert result == set(ALL_TOOLSETS.keys())
        assert len(result) == 21

    def test_all_keyword_case_insensitive(self, monkeypatch):
        """Test 'ALL' keyword is case-insensitive."""
        monkeypatch.setenv("TOOLSETS", "ALL")
        result = get_enabled_toolsets()
        assert result is not None
        assert result == set(ALL_TOOLSETS.keys())
        assert len(result) == 21

    def test_default_keyword(self, monkeypatch):
        """Test 'default' keyword returns 6 default toolset names."""
        monkeypatch.setenv("TOOLSETS", "default")
        result = get_enabled_toolsets()
        assert result is not None
        assert result == DEFAULT_TOOLSETS
        # 4 Jira defaults + 2 Confluence defaults
        assert len(result) == 6

    def test_default_plus_extra(self, monkeypatch):
        """Test 'default,jira_agile' returns defaults + jira_agile."""
        monkeypatch.setenv("TOOLSETS", "default,jira_agile")
        result = get_enabled_toolsets()
        assert result is not None
        assert result == DEFAULT_TOOLSETS | {"jira_agile"}

    def test_mixed_valid_and_unknown(self, monkeypatch):
        """Test 'default,typo_name' returns defaults only (typo ignored)."""
        monkeypatch.setenv("TOOLSETS", "default, typo_name")
        result = get_enabled_toolsets()
        assert result is not None
        assert result == DEFAULT_TOOLSETS

    def test_whitespace_handling(self, monkeypatch):
        """Test whitespace around toolset names is stripped."""
        monkeypatch.setenv("TOOLSETS", " jira_issues , jira_fields ")
        result = get_enabled_toolsets()
        assert result == {"jira_issues", "jira_fields"}

    def test_default_toolsets_content(self):
        """Verify the default toolsets contain expected names."""
        expected_defaults = {
            "jira_issues",
            "jira_fields",
            "jira_comments",
            "jira_transitions",
            "confluence_pages",
            "confluence_comments",
        }
        assert DEFAULT_TOOLSETS == expected_defaults

    def test_all_toolsets_count(self):
        """Verify ALL_TOOLSETS has exactly 21 entries."""
        assert len(ALL_TOOLSETS) == 21

    def test_all_toolsets_contains_jira_and_confluence(self):
        """Verify ALL_TOOLSETS has both Jira and Confluence toolsets."""
        jira_toolsets = {k for k in ALL_TOOLSETS if k.startswith("jira_")}
        confluence_toolsets = {k for k in ALL_TOOLSETS if k.startswith("confluence_")}
        assert len(jira_toolsets) == 15
        assert len(confluence_toolsets) == 6


class TestShouldIncludeToolByToolset:
    """Tests for should_include_tool_by_toolset() tag-based filtering."""

    @pytest.mark.parametrize(
        "tool_tags, enabled_toolsets, expected",
        [
            pytest.param(
                {"jira", "read", "toolset:jira_issues"},
                {"jira_issues"},
                True,
                id="matching_toolset",
            ),
            pytest.param(
                {"jira", "read", "toolset:jira_agile"},
                {"jira_issues"},
                False,
                id="non_matching_toolset",
            ),
            pytest.param(
                {"jira", "read", "toolset:jira_issues"},
                None,
                True,
                id="none_means_all_pass",
            ),
            pytest.param(
                {"jira", "read"},
                {"jira_issues"},
                True,
                id="no_toolset_tag_passes",
            ),
            pytest.param(
                {"jira", "read", "toolset:jira_issues"},
                set(),
                False,
                id="empty_set_blocks_all",
            ),
        ],
    )
    def test_filtering(self, tool_tags, enabled_toolsets, expected):
        """Test tool filtering by toolset tags."""
        result = should_include_tool_by_toolset(tool_tags, enabled_toolsets)
        assert result is expected

    def test_multiple_enabled_toolsets(self):
        """Test tool matches when multiple toolsets are enabled."""
        tool_tags = {"jira", "read", "toolset:jira_agile"}
        enabled = {"jira_issues", "jira_agile", "jira_fields"}
        assert should_include_tool_by_toolset(tool_tags, enabled) is True

    def test_tool_with_non_matching_multiple_enabled(self):
        """Test tool excluded when its toolset is not in enabled set."""
        tool_tags = {"jira", "read", "toolset:jira_worklog"}
        enabled = {"jira_issues", "jira_agile", "jira_fields"}
        assert should_include_tool_by_toolset(tool_tags, enabled) is False


class TestGetToolsetTag:
    """Tests for get_toolset_tag() helper."""

    def test_extracts_toolset_tag(self):
        """Test extraction of toolset tag from tag set."""
        tags = {"jira", "read", "toolset:jira_issues"}
        assert get_toolset_tag(tags) == "jira_issues"

    def test_no_toolset_tag(self):
        """Test returns None when no toolset tag exists."""
        tags = {"jira", "read"}
        assert get_toolset_tag(tags) is None

    def test_empty_tags(self):
        """Test returns None for empty tag set."""
        assert get_toolset_tag(set()) is None


class TestToolsetTagCompleteness:
    """Verify every registered tool has exactly one valid toolset tag."""

    @pytest.fixture()
    def jira_tools(self):
        """Get all registered Jira tools."""
        import asyncio

        from mcp_atlassian.servers.jira import jira_mcp

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(jira_mcp.get_tools())
        finally:
            loop.close()

    @pytest.fixture()
    def confluence_tools(self):
        """Get all registered Confluence tools."""
        import asyncio

        from mcp_atlassian.servers.confluence import confluence_mcp

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(confluence_mcp.get_tools())
        finally:
            loop.close()

    def test_jira_tools_have_toolset_tag(self, jira_tools):
        """Every Jira tool must have exactly one toolset:* tag."""
        for name, tool in jira_tools.items():
            tags = tool.tags if hasattr(tool, "tags") else set()
            toolset_tags = [t for t in tags if t.startswith(TOOLSET_TAG_PREFIX)]
            assert len(toolset_tags) == 1, (
                f"Jira tool '{name}' has {len(toolset_tags)} toolset tags "
                f"(expected 1): {toolset_tags}"
            )

    def test_confluence_tools_have_toolset_tag(self, confluence_tools):
        """Every Confluence tool must have exactly one toolset:* tag."""
        for name, tool in confluence_tools.items():
            tags = tool.tags if hasattr(tool, "tags") else set()
            toolset_tags = [t for t in tags if t.startswith(TOOLSET_TAG_PREFIX)]
            assert len(toolset_tags) == 1, (
                f"Confluence tool '{name}' has {len(toolset_tags)} toolset "
                f"tags (expected 1): {toolset_tags}"
            )

    def test_jira_toolset_tags_are_valid(self, jira_tools):
        """Every Jira tool's toolset tag must reference a valid toolset."""
        for name, tool in jira_tools.items():
            tags = tool.tags if hasattr(tool, "tags") else set()
            toolset_name = get_toolset_tag(tags)
            if toolset_name is not None:
                assert toolset_name in ALL_TOOLSETS, (
                    f"Jira tool '{name}' has unknown toolset "
                    f"'{toolset_name}' (not in ALL_TOOLSETS)"
                )

    def test_confluence_toolset_tags_are_valid(self, confluence_tools):
        """Every Confluence tool's toolset tag must reference a valid toolset."""
        for name, tool in confluence_tools.items():
            tags = tool.tags if hasattr(tool, "tags") else set()
            toolset_name = get_toolset_tag(tags)
            if toolset_name is not None:
                assert toolset_name in ALL_TOOLSETS, (
                    f"Confluence tool '{name}' has unknown toolset "
                    f"'{toolset_name}' (not in ALL_TOOLSETS)"
                )

    def test_jira_tool_count(self, jira_tools):
        """Verify expected number of Jira tools."""
        assert len(jira_tools) == 48, f"Expected 48 Jira tools, got {len(jira_tools)}"

    def test_confluence_tool_count(self, confluence_tools):
        """Verify expected number of Confluence tools."""
        assert len(confluence_tools) == 21, (
            f"Expected 21 Confluence tools, got {len(confluence_tools)}"
        )
