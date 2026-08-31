"""Jira DC-specific operation tests (single auth - basic)."""

from __future__ import annotations

import os
import uuid

import pytest
import requests
from requests.exceptions import HTTPError

from mcp_atlassian.jira import JiraFetcher

from .conftest import DCInstanceInfo, DCResourceTracker


def _delete_dc_comment(
    jira_fetcher: JiraFetcher, issue_key: str, comment_id: str
) -> None:
    """Best-effort cleanup for a comment created by the JSM e2e test."""
    try:
        jira_fetcher.jira.delete(f"rest/api/2/issue/{issue_key}/comment/{comment_id}")
    except requests.RequestException:
        pass


def _dc_jsm_project_key(
    dc_instance: DCInstanceInfo, issue_key: str | None = None
) -> str:
    """Return the explicitly configured JSM project or the E2E project."""
    configured = os.environ.get("DC_E2E_JSM_PROJECT_KEY", "").strip()
    if configured:
        return configured.upper()
    if issue_key and "-" in issue_key:
        return issue_key.split("-", 1)[0].strip().upper()
    return dc_instance.project_key.strip().upper()


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

    def test_search_assignable_users_by_project(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        """DC assignable-user search accepts username= with project scope."""
        users = jira_fetcher.search_assignable_users(
            query=dc_instance.admin_username,
            project_key=dc_instance.project_key,
            limit=5,
        )

        assert isinstance(users, list)

    def test_search_projects_by_key(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        """DC project picker returns the configured test project."""
        projects = jira_fetcher.search_projects(
            query=dc_instance.project_key,
            max_results=10,
        )

        assert any(
            project.get("key", "").upper() == dc_instance.project_key
            for project in projects
        )

    def test_move_issue_not_supported(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        with pytest.raises(NotImplementedError, match="Jira Cloud"):
            jira_fetcher.move_issue(
                dc_instance.test_issue_key,
                dc_instance.project_key,
            )


class TestJiraDCProjectAnalysis:
    """Project analysis through Jira Data Center offset pagination."""

    def test_project_analysis(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        hierarchy = jira_fetcher.get_project_epic_hierarchy(
            dc_instance.project_key,
            max_epics=10,
        )
        dependencies = jira_fetcher.get_cross_project_dependencies(
            dc_instance.project_key,
            max_issues=10,
        )

        assert hierarchy["project_key"] == dc_instance.project_key
        assert hierarchy["total_epics"] <= 10
        assert isinstance(hierarchy["groups"], list)
        assert dependencies["project_key"] == dc_instance.project_key
        assert dependencies["total_issues_scanned"] <= 10
        assert isinstance(dependencies["by_project"], dict)


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


class TestJiraDCVersionOperations:
    """Version creation and updates on DC."""

    def test_create_and_update_project_version(
        self,
        jira_fetcher: JiraFetcher,
        dc_instance: DCInstanceInfo,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        name = f"dc-e2e-version-{uid}"
        version: dict[str, object] | None = None

        try:
            version = jira_fetcher.create_project_version(
                project_key=dc_instance.project_key,
                name=name,
                description="Auto-created for DC version endpoint testing.",
            )

            assert version["name"] == name
            assert version.get("id")

            updated_name = f"{name}-updated"
            updated_version = jira_fetcher.update_project_version(
                version_id=str(version["id"]),
                name=updated_name,
            )

            assert updated_version["name"] == updated_name
            assert str(updated_version["id"]) == str(version["id"])
        finally:
            if version and version.get("id"):
                requests.post(
                    f"{dc_instance.jira_url}/rest/api/2/version/"
                    f"{version['id']}/removeAndSwap",
                    auth=(dc_instance.admin_username, dc_instance.admin_password),
                    json={},
                    timeout=30,
                ).raise_for_status()


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

        jira_fetcher.transition_issue(
            issue.key,
            target_id,
            comment=f"Data Center transition comment {uid}",
        )

        updated = jira_fetcher.get_issue(issue.key)
        assert updated.status is not None


class TestJiraDCJSMComments:
    """ServiceDesk visibility and internal-only comment behavior on DC."""

    def test_internal_only_comment_guard_matches_servicedesk_visibility(
        self,
        jsm_jira_fetcher: JiraFetcher,
        jsm_dc_instance: DCInstanceInfo,
        jsm_resource_tracker: DCResourceTracker,
    ) -> None:
        existing_issue_key = os.environ.get("DC_E2E_JSM_ISSUE_KEY", "").strip()
        if not existing_issue_key:
            pytest.skip(
                "DC JSM e2e requires DC_E2E_JSM_ISSUE_KEY (a pre-seeded "
                "ServiceDesk request); JSM projects reject plain issue creation"
            )

        project_key = _dc_jsm_project_key(jsm_dc_instance, existing_issue_key)
        project = jsm_jira_fetcher.jira.get(f"rest/api/2/project/{project_key}")
        if not isinstance(project, dict) or project.get("projectTypeKey") not in {
            "service_desk",
            "service-desk",
        }:
            pytest.skip(
                f"DC_E2E_JSM_PROJECT_KEY is not a Jira Service Management "
                f"project: {project_key}"
            )

        issue_key = existing_issue_key

        comment_ids: list[str] = []
        try:
            public_comment = jsm_jira_fetcher.add_comment(
                issue_key, "DC public ServiceDesk comment", public=True
            )
            internal_comment = jsm_jira_fetcher.add_comment(
                issue_key, "DC internal ServiceDesk comment", public=False
            )
            public_id = str(public_comment["id"])
            internal_id = str(internal_comment["id"])
            comment_ids.extend((public_id, internal_id))

            assert public_comment["public"] is True
            assert internal_comment["public"] is False
            assert (
                jsm_jira_fetcher._fetch_servicedesk_comment_is_public(
                    issue_key, public_id
                )
                is True
            )
            assert (
                jsm_jira_fetcher._fetch_servicedesk_comment_is_public(
                    issue_key, internal_id
                )
                is False
            )

            jsm_jira_fetcher.config.internal_only_projects = frozenset({project_key})

            # The add guard is the actual boundary: on a listed project a
            # customer-visible comment must be refused outright, and an omitted
            # 'public' must not quietly default to one.
            with pytest.raises(ValueError, match="internal-only"):
                jsm_jira_fetcher.add_comment(
                    issue_key, "must never reach the customer", public=True
                )
            with pytest.raises(ValueError, match="internal-only"):
                jsm_jira_fetcher.add_comment(issue_key, "must never reach the customer")

            # ...while an explicit internal comment still gets through — this is
            # exactly what the MCP boundary used to drop.
            guarded = jsm_jira_fetcher.add_comment(
                issue_key, "DC guarded internal comment", public=False
            )
            guarded_id = str(guarded["id"])
            comment_ids.append(guarded_id)
            assert guarded["public"] is False
            assert (
                jsm_jira_fetcher._fetch_servicedesk_comment_is_public(
                    issue_key, guarded_id
                )
                is False
            )

            with pytest.raises(ValueError, match="PUBLIC"):
                jsm_jira_fetcher.edit_comment(
                    issue_key, public_id, "must remain unchanged"
                )

            edited = jsm_jira_fetcher.edit_comment(
                issue_key, internal_id, "DC edited internal ServiceDesk comment"
            )
            assert edited["id"] == internal_id
            # The edit itself goes through the core Jira API, so assert the
            # comment is still internal afterwards: if that write ever dropped
            # the ServiceDesk visibility property, the guard would have let the
            # text through to the customer portal while the test still passed.
            assert (
                jsm_jira_fetcher._fetch_servicedesk_comment_is_public(
                    issue_key, internal_id
                )
                is False
            )
        finally:
            for comment_id in comment_ids:
                _delete_dc_comment(jsm_jira_fetcher, issue_key, comment_id)
