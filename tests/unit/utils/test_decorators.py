from unittest.mock import MagicMock

import pytest
from fastmcp.exceptions import ToolError
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.utils.decorators import (
    check_write_access,
    handle_auth_errors,
    handle_tool_errors,
)


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


# --- handle_auth_errors tests ---


def _make_http_error(status_code: int) -> HTTPError:
    """Create an HTTPError with a mocked response."""
    response = MagicMock()
    response.status_code = status_code
    err = HTTPError(response=response)
    return err


class _FakeService:
    """Dummy class to test the self-bound decorator."""

    @handle_auth_errors("Test API")
    def do_work(self, value: str) -> str:
        return f"ok:{value}"

    @handle_auth_errors("Test API")
    def raise_http_error(self, status_code: int) -> None:
        raise _make_http_error(status_code)

    @handle_auth_errors("Test API")
    def raise_value_error(self) -> None:
        raise ValueError("bad input")


def test_handle_auth_errors_returns_value():
    svc = _FakeService()
    assert svc.do_work("hello") == "ok:hello"


@pytest.mark.parametrize("status_code", [401, 403])
def test_handle_auth_errors_catches_auth_errors(
    status_code: int,
) -> None:
    svc = _FakeService()
    with pytest.raises(MCPAtlassianAuthenticationError) as exc:
        svc.raise_http_error(status_code)
    assert "Authentication failed" in str(exc.value)
    assert str(status_code) in str(exc.value)


def test_handle_auth_errors_passes_through_404():
    svc = _FakeService()
    with pytest.raises(HTTPError) as exc:
        svc.raise_http_error(404)
    assert exc.value.response.status_code == 404


def test_handle_auth_errors_passes_through_non_http_error():
    svc = _FakeService()
    with pytest.raises(ValueError, match="bad input"):
        svc.raise_value_error()


def test_handle_auth_errors_passes_through_no_response():
    """HTTPError with response=None should re-raise."""

    class Svc:
        @handle_auth_errors("Test API")
        def fail(self) -> None:
            raise HTTPError(response=None)

    with pytest.raises(HTTPError):
        Svc().fail()
