"""Test case operations mixin for Zephyr Scale."""

import logging
from typing import Any

from .client import ZephyrClient

logger = logging.getLogger(__name__)


class TestCasesMixin(ZephyrClient):
    """Mixin for Zephyr Scale test case operations."""

    def get_test_case(self, test_case_key: str) -> dict[str, Any]:
        """Get a test case by key.

        Args:
            test_case_key: Test case key (e.g., 'PROJ-T1')

        Returns:
            Test case data
        """
        return self.get(f"testcases/{test_case_key}")

    def search_test_cases(
        self,
        project_key: str,
        folder_id: int | None = None,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Search for test cases in a project.

        Args:
            project_key: Project key
            folder_id: Optional folder ID to filter by
            max_results: Maximum number of results to return

        Returns:
            Search results with test cases
        """
        params: dict[str, Any] = {
            "projectKey": project_key,
            "maxResults": max_results,
        }
        if folder_id:
            params["folderId"] = folder_id

        return self.get("testcases", params=params)

    def create_test_case(
        self,
        project_key: str,
        name: str,
        objective: str | None = None,
        precondition: str | None = None,
        priority: str | None = None,
        status: str | None = None,
        folder_id: int | None = None,
        labels: list[str] | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new test case.

        Args:
            project_key: Project key
            name: Test case name
            objective: Test objective/description
            precondition: Preconditions for the test
            priority: Priority (e.g., 'High', 'Medium', 'Low')
            status: Status (e.g., 'Draft', 'Approved')
            folder_id: Folder ID to place the test case in
            labels: List of labels
            custom_fields: Custom field values

        Returns:
            Created test case data
        """
        payload: dict[str, Any] = {
            "projectKey": project_key,
            "name": name,
        }

        if objective:
            payload["objective"] = objective
        if precondition:
            payload["precondition"] = precondition
        if priority:
            payload["priorityName"] = priority
        if status:
            payload["statusName"] = status
        if folder_id:
            payload["folderId"] = folder_id
        if labels:
            payload["labels"] = labels
        if custom_fields:
            payload["customFields"] = custom_fields

        return self.post("testcases", json=payload)

    def update_test_case(
        self,
        test_case_key: str,
        name: str | None = None,
        objective: str | None = None,
        precondition: str | None = None,
        priority: str | None = None,
        status: str | None = None,
        folder_id: int | None = None,
        labels: list[str] | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing test case.

        The Zephyr Scale v2 API clears any unspecified fields on PUT,
        so we GET the current test case first and merge changes into
        the full object before sending.

        Note: PUT expects priority and status as objects
        ({"id": N}) rather than name strings used in POST.

        Args:
            test_case_key: Test case key
            name: Test case name
            objective: Test objective/description
            precondition: Preconditions for the test
            priority: Priority name (will be resolved to object format)
            status: Status name (will be resolved to object format)
            folder_id: Folder ID
            labels: List of labels
            custom_fields: Custom field values

        Returns:
            Updated test case data
        """
        current = self.get_test_case(test_case_key)
        if not isinstance(current, dict):
            current = {}

        if name is not None:
            current["name"] = name
        if objective is not None:
            current["objective"] = objective
        if precondition is not None:
            current["precondition"] = precondition
        if priority is not None:
            current["priority"] = {"name": priority}
        if status is not None:
            current["status"] = {"name": status}
        if folder_id is not None:
            current["folderId"] = folder_id
        if labels is not None:
            current["labels"] = labels
        if custom_fields is not None:
            current["customFields"] = custom_fields

        return self.put(f"testcases/{test_case_key}", json=current)

    def delete_test_case(self, test_case_key: str) -> dict[str, Any]:
        """Delete a test case.

        Args:
            test_case_key: Test case key

        Returns:
            Empty response on success
        """
        return self.delete(f"testcases/{test_case_key}")

    def link_test_case_to_issue(
        self, test_case_key: str, issue_key: str
    ) -> dict[str, Any]:
        """Link a test case to a Jira issue.

        Args:
            test_case_key: Test case key
            issue_key: Jira issue key

        Returns:
            Link response
        """
        payload = {"issueKey": issue_key}
        return self.post(f"testcases/{test_case_key}/links/issues", json=payload)

    def get_test_case_links(self, test_case_key: str) -> dict[str, Any]:
        """Get all Jira issue links for a test case.

        Args:
            test_case_key: Test case key

        Returns:
            List of linked issues
        """
        return self.get(f"testcases/{test_case_key}/links/issues")
