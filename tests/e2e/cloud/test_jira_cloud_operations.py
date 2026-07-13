"""Jira Cloud-specific operation tests (single auth - basic)."""

from __future__ import annotations

import os
import uuid

import pytest
import requests
from requests.exceptions import HTTPError

from mcp_atlassian.jira import JiraFetcher

from .conftest import CloudInstanceInfo, CloudResourceTracker


def _delete_cloud_comment(
    jira_fetcher: JiraFetcher, issue_key: str, comment_id: str
) -> None:
    """Best-effort cleanup for a comment created by the JSM e2e test."""
    try:
        jira_fetcher.jira.delete(f"rest/api/3/issue/{issue_key}/comment/{comment_id}")
    except requests.RequestException:
        pass


def _cloud_jsm_project_key(
    cloud_instance: CloudInstanceInfo, issue_key: str | None = None
) -> str:
    """Return the explicitly configured JSM project or the E2E project."""
    configured = os.environ.get("CLOUD_E2E_JSM_PROJECT_KEY", "").strip()
    if configured:
        return configured.upper()
    if issue_key and "-" in issue_key:
        return issue_key.split("-", 1)[0].strip().upper()
    return cloud_instance.project_key.strip().upper()


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

    def test_search_assignable_users_by_project(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Cloud assignable-user search accepts query= with project scope."""
        users = jira_fetcher.search_assignable_users(
            query=cloud_instance.username.split("@", maxsplit=1)[0],
            project_key=cloud_instance.project_key,
            limit=5,
        )

        assert isinstance(users, list)

    def test_search_projects_by_key(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Cloud project search returns the configured test project."""
        projects = jira_fetcher.search_projects(
            query=cloud_instance.project_key,
            max_results=10,
        )

        assert any(
            project.get("key", "").upper() == cloud_instance.project_key
            for project in projects
        )


class TestJiraCloudProjectAnalysis:
    """Project analysis through Jira Cloud search pagination."""

    def test_project_analysis(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        hierarchy = jira_fetcher.get_project_epic_hierarchy(
            cloud_instance.project_key,
            max_epics=10,
        )
        dependencies = jira_fetcher.get_cross_project_dependencies(
            cloud_instance.project_key,
            max_issues=10,
        )

        assert hierarchy["project_key"] == cloud_instance.project_key
        assert hierarchy["total_epics"] <= 10
        assert isinstance(hierarchy["groups"], list)
        assert dependencies["project_key"] == cloud_instance.project_key
        assert dependencies["total_issues_scanned"] <= 10
        assert isinstance(dependencies["by_project"], dict)


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


class TestJiraCloudMoveOperations:
    """Issue move operations on Cloud."""

    def test_move_issue_same_project(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Cloud E2E Move Test {uid}",
            issue_type="Task",
            description="Issue for Cloud move testing.",
        )
        resource_tracker.add_jira_issue(issue.key)

        moved = jira_fetcher.move_issue(issue.key, cloud_instance.project_key)
        if moved.key != issue.key:
            resource_tracker.add_jira_issue(moved.key)

        assert moved.key.startswith(cloud_instance.project_key)


class TestJiraCloudVersionOperations:
    """Version creation and updates on Cloud."""

    def test_create_and_update_project_version(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        name = f"cloud-e2e-version-{uid}"
        version: dict[str, object] | None = None

        try:
            version = jira_fetcher.create_project_version(
                project_key=cloud_instance.project_key,
                name=name,
                description="Auto-created for Cloud version endpoint testing.",
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
                requests.delete(
                    f"{cloud_instance.jira_url}/rest/api/3/version/{version['id']}",
                    auth=(cloud_instance.username, cloud_instance.api_token),
                    timeout=30,
                ).raise_for_status()


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

        jira_fetcher.transition_issue(
            issue.key,
            target_id,
            comment=f"Cloud transition comment {uid}",
        )

        updated = jira_fetcher.get_issue(issue.key)
        assert updated.status is not None


class TestJiraCloudJSMComments:
    """ServiceDesk visibility and internal-only comment behavior on Cloud."""

    def test_internal_only_comment_guard_matches_servicedesk_visibility(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        existing_issue_key = os.environ.get("CLOUD_E2E_JSM_ISSUE_KEY", "").strip()
        project_key = _cloud_jsm_project_key(cloud_instance, existing_issue_key)
        project = jira_fetcher.jira.get(f"rest/api/3/project/{project_key}")
        if not isinstance(project, dict) or project.get("projectTypeKey") not in {
            "service_desk",
            "service-desk",
        }:
            pytest.skip(
                f"CLOUD_E2E_JSM_PROJECT_KEY is not a Jira Service Management "
                f"project: {project_key}"
            )

        issue_key = existing_issue_key
        if not issue_key:
            issue = jira_fetcher.create_issue(
                project_key=project_key,
                summary=f"Cloud E2E JSM comment test {uuid.uuid4().hex[:8]}",
                issue_type=os.environ.get("CLOUD_E2E_JSM_ISSUE_TYPE", "Task"),
            )
            issue_key = issue.key
            resource_tracker.add_jira_issue(issue_key)

        comment_ids: list[str] = []
        try:
            public_comment = jira_fetcher.add_comment(
                issue_key, "Cloud public ServiceDesk comment", public=True
            )
            internal_comment = jira_fetcher.add_comment(
                issue_key, "Cloud internal ServiceDesk comment", public=False
            )
            public_id = str(public_comment["id"])
            internal_id = str(internal_comment["id"])
            comment_ids.extend((public_id, internal_id))

            assert public_comment["public"] is True
            assert internal_comment["public"] is False
            assert (
                jira_fetcher._fetch_servicedesk_comment_is_public(issue_key, public_id)
                is True
            )
            assert (
                jira_fetcher._fetch_servicedesk_comment_is_public(
                    issue_key, internal_id
                )
                is False
            )

            jira_fetcher.config.internal_only_projects = frozenset({project_key})

            # The add guard is the actual boundary: on a listed project a
            # customer-visible comment must be refused outright, and an omitted
            # 'public' must not quietly default to one.
            with pytest.raises(ValueError, match="internal-only"):
                jira_fetcher.add_comment(
                    issue_key, "must never reach the customer", public=True
                )
            with pytest.raises(ValueError, match="internal-only"):
                jira_fetcher.add_comment(issue_key, "must never reach the customer")

            # ...while an explicit internal comment still gets through — this is
            # exactly what the MCP boundary used to drop.
            guarded = jira_fetcher.add_comment(
                issue_key, "Cloud guarded internal comment", public=False
            )
            guarded_id = str(guarded["id"])
            comment_ids.append(guarded_id)
            assert guarded["public"] is False
            assert (
                jira_fetcher._fetch_servicedesk_comment_is_public(issue_key, guarded_id)
                is False
            )

            with pytest.raises(ValueError, match="PUBLIC"):
                jira_fetcher.edit_comment(issue_key, public_id, "must remain unchanged")

            edited = jira_fetcher.edit_comment(
                issue_key, internal_id, "Cloud edited internal ServiceDesk comment"
            )
            assert edited["id"] == internal_id
            # The edit itself goes through the core Jira API, so assert the
            # comment is still internal afterwards: if that write ever dropped
            # the ServiceDesk visibility property, the guard would have let the
            # text through to the customer portal while the test still passed.
            assert (
                jira_fetcher._fetch_servicedesk_comment_is_public(
                    issue_key, internal_id
                )
                is False
            )
        finally:
            for comment_id in comment_ids:
                _delete_cloud_comment(jira_fetcher, issue_key, comment_id)
