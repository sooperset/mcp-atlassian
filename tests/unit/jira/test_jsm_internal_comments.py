"""Tests for JSM internal comments (upstream #847)."""

from __future__ import annotations

import inspect

from mcp_atlassian.jira import JiraFetcher


class TestJsmInternalComments:
    """JSM internal (agent-only) comments via public=False.

    Regression for https://github.com/sooperset/mcp-atlassian/issues/847
    Feature: same as #716 — add_comment(public=False) via ServiceDesk API.
    Already implemented. See also PR #1111 (closes #716, same feature).
    """

    def test_add_comment_has_public_param(self, jira_fetcher: JiraFetcher) -> None:
        """add_comment accepts a public parameter for JSM."""
        sig = inspect.signature(jira_fetcher.add_comment)
        assert "public" in sig.parameters, (
            "add_comment has no public param — JSM internal comments not supported"
        )

    def test_servicedesk_comment_method_exists(self, jira_fetcher: JiraFetcher) -> None:
        """_add_servicedesk_comment method exists for routing internal comments."""
        assert hasattr(jira_fetcher, "_add_servicedesk_comment"), (
            "_add_servicedesk_comment not found — ServiceDesk routing not implemented"
        )

    def test_public_false_routes_to_servicedesk(
        self, jira_fetcher: JiraFetcher
    ) -> None:
        """add_comment(public=False) routes through ServiceDesk API."""
        calls: list[tuple] = []
        original = jira_fetcher._add_servicedesk_comment

        def capture(*args: object, **kwargs: object) -> dict:
            calls.append(args)
            return {"id": "123", "body": "test", "public": False}

        jira_fetcher._add_servicedesk_comment = capture  # type: ignore[method-assign]
        try:
            jira_fetcher.add_comment("JSMTEST-1", "Internal note", public=False)
        finally:
            jira_fetcher._add_servicedesk_comment = original  # type: ignore[method-assign]

        assert len(calls) == 1, "add_comment(public=False) did not call ServiceDesk API"
        assert calls[0][1] == "Internal note"
        assert calls[0][2] is False
