"""E2E: get user details via Confluence API (regression #654)."""

from __future__ import annotations

import pytest

from mcp_atlassian.confluence import ConfluenceFetcher

pytestmark = pytest.mark.cloud_e2e


class TestConfluenceGetUserDetails:
    """Get user details by identifier or 'me'.

    Regression for https://github.com/sooperset/mcp-atlassian/issues/654
    The underlying methods existed but weren't exposed as MCP tools.
    """

    def test_get_current_user_via_me(
        self,
        confluence_fetcher: ConfluenceFetcher,
    ) -> None:
        result = confluence_fetcher.get_current_user_info()
        assert result is not None
        assert isinstance(result, dict)
        assert result.get("displayName") or result.get("accountId"), (
            "get_current_user_info returned no identifying fields"
        )
