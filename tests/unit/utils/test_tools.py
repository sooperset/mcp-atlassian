"""Tests for tool utility functions."""

import os
from unittest.mock import patch

from mcp_atlassian.utils.tools import get_enabled_tools, should_include_tool


def test_get_enabled_tools_not_set():
    """Test get_enabled_tools when ENABLED_TOOLS is not set."""
    with patch.dict(os.environ, {}, clear=True):
        assert get_enabled_tools() is None


def test_get_enabled_tools_empty_string():
    """Test get_enabled_tools with empty string."""
    with patch.dict(os.environ, {"ENABLED_TOOLS": ""}, clear=True):
        assert get_enabled_tools() is None


def test_get_enabled_tools_only_whitespace():
    """Test get_enabled_tools with string containing only whitespace."""
    with patch.dict(os.environ, {"ENABLED_TOOLS": "   "}, clear=True):
        assert get_enabled_tools() is None


def test_get_enabled_tools_only_commas():
    """Test get_enabled_tools with string containing only commas."""
    with patch.dict(os.environ, {"ENABLED_TOOLS": ",,,,"}, clear=True):
        assert get_enabled_tools() is None


def test_get_enabled_tools_whitespace_and_commas():
    """Test get_enabled_tools with string containing whitespace and commas."""
    with patch.dict(os.environ, {"ENABLED_TOOLS": " , , , "}, clear=True):
        assert get_enabled_tools() is None


def test_get_enabled_tools_single_tool():
    """Test get_enabled_tools with a single tool."""
    with patch.dict(os.environ, {"ENABLED_TOOLS": "tool1"}, clear=True):
        assert get_enabled_tools() == ["tool1"]


def test_get_enabled_tools_multiple_tools():
    """Test get_enabled_tools with multiple tools."""
    with patch.dict(os.environ, {"ENABLED_TOOLS": "tool1,tool2,tool3"}, clear=True):
        assert get_enabled_tools() == ["tool1", "tool2", "tool3"]


def test_get_enabled_tools_with_whitespace():
    """Test get_enabled_tools with whitespace around tool names."""
    with patch.dict(
        os.environ, {"ENABLED_TOOLS": " tool1 , tool2 , tool3 "}, clear=True
    ):
        assert get_enabled_tools() == ["tool1", "tool2", "tool3"]


def test_should_include_tool_none_enabled():
    """Test should_include_tool when enabled_tools is None."""
    assert should_include_tool("any_tool", None) is True


def test_should_include_tool_tool_enabled():
    """Test should_include_tool when tool is in enabled list."""
    enabled_tools = ["tool1", "tool2", "tool3"]
    assert should_include_tool("tool2", enabled_tools) is True


def test_should_include_tool_tool_not_enabled():
    """Test should_include_tool when tool is not in enabled list."""
    enabled_tools = ["tool1", "tool2", "tool3"]
    assert should_include_tool("tool4", enabled_tools) is False
