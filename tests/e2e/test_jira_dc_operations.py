"""Jira DC-specific operation tests (single auth - basic)."""

from __future__ import annotations

import uuid

import pytest
from requests.exceptions import HTTPError

from mcp_atlassian.jira import JiraFetcher

from .conftest import DCInstanceInfo, DCResourceTracker

pytestmark = pytest.mark.dc_e2e


class TestJiraDCBehavior:
    """Tests for DC-specific Jira behavior."""

    def test_is_not_cloud(self, jira_fetcher: JiraFetcher) -> None:
        assert jira_fetcher.config.is_cloud is False

    def test_assignee_uses_name_field(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        """DC uses 'name' for assignee, not 'accountId' (Cloud)."""
        issue = jira_fetcher.get_issue(dc_instance.test_issue_key)
        simplified = issue.to_simplified_dict()
        if "assignee" in simplified and simplified["assignee"]:
            assignee = simplified["assignee"]
            if isinstance(assignee, dict):
                assert "name" in assignee or "displayName" in assignee


class TestJiraDCEpicOperations:
    """Epic creation with DC custom fields."""

    def test_create_epic(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        try:
            epic = jira_fetcher.create_issue(
                project_key=dc_instance.project_key,
                summary=f"E2E DC Epic {uid}",
                issue_type="Epic",
                description="Epic for DC testing.",
            )
        except HTTPError as e:
            if "issue type" in str(e).lower():
                pytest.skip(
                    f"Epic issue type not available in project "
                    f"{dc_instance.project_key}"
                )
            raise
        resource_tracker.add_jira_issue(epic.key)
        assert epic.key.startswith(dc_instance.project_key)


class TestJiraDCSubtask:
    """Subtask creation under parent."""

    def test_create_subtask(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        parent = jira_fetcher.create_issue(
            project_key=dc_instance.project_key,
            summary=f"E2E Parent {uid}",
            issue_type="Task",
            description="Parent for subtask test.",
        )
        resource_tracker.add_jira_issue(parent.key)

        subtask = jira_fetcher.create_issue(
            project_key=dc_instance.project_key,
            summary=f"E2E Subtask {uid}",
            issue_type="Sub-task",
            description="Subtask for DC testing.",
            parent=parent.key,
        )
        resource_tracker.add_jira_issue(subtask.key)
        assert subtask.key.startswith(dc_instance.project_key)


class TestJiraDCIssueLinks:
    """Issue link creation."""

    def test_create_issue_link(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue1 = jira_fetcher.create_issue(
            project_key=dc_instance.project_key,
            summary=f"E2E Link Source {uid}",
            issue_type="Task",
        )
        issue2 = jira_fetcher.create_issue(
            project_key=dc_instance.project_key,
            summary=f"E2E Link Target {uid}",
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


class TestJiraDCWorklog:
    """Worklog operations."""

    def test_add_worklog(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=dc_instance.project_key,
            summary=f"E2E Worklog Test {uid}",
            issue_type="Task",
        )
        resource_tracker.add_jira_issue(issue.key)

        result = jira_fetcher.add_worklog(
            issue_key=issue.key,
            time_spent="1h",
            comment="E2E worklog test",
        )
        assert result is not None


class TestJiraDCTransitions:
    """Transition lifecycle."""

    def test_transition_lifecycle(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
        resource_tracker: DCResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=dc_instance.project_key,
            summary=f"E2E Transition Test {uid}",
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
