"""Agent issue-creation workflow: discover types, fields, create issue.

Regression for https://github.com/sooperset/mcp-atlassian/issues/460
"""

from __future__ import annotations

import uuid

import pytest

from mcp_atlassian.jira import JiraFetcher

from .conftest import CloudInstanceInfo, CloudResourceTracker

pytestmark = pytest.mark.cloud_e2e


class TestAgentIssueCreationWorkflow:
    """Acceptance test: agent can discover types, fields, and create an issue.

    Regression for https://github.com/sooperset/mcp-atlassian/issues/460
    Proves the full agent workflow: discover issue types -> discover required
    fields -> create issue with correct data. Without these tools, agents
    need 5-6 calls and often fail due to missing field information.
    """

    def test_discover_issue_types(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Agent can discover what issue types a project supports."""
        types = jira_fetcher.get_project_issue_types(cloud_instance.project_key)
        assert len(types) > 0, "No issue types returned"
        names = [t.get("name") for t in types]
        assert "Task" in names or "Bug" in names, f"Expected common types, got: {names}"

    def test_discover_create_fields(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
    ) -> None:
        """Agent can discover what fields are needed for an issue type."""
        types = jira_fetcher.get_project_issue_types(cloud_instance.project_key)
        task_type = next((t for t in types if t["name"] == "Task"), types[0])

        fields = jira_fetcher.get_create_fields(
            cloud_instance.project_key, task_type["id"]
        )
        assert len(fields) > 0, "No fields returned"
        field_ids = [f.get("fieldId") for f in fields]
        assert "summary" in field_ids, "summary field not in create fields"

    def test_full_agent_workflow_discover_and_create(
        self,
        jira_fetcher: JiraFetcher,
        cloud_instance: CloudInstanceInfo,
        resource_tracker: CloudResourceTracker,
    ) -> None:
        """Full workflow: discover types -> discover fields -> create issue."""
        uid = uuid.uuid4().hex[:8]

        # Step 1: Discover issue types
        types = jira_fetcher.get_project_issue_types(cloud_instance.project_key)
        assert len(types) > 0

        # Step 2: Pick Task
        task_type = next(t for t in types if t["name"] == "Task")

        # Step 3: Discover fields
        fields = jira_fetcher.get_create_fields(
            cloud_instance.project_key, task_type["id"]
        )
        required_fields = [f for f in fields if f.get("required")]
        # summary and issuetype should be required
        required_ids = [f["fieldId"] for f in required_fields]
        assert "summary" in required_ids or "issuetype" in required_ids

        # Step 4: Create issue using discovered metadata
        issue = jira_fetcher.create_issue(
            project_key=cloud_instance.project_key,
            summary=f"Agent workflow test {uid}",
            issue_type=task_type["name"],
        )
        resource_tracker.add_jira_issue(issue.key)
        assert issue.key.startswith(cloud_instance.project_key)
