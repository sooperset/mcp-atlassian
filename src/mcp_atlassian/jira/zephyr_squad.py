"""Zephyr Squad (Jira plugin) operations mixin."""

import logging
from typing import Any

from .client import JiraClient

logger = logging.getLogger(__name__)


class ZephyrSquadMixin(JiraClient):
    """Mixin for Zephyr Squad (Jira plugin) operations.

    Zephyr Squad is a test management plugin for Jira that uses the ZAPI endpoints.
    These endpoints are available at /rest/zapi/latest/ on your Jira instance.
    """

    def get_zephyr_cycles(
        self,
        project_id: str,
        version_id: str | None = None,
    ) -> dict[str, Any]:
        """Get test cycles for a project.

        Args:
            project_id: Numeric project ID (not project key)
            version_id: Optional version ID to filter cycles

        Returns:
            Dictionary of cycles
        """
        params: dict[str, Any] = {"projectId": project_id}
        if version_id:
            params["versionId"] = version_id

        return self._session.get("rest/zapi/latest/cycle", params=params).json()

    def create_zephyr_cycle(
        self,
        project_id: str,
        version_id: str,
        name: str,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Create a new test cycle.

        Args:
            project_id: Numeric project ID
            version_id: Version ID
            name: Cycle name
            description: Optional description
            start_date: Optional start date (format: dd/MMM/yy)
            end_date: Optional end date (format: dd/MMM/yy)

        Returns:
            Created cycle data
        """
        payload: dict[str, Any] = {
            "projectId": project_id,
            "versionId": version_id,
            "name": name,
        }
        if description:
            payload["description"] = description
        if start_date:
            payload["startDate"] = start_date
        if end_date:
            payload["endDate"] = end_date

        return self._session.post("rest/zapi/latest/cycle", json=payload).json()

    def get_zephyr_executions(
        self,
        cycle_id: str | None = None,
        issue_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get test executions.

        Args:
            cycle_id: Optional cycle ID to filter by
            issue_id: Optional issue ID to filter by
            offset: Pagination offset
            limit: Number of results

        Returns:
            Execution data
        """
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if cycle_id:
            params["cycleId"] = cycle_id
        if issue_id:
            params["issueId"] = issue_id

        return self._session.get("rest/zapi/latest/execution", params=params).json()

    def create_zephyr_execution(
        self,
        issue_id: str,
        cycle_id: str,
        project_id: str,
        version_id: str,
        assignee_type: str = "assignee",
        assignee: str | None = None,
    ) -> dict[str, Any]:
        """Create a test execution.

        Args:
            issue_id: Issue ID (test case)
            cycle_id: Cycle ID
            project_id: Project ID
            version_id: Version ID
            assignee_type: Type of assignee ('assignee', 'currentUser', etc.)
            assignee: Optional assignee username

        Returns:
            Created execution data
        """
        payload: dict[str, Any] = {
            "issueId": issue_id,
            "cycleId": cycle_id,
            "projectId": project_id,
            "versionId": version_id,
            "assigneeType": assignee_type,
        }
        if assignee:
            payload["assignee"] = assignee

        return self._session.post("rest/zapi/latest/execution", json=payload).json()

    def execute_zephyr_test(
        self,
        execution_id: str,
        status: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Execute a test (set its status).

        Args:
            execution_id: Execution ID
            status: Status ID (e.g., '1' for Pass, '2' for Fail)
            comment: Optional comment

        Returns:
            Updated execution data
        """
        payload: dict[str, Any] = {"status": status}
        if comment:
            payload["comment"] = comment

        return self._session.put(
            f"rest/zapi/latest/execution/{execution_id}/execute", json=payload
        ).json()

    def get_zephyr_test_steps(self, issue_id: str) -> dict[str, Any]:
        """Get test steps for a test case.

        Args:
            issue_id: Issue ID of the test case

        Returns:
            List of test steps
        """
        return self._session.get(f"rest/zapi/latest/teststep/{issue_id}").json()

    def get_zephyr_execution_summary(
        self,
        cycle_id: str,
        version_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Get execution summary for a cycle.

        Args:
            cycle_id: Cycle ID
            version_id: Version ID
            project_id: Project ID

        Returns:
            Execution summary data
        """
        params = {
            "cycleId": cycle_id,
            "versionId": version_id,
            "projectId": project_id,
        }
        return self._session.get(
            "rest/zapi/latest/execution/executionSummary", params=params
        ).json()
