"""get_issue include param: inline enrichments in one call.

Regression for https://github.com/sooperset/mcp-atlassian/issues/857
and https://github.com/sooperset/mcp-atlassian/issues/1101
"""

from __future__ import annotations

import uuid

import pytest

from mcp_atlassian.jira import JiraFetcher

from .conftest import CloudInstanceInfo, CloudResourceTracker

pytestmark = pytest.mark.cloud_e2e


class TestGetIssueIncludeEnrichments:
    """get_issue include param inlines enrichments in one call.

    Regression for github.com/sooperset/mcp-atlassian/issues/857
    and github.com/sooperset/mcp-atlassian/issues/1101
    """

    def test_get_remote_issue_links(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Include test {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue.key)

        jira_fetcher.create_remote_issue_link(
            issue.key,
            {
                "object": {
                    "url": f"https://example.com/{uid}",
                    "title": "Test Link",
                }
            },
        )

        links = jira_fetcher.get_remote_issue_links(issue.key)
        assert isinstance(links, list)
        assert len(links) >= 1

    def test_get_transitions(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Transitions test {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue.key)

        transitions = jira_fetcher.get_transitions(issue.key)
        assert isinstance(transitions, list)
        assert len(transitions) > 0

    def test_get_watchers(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Watchers test {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue.key)

        watchers = jira_fetcher.get_issue_watchers(issue.key)
        assert isinstance(watchers, dict)
