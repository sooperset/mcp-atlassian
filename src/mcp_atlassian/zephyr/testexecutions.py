"""Test execution operations mixin for Zephyr Scale."""

import logging
from typing import Any

from .client import ZephyrClient

logger = logging.getLogger(__name__)


class TestExecutionsMixin(ZephyrClient):
    """Mixin for Zephyr Scale test execution operations."""

    def get_test_execution(self, test_execution_key: str) -> dict[str, Any]:
        """Get a test execution by key.

        Args:
            test_execution_key: Test execution key (e.g., 'PROJ-E1')

        Returns:
            Test execution data
        """
        return self.get(f"testexecutions/{test_execution_key}")

    def search_test_executions(
        self,
        project_key: str,
        test_cycle_key: str | None = None,
        test_case_key: str | None = None,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Search for test executions in a project.

        Args:
            project_key: Project key
            test_cycle_key: Optional test cycle key to filter by
            test_case_key: Optional test case key to filter by
            max_results: Maximum number of results to return

        Returns:
            Search results with test executions
        """
        params: dict[str, Any] = {
            "projectKey": project_key,
            "maxResults": max_results,
        }
        if test_cycle_key:
            params["testCycle"] = test_cycle_key
        if test_case_key:
            params["testCase"] = test_case_key

        return self.get("testexecutions", params=params)

    def create_test_execution(
        self,
        project_key: str,
        test_case_key: str,
        test_cycle_key: str | None = None,
        status: str | None = None,
        environment: str | None = None,
        assigned_to: str | None = None,
        executed_by: str | None = None,
        execution_time: int | None = None,
        comment: str | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new test execution.

        Args:
            project_key: Project key
            test_case_key: Test case key
            test_cycle_key: Optional test cycle key
            status: Execution status (e.g., 'Pass', 'Fail', 'Blocked', 'Not Executed')
            environment: Test environment
            assigned_to: Account ID of user assigned to execute
            executed_by: Account ID of user who executed
            execution_time: Execution time in milliseconds
            comment: Execution comment/notes
            custom_fields: Custom field values

        Returns:
            Created test execution data
        """
        payload: dict[str, Any] = {
            "projectKey": project_key,
            "testCaseKey": test_case_key,
        }

        if test_cycle_key:
            payload["testCycleKey"] = test_cycle_key
        if status:
            payload["statusName"] = status
        if environment:
            payload["environmentName"] = environment
        if assigned_to:
            payload["assignedToId"] = assigned_to
        if executed_by:
            payload["executedById"] = executed_by
        if execution_time is not None:
            payload["executionTime"] = execution_time
        if comment:
            payload["comment"] = comment
        if custom_fields:
            payload["customFields"] = custom_fields

        return self.post("testexecutions", json=payload)

    def update_test_execution(
        self,
        test_execution_key: str,
        status: str | None = None,
        environment: str | None = None,
        assigned_to: str | None = None,
        executed_by: str | None = None,
        execution_time: int | None = None,
        comment: str | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing test execution.

        Args:
            test_execution_key: Test execution key
            status: Execution status
            environment: Test environment
            assigned_to: Account ID of user assigned to execute
            executed_by: Account ID of user who executed
            execution_time: Execution time in milliseconds
            comment: Execution comment/notes
            custom_fields: Custom field values

        Returns:
            Updated test execution data
        """
        payload: dict[str, Any] = {}

        if status:
            payload["statusName"] = status
        if environment:
            payload["environmentName"] = environment
        if assigned_to:
            payload["assignedToId"] = assigned_to
        if executed_by:
            payload["executedById"] = executed_by
        if execution_time is not None:
            payload["executionTime"] = execution_time
        if comment:
            payload["comment"] = comment
        if custom_fields:
            payload["customFields"] = custom_fields

        return self.put(f"testexecutions/{test_execution_key}", json=payload)

    def delete_test_execution(self, test_execution_key: str) -> dict[str, Any]:
        """Delete a test execution.

        Args:
            test_execution_key: Test execution key

        Returns:
            Empty response on success
        """
        return self.delete(f"testexecutions/{test_execution_key}")

    def get_test_execution_results(
        self, project_key: str, test_cycle_key: str | None = None
    ) -> dict[str, Any]:
        """Get test execution results summary.

        Args:
            project_key: Project key
            test_cycle_key: Optional test cycle key to filter by

        Returns:
            Test execution results summary
        """
        params: dict[str, Any] = {"projectKey": project_key}
        if test_cycle_key:
            params["testCycle"] = test_cycle_key

        return self.get("testexecutions/results", params=params)
