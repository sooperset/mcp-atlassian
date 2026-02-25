"""Jira Cloud auth matrix tests -- read/write ops x 2 auth methods."""

from __future__ import annotations

import uuid

import pytest

from mcp_atlassian.jira import JiraFetcher
from mcp_atlassian.jira.config import JiraConfig

from .conftest import AuthVariant, CloudInstanceInfo, CloudResourceTracker

pytestmark = pytest.mark.cloud_e2e


@pytest.fixture(params=["basic", "byo_oauth"])
def jira_auth(
    request: pytest.FixtureRequest,
    auth_variants: list[AuthVariant],
) -> JiraConfig:
    """Parametrized fixture yielding JiraConfig per auth method."""
    name = request.param
    for variant in auth_variants:
        if variant.name == name:
            return variant.jira_config
    pytest.skip(f"Auth variant '{name}' not available")


@pytest.fixture
def authed_jira(jira_auth: JiraConfig) -> JiraFetcher:
    """Create a JiraFetcher from the parametrized auth config."""
    return JiraFetcher(config=jira_auth)


class TestJiraReadOperations:
    """Jira read operations tested across all auth methods."""

    def test_get_issue(
        self,
        authed_jira: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        issue = authed_jira.get_issue(cloud_instance.test_issue_key)
        assert issue is not None
        assert issue.key == cloud_instance.test_issue_key

    def test_search_issues(
        self,
        authed_jira: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        result = authed_jira.search_issues(
            jql=f"project={cloud_instance.project_key}",
            limit=5,
        )
        assert result.issues is not None
        assert len(result.issues) > 0

    def test_get_project_keys(
        self,
        authed_jira: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        keys = authed_jira.get_project_keys()
        assert isinstance(keys, list)
        assert cloud_instance.project_key in keys

    def test_get_transitions(
        self,
        authed_jira: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        transitions = authed_jira.get_transitions(cloud_instance.test_issue_key)
        assert isinstance(transitions, list)
        assert len(transitions) > 0

    def test_get_project_issue_types(
        self,
        authed_jira: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        meta = authed_jira.get_project_issue_types(cloud_instance.project_key)
        assert meta is not None


class TestJiraWriteOperations:
    """Jira write operations tested across all auth methods."""

    def test_create_and_delete_issue(
        self,
        authed_jira: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = authed_jira.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Cloud E2E Auth Matrix Test {uid}",
            issue_type="Task",
            description="Created by auth matrix test.",
        )
        resource_tracker.add_jira_issue(issue.key)
        assert issue.key.startswith(cloud_instance.project_key)

    def test_update_issue(
        self,
        authed_jira: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = authed_jira.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Cloud E2E Update Test {uid}",
            issue_type="Task",
            description="Will be updated.",
        )
        resource_tracker.add_jira_issue(issue.key)

        updated = authed_jira.update_issue(issue.key, {"summary": f"Updated {uid}"})
        assert updated is not None

    def test_add_comment(
        self,
        authed_jira: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        uid = uuid.uuid4().hex[:8]
        issue = authed_jira.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Cloud E2E Comment Test {uid}",
            issue_type="Task",
            description="For comment testing.",
        )
        resource_tracker.add_jira_issue(issue.key)

        comment = authed_jira.add_comment(
            issue_key=issue.key,
            comment=f"Test comment {uid}",
        )
        assert comment is not None
