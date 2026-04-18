"""E2E: get_user_profile handles 'me' identifier (regression #596)."""

from __future__ import annotations

import pytest

from mcp_atlassian.jira import JiraFetcher

from .conftest import CloudInstanceInfo

pytestmark = pytest.mark.cloud_e2e


class TestJiraUserProfileMe:
    """get_user_profile_by_identifier should handle 'me' without crashing.

    Regression for https://github.com/sooperset/mcp-atlassian/issues/596
    Bug: calling get_user_profile with 'me' crashes with unhelpful error.
    """

    def test_get_user_profile_with_me_identifier(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """get_user_profile_by_identifier('me') returns current user."""
        result = jira_fetcher.get_user_profile_by_identifier("me")
        assert result is not None, "'me' identifier returned None"
        assert result.account_id or result.display_name, (
            "User profile missing account_id and display_name"
        )
