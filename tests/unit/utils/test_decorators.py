from unittest.mock import MagicMock

import pytest
from fastmcp.exceptions import ToolError

from mcp_atlassian.utils.decorators import check_write_access, handle_tool_errors


class DummyContext:
    def __init__(self, read_only):
        self.request_context = MagicMock()
        self.request_context.lifespan_context = {
            "app_lifespan_context": MagicMock(read_only=read_only)
        }


@pytest.mark.asyncio
async def test_check_write_access_blocks_in_read_only():
    @check_write_access
    async def dummy_tool(ctx, x):
        return x * 2

    ctx = DummyContext(read_only=True)
    with pytest.raises(ToolError) as exc:
        await dummy_tool(ctx, 3)
    assert "read-only mode" in str(exc.value)


@pytest.mark.asyncio
async def test_check_write_access_allows_in_writable():
    @check_write_access
    async def dummy_tool(ctx, x):
        return x * 2

    ctx = DummyContext(read_only=False)
    result = await dummy_tool(ctx, 4)
    assert result == 8


@pytest.mark.asyncio
async def test_handle_tool_errors_wraps_exception_as_tool_error():
    @handle_tool_errors
    async def failing_tool():
        raise ValueError("something went wrong")

    with pytest.raises(ToolError) as exc:
        await failing_tool()
    assert "something went wrong" in str(exc.value)


@pytest.mark.asyncio
async def test_handle_tool_errors_passes_through_tool_error():
    @handle_tool_errors
    async def tool_with_tool_error():
        raise ToolError("explicit tool error")

    with pytest.raises(ToolError) as exc:
        await tool_with_tool_error()
    assert "explicit tool error" in str(exc.value)


@pytest.mark.asyncio
async def test_handle_tool_errors_preserves_return_value():
    @handle_tool_errors
    async def good_tool():
        return "success"

    result = await good_tool()
    assert result == "success"
