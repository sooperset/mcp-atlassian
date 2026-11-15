"""Confluence tools must surface authentication errors, not swallow them."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.servers import confluence as confluence_server

# (tool, call arguments, fetcher method the tool calls)
AUTH_CASES = [
    ("delete_page", {"page_id": "1"}, "delete_page"),
    ("add_comment", {"page_id": "1", "body": "hi"}, "add_comment"),
    ("reply_to_comment", {"comment_id": "1", "body": "hi"}, "reply_to_comment"),
    (
        "add_inline_comment",
        {"page_id": "1", "body": "hi", "text_selection": "text"},
        "add_inline_comment",
    ),
    ("get_inline_comments", {"page_id": "1"}, "get_inline_comments"),
]


def _patched_fetcher(fetcher: MagicMock):
    return patch.object(
        confluence_server, "get_confluence_fetcher", AsyncMock(return_value=fetcher)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool", "kwargs", "method"), AUTH_CASES)
async def test_auth_error_is_not_swallowed(tool, kwargs, method):
    """An authentication failure surfaces as a tool error, not success=false JSON."""
    fetcher = MagicMock()
    getattr(fetcher, method).side_effect = MCPAtlassianAuthenticationError(
        "token expired"
    )

    with _patched_fetcher(fetcher), pytest.raises(ToolError, match="token expired"):
        await getattr(confluence_server, tool)(ctx=MagicMock(), **kwargs)


@pytest.mark.asyncio
async def test_other_errors_still_return_soft_failure_json():
    """Non-authentication errors keep the existing success=false response."""
    fetcher = MagicMock()
    fetcher.reply_to_comment.side_effect = RuntimeError("boom")

    with _patched_fetcher(fetcher):
        result = await confluence_server.reply_to_comment(
            ctx=MagicMock(), comment_id="1", body="hi"
        )

    response = json.loads(result)
    assert response["success"] is False
    assert response["error"] == "boom"
