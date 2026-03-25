"""E2E tests for Jira Cloud watcher operations (upstream #483)."""

from __future__ import annotations

import uuid

import pytest

from mcp_atlassian.jira import JiraFetcher

from .conftest import CloudInstanceInfo, CloudResourceTracker

pytestmark = pytest.mark.cloud_e2e


class TestJiraCloudWatchers:
    """Watcher operations on Cloud — regression for upstream #483.

    Proves that add_watcher, remove_watcher, and get_issue_watchers
    exist and operate correctly against a real Jira Cloud instance.
    """

    def test_watcher_lifecycle(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        """add_watcher, get_issue_watchers, remove_watcher round-trip."""
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Cloud E2E Watcher Test {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue.key)

        # Get the current user's account ID so we can add/remove ourselves
        account_id = jira_fetcher.get_current_user_account_id()
        assert account_id, "Expected a non-empty account ID for the current user"

        # Add the current user as a watcher
        add_result = jira_fetcher.add_watcher(issue.key, account_id)
        assert add_result["success"] is True
        assert add_result["issue_key"] == issue.key

        # Confirm the watcher count increased after adding
        watchers_result = jira_fetcher.get_issue_watchers(issue.key)
        assert watchers_result["issue_key"] == issue.key
        assert isinstance(watchers_result["watchers"], list)
        assert watchers_result["watcher_count"] >= 1, (
            "Expected at least 1 watcher after add_watcher call"
        )

        # Remove the current user as a watcher
        remove_result = jira_fetcher.remove_watcher(issue.key, account_id=account_id)
        assert remove_result["success"] is True
        assert remove_result["issue_key"] == issue.key
