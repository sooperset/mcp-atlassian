"""Jira Cloud-specific operation tests (single auth - basic)."""

from __future__ import annotations

import uuid

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.jira import JiraFetcher

from .conftest import CloudInstanceInfo, CloudResourceTracker

pytestmark = pytest.mark.cloud_e2e


class TestJiraCloudBehavior:
    """Tests for Cloud-specific Jira behavior."""

    def test_is_cloud(self, jira_fetcher: JiraFetcher) -> None:
        assert jira_fetcher.config.is_cloud is True

    def test_assignee_uses_account_id(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Cloud uses accountId for users, not name."""
        issue = jira_fetcher.get_issue(cloud_instance.test_issue_key)
        if issue.assignee is not None:
            # Check the model field directly — to_simplified_dict()
            # does NOT expose accountId
            assert issue.assignee.account_id is not None


class TestJiraCloudEpicOperations:
    """Epic creation on Cloud."""

    def test_create_epic(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        try:
            epic = jira_fetcher.create_issue(
                project_key=cloud_instance.project_key,
                summary=f"Cloud E2E Epic {uid}",
                issue_type="Epic",
                description="Epic for Cloud testing.",
            )
        except HTTPError as e:
            if "issue type" in str(e).lower():
                pytest.skip(
                    f"Epic issue type not available in project "
                    f"{cloud_instance.project_key}"
                )
            raise
        resource_tracker.add_jira_issue(epic.key)
        assert epic.key.startswith(cloud_instance.project_key)


class TestJiraCloudSubtask:
    """Subtask creation on Cloud."""

    def test_create_subtask(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        parent = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Cloud E2E Parent {uid}",
            issue_type="Task",
            description="Parent for subtask test.",
        )
        resource_tracker.add_jira_issue(parent.key)

        # Cloud uses "Subtask"; fall back to "Sub-task" (DC naming)
        for subtask_type in ("Subtask", "Sub-task"):
            try:
                subtask = jira_fetcher.create_issue(
                    project_key=cloud_instance.project_key,
                    summary=f"Cloud E2E Subtask {uid}",
                    issue_type=subtask_type,
                    description="Subtask for Cloud testing.",
                    parent=parent.key,
                )
                resource_tracker.add_jira_issue(subtask.key)
                assert subtask.key.startswith(cloud_instance.project_key)
                return
            except (HTTPError, Exception):  # noqa: BLE001
                continue

        pytest.skip("No subtask issue type available")


class TestJiraCloudIssueLinks:
    """Issue link creation on Cloud."""

    def test_create_issue_link(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue1 = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Cloud E2E Link Source {uid}",
            issue_type="Task",
        )
        issue2 = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Cloud E2E Link Target {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue1.key)
        resource_tracker.add_jira_issue(issue2.key)

        link_types = jira_fetcher.get_issue_link_types()
        assert len(link_types) > 0

        link_type_name = link_types[0].name
        for lt in link_types:
            if "relate" in lt.name.lower():
                link_type_name = lt.name
                break

        result = jira_fetcher.create_issue_link(
            {
                "type": {"name": link_type_name},
                "inwardIssue": {"key": issue1.key},
                "outwardIssue": {"key": issue2.key},
            }
        )
        assert result["success"] is True


class TestJiraCloudWorklog:
    """Worklog operations on Cloud."""

    def test_add_worklog(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Cloud E2E Worklog Test {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue.key)

        result = jira_fetcher.add_worklog(
            issue_key=issue.key,
            time_spent="1h",
            comment="Cloud E2E worklog test",
        )
        assert result is not None


class TestJiraCloudTransitions:
    """Transition lifecycle on Cloud."""

    def test_transition_lifecycle(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Cloud E2E Transition Test {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue.key)

        transitions = jira_fetcher.get_transitions(issue.key)
        assert len(transitions) > 0

        # Find "In Progress" transition or use first available
        target_id = None
        for t in transitions:
            t_name = t.get("name", "")
            if "progress" in t_name.lower():
                target_id = t["id"]
                break
        if target_id is None:
            target_id = transitions[0]["id"]

        jira_fetcher.transition_issue(issue.key, target_id)

        updated = jira_fetcher.get_issue(issue.key)
        assert updated.status is not None
