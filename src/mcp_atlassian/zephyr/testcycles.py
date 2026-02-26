"""Test cycle operations mixin for Zephyr Scale."""

import logging
from typing import Any

from .client import ZephyrClient

logger = logging.getLogger(__name__)


class TestCyclesMixin(ZephyrClient):
    """Mixin for Zephyr Scale test cycle operations."""

    def get_test_cycle(self, test_cycle_key: str) -> dict[str, Any]:
        """Get a test cycle by key.

        Args:
            test_cycle_key: Test cycle key (e.g., 'PROJ-C1')

        Returns:
            Test cycle data
        """
        return self.get(f"testcycles/{test_cycle_key}")

    def search_test_cycles(
        self,
        project_key: str,
        folder_id: int | None = None,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Search for test cycles in a project.

        Args:
            project_key: Project key
            folder_id: Optional folder ID to filter by
            max_results: Maximum number of results to return

        Returns:
            Search results with test cycles
        """
        params: dict[str, Any] = {
            "projectKey": project_key,
            "maxResults": max_results,
        }
        if folder_id:
            params["folderId"] = folder_id

        return self.get("testcycles", params=params)

    def create_test_cycle(
        self,
        project_key: str,
        name: str,
        description: str | None = None,
        planned_start_date: str | None = None,
        planned_end_date: str | None = None,
        status: str | None = None,
        folder_id: int | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new test cycle.

        Args:
            project_key: Project key
            name: Test cycle name
            description: Test cycle description
            planned_start_date: Start date (ISO 8601 format)
            planned_end_date: End date (ISO 8601 format)
            status: Status (e.g., 'Not Started', 'In Progress', 'Done')
            folder_id: Folder ID to place the test cycle in
            custom_fields: Custom field values

        Returns:
            Created test cycle data
        """
        payload: dict[str, Any] = {
            "projectKey": project_key,
            "name": name,
        }

        if description:
            payload["description"] = description
        if planned_start_date:
            payload["plannedStartDate"] = planned_start_date
        if planned_end_date:
            payload["plannedEndDate"] = planned_end_date
        if status:
            payload["statusName"] = status
        if folder_id:
            payload["folderId"] = folder_id
        if custom_fields:
            payload["customFields"] = custom_fields

        return self.post("testcycles", json=payload)

    def update_test_cycle(
        self,
        test_cycle_key: str,
        name: str | None = None,
        description: str | None = None,
        planned_start_date: str | None = None,
        planned_end_date: str | None = None,
        status: str | None = None,
        folder_id: int | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing test cycle.

        The Zephyr Scale v2 API clears any unspecified fields on PUT,
        so we GET the current test cycle first and merge changes into
        the full object before sending.

        Args:
            test_cycle_key: Test cycle key
            name: Test cycle name
            description: Test cycle description
            planned_start_date: Start date (ISO 8601 format)
            planned_end_date: End date (ISO 8601 format)
            status: Status name (will be resolved to object format)
            folder_id: Folder ID
            custom_fields: Custom field values

        Returns:
            Updated test cycle data
        """
        current = self.get_test_cycle(test_cycle_key)
        if not isinstance(current, dict):
            current = {}

        if name is not None:
            current["name"] = name
        if description is not None:
            current["description"] = description
        if planned_start_date is not None:
            current["plannedStartDate"] = planned_start_date
        if planned_end_date is not None:
            current["plannedEndDate"] = planned_end_date
        if status is not None:
            current["status"] = {"name": status}
        if folder_id is not None:
            current["folderId"] = folder_id
        if custom_fields is not None:
            current["customFields"] = custom_fields

        return self.put(f"testcycles/{test_cycle_key}", json=current)

    def delete_test_cycle(self, test_cycle_key: str) -> dict[str, Any]:
        """Delete a test cycle.

        Args:
            test_cycle_key: Test cycle key

        Returns:
            Empty response on success
        """
        return self.delete(f"testcycles/{test_cycle_key}")

    def link_test_cycle_to_issue(
        self, test_cycle_key: str, issue_key: str
    ) -> dict[str, Any]:
        """Link a test cycle to a Jira issue.

        Args:
            test_cycle_key: Test cycle key
            issue_key: Jira issue key

        Returns:
            Link response
        """
        payload = {"issueKey": issue_key}
        return self.post(f"testcycles/{test_cycle_key}/links/issues", json=payload)
